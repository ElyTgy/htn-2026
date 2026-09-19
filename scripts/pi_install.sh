#!/bin/sh
# Clone (or update) the project on the Pi and install its Python dependencies.
set -e
REPO=https://github.com/ElyTgy/htn-2026.git
DIR="$HOME/caption-glasses"

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone "$REPO" "$DIR"
fi
cd "$DIR"

dpkg -s python3-picamera2 >/dev/null 2>&1 || sudo apt-get install -y python3-picamera2

# --system-site-packages so the venv can see the apt-installed picamera2
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r pi/requirements.txt

.venv/bin/python - <<'EOF'
import mediapipe, cv2, aiohttp, numpy, picamera2
print("mediapipe", mediapipe.__version__, "| opencv", cv2.__version__, "| numpy", numpy.__version__, "| picamera2 ok")
EOF
echo "installed in $DIR at commit $(git rev-parse --short HEAD)"
