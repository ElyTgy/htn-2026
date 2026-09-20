#!/bin/sh
# Compile and upload the Arduino Uno sound-sensor firmware with arduino-cli.
set -eu
cd "$(dirname "$0")/.."
PORT=${1:-}
if [ -z "$PORT" ]; then
  echo "usage: $0 /dev/ttyACM0   (prefer the matching /dev/serial/by-id/... path)"
  exit 2
fi
command -v arduino-cli >/dev/null 2>&1 || {
  echo "arduino-cli is not installed; install it or open firmware/sound_sensors/sound_sensors.ino in Arduino IDE"
  exit 1
}
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:uno firmware/sound_sensors
arduino-cli upload -p "$PORT" --fqbn arduino:avr:uno firmware/sound_sensors
echo "uploaded; verify with: arduino-cli monitor -p $PORT -c baudrate=115200"
