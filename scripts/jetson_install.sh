#!/bin/sh
# Install the parallel Jetson runtime. Run on a Jetson Orin Nano with JetPack installed.
set -eu

REPO=https://github.com/ElyTgy/htn-2026.git
DEFAULT_DIR="$HOME/caption-glasses"
OPENCV_VERSION=4.12.0
GPU_WHEEL=mediapipe-0.10.23+gpu-cp310-cp310-linux_aarch64.whl
GPU_WHEEL_URL="https://github.com/mdbug/mediapipe-jetson-gpu/releases/download/v0.10.23-gpu/$GPU_WHEEL"
GPU_WHEEL_SHA256=c1c82c28d6e30d77aacdf92212eeac882322f22eed2ea57e82de3e9f34f34524
JETSON_BUILD_ROOT=
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
CHECKOUT=$(dirname "$SCRIPT_DIR")

cleanup() {
  if [ -n "$JETSON_BUILD_ROOT" ] && [ -d "$JETSON_BUILD_ROOT" ]; then
    rm -rf "$JETSON_BUILD_ROOT"
  fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

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
  git wget openssl avahi-daemon build-essential cmake ninja-build pkg-config \
  python3-dev python3-pip python3-venv python3-opencv python3-numpy libportaudio2 \
  libopencv-core-dev libopencv-highgui-dev libopencv-calib3d-dev \
  libopencv-features2d-dev libopencv-imgproc-dev libopencv-video-dev \
  libgtk-3-dev libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libjpeg-dev libpng-dev libtiff-dev libv4l-dev \
  v4l-utils gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-libav

# The Jetson GPU MediaPipe wheel was linked against OpenCV 4.12. JetPack 6.2 may still ship an older
# ABI, so build only the modules the wheel and camera sources use. This preserves GStreamer and avoids
# mixing an opaque PyPI cv2 binary with JetPack's media stack. A rerun skips this once 4.12 is present.
if ! python3 - <<'PY'
import cv2
import re
raise SystemExit(0 if cv2.__version__.startswith("4.12.") and
                 re.search(r"GStreamer:\s+YES", cv2.getBuildInformation()) else 1)
PY
then
  JETSON_BUILD_ROOT=$(mktemp -d /tmp/caption-glasses-opencv.XXXXXX)
  git clone --depth 1 --branch "$OPENCV_VERSION" https://github.com/opencv/opencv.git \
    "$JETSON_BUILD_ROOT/opencv"
  cmake -S "$JETSON_BUILD_ROOT/opencv" -B "$JETSON_BUILD_ROOT/opencv/build" -G Ninja \
    -D CMAKE_BUILD_TYPE=Release \
    -D CMAKE_INSTALL_PREFIX=/usr/local \
    -D BUILD_LIST=core,imgproc,highgui,video,features2d,calib3d,imgcodecs,videoio,python3 \
    -D BUILD_SHARED_LIBS=ON \
    -D BUILD_TESTS=OFF -D BUILD_PERF_TESTS=OFF -D BUILD_EXAMPLES=OFF \
    -D BUILD_JAVA=OFF -D BUILD_opencv_apps=OFF -D BUILD_opencv_python3=ON \
    -D PYTHON3_EXECUTABLE=/usr/bin/python3 \
    -D PYTHON3_PACKAGES_PATH=/usr/local/lib/python3.10/dist-packages \
    -D WITH_CUDA=OFF -D WITH_OPENCL=OFF -D WITH_IPP=OFF \
    -D WITH_GSTREAMER=ON -D WITH_FFMPEG=ON -D WITH_GTK=ON
  cmake --build "$JETSON_BUILD_ROOT/opencv/build" --parallel 4
  sudo cmake --install "$JETSON_BUILD_ROOT/opencv/build"
  sudo ldconfig
fi

# Keep /usr/local and JetPack packages visible inside the venv. The portable requirements file pins
# the CPU wheel for Pi/macOS; replace it here with the checksum-verified Jetson GPU build.
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r pi/requirements.txt pyserial
.venv/bin/pip install depthai
.venv/bin/pip uninstall -y opencv-contrib-python opencv-python opencv-python-headless >/dev/null 2>&1 || true

if [ -z "$JETSON_BUILD_ROOT" ]; then
  JETSON_BUILD_ROOT=$(mktemp -d /tmp/caption-glasses-mediapipe.XXXXXX)
fi
wget -q -O "$JETSON_BUILD_ROOT/$GPU_WHEEL" "$GPU_WHEEL_URL"
echo "$GPU_WHEEL_SHA256  $JETSON_BUILD_ROOT/$GPU_WHEEL" | sha256sum -c -
.venv/bin/pip install --force-reinstall --no-deps "$JETSON_BUILD_ROOT/$GPU_WHEEL"

# OAK cameras enumerate as Movidius USB devices. Linux needs this rule for
# non-root access before DepthAI can upload the camera pipeline.
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/80-movidius.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

.venv/bin/python - <<'PY'
import cv2
import depthai
import mediapipe
import serial

gst = next((line.strip() for line in cv2.getBuildInformation().splitlines() if "GStreamer:" in line), "")
print("mediapipe", mediapipe.__version__, "| opencv", cv2.__version__, "| pyserial", serial.VERSION,
      "| depthai", depthai.__version__)
print(gst)
if mediapipe.__version__ != "0.10.23+gpu":
    raise SystemExit("the Jetson GPU MediaPipe wheel is not active")
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
