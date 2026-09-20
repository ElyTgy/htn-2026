# Directional haptics — Rev 3.0.0

Three SparkFun SEN-12642 ENVELOPE signals drive left, right and back DRAKE motors through an Arduino Uno and TITAN Core. The Uno owns sensing, calibration and intensity mapping. The computer only displays and records diagnostics. Existing `firmware/sound_sensors` and previous comparison tests are separate.

See [microphone and motor maximums](docs/MAXIMUMS.md) for the exact A0/A1/A2 full-output point, motor channels, command frequencies, 100% command strings, and the observed difference in sensation between the red, yellow, and white motors.

**Bench candidate:** the Uno build and host tests pass. Rev 3 has not yet been flashed or physically qualified. The stock TITAN adapter's repeated short effects, independent overlap, stopping and latency still need bench validation. See [the test record](docs/TEST_RECORD.md) before enabling output.

## Wiring

| Signal / motor | Connection |
| --- | --- |
| Back SparkFun ENVELOPE | Uno A0 |
| Left SparkFun ENVELOPE | Uno A1 |
| Right SparkFun ENVELOPE | Uno A2 |
| Each microphone VCC / GND | Uno 5 V / GND |
| Each microphone AUDIO / GATE | Leave disconnected |
| Uno D3, SoftwareSerial TX | TITAN RXD (IO3) |
| Uno D2, SoftwareSerial RX | TITAN TXD (IO1) |
| Uno GND | TITAN GND |
| Red DRAKE LF, left | TITAN L+/L−; channel 1, 95 Hz |
| Yellow DRAKE MF, right | TITAN R+/R−; channel 2, 130 Hz |
| White DRAKE HF, back | TITAN M+/M−; channel 3, 160 Hz |

Keep the factory components on the microphone boards; “no resistor” means no **added** gain resistor at R17. This firmware expects three ENVELOPE outputs, not KY-038/Grove raw audio.

Power TITAN through its supported USB/battery path, separately from the Uno's 5 V motor load. Keep the shared ground. TITAN lists 3.3 V/5 V I/O support. Do not connect motor outputs to Arduino GPIO or power rails.

**Remove the mode-selection jumper:** IO21–IO22 selects the effect-loop demo. It is not a programming jumper. Normal serial operation uses no mode jumper. Flashing, when automatic boot fails, uses a temporary wire from **IO0 (zero)** to GND during power-up; remove it after programming.

TITAN's RXD/TXD header shares the ESP32 UART used by its USB bridge. Disconnect Uno D3 → TITAN RXD while flashing or testing TITAN directly over USB. For normal operation, reconnect D3 and use TITAN's battery/power supply instead of a competing computer serial connection. A USB power-only cable does not necessarily disconnect the onboard bridge's TX pin; if UART corruption persists, investigate electrical contention before qualifying the setup. Do not have the recorder, an IDE serial monitor and a browser all own the Uno serial port.

## Behavior

**Power-on cue:** five seconds after every Uno reset, the left, back and right motors each play one finite 3-second effect in that order, at the intensity ceiling and that motor's trim. It needs no calibration or qualification and does not count toward qualification. Sound-driven output and most commands (`BUSY`) pause while it plays; any mute cancels what remains. Opening the Uno's USB serial port resets the Uno, so connecting the recorder replays it. With no confirmed TITAN version it uses the VH 2.0 command order, which this kit's TITAN reported (2.0.1.0); change `STARTUP_FALLBACK_PROFILE` in `TitanAdapter.h` if TITAN is reflashed to VH 2.1 before a profile is saved.

Each input is averaged in approximately 5 ms windows. The ADC runs at its standard Uno configuration; the first conversion after switching channels is discarded for settling. No deliberate sample delay is used. SoftwareSerial writes **block** sampling, and the actual interruption appears in telemetry.

