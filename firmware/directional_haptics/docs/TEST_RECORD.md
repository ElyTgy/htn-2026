# Rev 3 test record — 2026-09-20

**Status: software candidate; hardware deployment and qualification pending.** Nothing below substitutes generated readings for a physical measurement.

| Check | Result / evidence |
| --- | --- |
| Uno AVR compile | PASS, Arduino AVR core 1.8.6, `arduino:avr:uno`: 20,830 bytes flash (64%); 1,004 bytes static SRAM (49%); 1,044 bytes remain for stack/heap |
| Signal and actual sketch logic | PASS, native C++ with AddressSanitizer + UndefinedBehaviorSanitizer; see `tests/firmware_test.cpp` |
| Quiet → zero command | PASS in native tests, including clearing an above-floor release tail |
| Full-scale input → full command | PASS in native tests for all three channels at 970 counts and above |
| Monotonic response | PASS, swept 0–1023 for one channel with the others held fixed; sensitivity curves also swept |
| Small directional differences | PASS in native tests: contrast increases the output separation for a 2-count input difference |
| Optional matching | PASS, known unequal gains corrected for directional comparison; insufficient reference retained previous calibration |
| Calibration clipping/rejection | PASS in native tests; clipped quiet input does not replace valid calibration |
| Motor channel/frequency formatting | PASS for VH 2.0 and VH 2.1; A0→M160Hz, A1→L95Hz, A2→R130Hz |
| EEPROM CRC/version/interrupted write | PASS in native tests; latest completed slot restored, incomplete slot rejected |
| Parser and USB backpressure | PASS in native tests; malformed/overlong commands rejected and telemetry dropped without unbounded queuing |
| Host protocol / recording | PASS, 4 Python tests including split frames, CRC recovery, bounds, DH v2 rejection, DH v3 settings, recording rotation, settings persistence in take metadata and command bounds |
| Dashboard simulation | PASS, synthetic silence, changing direction and near-rail full output; no hardware writes |
| Dashboard browser | PASS, local in-app browser: Rev 3 labels, distinct changing motor bars, Apart view and requested-haptic comparison; firmware actions disabled in simulation; no captured console warnings/errors |
| Prior direct-USB motor check | User reported left/back/right 2-second, 100% tests worked on stock VH 2.0 at 95/160/130 Hz. This was before Rev 3 and does not qualify header streaming |
| Requested final haptic check | 2026-09-20: direct USB sent `CHNL 1;vibrate 95 1.000 2000 1 0;` after a clean Vector Haptics 2.0.1.0 boot. All 34 bytes were written; TITAN returned no serial acknowledgment. Physical actuation was not confirmed, so this is recorded as inconclusive rather than a pass |
| Uno Rev 3 flash with power-on cue | 2026-09-20: uploaded to the Uno (CH340), 21,448 bytes flash (66%), 1,019 bytes static SRAM (49%). Boot event `DIRECTIONAL_HAPTICS_3.0.0`; saved calibration loaded, profile 0, not qualified |
| Power-on cue, Uno header → TITAN | 2026-09-20: telemetry showed left, back, right at 100% from device time 5.04, 8.04 and 11.05 s, ending 14.07 s; blocking write about 3.3 ms per command. TITAN (VH 2.0.1.0), observed over its USB port, printed `Vibrate done` for 95, 160 and 130 Hz, 3000 ms, intensity 1.000, about 3 s apart. This proves the header path parses and runs the commands; nobody recorded feeling the motors, and TITAN USB was attached, which the wiring notes warn can contend with the Uno's TX |
| Profile, tests, qualification saved | 2026-09-20: `PROFILE 20`, `TEST 1`–`4`, `QUALIFY 1`, `RESUME`, `SAVE` all acknowledged, then `SAVED`. The user reported the motors working; the unequal overlap test was sent but nobody recorded observing it. In the following 20 s of room sound, amplitudes reached 25–27 counts against floors of 10.6–16.1, requested levels peaked at 12% back, 19% left, 9% right, and 1,709 motor commands were issued. Requested levels, not measured vibration |
| Loudness threshold on the bench | 2026-09-20: with the floor-only gate the user reported the motors firing constantly on room sound. After flashing the 40-count threshold (gates at 52.4 back, 50.6 left, 56.1 right), 25 s of room sound peaked at 40, 37 and 41 counts and produced zero motor commands. Response to a deliberately loud sound and the felt result are PENDING |
| TITAN backup / VH 2.1 flash | PENDING. Automatic download entry failed; manual IO0-to-GND setup needed. IO21/IO22 cap is demo mode, not download mode |
| Three simultaneous independent motors | PENDING on Rev 3 header path |
| Finite physical stopping / no queued tail | PENDING on target driver |
| Smooth repeated playback | PENDING; 30 ms effects, 25 ms stable refresh and ≥8 ms changed-level guard remain a candidate |
| Actual sampling with telemetry on/off | PENDING on target Uno |
| Electrical input → completed UART command latency | NOT MEASURED. No sub-20 ms claim; the current refresh guard can itself exceed that target |
| Quiet / distant speech / clap / moving sound | PENDING on saved Rev 3 calibration |
| Motor acoustic/mechanical feedback | PENDING in assembled beanie |
| Browser disconnect and standalone cold boot | PENDING on flashed boards with saved settings |

The software tests use synthetic ADC values and mocked serial/EEPROM timing. SRAM figures are static allocation, not measured peak stack use. A firmware ACK reports command parsing, not physical actuation.

## Bench completion record

For each run, retain the original take plus event markers identifying quiet, source side, distance, speech/clap, telemetry mode and motor attachment. Use `tools/analyze_capture.py` to summarize sampling gaps, rates and command snapshots. Do not commit private recordings.

To measure input-to-command latency, use an electrical sensor-input transition and a logic analyzer/oscilloscope observing the transition and TITAN RXD. Measure both first and last UART bit. Repeat across channels, with all motors active, and with telemetry enabled/disabled. Report sensor and motor mechanical delays separately. 25 Hz browser traces and last UART write duration cannot establish this latency.

Observe motor start/stop and simultaneous unequal outputs before setting qualification. Confirm there is no delayed queue after stopping transmission. If stock VH 2.1 queues effects or cannot maintain the required independent smooth output, revise the driver implementation using supported TITAN source/API; do not claim the current adapter is production-ready.
