"""Luxonis OAK-1 backend: SKELETON, NOT TESTED (no hardware was available when this was written).

The idea: run face detection + landmarks on the camera's own chip and emit the
same Detection objects as the MediaPipe backend, so nothing downstream changes.
See docs/PORTING.md for the full walkthrough.

The quickest route that needs none of this file: use the OAK-1 as a plain
camera and keep MediaPipe on the host:
    python pi/main.py --backend mediapipe --source opencv --source-arg <index>
(after putting the OAK in UVC mode), or write an OakSource in sources/ that
returns depthai preview frames.
"""
from .base import Detection  # noqa: F401  (used once the TODOs are filled in)


class OakBackend:
    def __init__(self, cfg):
        self.cfg = cfg
        self._device = None
        self._frame = None

    def start(self):
        try:
            import depthai as dai  # noqa: F401
        except ImportError as e:
            raise RuntimeError("pip install depthai (and add the udev rule, see docs/PORTING.md)") from e
        # TODO build the pipeline:
        #   ColorCamera (preview 300x300 for the detector, plus a video output for /video)
        #   -> face detection NN (e.g. face-detection-retail-0004 or YuNet blob)
        #   -> ImageManip crop per face
        #   -> landmarks NN that includes inner-lip points (e.g. a MediaPipe face mesh blob)
        #   -> XLinkOut queues: "detections", "landmarks", "video"
        raise NotImplementedError("OAK backend is a skeleton; see docs/PORTING.md")

    def read(self):
        # TODO
        #   1. pull the next synced (detections, landmarks) packet from the device queues
        #   2. for each face: bbox as 0-1 fractions of the full frame, and
        #      mouth_open = inner-lip gap / face height (same definition as mediapipe_backend.py)
        #   3. return (time.monotonic(), [Detection(...), ...])
        raise NotImplementedError

    def latest_frame(self):
        return self._frame

    def stop(self):
        if self._device is not None:
            self._device.close()
            self._device = None
