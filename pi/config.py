"""All tunable settings in one place."""
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
MODEL_DIR = ROOT / "models"
CERT_DIR = ROOT / "certs"
SETTINGS_FILE = ROOT / "settings.json"   # settings changed from the page, kept across restarts

# Fields the page may change at runtime (POST /settings), with the values each accepts.
PAGE_SETTINGS = {"rotate": (0, 90, 180, 270)}


@dataclass
class Config:
    # Camera
    width: int = 1280
    height: int = 720
    fps: int = 30
    rotate: int = 0                # degrees counter-clockwise to turn each frame; set from the page
    max_faces: int = 4

    @property
    def frame_size(self) -> tuple[int, int]:
        """(width, height) of frames after rotation, which swaps the two for 90/270."""
        return (self.height, self.width) if self.rotate % 180 else (self.width, self.height)

    def page_settings(self) -> dict:
        return {k: getattr(self, k) for k in PAGE_SETTINGS}

    def load_settings(self):
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
        except (OSError, ValueError):
            return
        for k, allowed in PAGE_SETTINGS.items():
            if saved.get(k) in allowed:
                setattr(self, k, saved[k])

    def apply_settings(self, changes: dict):
        """Apply page settings and save them. Raises ValueError on an unknown key or value."""
        if not isinstance(changes, dict):
            raise ValueError("settings must be an object")
        for k, v in changes.items():
            if k not in PAGE_SETTINGS or type(v) is not int or v not in PAGE_SETTINGS[k]:
                raise ValueError(f"bad setting {k}={v!r}")
        for k, v in changes.items():
            setattr(self, k, v)
        SETTINGS_FILE.write_text(json.dumps(self.page_settings(), indent=2) + "\n")

    # Tracker
    track_max_dist: float = 0.15   # max centre jump (fraction of frame width) to keep the same ID
    track_max_age: float = 2.0     # seconds a track survives without a detection

    # Remembering people across tracking dropouts (identity.py)
    identity_threshold: float = 0.363   # cosine similarity to count as the same person (SFace's
                                        # recommended value; raise if two people get merged,
                                        # lower if one person keeps getting new numbers)
    identity_refresh: float = 1.0       # seconds between new signatures for a tracked face
    identity_gallery: int = 12          # signatures kept per person (covers different angles)
    identity_min_face_px: int = 48      # faces narrower than this are too small to identify
    identity_merge_window: float = 3.0  # how long a brand-new person may still be merged into a known one

    # Active speaker (mouth_open = inner-lip gap / face height)
    speak_window: float = 0.25     # react to turn changes instead of averaging them away
    speak_std_full: float = 0.012  # normal conversational lip motion maps strongly into the score
    speak_on: float = 0.12         # switch on with modest, real mouth movement
    speak_off: float = 0.06        # resist flicker without suppressing quiet speakers
    speak_hold: float = 0.18       # bridge syllable gaps, then release quickly at handoff

    # Server
    # None = listen on every interface over both IPv4 and IPv6. Phone hotspots are often
    # IPv6-only for laptops and Android devices, so an IPv4-only server would be unreachable.
    host: str | None = None
    port: int = 8080
    https_port: int = 8443         # only used when certs/ exists
    default_stt: str = "speechmatics"
