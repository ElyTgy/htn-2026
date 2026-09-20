#!/bin/sh
# Isolated Jetson camera + browser-microphone smoke test.
# It does not start the Arduino/TITAN bridge and does not change the Pi startup path.
set -eu
cd "$(dirname "$0")/.."

CAMERA=${1:-csi}
case "$CAMERA" in
  oak|csi|usb) ;;
  *) echo "usage: sh scripts/jetson_video_mic_test.sh [oak|csi|usb]"; exit 2 ;;
esac

if [ ! -x .venv/bin/python ]; then
  echo "Jetson runtime is not installed. Run: sh scripts/jetson_install.sh"
  exit 1
fi

if [ ! -r certs/cert.pem ] || [ ! -r certs/key.pem ]; then
  echo "Creating the local HTTPS certificate required by browser microphone permission..."
  sh scripts/make_cert.sh
fi

sh scripts/jetson_start.sh --camera "$CAMERA" --no-haptics

NAME=$(hostname)
PATH_Q='/?video=1&debug=1&stt=mic-test'
echo
echo "Open this on a laptop or phone on the same network:"
echo "  https://$NAME.local:8443$PATH_Q"
for ip in $(hostname -I 2>/dev/null); do
  echo "  https://$ip:8443$PATH_Q"
done
echo
echo "Accept the self-signed certificate warning, press Start captions, and allow microphone access."
echo "Pass: live camera + face box + a mic meter that grows when you speak."
echo "Logs: tail -f server.log"
