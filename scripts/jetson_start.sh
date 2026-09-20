#!/bin/sh
# Start the Jetson caption server and, when enabled, the Arduino -> TITAN bridge.
set -u
cd "$(dirname "$0")/.." || exit 1

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

CAMERA=${JETSON_CAMERA:-csi}
SENSOR_ID=${CSI_SENSOR_ID:-auto}
CAMERA_INDEX=${USB_CAMERA_INDEX:-0}
SENSOR_PORT=${ARDUINO_PORT:-auto}
HAPTIC_PORT=${TITAN_PORT:-auto}
HARDWARE=1

while [ "$#" -gt 0 ]; do
  case "$1" in
    --camera) CAMERA=$2; shift 2 ;;
    --sensor-id) SENSOR_ID=$2; shift 2 ;;
    --camera-index) CAMERA_INDEX=$2; shift 2 ;;
    --sensor-port) SENSOR_PORT=$2; shift 2 ;;
    --titan-port) HAPTIC_PORT=$2; shift 2 ;;
    --no-haptics) HARDWARE=0; shift ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done

mkdir -p .run
for name in vision hardware; do
  pidfile=".run/jetson-$name.pid"
  if [ -r "$pidfile" ]; then
    pid=$(sed -n '1p' "$pidfile")
    case "$pid" in
      *[!0-9]*|'') ;;
      *) kill "$pid" 2>/dev/null || true ;;
    esac
    rm -f "$pidfile"
  fi
done
sleep 1

case "$CAMERA" in
  csi)
    if [ "$SENSOR_ID" = auto ]; then
      set -- --backend mediapipe --source jetson-csi
    else
      set -- --backend mediapipe --source jetson-csi --source-arg "$SENSOR_ID"
    fi
    ;;
  usb) set -- --backend mediapipe --source opencv --source-arg "$CAMERA_INDEX" ;;
  oak) set -- --backend mediapipe --source oak --width 512 --height 384 ;;
  fake) set -- --backend fake ;;
  *) echo "camera must be oak, csi, usb, or fake"; exit 2 ;;
esac

nohup .venv/bin/python -u pi/main.py "$@" > server.log 2>&1 < /dev/null &
VISION_PID=$!
echo "$VISION_PID" > .run/jetson-vision.pid

if [ "$HARDWARE" -eq 1 ]; then
  nohup .venv/bin/python -u jetson/hardware_bridge.py \
    --sensor-port "$SENSOR_PORT" --titan-port "$HAPTIC_PORT" > hardware.log 2>&1 < /dev/null &
  HARDWARE_PID=$!
  echo "$HARDWARE_PID" > .run/jetson-hardware.pid
fi

sleep 8
printf "vision: "
kill -0 "$VISION_PID" 2>/dev/null && echo running || echo "NOT RUNNING (see server.log)"
if [ "$HARDWARE" -eq 1 ]; then
  printf "sound/haptics: "
  kill -0 "$HARDWARE_PID" 2>/dev/null && echo running || echo "NOT RUNNING (see hardware.log)"
fi
echo "--- vision log ---"
tail -12 server.log
if [ "$HARDWARE" -eq 1 ]; then
  echo "--- hardware log ---"
  tail -12 hardware.log
fi

kill -0 "$VISION_PID" 2>/dev/null || exit 1
if [ "$HARDWARE" -eq 1 ]; then
  kill -0 "$HARDWARE_PID" 2>/dev/null || exit 1
fi
