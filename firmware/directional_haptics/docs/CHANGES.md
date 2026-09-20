# Rev 3.0.0 change notes

- Three matched SparkFun envelope inputs: A1 left, A2 right, A0 back.
- Maximum intensity tied to a near-full ADC reading (970), rather than the calibration sound.
- Quiet calibration is sufficient to establish a usable mapping; optional equal-exposure matching adjusts directional comparison separately.
- Fixed sensitivity curves expose quiet activity; adjustable directional contrast suppresses quieter sides. No moving peak normalization or AGC.
- Exact zero command at the noise floor; 5 ms attack / 50 ms release above it.
- Variant-specific DRAKE frequencies: red LF 95 Hz, yellow MF 130 Hz, white HF 160 Hz.
- Default ceiling 100%, with per-motor reduction trims.
- Version 3 EEPROM and CRC-framed DH v3 USB telemetry; old calibration is rejected.
- Matching dashboard retains Together/Apart/individual views, adds sensitivity and contrast controls, and includes a clearly labeled simulation.
- Setup tools pin the official TITAN VH 2.1 image and back up the ESP32 before writing. Existing two-sensor firmware and earlier comparison recordings are preserved.
- Power-on cue: five seconds after reset, left, back and right each play one 3-second effect. The adapter's effect-duration limit rose from 2000 to 3000 ms for it.
- Loudness threshold: a channel opens only above its calibrated noise floor plus `THRESHOLD` ADC counts (default 40), and the output range starts there. Settings frames grew to 17 bytes to report it; it is stored at EEPROM 640–641 beside the unchanged v3 record. Added after the floor-only gate fired continuously on ordinary room sound.
- Motor scheduler rebuilt around measured TITAN behavior: one 40 ms effect per 50 ms slot to the next active channel in rotation, lines ended with CR LF. The previous cadence outran TITAN and had most channel selections rejected. TEST 4 is now a two-second rotation test, not an overlap.
- Low gate made safe: the gate rises while motors play (self-noise measured by the power-on cue) and across the back channel's shutdown spike 1.05 s after it goes idle. Threshold default 40 → 10, and an open microphone starts at a 20% command. The dashboard gains a live "How the firmware decides" panel.

Physical deployment/qualification is pending; see TEST_RECORD.md.
