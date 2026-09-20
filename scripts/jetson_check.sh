#!/bin/sh
# Read-only inventory before installing or debugging the Jetson build.
set -u

echo "user: $(whoami)   host: $(hostname)"
head -2 /etc/os-release 2>/dev/null || true
echo "arch: $(uname -m)   $(python3 --version 2>&1)"
printf "board: "
tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown
echo
if [ -r /etc/nv_tegra_release ]; then
  printf "Jetson Linux: "
  head -1 /etc/nv_tegra_release
fi
free -h | sed -n '2p'
df -h / | tail -1

echo "--- camera ---"
if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-devices 2>&1 | sed -n '1,30p'
else
  echo "v4l2-ctl missing (jetson_install.sh installs it)"
fi
if command -v gst-inspect-1.0 >/dev/null 2>&1; then
  gst-inspect-1.0 nvarguscamerasrc >/dev/null 2>&1 && echo "nvarguscamerasrc: yes" || echo "nvarguscamerasrc: NO"
else
  echo "GStreamer tools: missing"
fi

echo "--- OpenCV ---"
PYTHON=python3
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python
"$PYTHON" - <<'PY' 2>&1 || true
try:
    import cv2
    line = next((line.strip() for line in cv2.getBuildInformation().splitlines() if "GStreamer:" in line), "GStreamer: unknown")
    print("opencv", cv2.__version__, "|", line)
except Exception as exc:
    print("opencv unavailable:", exc)
PY

echo "--- serial ---"
find /dev/serial/by-id -maxdepth 1 -type l -print 2>/dev/null || echo "no /dev/serial/by-id devices"
if [ -x .venv/bin/python ]; then
  .venv/bin/python jetson/hardware_bridge.py --list-ports 2>&1 || true
fi

echo "--- network ---"
printf "addresses: "
hostname -I 2>/dev/null || true
