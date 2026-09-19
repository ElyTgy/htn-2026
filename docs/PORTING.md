# Porting to Jetson Orin Nano and/or the OAK-1

The code has two seams. Everything after them (tracking, speaking detection, server, the whole web
page) is shared and does not change.

| Seam | File | What it abstracts |
|---|---|---|
| `FrameSource` | `pi/sources/base.py` | Just the camera: returns RGB frames |
| `VisionBackend` | `pi/backends/base.py` | Camera **and** face analysis: returns `Detection(x, y, w, h, mouth_open)` per face |

## A. Jetson with a USB or CSI camera (easiest)

Nothing to write. Same MediaPipe backend, different source:

```bash
python3 -m venv .venv && .venv/bin/pip install -r pi/requirements.txt
# USB webcam
.venv/bin/python pi/main.py --backend mediapipe --source opencv --source-arg 0
# CSI camera (IMX219 / IMX477) through GStreamer
.venv/bin/python pi/main.py --backend mediapipe --source opencv --source-arg \
  "nvarguscamerasrc ! video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1 ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
```

Notes: JetPack 6 has Python 3.10, which `mediapipe==0.10.18` supports. The GStreamer string needs an
OpenCV built with GStreamer (JetPack's system OpenCV is; the pip wheel is not, so for CSI cameras
create the venv with `--system-site-packages` and remove `opencv-python-headless` from requirements).

## B. OAK-1 as a plain camera (easy)

Keeps MediaPipe on the host; the OAK is just a good USB camera.

1. `pip install depthai`, then add the udev rule:
   `echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules && sudo udevadm control --reload-rules && sudo udevadm trigger`
2. Add `pi/sources/oak_source.py` implementing `FrameSource`: build a depthai pipeline with a colour
   camera and one preview output (1280x720 RGB), and in `read()` return `(queue.get().getCvFrame()[..., ::-1], time.monotonic())`.
3. Register it in `pi/sources/__init__.py`, run with `--source oak`.

Use a USB 3 port and cable; if it drops out, the port isn't supplying enough power (powered hub or Y-cable).

## C. OAK-1 doing the vision on-camera (most work, frees the host)

Worth it only if the host is weak (Pi 3/4) or busy (Jetson running Whisper). Fill in
`pi/backends/oak_backend.py` (currently an untested skeleton):

1. Pipeline: colour camera → face detector NN (e.g. `face-detection-retail-0004` or YuNet from the
   Luxonis model zoo) → per-face crop (`ImageManip`) → a landmarks NN that includes inner-lip points
   (a MediaPipe face-mesh blob from the zoo) → XLink outputs.
2. In `read()`: convert each face to a `Detection`. `mouth_open` must use the same definition as
   `mediapipe_backend.py` (inner-lip gap ÷ forehead-to-chin distance) or the thresholds in `config.py` need retuning.
3. Run with `--backend oak`. Set `latest_frame()` from a low-res preview stream so `/video` still works.

## D. On-device speech-to-text on the Jetson (no internet)

The page only needs the normalised transcript event described in `web/stt/provider.js`, so:

1. Add a WebSocket endpoint on the Jetson (e.g. `/stt-audio`) that receives the page's MediaRecorder
   chunks, decodes them (ffmpeg → 16 kHz PCM) and feeds faster-whisper / whisper.cpp in short windows.
2. Add `web/stt/local.js`: same shape as `deepgram.js`, but the socket points at `/stt-audio` and the
   server replies with `{text, isFinal, start, end, words?}` which the provider offsets by `t0`.
3. Whisper gives no speaker labels, so attribution runs on lips only. Everything else is unchanged.

## Phase 2: haptics

The vision loop in `pi/main.py` already knows each face's horizontal position and who is speaking.
Add a small module that maps the active speaker's `x + w/2` to a blend between the front-left and
front-right motors (PWM through transistors), and pulses the back motors when the page reports speech
with no visible speaker (send that back over the existing WebSocket). If the 4 sound sensor modules +
Arduino are added, read its sector over USB serial and let it choose the side for off-camera sounds.
