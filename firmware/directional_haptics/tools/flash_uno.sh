#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /dev/cu.usbserial-... (or COM... / /dev/ttyUSB...)" >&2
  exit 2
fi
FIRMWARE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ARDUINO_CLI=${ARDUINO_CLI:-arduino-cli}
"$ARDUINO_CLI" compile --fqbn arduino:avr:uno --build-path "$FIRMWARE_ROOT/build/uno" "$FIRMWARE_ROOT/arduino/DirectionalHaptics"
"$ARDUINO_CLI" upload --fqbn arduino:avr:uno --port "$1" --input-dir "$FIRMWARE_ROOT/build/uno" "$FIRMWARE_ROOT/arduino/DirectionalHaptics"
echo "Uno uploaded. Use this package's recorder for protocol DH v3. Saved Rev 2 calibration is deliberately not reused."
