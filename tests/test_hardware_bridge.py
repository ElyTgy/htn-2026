"""Run with: python3 tests/test_hardware_bridge.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jetson"))

from hardware_bridge import (  # noqa: E402
    Calibration,
    DirectionDetector,
    SensorSample,
    parse_sample,
    titan_pulse_command,
)


def sample(seq, left, right):
    return SensorSample(seq, seq * 25, left, right)


def test_parse_versioned_sample_and_ignore_noise():
    assert parse_sample("S1,7,175,222,18\n") == sample(7, 222, 18)
    assert parse_sample("# boot") is None
    assert parse_sample("S2,7,175,222,18") is None
    assert parse_sample("S1,7,175,2000,18") is None


def test_calibration_makes_different_sensor_scales_comparable():
    quiet = [sample(i, 100 + i % 2, 10 + i % 2) for i in range(40)]
    centered = [sample(i, 295 + i % 10, 105 + i % 5) for i in range(80)]
    calibration = Calibration.from_recordings(quiet, centered)
    left, right = calibration.normalise(sample(100, 300, 105))
    assert 0.95 <= left <= 1.05
    assert 0.95 <= right <= 1.05


def test_direction_detector_requires_stable_signal_and_rate_limits():
    detector = DirectionDetector(smoothing=1.0, consecutive=2, cooldown_seconds=0.5)
    assert detector.update(1.0, 0.1, 0.0) is None
    event = detector.update(1.0, 0.1, 0.1)
    assert event and event.direction == "left"
    assert detector.update(1.0, 0.1, 0.2) is None
    event = detector.update(1.0, 0.1, 0.7)
    assert event and event.direction == "left"


def test_balanced_sound_uses_middle_channel():
    detector = DirectionDetector(smoothing=1.0, consecutive=1, cooldown_seconds=0.0)
    event = detector.update(0.8, 0.9, 1.0)
    assert event and event.direction == "center"


def test_titan_commands_are_bounded_and_map_channels():
    assert titan_pulse_command("left", 1.4, 0) == b"CHNL 1; Pulse 1.00 1;\r\n"
    assert titan_pulse_command("right", 0.5, 40) == b"CHNL 2; Pulse 0.50 40;\r\n"
    assert titan_pulse_command("center", -1, 999) == b"CHNL 3; Pulse 0.00 500;\r\n"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
