#!/bin/sh
# Self-signed certificate so the page can be served over https:// (browsers only allow the
# microphone on https or localhost). Covers this machine's .local names and current addresses.
# Re-run it if the hostname changes. Usage: sh scripts/make_cert.sh
set -e
cd "$(dirname "$0")/.."
NAME="$(hostname)"
# "<name>-2.local" is what mDNS falls back to when the plain name is already taken.
SAN="DNS:localhost,DNS:$NAME,DNS:$NAME.local,DNS:$NAME-2.local,DNS:$NAME-3.local,IP:127.0.0.1"
for ip in $(hostname -I 2>/dev/null); do SAN="$SAN,IP:$ip"; done
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 60 \
  -keyout certs/key.pem -out certs/cert.pem \
  -subj "/CN=$NAME.local" -addext "subjectAltName=$SAN" 2>/dev/null
echo "created certs/ for: $SAN"
echo "Restart the server, open https://$NAME.local:8443/ and accept the browser's warning once."
