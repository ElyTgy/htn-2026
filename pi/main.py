"""Caption Glasses, Pi side: watch faces, work out who is talking, feed the caption page.

Examples
  python pi/main.py --backend fake                                # no camera, synthetic faces
  python pi/main.py --backend mediapipe --source opencv           # laptop / USB webcam
  python pi/main.py --backend mediapipe --source picamera2        # Raspberry Pi camera
"""
import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

from active_speaker import ActiveSpeakerDetector  # noqa: E402
from backends import make_backend  # noqa: E402
from config import ROOT, Config  # noqa: E402
from server import CaptionServer  # noqa: E402
from tracking import Tracker  # noqa: E402


def vision_loop(cfg, backend, server, stop):
    tracker = Tracker(cfg)
    speakers = ActiveSpeakerDetector(cfg)
    min_gap = 1.0 / cfg.send_hz
    last_sent = 0.0
    frames, fps, fps_t0 = 0, 0.0, time.monotonic()

    try:
        backend.start()
    except Exception as e:
        hint = ("\nOn macOS: allow camera access for the app running this terminal in System Settings → "
                "Privacy & Security → Camera, then run again.") if sys.platform == "darwin" else ""
        raise SystemExit(f"could not start the camera/vision backend: {e}{hint}")
    try:
        while not stop.is_set():
            got = backend.read()
            if got is None:
                print("camera stream ended")
                break
            ts, detections = got
            tracks = tracker.update(ts, detections)

            faces = []
            for tr in tracks:
                score, speaking = speakers.update(ts, tr.id, tr.det.mouth_open)
                d = tr.det
                faces.append({
                    "id": tr.id,
                    "x": round(d.x, 4), "y": round(d.y, 4), "w": round(d.w, 4), "h": round(d.h, 4),
                    "mouth": round(d.mouth_open, 4),
                    "score": round(score, 3),
                    "speaking": speaking,
                })
            speakers.forget_except(tracker.tracks.keys())

            frames += 1
            if ts - fps_t0 >= 2.0:
                fps = frames / (ts - fps_t0)
                frames, fps_t0 = 0, ts
                detail = "  ".join(f"#{f['id']} mouth={f['mouth']:.3f} score={f['score']:.2f}" for f in faces)
                print(f"{fps:5.1f} fps, {len(faces)} face(s)  {detail}".ljust(100), end="\r", flush=True)

            if ts - last_sent >= min_gap:
                last_sent = ts
                server.publish({"type": "frame", "t": round(ts * 1000), "fps": round(fps, 1), "faces": faces})
    finally:
        backend.stop()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", choices=["mediapipe", "fake", "oak"], default="mediapipe")
    p.add_argument("--source", choices=["picamera2", "opencv"], default="picamera2")
    p.add_argument("--source-arg", default="", help="camera index, video file or GStreamer string (opencv source)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--https", action="store_true", help="serve over HTTPS with certs/cert.pem (scripts/make_cert.sh)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    args = p.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = Config(width=args.width, height=args.height, port=args.port)
    backend = make_backend(args.backend, args.source, args.source_arg, cfg)
    server = CaptionServer(cfg, backend, args.backend)

    # The camera loop owns the main thread and the web server runs in the background.
    # macOS requires this: its camera API only delivers frames (and only shows the permission
    # prompt) on the main thread. It makes no difference on the Pi.
    server.start_in_thread(https=args.https)
    try:
        vision_loop(cfg, backend, server, threading.Event())
    except KeyboardInterrupt:
        print("\nstopping")


if __name__ == "__main__":
    main()
