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

Physical deployment/qualification is pending; see TEST_RECORD.md.
