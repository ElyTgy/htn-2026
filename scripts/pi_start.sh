#!/bin/sh
# (Re)start the caption server on the Pi in the background. Log: ~/caption-glasses/server.log
cd "$HOME/caption-glasses" || exit 1
pkill -f "pi/main.py" 2>/dev/null && sleep 1
nohup .venv/bin/python -u pi/main.py --backend mediapipe --source picamera2 "$@" > server.log 2>&1 < /dev/null &
sleep 12
printf ".env with key present: "; grep -q '^DEEPGRAM_API_KEY=.\+' .env 2>/dev/null && echo yes || echo NO
printf "process: "; pgrep -f "pi/main.py" >/dev/null && echo running || echo NOT RUNNING
echo "--- log (filtered) ---"
tr '\r' '\n' < server.log | grep -vE "^(W0000|I0000|INFO|\[[0-9:]+\.[0-9]+\] \[[0-9]+\] +INFO)" | grep -v "^ *$" | tail -12
