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
            current = tr.det
            incoming = detections[di]
            a = self.cfg.track_smoothing
            # Stabilize geometry only. Mouth movement and identity keypoints must remain from
            # the current frame or temporal smoothing would suppress speech and blur identity.
            tr.det = Detection(
                x=current.x + (incoming.x - current.x) * a,
                y=current.y + (incoming.y - current.y) * a,
                w=current.w + (incoming.w - current.w) * a,
                h=current.h + (incoming.h - current.h) * a,
                mouth_open=incoming.mouth_open,
                keypoints=incoming.keypoints,
            )
            tr.last_seen = ts
            seen.append(tr)

        for di, d in enumerate(detections):
            if di not in used_dets:
                tr = Track(self._next_id, d, ts)
                self._next_id += 1
                self.tracks[tr.id] = tr
                used_tracks.add(tr.id)
                seen.append(tr)

        # MediaPipe can miss an occluded face for a few frames. Keep the last stable geometry
        # available so boxes and person-owned captions do not blink or fall off the person.
        for tid, tr in self.tracks.items():
            if tid not in used_tracks and ts - tr.last_seen <= self.cfg.track_bridge_age:
                seen.append(tr)

        for tid in [t for t, tr in self.tracks.items() if ts - tr.last_seen > self.cfg.track_max_age]:
            del self.tracks[tid]
        return seen
