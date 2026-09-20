"""Rotate frames from any source, for a camera that is mounted sideways or upside down.

The Pi's camera pipeline can only flip (180°), so 90° turns are done here on the CPU.
cfg.rotate is read on every frame so the page can change it while running.
np.rot90 is just a strided view; the copy makes the array contiguous, which mediapipe needs.
"""
import numpy as np

from .base import FrameSource


class RotatedSource:
    def __init__(self, inner: FrameSource, cfg):
        self.inner = inner
        self.cfg = cfg

    def start(self):
        self.inner.start()

    def read(self):
        got = self.inner.read()
        k = (self.cfg.rotate // 90) % 4   # np.rot90 turns counter-clockwise k times
        if got is None or k == 0:
            return got
        frame, ts = got
        return np.ascontiguousarray(np.rot90(frame, k)), ts

    def stop(self):
        self.inner.stop()

    def latest_frame(self):
        latest = getattr(self.inner, "latest_frame", None)
        frame = latest() if latest else None
        k = (self.cfg.rotate // 90) % 4
        if frame is None or k == 0:
            return frame
        return np.ascontiguousarray(np.rot90(frame, k))

    @property
    def capture_fps(self):
        return getattr(self.inner, "capture_fps", 0.0)
