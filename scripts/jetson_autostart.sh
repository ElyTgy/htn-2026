#!/bin/sh
# Install two independent services: captions survive if the optional haptic bridge fails.
set -eu
DIR=$(cd "$(dirname "$0")/.." && pwd)
VISION_UNIT=/etc/systemd/system/caption-glasses-jetson.service
HARDWARE_UNIT=/etc/systemd/system/caption-glasses-hardware.service
CAMERA=${1:-csi}
CAMERA_INDEX=${2:-0}

if [ "$CAMERA" = remove ]; then
  sudo systemctl disable --now caption-glasses-jetson caption-glasses-hardware 2>/dev/null || true
  sudo rm -f "$VISION_UNIT" "$HARDWARE_UNIT"
  sudo systemctl daemon-reload
  echo "Jetson autostart removed"
  exit 0
fi

case "$CAMERA" in
  csi) VISION_ARGS="--backend mediapipe --source jetson-csi" ;;
  usb) VISION_ARGS="--backend mediapipe --source opencv --source-arg $CAMERA_INDEX" ;;
  *) echo "usage: $0 [csi|usb|remove]"; exit 2 ;;
esac

sudo tee "$VISION_UNIT" >/dev/null <<EOF
[Unit]
Description=Caption Glasses vision and web server (Jetson)
After=network-online.target
Wants=network-online.target

[Service]
User=$(whoami)
SupplementaryGroups=video
WorkingDirectory=$DIR
EnvironmentFile=-$DIR/.env
ExecStart=$DIR/.venv/bin/python -u pi/main.py $VISION_ARGS
Restart=always
RestartSec=3
StandardOutput=append:$DIR/server.log
StandardError=append:$DIR/server.log

[Install]
WantedBy=multi-user.target
EOF

sudo tee "$HARDWARE_UNIT" >/dev/null <<EOF
[Unit]
Description=Caption Glasses sound sensor and haptic bridge
After=caption-glasses-jetson.service

[Service]
User=$(whoami)
SupplementaryGroups=dialout
WorkingDirectory=$DIR
EnvironmentFile=-$DIR/.env
ExecStart=$DIR/.venv/bin/python -u jetson/hardware_bridge.py
Restart=always
RestartSec=3
StandardOutput=append:$DIR/hardware.log
StandardError=append:$DIR/hardware.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now caption-glasses-jetson caption-glasses-hardware
echo "installed; follow logs with: journalctl -u caption-glasses-jetson -u caption-glasses-hardware -f"
