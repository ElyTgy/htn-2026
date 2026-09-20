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
| TITAN backup / VH 2.1 flash | PENDING. Automatic download entry failed; manual IO0-to-GND setup needed. IO21/IO22 cap is demo mode, not download mode |
| Uno Rev 3 flash | PENDING. Arduino USB was absent during this revision's build |
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
