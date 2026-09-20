"""Run with: .venv/bin/python tests/test_sound.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pi"))

from sound import TARGETS, selected_events  # noqa: E402


def test_selected_events_only_returns_requested_labels():
    scores = np.zeros(521, dtype=np.float32)
    scores[10] = 0.99  # An unrelated AudioSet class must never reach the overlay.
    scores[70] = 0.42
    scores[394] = 0.81
    assert selected_events(scores, 0.35) == [
        {"id": "fire-alarm", "label": "Fire alarm", "score": 0.81, "priority": 3},
        {"id": "bark", "label": "Barking", "score": 0.42, "priority": 1},
    ]


def test_target_indices_fit_yamnet_score_vector():
    assert [target.index for target in TARGETS] == [70, 289, 302, 394]
    assert all(0 <= target.index < 521 for target in TARGETS)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
