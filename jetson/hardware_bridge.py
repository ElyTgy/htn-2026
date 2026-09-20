#!/usr/bin/env python3
"""Read the Arduino sound bridge and send directional pulses to a TITAN Core.

This process is deliberately separate from the caption/vision server. Losing a sound sensor or
haptic serial link must not take down captions. Run ``--help`` for calibration and hardware tests.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CALIBRATION = ROOT / "jetson" / "sound_calibration.json"
ARDUINO_VIDS = {0x2341, 0x2A03}


@dataclass(frozen=True)
class SensorSample:
    sequence: int
    device_ms: int
    left_raw: int
    right_raw: int


def parse_sample(line: str) -> Optional[SensorSample]:
    """Parse one versioned Arduino line; comments and malformed lines are ignored."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    fields = line.split(",")
    if len(fields) != 5 or fields[0] != "S1":
        return None
    try:
        sequence, device_ms, left_raw, right_raw = map(int, fields[1:])
    except ValueError:
        return None
    if sequence < 0 or device_ms < 0 or not (0 <= left_raw <= 1023) or not (0 <= right_raw <= 1023):
        return None
    return SensorSample(sequence, device_ms, left_raw, right_raw)


def percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot take a percentile of no samples")
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return float(ordered[index])


@dataclass(frozen=True)
class Calibration:
    protocol: str
    left_baseline: float
    left_reference: float
    right_baseline: float
    right_reference: float

    @classmethod
    def from_recordings(
        cls, quiet: list[SensorSample], centered_sound: list[SensorSample]
    ) -> "Calibration":
        if len(quiet) < 20 or len(centered_sound) < 20:
            raise ValueError("not enough valid samples; check the Arduino serial stream")
        left_baseline = statistics.median(s.left_raw for s in quiet)
        right_baseline = statistics.median(s.right_raw for s in quiet)
        left_reference = percentile((s.left_raw for s in centered_sound), 0.90)
        right_reference = percentile((s.right_raw for s in centered_sound), 0.90)
        if left_reference - left_baseline < 5:
            raise ValueError("the SEN-12642 barely changed; check ENVELOPE -> A0 and repeat louder")
        if right_reference - right_baseline < 5:
            raise ValueError("the KY-038 barely changed; check AO -> A1, its trim pot, and repeat louder")
        return cls(
            protocol="S1",
            left_baseline=float(left_baseline),
            left_reference=float(left_reference),
            right_baseline=float(right_baseline),
            right_reference=float(right_reference),
        )

    def normalise(self, sample: SensorSample) -> tuple[float, float]:
        left_span = max(self.left_reference - self.left_baseline, 1.0)
        right_span = max(self.right_reference - self.right_baseline, 1.0)
        left = max(0.0, (sample.left_raw - self.left_baseline) / left_span)
        right = max(0.0, (sample.right_raw - self.right_baseline) / right_span)
        return left, right

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        data = json.loads(path.read_text())
        calibration = cls(**data)
        if calibration.protocol != "S1":
            raise ValueError(f"unsupported calibration protocol {calibration.protocol!r}")
        return calibration

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")


@dataclass(frozen=True)
class HapticEvent:
    direction: str
    strength: float
    activity: float
    balance: float


class DirectionDetector:
    """Smooth two independently calibrated levels and emit rate-limited directions."""

    def __init__(
        self,
        minimum_activity: float = 0.18,
        direction_deadband: float = 0.22,
        smoothing: float = 0.30,
        consecutive: int = 3,
        cooldown_seconds: float = 0.35,
    ):
        self.minimum_activity = minimum_activity
        self.direction_deadband = direction_deadband
        self.smoothing = smoothing
        self.consecutive = consecutive
        self.cooldown_seconds = cooldown_seconds
        self.left = 0.0
        self.right = 0.0
        self.candidate = None
        self.candidate_count = 0
        self.last_event_at = -math.inf

    def update(self, left: float, right: float, now: float) -> Optional[HapticEvent]:
        a = self.smoothing
        self.left = a * left + (1.0 - a) * self.left
        self.right = a * right + (1.0 - a) * self.right
        activity = max(self.left, self.right)
        if activity < self.minimum_activity:
            self.candidate = None
            self.candidate_count = 0
            return None

        balance = (self.right - self.left) / max(self.left + self.right, 1e-6)
        if balance > self.direction_deadband:
            direction = "right"
        elif balance < -self.direction_deadband:
            direction = "left"
        else:
            direction = "center"

        if direction == self.candidate:
            self.candidate_count += 1
        else:
            self.candidate = direction
            self.candidate_count = 1
        if self.candidate_count < self.consecutive or now - self.last_event_at < self.cooldown_seconds:
            return None

        self.last_event_at = now
        strength = min(0.75, max(0.20, 0.18 + activity * 0.32))
        return HapticEvent(direction, strength, activity, balance)


