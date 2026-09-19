"""All tunable settings in one place."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
MODEL_DIR = ROOT / "models"
CERT_DIR = ROOT / "certs"


@dataclass
class Config:
    # Camera
    width: int = 1280
    height: int = 720
    fps: int = 30
    max_faces: int = 4

    # Tracker
    track_max_dist: float = 0.15   # max centre jump (fraction of frame width) to keep the same ID
    track_max_age: float = 1.0     # seconds a track survives without a detection

    # Active speaker (mouth_open = inner-lip gap / face height)
    speak_window: float = 0.6      # seconds of mouth history used for the score
    speak_std_full: float = 0.02   # std of mouth_open that maps to score 1.0
    speak_on: float = 0.35         # score needed to switch to "speaking"
    speak_off: float = 0.20        # score below which "speaking" may switch off
    speak_hold: float = 0.4        # seconds to keep "speaking" after the score drops

    # Server
    # None = listen on every interface over both IPv4 and IPv6. Phone hotspots are often
    # IPv6-only for laptops and Android devices, so an IPv4-only server would be unreachable.
    host: str | None = None
    port: int = 8080
    https_port: int = 8443         # only used when certs/ exists
    send_hz: float = 15.0          # max frame messages per second to the page
    default_stt: str = "deepgram"
