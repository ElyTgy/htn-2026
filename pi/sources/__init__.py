from .base import FrameSource


def make_source(name: str, arg: str, cfg) -> FrameSource:
    if name == "picamera2":
        from .picamera2_source import Picamera2Source
        source = Picamera2Source(cfg)
    elif name == "opencv":
        from .opencv_source import OpenCvSource
        source = OpenCvSource(arg, cfg)
    else:
        raise ValueError(f"unknown source: {name}")
    from .rotate import RotatedSource
    return RotatedSource(source, cfg)