TITAN_CHANNEL = {"left": 1, "right": 2, "center": 3}


def titan_pulse_command(direction: str, strength: float, duration_ms: int = 55) -> bytes:
    if direction not in TITAN_CHANNEL:
        raise ValueError(f"unknown haptic direction {direction!r}")
    strength = min(1.0, max(0.0, strength))
    duration_ms = min(500, max(1, int(duration_ms)))
    return f"CHNL {TITAN_CHANNEL[direction]}; Pulse {strength:.2f} {duration_ms};\r\n".encode("ascii")


def serial_ports():
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise SystemExit("pyserial is missing; run scripts/jetson_install.sh") from exc
    return list(list_ports.comports())


def port_description(port) -> str:
    vid_pid = ""
    if port.vid is not None and port.pid is not None:
        vid_pid = f" {port.vid:04x}:{port.pid:04x}"
    serial_number = f" serial={port.serial_number}" if port.serial_number else ""
    return f"{port.device}{vid_pid} {port.description or ''}{serial_number}".strip()


def resolve_port(requested: str, role: str, excluded: set[str] | None = None) -> str:
    if requested != "auto":
        return requested
    excluded = excluded or set()
    excluded_real = {os.path.realpath(path) for path in excluded}
    ports = [
        p for p in serial_ports()
        if p.device not in excluded and os.path.realpath(p.device) not in excluded_real
    ]
    if role == "sensor":
        preferred = [p for p in ports if p.vid in ARDUINO_VIDS or "arduino" in (p.description or "").lower()]
    else:
        keywords = ("titan", "cp210", "silicon labs", "ch340", "ftdi")
        preferred = [p for p in ports if any(k in ((p.description or "") + " " + (p.manufacturer or "")).lower()
                                                 for k in keywords)]
    choices = preferred or ports
    if len(choices) != 1:
        listed = "\n  ".join(port_description(p) for p in ports) or "(none)"
        raise SystemExit(
            f"could not uniquely auto-detect the {role} serial port. Available ports:\n  {listed}\n"
            f"Set {'ARDUINO_PORT' if role == 'sensor' else 'TITAN_PORT'} to a /dev/serial/by-id/... path."
        )
    return choices[0].device


def open_serial(path: str, settle_seconds: float):
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is missing; run scripts/jetson_install.sh") from exc
    try:
        connection = serial.Serial(path, 115200, timeout=0.25, write_timeout=1.0)
    except serial.SerialException as exc:
        raise SystemExit(f"could not open {path}: {exc}. Check the dialout group and cable.") from exc
    time.sleep(settle_seconds)
    connection.reset_input_buffer()
    return connection


def read_sample(connection, deadline: float) -> Optional[SensorSample]:
    while time.monotonic() < deadline:
        raw = connection.readline()
        if not raw:
            continue
        sample = parse_sample(raw.decode("ascii", errors="replace"))
        if sample is not None:
            return sample
    return None


def record(connection, seconds: float) -> list[SensorSample]:
    deadline = time.monotonic() + seconds
    result = []
    while time.monotonic() < deadline:
        sample = read_sample(connection, min(deadline, time.monotonic() + 0.5))
        if sample is not None:
            result.append(sample)
    return result


