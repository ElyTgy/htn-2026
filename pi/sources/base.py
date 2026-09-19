"""A camera. Swap this to change where frames come from; nothing else changes."""
from typing import Optional, Protocol

import numpy as np


class FrameSource(Protocol):
    def start(self) -> None: ...

    def read(self) -> Optional[tuple[np.ndarray, float]]:
        """Block for the next frame. Returns (rgb_frame, time.monotonic()), or None at end of stream."""
        ...

    def stop(self) -> None: ...
