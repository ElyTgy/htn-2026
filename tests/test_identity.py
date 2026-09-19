"""Run with: .venv/bin/python tests/test_identity.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pi"))

from backends.base import Detection  # noqa: E402
from config import Config  # noqa: E402
from identity import FaceMemory  # noqa: E402
from tracking import Track  # noqa: E402

rng = np.random.default_rng(0)
ALICE, BOB = (v / np.linalg.norm(v) for v in rng.normal(size=(2, 128)))
KP = [(0.4, 0.4), (0.6, 0.4), (0.5, 0.5), (0.43, 0.6), (0.57, 0.6)]


def make_memory(faces_by_track):
    """FaceMemory whose signature for a track is a noisy copy of that track's person vector (or None)."""
    m = FaceMemory(Config(), enabled=False)
    def fake_signature(frame, det):
        base = faces_by_track.get(det.tag)
        if base is None:
            return None
        v = base + rng.normal(scale=0.03, size=128)
        return v / np.linalg.norm(v)
    m._signature = fake_signature
    return m


def track(tid, tag):
    d = Detection(0.4, 0.3, 0.2, 0.4, 0.01, KP)
    d.tag = tag
    return Track(tid, d, 0.0)


def test_same_person_keeps_number_after_dropout():
    m = make_memory({"a": ALICE, "b": BOB, "a2": ALICE})
    ids = m.update(0.0, None, [track(1, "a"), track(2, "b")], {1, 2})
    alice, bob = ids[1], ids[2]
    assert alice != bob
    m.update(5.0, None, [track(2, "b")], {2})                # Alice's track dies
    ids = m.update(6.0, None, [track(2, "b"), track(3, "a2")], {2, 3})  # she comes back as track 3
    assert ids[3] == alice and ids[2] == bob


def test_two_people_in_view_never_share_a_number():
    m = make_memory({"a": ALICE, "a_twin": ALICE})
    ids = m.update(0.0, None, [track(1, "a"), track(2, "a_twin")], {1, 2})
    assert ids[1] != ids[2]


def test_bad_first_frame_is_merged_once_a_good_one_arrives():
    faces = {"a": ALICE, "late": None}
    m = make_memory(faces)
    alice = m.update(0.0, None, [track(1, "a")], {1})[1]
    m.update(3.0, None, [], set())
    new = m.update(4.0, None, [track(2, "late")], {2})[2]     # blurry: no signature, gets a new number
    assert new != alice
    faces["late"] = ALICE                                      # a second later the face is clear
    assert m.update(5.1, None, [track(2, "late")], {2})[2] == alice


def test_real_model_runs_on_a_frame():
    m = FaceMemory(Config())
    if not m.available:
        print("  (model unavailable, skipped)")
        return
    frame = rng.integers(0, 255, size=(720, 1280, 3), dtype=np.uint8)
    sig = m._signature(frame, Detection(0.4, 0.3, 0.2, 0.4, 0.01, KP))
    assert sig is not None and sig.shape == (128,) and abs(np.linalg.norm(sig) - 1) < 1e-5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
