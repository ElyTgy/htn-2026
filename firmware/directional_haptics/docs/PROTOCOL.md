# DH v3 USB protocol

Uno hardware USB UART: 115200 baud, 8N1. TITAN uses SoftwareSerial D2 RX / D3 TX at 115200. Do not mix USB command formats with TITAN commands.

## Host → Uno

ASCII line: `D3 <id> <name> <integer>\n` (optional CR before LF). IDs 1–65535. Firmware input buffer is 48 bytes including terminator. Lines time out after 500 ms; overflow, extra tokens and invalid ranges are rejected. Host sends one request at a time and awaits its acknowledgment. No automatic replay of an uncertain actuation command.

| Command | Value | Effect |
| --- | --- | --- |
| HELLO | 0 | Version event and settings report |
| QUIET | 0 | Five seconds quiet calibration, then automatic save |
| REFERENCE | 0 | Five seconds microphone matching; quiet calibration required |
| CANCEL | 0 | Cancel in-progress calibration |
| SAVE | 0 | Persist current calibration/settings |
| MUTE / RESUME | 0 | Stop issuing effects / allow qualified sound output |
| SENSITIVITY | 1–5 | Fixed amplitude curve |
| CONTRAST | 0–30 | Directional exponent in tenths |
| THRESHOLD | 0–200 | Loudness threshold in ADC counts above each calibrated noise floor; clears current levels |
| CEILING | 0–100 | Output ceiling in percent |
| TRIM0 / TRIM1 / TRIM2 | 25–100 | Back / left / right motor trim |
| PROFILE | 0, 20, 21 | Unknown / VH 2.0 / VH 2.1; mutes and clears qualification |
| PROBE | 0 | Bounded `HDI D` header query; keeps output muted |
| TEST | 1–4 | Left / right / back / unequal overlap finite test |
| QUALIFY | 1 | Records observation after all four tests were sent |
| TELEMETRY | 0, 1 | Debug-only report disable/enable; ACK/settings continue |

MUTE takes precedence during calibration or save. Output stops by expiry of outstanding finite effects; an ACK means the Uno accepted the request, not that a motor was measured to stop. Qualification likewise requires external observation.

## Uno → host

Each frame is `44 48 <payload_length> <version/type> <payload> <crc_low> <crc_high>`. CRC16-CCITT uses initial `0xffff` over the length, version/type and payload. All binary numbers are little endian; maximum payload is 114 bytes. Invalid frames are discarded with bounded resynchronization. Version/type tags are 0x31, 0x32, 0x33; Rev 2 is rejected.

- **0x31 telemetry:** 114 bytes, nominal 25 Hz. Python schema `<II10H8B` followed by three `<13H>` channel records in **A0, A1, A2** order. See `Wire.h` and `protocol.py` for exact matching names.
- **0x32 event:** up to 71 ASCII bytes: `<id> OK|ERR|TITAN <message>`. ID 0 denotes unsolicited status or parser errors. Saving/calibration completion arrives after the initiating ACK.
- **0x33 settings:** 17 bytes, `<BB7HB>`: sensitivity, contrast, full-scale ADC, three gains × 1000, three motor frequencies, loudness threshold in ADC counts. At approximately 1 Hz and after changes. Gains/frequencies are A0/back, A1/left, A2/right.

ADC window means, amplitudes, thresholds and peaks are unsigned Q4 (divide by 16). The reported floor and close values are the effective gate: the calibrated noise floor plus the loudness threshold. Normalization, smoothed, desired and sent levels are permille (divide by 10 for percent). `sent` is the last issued amplitude until its local estimated expiration, not a driver acknowledgment or measured vibration. `rate` is samples/second **per microphone**; `updateRate` counts commands/second **across all motors**. `gapUs` is the largest sample-cycle gap in the current report interval; `txUs` is the most recent blocking TITAN write duration. `onsetLatencyUs` is the maximum internal timestamp from an ADC sample first crossing a closed gate to completion of that channel's SoftwareSerial write; zero means no measured onset in the interval. These values saturate at 65535. Aggregate successive reports to find maxima. The onset metric excludes sensor and mechanical motor delay and is not an oscilloscope measurement.

`commandSequence` wraps at 65536, report sequence and device milliseconds at 2^32. Reports are snapshots, so peaks and commands between them may be missed. `dropped` counts telemetry rejected because its bounded transmit buffer was occupied. USB backpressure never queues unlimited history.

## TITAN adapter

Per-channel `CHNL` values are L=1, R=2, M=3. Vendor terminal command order differs:

```text
VH 2.0: CHNL <channel>;vibrate <frequency> <0.000–1.000> <duration_ms> 1 0;\r
VH 2.1: CHNL <channel>;vibrate <duration_ms> <0.000–1.000> <frequency> 0;\r
```

Only `TitanAdapter.h` formats these commands. Current short-effect cadence is a bench candidate. Correct syntax does not establish header compatibility, simultaneous playback, queue bounds or physical stopping.
