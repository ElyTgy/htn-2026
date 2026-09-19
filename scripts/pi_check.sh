#!/bin/sh
# Prints what we need to know about a Pi before installing. Read-only.
echo "user: $(whoami)   host: $(hostname)"
head -2 /etc/os-release
echo "arch: $(uname -m)   $(python3 --version 2>&1)"
tr -d '\0' < /proc/device-tree/model 2>/dev/null; echo
free -h | sed -n 2p
df -h / | tail -1
printf "passwordless sudo: "; sudo -n true 2>/dev/null && echo yes || echo no
echo "--- camera ---"
(rpicam-hello --list-cameras 2>&1 || libcamera-hello --list-cameras 2>&1) | head -8
echo "--- tools ---"
printf "git: "; which git || echo missing
printf "picamera2: "; dpkg -s python3-picamera2 2>/dev/null | grep '^Version' || echo "not installed"
printf "addresses: "; hostname -I
