"""Remember who is who, so a person keeps the same number when tracking drops and recovers.

The tracker (tracking.py) only follows a face from frame to frame by position. When a face is
lost for a moment (head turn, blur, hand in front) it comes back as a new track. Here each track
is mapped to a *person*: a face signature (a 128-number embedding from OpenCV's SFace model) is
compared with the people seen so far this session, and a match gets its old person ID back. The
page only ever sees person IDs, so caption colour and the learned voice label survive dropouts.

Privacy: signatures are anonymous numbers held in memory only. Nothing is saved to disk, sent
anywhere, or linked to a name, and everything is forgotten when the program exits.
"""
import urllib.request
from collections import deque

import numpy as np

from config import MODEL_DIR

MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_recognition_sface/face_recognition_sface_2021dec.onnx")
MODEL_PATH = MODEL_DIR / "face_recognition_sface_2021dec.onnx"


class FaceMemory:
    def __init__(self, cfg, enabled=True):
        self.cfg = cfg
        self.people: dict[int, deque] = {}      # person id → recent signatures (unit vectors)
        self.track_person: dict[int, int] = {}  # tracker's track id → person id
        self._new_since: dict[int, float] = {}  # track id → when it was given a brand-new person
        self._last_sig: dict[int, float] = {}   # track id → when we last took a signature
        self._next_person = 1
        self._model = self._load() if enabled else None

    @property
    def available(self):
        return self._model is not None

    def _load(self):
        try:
            import cv2
            if not MODEL_PATH.exists():
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                print(f"downloading face signature model to {MODEL_PATH} ...")
                urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            return cv2.FaceRecognizerSF.create(str(MODEL_PATH), "")
        except Exception as e:  # no model = no memory, but captions still work
            print(f"face memory disabled ({e}); people will get a new number after each dropout")
            return None

    def update(self, ts, frame, tracks, live_track_ids):
        """tracks: the tracker's tracks seen this frame. Returns {track id: person id}."""
        for tr in tracks:
            if tr.id not in self.track_person:
                self._assign(ts, frame, tr)
            elif ts - self._last_sig.get(tr.id, 0.0) >= self.cfg.identity_refresh:
                self._refresh(ts, frame, tr)

        for tid in [t for t in self.track_person if t not in live_track_ids]:
            self.track_person.pop(tid)
            self._new_since.pop(tid, None)
            self._last_sig.pop(tid, None)
        return {tr.id: self.track_person[tr.id] for tr in tracks}

    def _assign(self, ts, frame, tr):
        sig = self._signature(frame, tr.det)
        self._last_sig[tr.id] = ts
        person = self._match(sig, exclude=set(self.track_person.values()))
        if person is None:
            person = self._next_person
            self._next_person += 1
            self.people[person] = deque(maxlen=self.cfg.identity_gallery)
            self._new_since[tr.id] = ts
        self.track_person[tr.id] = person
        if sig is not None:
            self.people[person].append(sig)

    def _refresh(self, ts, frame, tr):
        sig = self._signature(frame, tr.det)
        if sig is None:
            return
        self._last_sig[tr.id] = ts
        person = self.track_person[tr.id]
        born = self._new_since.get(tr.id)
        if born is not None:
            # This track was given a new person, maybe because its first frame was blurry or side-on.
            # For a few seconds keep checking whether it is really someone we already know.
            if ts - born > self.cfg.identity_merge_window:
                self._new_since.pop(tr.id)
            else:
                others = set(self.track_person.values())
                known = self._match(sig, exclude=others)
                if known is not None:
                    self.people[known].extend(self.people.pop(person))
                    self.track_person[tr.id] = person = known
                    self._new_since.pop(tr.id)
        self.people[person].append(sig)

    def _match(self, sig, exclude):
        if sig is None:
            return None
        best, best_sim = None, self.cfg.identity_threshold
        for person, gallery in self.people.items():
            if person in exclude or not gallery:
                continue
            sim = max(float(sig @ g) for g in gallery)
            if sim >= best_sim:
                best, best_sim = person, sim
        return best

    def _signature(self, frame, det):
        """Unit-length face signature, or None if we can't take a good one from this frame."""
        if self._model is None or frame is None or not det.keypoints:
            return None
        import cv2
        h, w = frame.shape[:2]
        if det.w * w < self.cfg.identity_min_face_px:
            return None  # too small to tell people apart reliably
        # SFace's aligner takes a YuNet-style row: box, five landmarks (pixels), score.
        row = [det.x * w, det.y * h, det.w * w, det.h * h]
        for kx, ky in det.keypoints:
            row += [kx * w, ky * h]
        row.append(1.0)
        try:
            aligned = self._model.alignCrop(frame, np.array([row], dtype=np.float32))
            feat = self._model.feature(cv2.cvtColor(aligned, cv2.COLOR_RGB2BGR)).flatten()
        except cv2.error:
            return None
        norm = float(np.linalg.norm(feat))
        return feat / norm if norm > 1e-6 else None
