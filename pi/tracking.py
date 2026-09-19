"""Give each face a stable ID across frames by matching to the nearest previous position."""
from dataclasses import dataclass

from backends.base import Detection


@dataclass
class Track:
    id: int
    det: Detection
    last_seen: float

    @property
    def centre(self):
        return (self.det.x + self.det.w / 2, self.det.y + self.det.h / 2)


class Tracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, ts: float, detections: list[Detection]) -> list[Track]:
        """Returns the tracks seen in this frame."""
        pairs = []
        for tid, tr in self.tracks.items():
            tx, ty = tr.centre
            for di, d in enumerate(detections):
                dist = ((tx - (d.x + d.w / 2)) ** 2 + (ty - (d.y + d.h / 2)) ** 2) ** 0.5
                # Allow bigger jumps for bigger (closer) faces.
                if dist <= max(self.cfg.track_max_dist, d.w):
                    pairs.append((dist, tid, di))
        pairs.sort()

        used_tracks, used_dets, seen = set(), set(), []
        for _, tid, di in pairs:
            if tid in used_tracks or di in used_dets:
                continue
            used_tracks.add(tid)
            used_dets.add(di)
            tr = self.tracks[tid]
            tr.det, tr.last_seen = detections[di], ts
            seen.append(tr)

        for di, d in enumerate(detections):
            if di not in used_dets:
                tr = Track(self._next_id, d, ts)
                self._next_id += 1
                self.tracks[tr.id] = tr
                seen.append(tr)

        for tid in [t for t, tr in self.tracks.items() if ts - tr.last_seen > self.cfg.track_max_age]:
            del self.tracks[tid]
        return seen
