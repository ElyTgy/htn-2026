# Setup: laptop view and glasses view

One server on the Pi, one page, two ways to open it.

| | Link | What you see | Use it for |
|---|---|---|---|
| **Laptop (debug)** | `https://<pi>:8443/?video=1&debug=1` | Camera feed, boxes on faces, speaking scores, mic level, captions | Aiming the camera, checking faces are found, checking who gets each caption |
| **Glasses** | `https://<pi>:8443/` | Black page (= transparent in the glasses) with only the captions | Wearing it |

`<pi>` is the Pi's address, e.g. `10.37.113.242` or `caption-pi.local`. Run `hostname -I` on the Pi
to get it. Both can be open at the same time.

Never open the debug link in the glasses: `video=1` paints the camera feed over your whole view
and switches calibration off.

## 0. Once per Pi

```bash
sh scripts/pi_install.sh        # clone/update the repo in ~/caption-glasses and install dependencies
cp .env.example .env            # then paste the Deepgram key into .env
sh scripts/make_cert.sh         # https certificate; the mic only works over https
```

The certificate lists the Pi's addresses at the time it was made. On a new network (new IP) run
`make_cert.sh` again and restart, or the browser warning comes back.

## 1. Start (or restart) the server

On the Pi:

```bash
sh ~/caption-glasses/scripts/pi_start.sh
```

It stops any running copy, starts a new one in the background, and prints whether the key was
found, whether the process is up, and the last log lines. The live log is
`~/caption-glasses/server.log`:

```bash
tail -f ~/caption-glasses/server.log
```

To have it start on every boot instead, run `sh scripts/pi_autostart.sh` once; from then on restart
with `sudo systemctl restart caption-glasses`.

**After `git pull`:** changes under `web/` are picked up by reloading the page (the server reads
them from disk and tells the browser not to cache). Changes under `pi/` need a restart.

## 2. Camera

1. Peel the protective film off the Camera Module 3 lens, and take it out of its bag.
2. Mount it facing forward from your head, looking where your eyes look.
3. Open the laptop link and check the picture:
   - sharp, upright, people in frame. If it's on its side, toggle **Camera is sideways** in Settings
     (top-left corner). The Pi remembers this in `settings.json`.
   - a **blue box** on each face, turning **green** while that person talks.

No box on a face means no caption above that face. Captions for speech with no visible face go to
the grey bar at the bottom, which is what happens when the camera is covered, blurry, or pointing at
the ceiling. The log shows it too: `30.0 fps, 0 face(s)`.

## 3. Laptop view

1. Same network as the Pi.
2. Open `https://<pi>:8443/?video=1&debug=1`, accept the certificate warning once (Advanced → Proceed).
3. Tap **Start captions**, allow the microphone.

The mic used is the one on the device showing the page, so for a laptop test, talk near the laptop.
It does not go fullscreen in this mode, and calibration is ignored because the camera image fills
the page.

## 4. Glasses view

1. Phone / Beam Pro on the same network as the Pi, glasses plugged into it.
2. In Chrome open `https://<pi>:8443/` with **nothing after the `/`**. Accept the certificate warning once.
3. Tap **Start captions**, allow the microphone. The page goes fullscreen and turns landscape by
   itself. If the address bar ever comes back (back swipe, screen lock), tap anywhere.
4. Put the glasses in **follow / head-locked** mode, so the screen stays fixed to your head rather
   than hanging in the room.
5. If you see boxes or green status text, tap the dim **Boxes** button (bottom-left) to turn them off.

### Calibrate (once per device, again if the camera mount changes)

The camera and the glasses don't see the same angle, so faces have to be mapped onto the display.

1. Tap the top-left corner → Settings → tick **Show face boxes**.
2. Tap **XREAL starting point**.
3. Look at someone 1-2 m away and nudge until the box sits on their real face:
   arrows move it, **Bigger / Smaller** scale both ways, **Narrower / Wider** scale sideways only.
4. Box moves opposite to the person → tick **Mirror horizontally**.
5. Close, turn the boxes off.

With **Camera is sideways** on, the camera picture is tall and narrow while the display is wide, so
the starting point is further off: expect several presses of **Narrower** and a few of **Bigger**.

A caption pinned to a screen edge with an arrow (◀ ▶ ▲ ▼) means the camera sees that person but
they are outside what the display can reach. Turn your head that way.

## Checking from the Pi log

The page reports to `server.log` as `[page] ...` lines, so you can debug the glasses without
reaching the phone's browser console.

| Log line | Meaning |
|---|---|
| `30.0 fps, 0 face(s)` | Camera running but sees nobody: check aim, lens, focus |
| `[page] view / fullscreen=true page=800x360 ... video=false boxes=false` | Glasses page is set up right |
| `[page] view /?video=1...` on the phone | The phone has the debug link open; use the plain one |
| `[page] fullscreen/landscape refused: ...` | Browser refused fullscreen; tap the page once more |
| `[page] mic "..." live peak level 0.137` | Mic is hearing speech (0.000 = silence, wrong mic, or muted) |
| `[page] "text" → face #2 (lips)` | Caption went above face 2, chosen by lip movement |
| `[page] "text" → bar (voice)` | No face matched, so it went to the bottom bar |

## Quick fixes

| Symptom | Fix |
|---|---|
| Camera feed / a browser window floating in the glasses | The phone is on the debug link, or not fullscreen. Open the plain link, tap **Start captions**, tap once more if the address bar is showing |
| Black screen, captions only ever in the bottom bar | Camera sees no faces (section 2) |
| Captions appear but off to the side of the person | Calibrate |
| Boxes still showing on the plain link | Tap **Boxes**, or open `/?debug=0` |
| "cannot use the microphone" | You're on `http://`. Use `https://<pi>:8443/` |
| Page won't load | Different network, the Pi's IP changed, or the server is down: `sh scripts/pi_start.sh` |
| No text at all | Look for `stt deepgram:` errors in the log; check the key in `.env` and that the network has internet |
