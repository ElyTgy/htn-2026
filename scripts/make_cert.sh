#!/bin/sh
# Self-signed certificate so the page can be served over https:// (needed for mic access
# unless you use the chrome://flags route in the README). Usage: scripts/make_cert.sh [pi-ip]
set -e
cd "$(dirname "$0")/.."
IP="${1:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
[ -n "$IP" ] || { echo "usage: $0 <this-machine's-ip>"; exit 1; }
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout certs/key.pem -out certs/cert.pem \
  -subj "/CN=caption-glasses" -addext "subjectAltName=IP:$IP,DNS:localhost"
echo "created certs/ for $IP. Run with --https, open https://$IP:8080/ and accept the warning once."
