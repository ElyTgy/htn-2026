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
- `pi/sources/oak_source.py`: OAK RGB capture through DepthAI 2 or 3, with MediaPipe on the Jetson;
- `scripts/jetson_*`: inventory, installation, launch, and boot services;
- `firmware/sound_sensors`: the two-analog-sensor Arduino firmware; and
- `jetson/hardware_bridge.py`: calibration, coarse left/right decisions, and TITAN L/R/M commands.

See [JETSON_SETUP.md](JETSON_SETUP.md) for the complete wiring and acceptance test. The old one-line
GStreamer recipe was not a full port: a pip OpenCV wheel lacks JetPack's GStreamer integration, and
the Jetson host also needs an explicit sound/haptic transport.

## OAK-1 as a plain camera

This path is implemented in `pi/sources/oak_source.py`. It keeps MediaPipe on the host and uses
DepthAI only to stream RGB frames:

1. `scripts/jetson_install.sh` installs `depthai` and the Movidius udev rule.
2. `sh scripts/jetson_start.sh --camera oak --no-haptics` starts the vision server.
3. The source requests 640x360 BGR frames at 60 fps, converts them to RGB, and retains exactly the
   newest frame while the Jetson GPU runs face landmarks.

## On-device speech-to-text

The Jetson port keeps the existing browser-to-cloud transcription path. Local STT is a separate
feature: add a WebSocket audio endpoint, decode to 16 kHz PCM, run a streaming model, and return the
normalised transcript event documented in `web/stt/provider.js`. Whisper-style output has no live
speaker labels, so attribution then relies on lip movement alone.
