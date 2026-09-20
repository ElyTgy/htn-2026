"""Regression checks for tolerant, stabilized face tracking."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pi"))
sys.modules.setdefault("numpy", SimpleNamespace(ndarray=object))

from backends.base import Detection  # noqa: E402
from tracking import Tracker  # noqa: E402


def _cfg():
    return SimpleNamespace(track_max_dist=0.15, track_max_age=2.0,
                           track_bridge_age=0.25, track_smoothing=0.5)


def _d(x, mouth=0.01):
    return Detection(x=x, y=0.2, w=0.2, h=0.3, mouth_open=mouth,
                     keypoints=[(x, 0.2)])


def test_geometry_is_smoothed_but_mouth_is_current():
    tracker = Tracker(_cfg())
    first = tracker.update(0.0, [_d(0.1, 0.01)])[0]
    second = tracker.update(0.02, [_d(0.2, 0.08)])[0]
    assert first.id == second.id
    assert abs(second.det.x - 0.15) < 1e-9
    assert second.det.mouth_open == 0.08
    assert second.det.keypoints == [(0.2, 0.2)]


def test_short_detection_dropout_keeps_face_visible_once():
    tracker = Tracker(_cfg())
    face = tracker.update(0.0, [_d(0.1)])[0]
    bridged = tracker.update(0.10, [])
    assert [track.id for track in bridged] == [face.id]
    assert tracker.update(0.30, []) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().copy().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
