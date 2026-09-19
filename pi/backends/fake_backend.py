"""Synthetic faces for working on the page with no camera.

Two faces drift slowly; they take turns "talking" in 4-second blocks, with a
2-second block where nobody talks, so attribution and the bottom bar can be tested.
"""
import math
import time

from .base import Detection

TURN = 4.0
CYCLE = [0, 1, None]  # face index speaking in each block; None = silence


class FakeBackend:
    def __init__(self, cfg):
        self.cfg = cfg
        self._t0 = 0.0

    def start(self):
        self._t0 = time.monotonic()

    def read(self):
        time.sleep(1.0 / self.cfg.fps)
        now = time.monotonic()
        t = now - self._t0
        talker = CYCLE[int(t // TURN) % len(CYCLE)]
        faces = []
        for i, (cx, cy) in enumerate([(0.32, 0.45), (0.68, 0.42)]):
            cx += 0.06 * math.sin(t * 0.5 + i * 2.0)
            cy += 0.03 * math.cos(t * 0.7 + i)
            w, h = 0.12, 0.28
            mouth = 0.01
            if talker == i:
                mouth = 0.03 + 0.03 * abs(math.sin(t * 9.0)) * abs(math.sin(t * 2.3 + 1))
            faces.append(Detection(cx - w / 2, cy - h / 2, w, h, mouth))
        return now, faces

    def latest_frame(self):
        return None

    def stop(self):
        pass
