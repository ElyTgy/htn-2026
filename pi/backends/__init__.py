from .base import Detection, VisionBackend


def make_backend(name: str, source_name: str, source_arg: str, cfg) -> VisionBackend:
    """Imports are lazy so a backend's dependencies are only needed if it is used."""
    if name == "fake":
        from .fake_backend import FakeBackend
        return FakeBackend(cfg)
    if name == "mediapipe":
        from sources import make_source
        from .mediapipe_backend import MediaPipeBackend
        return MediaPipeBackend(make_source(source_name, source_arg, cfg), cfg)
    raise ValueError(f"unknown backend: {name}")