def run_calibration(connection, path: Path, silence_seconds: float, reference_seconds: float) -> None:
    input(f"Keep the room quiet and both sensors still. Press Enter for {silence_seconds:g} s of silence...")
    quiet = record(connection, silence_seconds)
    input(
        "Place a phone/speaker directly in front, equally far from both sensors. Start a steady "
        f"sound, then press Enter for {reference_seconds:g} s..."
    )
    centered = record(connection, reference_seconds)
    calibration = Calibration.from_recordings(quiet, centered)
    calibration.save(path)
    print(f"saved calibration to {path}")
    print(json.dumps(asdict(calibration), indent=2))


def test_titan(connection) -> None:
    print("Pulsing L, R, then M at low strength...")
    for direction in ("left", "right", "center"):
        command = titan_pulse_command(direction, 0.25, 60)
        print(f"  {direction}: {command.decode().strip()}")
        connection.write(command)
        connection.flush()
        time.sleep(0.8)


def run_bridge(sensor, titan, calibration: Calibration, monitor: bool, dry_run: bool) -> None:
    detector = DirectionDetector()
    last_log = 0.0
    last_sequence = None
    while True:
        sample = read_sample(sensor, time.monotonic() + 1.0)
        if sample is None:
            print("no valid Arduino samples for 1 s; check firmware/cable", file=sys.stderr)
            continue
        if last_sequence is not None and sample.sequence > last_sequence + 1:
            print(f"warning: lost {sample.sequence - last_sequence - 1} sensor samples", file=sys.stderr)
        last_sequence = sample.sequence
        left, right = calibration.normalise(sample)
        now = time.monotonic()
        event = detector.update(left, right, now)
        if monitor or now - last_log >= 2.0:
            print(
                f"raw L={sample.left_raw:4d} R={sample.right_raw:4d}  "
                f"normalised L={left:5.2f} R={right:5.2f}",
                flush=True,
            )
            last_log = now
        if event is not None:
            command = titan_pulse_command(event.direction, event.strength)
            print(
                f"haptic {event.direction:6s} strength={event.strength:.2f} "
                f"activity={event.activity:.2f} balance={event.balance:+.2f}",
                flush=True,
            )
            if not dry_run:
                titan.write(command)
                titan.flush()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sensor-port", default=os.getenv("ARDUINO_PORT", "auto"))
    p.add_argument("--titan-port", default=os.getenv("TITAN_PORT", "auto"))
    p.add_argument(
        "--calibration",
        type=Path,
        default=Path(os.getenv("SOUND_CALIBRATION", str(DEFAULT_CALIBRATION))),
    )
    p.add_argument("--calibrate", action="store_true", help="record silence and centered-sound calibration")
    p.add_argument("--silence-seconds", type=float, default=3.0)
    p.add_argument("--reference-seconds", type=float, default=6.0)
    p.add_argument("--monitor", action="store_true", help="print every normalised sensor sample")
    p.add_argument("--dry-run", action="store_true", help="show decisions without opening or driving TITAN")
    p.add_argument("--test-titan", action="store_true", help="pulse TITAN channels L, R, M and exit")
    p.add_argument("--list-ports", action="store_true", help="list serial devices and exit")
    return p


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    args = parser().parse_args()

    if args.list_ports:
        ports = serial_ports()
        print("\n".join(port_description(p) for p in ports) if ports else "no serial ports found")
        return

    if args.test_titan:
        titan_path = resolve_port(args.titan_port, "titan")
        with open_serial(titan_path, 2.0) as titan:
            print(f"TITAN: {titan_path}")
            test_titan(titan)
        return

    sensor_path = resolve_port(args.sensor_port, "sensor")
    with open_serial(sensor_path, 2.2) as sensor:
        print(f"Arduino: {sensor_path}")
        if args.calibrate:
            run_calibration(sensor, args.calibration, args.silence_seconds, args.reference_seconds)
            return
        try:
            calibration = Calibration.load(args.calibration)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SystemExit(
                f"no usable calibration at {args.calibration}: {exc}\n"
                "Run this command once with --calibrate before enabling haptics."
            ) from exc

        if args.dry_run:
            run_bridge(sensor, None, calibration, args.monitor, dry_run=True)
        else:
            titan_path = resolve_port(args.titan_port, "titan", {sensor_path})
            with open_serial(titan_path, 2.0) as titan:
                print(f"TITAN: {titan_path}")
                run_bridge(sensor, titan, calibration, args.monitor, dry_run=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopping")
