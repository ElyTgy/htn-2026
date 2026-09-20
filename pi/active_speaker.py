"""Decide who is talking from how much each mouth has been moving recently.

A talking mouth opens and closes several times a second, so the spread (standard
deviation) of mouth_open over a short window is high. A closed mouth, or one held
open (a smile, a yawn), has a low spread.
"""
from collections import deque
from statistics import pstdev


class SpeakerState:
    def __init__(self):
        self.history = deque()  # (timestamp, mouth_open)
        self.score = 0.0
        self.speaking = False
        self.last_above = 0.0


class ActiveSpeakerDetector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.states: dict[int, SpeakerState] = {}

    def update(self, ts: float, track_id: int, mouth_open: float) -> tuple[float, bool]:
        st = self.states.setdefault(track_id, SpeakerState())
        st.history.append((ts, mouth_open))
        while st.history and ts - st.history[0][0] > self.cfg.speak_window:
            st.history.popleft()

        # At 60 fps, two frames provide evidence in about 17 ms.
        if len(st.history) >= 2:
            spread = pstdev(m for _, m in st.history)
            st.score = min(spread / self.cfg.speak_std_full, 1.0)
        else:
            st.score = 0.0

        if st.score >= self.cfg.speak_on:
            st.speaking = True
        if st.score >= self.cfg.speak_off:
            st.last_above = ts
        elif st.speaking and ts - st.last_above > self.cfg.speak_hold:
            st.speaking = False
        return st.score, st.speaking

    def forget_except(self, live_ids):
        for tid in [t for t in self.states if t not in live_ids]:
            del self.states[tid]
