#!/bin/sh
# Install the parallel Jetson runtime. Run on a Jetson Orin Nano with JetPack installed.
set -eu

REPO=https://github.com/ElyTgy/htn-2026.git
DEFAULT_DIR="$HOME/caption-glasses"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
CHECKOUT=$(dirname "$SCRIPT_DIR")

# Prefer the checkout containing this script. That makes a copied development tree installable and
# avoids pulling over local project changes. Clone only when this standalone script is run outside a
# repository checkout.
if [ -f "$CHECKOUT/pi/requirements.txt" ] && [ -f "$CHECKOUT/web/app.js" ]; then
  DIR=$CHECKOUT
elif [ -d "$DEFAULT_DIR/.git" ]; then
  DIR=$DEFAULT_DIR
else
  git clone "$REPO" "$DEFAULT_DIR"
  DIR=$DEFAULT_DIR
fi
cd "$DIR"

python3 - <<'PY'
import sys
if not ((3, 10) <= sys.version_info[:2] <= (3, 12)):
    raise SystemExit(f"Python 3.10-3.12 is required; found {sys.version.split()[0]}")
PY

if ! tr -d '\0' < /proc/device-tree/model 2>/dev/null | grep -qi 'Jetson Orin Nano'; then
  echo "warning: this does not look like a Jetson Orin Nano developer kit"
fi

sudo apt-get update
sudo apt-get install -y \
  git openssl avahi-daemon python3-pip python3-venv python3-opencv python3-numpy libportaudio2 \
  v4l-utils gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav

# The NVIDIA/Ubuntu OpenCV package has GStreamer; PyPI OpenCV wheels do not. Keep the apt package
# visible inside the venv, install MediaPipe's dependencies, then remove only the pip OpenCV wheel.
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r pi/requirements.txt pyserial
.venv/bin/pip uninstall -y opencv-contrib-python opencv-python opencv-python-headless >/dev/null 2>&1 || true

.venv/bin/python - <<'PY'
import cv2
import mediapipe
import serial

gst = next((line.strip() for line in cv2.getBuildInformation().splitlines() if "GStreamer:" in line), "")
print("mediapipe", mediapipe.__version__, "| opencv", cv2.__version__, "| pyserial", serial.VERSION)
print(gst)
if "YES" not in gst:
    raise SystemExit("OpenCV has no GStreamer support; a pip cv2 package may still be shadowing JetPack OpenCV")
PY

sudo usermod -aG video,dialout "$(whoami)"
if git -C "$DIR" rev-parse --short HEAD >/dev/null 2>&1; then
  echo "installed in $DIR at commit $(git -C "$DIR" rev-parse --short HEAD)"
else
  echo "installed from copied checkout in $DIR"
fi
echo "Log out/in (or reboot) once so video and dialout group membership takes effect."
