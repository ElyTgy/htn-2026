"""Faces and mouth opening from MediaPipe Face Landmarker, fed by any FrameSource."""
import urllib.request

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from config import MODEL_DIR
from .base import Detection

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
MODEL_PATH = MODEL_DIR / "face_landmarker.task"

# Face mesh landmark indices
LIP_UPPER_INNER = 13
LIP_LOWER_INNER = 14
FOREHEAD = 10
CHIN = 152


def ensure_model():
    if MODEL_PATH.exists():
        return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading face landmark model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)


class MediaPipeBackend:
    def __init__(self, source, cfg):
        self.source = source
        self.cfg = cfg
        self._landmarker = None
        self._frame = None
        self._t0 = None
        self._last_ms = -1

    def start(self):
        ensure_model()
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(MODEL_PATH),
                # Explicit CPU: leaving it unset crashes on some builds ("Service is unavailable").
                delegate=mp_python.BaseOptions.Delegate.CPU,
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=self.cfg.max_faces,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self.source.start()

    def read(self):
        got = self.source.read()
        if got is None:
            return None
        frame, ts = got
        self._frame = frame
        if self._t0 is None:
            self._t0 = ts
        # VIDEO mode needs strictly increasing integer milliseconds.
        ms = max(int((ts - self._t0) * 1000), self._last_ms + 1)
        self._last_ms = ms

        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        result = self._landmarker.detect_for_video(image, ms)

        h_px, w_px = frame.shape[:2]
        detections = []
        for lm in result.face_landmarks:
            xs = [p.x for p in lm]
            ys = [p.y for p in lm]
            x0, x1 = max(min(xs), 0.0), min(max(xs), 1.0)
            y0, y1 = max(min(ys), 0.0), min(max(ys), 1.0)
            # Measure in pixels so a non-square frame doesn't skew the ratio.
            gap = _dist_px(lm[LIP_UPPER_INNER], lm[LIP_LOWER_INNER], w_px, h_px)
            face_h = _dist_px(lm[FOREHEAD], lm[CHIN], w_px, h_px)
            mouth = gap / face_h if face_h > 1e-6 else 0.0
            keypoints = [
                _mid(lm[33], lm[133]),    # person's right eye (corners averaged)
                _mid(lm[362], lm[263]),   # person's left eye
                (lm[1].x, lm[1].y),       # nose tip
                (lm[61].x, lm[61].y),     # right mouth corner
                (lm[291].x, lm[291].y),   # left mouth corner
            ]
            detections.append(Detection(x0, y0, x1 - x0, y1 - y0, mouth, keypoints))
        return ts, detections

    def latest_frame(self):
        return self._frame

    def stop(self):
        self.source.stop()
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None


def _mid(a, b):
    return ((a.x + b.x) / 2, (a.y + b.y) / 2)


def _dist_px(a, b, w, h):
    return (((a.x - b.x) * w) ** 2 + ((a.y - b.y) * h) ** 2) ** 0.5
