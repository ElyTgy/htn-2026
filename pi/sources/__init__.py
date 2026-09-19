from .base import FrameSource


def make_source(name: str, arg: str, cfg) -> FrameSource:
    if name == "picamera2":
        from .picamera2_source import Picamera2Source
        return Picamera2Source(cfg)
    if name == "opencv":
        from .opencv_source import OpenCvSource
        return OpenCvSource(arg, cfg)
    raise ValueError(f"unknown source: {name}")
