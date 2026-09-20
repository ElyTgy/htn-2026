#!/bin/sh
# Make the caption server start by itself whenever the Pi boots (and restart if it crashes).
# Run ON THE PI, once:   sh scripts/pi_autostart.sh          (undo with: sh scripts/pi_autostart.sh remove)
# Afterwards:  sudo systemctl restart caption-glasses   |   journalctl -u caption-glasses -f
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT=/etc/systemd/system/caption-glasses.service

if [ "$1" = "remove" ]; then
  sudo systemctl disable --now caption-glasses 2>/dev/null || true
  sudo rm -f "$UNIT"
  sudo systemctl daemon-reload
  echo "autostart removed"
  exit 0
fi

pkill -f "pi/main.py" 2>/dev/null || true   # stop a manually started copy so the port is free
sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=Caption Glasses server
After=network-online.target
Wants=network-online.target

[Service]
User=$(whoami)
WorkingDirectory=$DIR
ExecStartPre=/usr/bin/truncate -s 0 $DIR/server.log
ExecStart=$DIR/.venv/bin/python -u pi/main.py --backend mediapipe --source picamera2
Restart=always
RestartSec=3
StandardOutput=append:$DIR/server.log
StandardError=append:$DIR/server.log

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now caption-glasses
sleep 8
systemctl is-active caption-glasses && echo "autostart installed; the server now starts on every boot"