Five seconds of quiet establish a separate noise floor per microphone: mean + max(1.5 counts, 3 standard deviations), with a lower close level. A **loudness threshold** (default 40 ADC counts, `THRESHOLD` 0–200, saved with the settings) is added to both, so ordinary room activity stays silent and only louder sound opens a channel. In this kit's recordings quiet read about 7 counts, room activity 10–40 and loud events 70–500. At or below the opening level, commanded intensity is exactly zero. A previously sent finite effect may still be finishing. Clipped or interrupted calibration is rejected and the last valid record retained.

Above each threshold:

1. Measure the fraction of the ADC range from the opening level (noise floor + loudness threshold) up to **970 / 1023 counts**. A normal speech/reference sound does not redefine maximum output.
2. Apply a fixed sensitivity curve. The default is `x^0.4`; levels 1–5 use exponents 0.8, 0.6, 0.4, 0.3, 0.2. This lifts small sound changes without automatic gain control.
3. Compare the three excess amplitudes. Directional contrast suppresses quieter sides and fades near full scale. It never creates output on a silent channel. The default exponent is `1.5 × (1 − x)²` applied to the ratio to the loudest channel.
4. Smooth with approximately 5 ms attack / 50 ms release while above the floor. Returning to the floor clears the command immediately.
5. Apply the intensity ceiling and each motor's trim. The default ceiling is 100%, matching the requested tested maximum; trim can reduce a stronger motor.

Optional **Match microphones** uses five seconds of the same steady sound reaching all three equally. It saves fixed gain corrections (0.5–2×) for directional comparison. It does not change the 970-count full-scale point or equalize motor sensation. LF, MF and HF motors feel different at the same numerical command.

This measures relative envelope strength, not dB SPL or exact 3D source position. Reflections, microphone placement, simultaneous sources and motor vibration can affect direction cues. The noise gate cannot distinguish distant speech from background speech with the same amplitude. Keep motors mechanically separated from the microphones and test feedback after assembly.

## Install and flash

Use Python 3.10+ with pyserial/esptool, Node.js for dashboard tests, and Arduino CLI with the AVR core:

```sh
cd firmware/directional_haptics
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
arduino-cli core update-index
arduino-cli core install arduino:avr@1.8.6
python -m serial.tools.list_ports -v
```

Identify devices before flashing. This kit previously enumerated as CH340 (Uno, VID:PID 1A86:7523) and CP2104 (TITAN, 10C4:EA60). Names can change after reconnecting. Stop any recorder or serial monitor first.

### TITAN

The package uses TITAN's **official Vector Haptics 2.1 image**, not an invented motor-driver pin map. Its reviewed URL, size, SHA-256 and flash offset are in [titan/manifest.json](titan/manifest.json). The image is downloaded from the vendor; it is not redistributed in this repository.

