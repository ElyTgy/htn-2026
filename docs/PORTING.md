# Alternate vision hosts and cameras

The code has two seams. Everything after them (tracking, speaking detection, server, and browser page)
is shared.

| Seam | File | What it abstracts |
|---|---|---|
| `FrameSource` | `pi/sources/base.py` | camera frames as RGB arrays |
| `VisionBackend` | `pi/backends/base.py` | face boxes, landmarks, and mouth opening |

## Jetson Orin Nano

The implemented Jetson build includes:

- `pi/sources/jetson_csi_source.py`: bounded-latency Argus/GStreamer CSI capture with sensor-id 0/1 probing;
- the existing OpenCV source for a UVC USB camera;
- `scripts/jetson_*`: inventory, installation, launch, and boot services;
- `firmware/sound_sensors`: the two-analog-sensor Arduino firmware; and
- `jetson/hardware_bridge.py`: calibration, coarse left/right decisions, and TITAN L/R/M commands.

See [JETSON_SETUP.md](JETSON_SETUP.md) for the complete wiring and acceptance test. The old one-line
GStreamer recipe was not a full port: a pip OpenCV wheel lacks JetPack's GStreamer integration, and
the Jetson host also needs an explicit sound/haptic transport.

## OAK-1 as a plain camera

This remains a future option. Keep MediaPipe on the host and implement `FrameSource` with DepthAI:

1. Install `depthai` and its udev rule.
2. Build a colour-camera preview pipeline at 1280x720.
3. Return `(rgb_frame, time.monotonic())` from `read()`.
4. Register `--source oak` in `pi/sources/__init__.py`.

## OAK-1 doing vision on-camera

`pi/backends/oak_backend.py` is an untested skeleton. It needs a face detector, per-face crops, a
landmark model with inner-lip points, and a conversion to the shared `Detection` shape. Keep
`mouth_open` as inner-lip gap divided by face height or retune the thresholds in `pi/config.py`.

## On-device speech-to-text

The Jetson port keeps the existing browser-to-cloud transcription path. Local STT is a separate
feature: add a WebSocket audio endpoint, decode to 16 kHz PCM, run a streaming model, and return the
normalised transcript event documented in `web/stt/provider.js`. Whisper-style output has no live
speaker labels, so attribution then relies on lip movement alone.
