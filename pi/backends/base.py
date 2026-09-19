"""The seam between "something that sees faces" and the rest of the app.

A backend only has to report, per frame, where each face is and how open its
mouth is. Tracking (stable IDs), speaking detection, the server and the web
page all sit downstream and never change when the backend is swapped.
"""
from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np


@dataclass
class Detection:
    """One face in one frame. All coordinates are fractions (0-1) of the camera frame."""
    x: float           # left edge
    y: float           # top edge
    w: float
    h: float
    mouth_open: float  # inner-lip gap divided by face height
    # Optional, for remembering who is who (identity.py): five (x, y) points as fractions of the
    # frame, in this order: the person's right eye, left eye, nose tip, right and left mouth corners.
    # ("Right" is the person's own right, so it appears on the left of the image.)
    keypoints: Optional[list] = None


class VisionBackend(Protocol):
    def start(self) -> None: ...

    def read(self) -> Optional[tuple[float, list[Detection]]]:
        """Block until the next frame is processed.

        Returns (timestamp_seconds, detections), or None when the source has ended.
        The timestamp is time.monotonic() at frame capture.
        """
        ...

    def latest_frame(self) -> Optional[np.ndarray]:
        """Most recent RGB frame for the debug video feed, or None if unavailable."""
        ...

    def stop(self) -> None: ...