1. Power TITAN off. Remove the IO21/IO22 demo cap and disconnect the Uno TX → TITAN RXD wire.
2. If automatic download mode fails, wire labeled IO0 to labeled GND, then reconnect TITAN USB to the computer. Check labels against the [official pinout](https://titanhaptics.com/images/products/titan-core/pinout-top.png).
3. Run the following, replacing the device path:

```sh
python tools/flash_titan.py --port /dev/cu.usbserial-TITAN
```

The tool downloads and verifies the pinned image, backs up **all detected flash**, writes at the vendor's `0x1000` offset, and verifies the written bytes. It stops before writing if backup or image validation fails. Backups remain local under `backups/`; retain them for recovery and do not commit them.

4. After verification, power off, remove **IO0 → GND**, and power on with the demo jumper still removed. Confirm the installed VH version. Restore the Uno UART wire only when direct USB transmission to TITAN has ended.

A full local backup can be restored with esptool at address `0x0`; first put TITAN back into download mode and select the matching device's backup. A backup contains settings, so never use another person's dump.

### Uno

```sh
./tools/flash_uno.sh /dev/cu.usbserial-UNO
```

The script builds `arduino/DirectionalHaptics` for `arduino:avr:uno` and uploads it. `ARDUINO_CLI` can name a different CLI executable. Rev 2 calibration is deliberately not reused. On first boot readings are available, but normal motor output stays off until calibration and TITAN qualification are saved.

## Dashboard and recording

```sh
python record.py --serial /dev/cu.usbserial-UNO --port 8766
```

Open **http://127.0.0.1:8766/**. Python owns the USB connection, avoiding in-app-browser Web Serial limitations. The browser consumes that exact recorded stream. Keep the familiar **All together**, **Apart**, and individual views. “Requested haptic” graphs and motor bars describe commands, not measured vibration.

Use `?demo=1` for clearly labeled synthetic data. Its firmware controls and recording are disabled. It illustrates silence, moving levels and near-full-scale sound; its timing numbers are not hardware measurements.

Each take records `readings.csv`, `readings.jsonl`, raw serial hex in `serial.log`, event markers and settings changes in `events.jsonl`, and `metadata.json`. Reports arrive at 25 Hz and contain raw minimum/maximum, mean, latest processing-window amplitude, peak, normalization, smoothed/desired/issued levels, clipping indication and timing. This is **not** an every-sample audio recording or every-command motor log. The command counter shows that multiple commands may occur between reports.

Closing the browser does not stop the recorder or the Uno. Stopping the recorder disconnects diagnostics; saved standalone operation should continue. Explicit Mute stays active until Resume or an Uno restart. Save does not persist mute.

## First setup and validation

1. Identify the installed TITAN version, select it under TITAN setup and apply. Changing it mutes output and clears qualification.
2. With the motors in hand, run each motor test and the unequal overlap test. Individual qualification pulses are one second at 100%. The overlap is one second with left 40%, back 70%, right 100%, chosen so the weaker MF/HF variants remain perceptible. Wait for each to stop before continuing.
3. Verify correct channels, independent concurrent playback, finite stopping and smooth repeated effects. The on-screen checkbox records the human observation; command acknowledgment alone proves none of these.
4. Use Quiet calibration during five seconds of representative quiet with motors off. Talking during this step raises the measured floor. Optional: match microphones side by side using steady equal exposure, then restore their beanie positions.
5. Resume. Compare quiet, distant activity, speech, a clap and a moving source. Adjust sensitivity and contrast; trim the red motor if its sensation dominates. Save settings and wait for `SAVED`.
6. Disconnect the browser, then the computer. Power-cycle both boards on their intended power supplies. Confirm the calibration/settings reload and sound drives the same spatial pattern autonomously.

The EEPROM record includes calibration, gains, profile, qualification, ceiling, trims, sensitivity and contrast, with a version, CRC and two alternating slots. Successful calibration is saved automatically. Other changes require **Save settings**. Interrupted writes preserve the previous committed record.

## Development and evidence

```sh
./tools/test.sh
arduino-cli compile --fqbn arduino:avr:uno arduino/DirectionalHaptics
python tools/analyze_capture.py recordings/take-EXAMPLE/readings.csv
```

The native harness executes the actual sketch against ADC/serial/EEPROM stubs; it tests logic and packet formatting, not AVR execution time, UART voltage or physical sensation. [Protocol details](docs/PROTOCOL.md), [test record](docs/TEST_RECORD.md), and [change notes](docs/CHANGES.md) explain the limits.

The candidate adapter sends finite 30 ms effects. A level change of at least 1% may transmit eight milliseconds after the previous completed write; an unchanged level refreshes every 25 ms. There is a sampling loop between channel writes and only one write per loop. This is intended to keep stable traffic bounded while leaving room for a sub-20 ms changed-channel target, but it is not proof of that target. Queuing/replacement behavior of stock firmware and timing with all motors active must be measured before release. Do not lengthen durations or stream faster on the assumption that TITAN replaces queued effects.

Vendor references: [serial terminal](https://vhterminal.titanhaptics.com/), [official flasher](https://vhterminal.titanhaptics.com/flash.html), [TITAN Core](https://titanhaptics.com/titan-core-development-kit/), [mode selection](https://titanhaptics.com/carlton-quickstart/), [DRAKE variants](https://titanhaptics.com/drake/).
