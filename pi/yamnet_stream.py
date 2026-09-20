"""Optional TF Hub YAMNet for browser microphone audio; no local sounddevice input."""
import asyncio
import csv
import math
import threading
import time
from dataclasses import dataclass

import numpy as np
from aiohttp import web, WSMsgType

MODEL_URL = "https://tfhub.dev/google/yamnet/1"
CHUNK_SECONDS = 1.0
TARGET_RATE = 16000


@dataclass(frozen=True)
class SoundFamily:
    id: str
    label: str
    emoji: str
    urgency: str
    priority: int
    threshold: float
    indices: tuple[int, ...]


# AudioSet/YAMNet indices. Related raw guesses collapse into one useful human-facing event.
# Speech, conversation, music, silence, room tone and generic noise are deliberately absent.
SOUND_FAMILIES = (
    SoundFamily('fire-alarm', 'Fire alarm', '🔥', 'urgent', 3, .08, (393, 394)),
    SoundFamily('siren', 'Siren', '🚨', 'urgent', 3, .10, (317, 318, 319, 390, 391)),
    SoundFamily('vehicle-horn', 'Vehicle horn', '🚗', 'urgent', 3, .10, (302, 312, 325)),
    SoundFamily('breaking-glass', 'Breaking glass', '💥', 'urgent', 3, .10, (434, 435, 437)),
    SoundFamily('doorbell', 'Doorbell', '🔔', 'attention', 2, .12, (349,)),
    SoundFamily('knocking', 'Knocking', '🚪', 'attention', 2, .12, (353,)),
    SoundFamily('phone-ringing', 'Phone ringing', '📱', 'attention', 2, .12, (384, 385)),
    SoundFamily('baby-crying', 'Baby crying', '👶', 'attention', 2, .12, (20,)),
    SoundFamily('shouting', 'Someone shouting', '📣', 'attention', 2, .16, (6, 10)),
    SoundFamily('dog-barking', 'Dog barking', '🐕', 'awareness', 1, .10, (69, 70, 71, 73)),
    SoundFamily('vehicle-nearby', 'Vehicle nearby', '🚙', 'awareness', 1, .15, (294, 300, 301, 308)),
    SoundFamily('running-water', 'Running water', '🚰', 'awareness', 1, .15, (282, 364, 444)),
)


def validate_rate(value):
    if type(value) is not int or not 8000 <= value <= 192000:
        raise ValueError("sampleRate must be an integer between 8000 and 192000")
    return value


def decode_audio(raw, sample_rate):
    validate_rate(sample_rate)
    if len(raw) % 4:
        raise ValueError("audio byte length is not float32-aligned")
    duration = len(raw) / 4 / sample_rate
    # Current clients send 1.0 s. Accept the earlier 1.5 s client during rolling updates so a
    # cached browser module cannot silently break environmental captions after a server restart.
    if not .9 <= duration <= 1.6:
        raise ValueError("expected 0.9–1.6 seconds of mono float32 little-endian PCM")
    audio = np.frombuffer(raw, dtype="<f4")
    if not np.isfinite(audio).all():
        raise ValueError("audio contains non-finite samples")
    return np.clip(audio, -1, 1)


def top_predictions(scores, names):
    scores = np.asarray(scores)
    if scores.ndim != 2 or not len(scores) or scores.shape[1] != len(names):
        raise ValueError("unexpected YAMNet score shape")
    if not np.isfinite(scores).all():
        raise ValueError("non-finite YAMNet scores")
    averages = scores.mean(axis=0)
    return [{"label": names[int(i)], "score": float(averages[i])}
            for i in np.argsort(averages)[::-1][:5]]


def sound_candidates(scores):
    """Collapse YAMNet's raw classes into a short priority-ranked product vocabulary."""
    scores = np.asarray(scores)
    if scores.ndim != 2 or not len(scores) or scores.shape[1] != 521:
        raise ValueError("unexpected YAMNet score shape")
    averages = scores.mean(axis=0)
    result = []
    for family in SOUND_FAMILIES:
        score = float(max(averages[index] for index in family.indices))
        if score >= family.threshold:
            result.append({
                'id': family.id, 'label': family.label, 'emoji': family.emoji,
                'urgency': family.urgency, 'priority': family.priority, 'score': score,
            })
    return sorted(result, key=lambda event: (-event['priority'], -event['score']))


class EventGate:
    """Confirm ordinary sounds, hold one card steady, and rate-limit repeats."""
    def __init__(self, hold_seconds=2.5, cooldown_seconds=2.0):
        self.hold_seconds = hold_seconds
        self.cooldown_seconds = cooldown_seconds
        self.candidate_id = None
        self.candidate_count = 0
        self.active = None
        self.last_seen = 0.0
        self.cooldowns = {}

    def update(self, candidates, now=None):
        now = time.monotonic() if now is None else now
        top = candidates[0] if candidates else None
        if top and top['id'] == self.candidate_id:
            self.candidate_count += 1
        else:
            self.candidate_id = top['id'] if top else None
            self.candidate_count = 1 if top else 0

        # The vocabulary and thresholds already suppress irrelevant raw classes. Show a supported
        # event on its first confident one-second window so short knocks and barks are not missed.
        qualifies = bool(top)
        if self.active:
            matching = next((event for event in candidates if event['id'] == self.active['id']), None)
            if matching:
                self.active = matching
                self.last_seen = now
            elif qualifies and top['priority'] > self.active['priority']:
                self.cooldowns[self.active['id']] = now + self.cooldown_seconds
                self.active, self.last_seen = top, now
            elif now - self.last_seen >= self.hold_seconds:
                self.cooldowns[self.active['id']] = now + self.cooldown_seconds
                self.active = None

        if not self.active and qualifies and now >= self.cooldowns.get(top['id'], 0):
            self.active, self.last_seen = top, now

        if not self.active:
            return None
        return {key: self.active[key] for key in ('id', 'label', 'emoji', 'urgency')}


class YAMNet:
    def __init__(self):
        self.model = None
        self.names = []
        # A disconnected browser can leave a to_thread call finishing in the background.
        self.lock = threading.Lock()

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            try:
                import tensorflow_hub as hub
                import scipy.signal  # verify resampling dependency before accepting audio
            except ImportError as exc:
                raise RuntimeError("YAMNet dependencies missing; see docs/YAMNET.md") from exc
            model = hub.load(MODEL_URL)
            with open(model.class_map_path().numpy().decode("utf-8"), newline="") as file:
                names = [row["display_name"] for row in csv.DictReader(file)]
            if len(names) != 521:
                raise RuntimeError("expected 521 YAMNet class names")
            self.names, self.model = names, model

    def classify(self, raw, sample_rate):
        from scipy.signal import resample_poly
        audio = decode_audio(raw, sample_rate)
        factor = math.gcd(TARGET_RATE, sample_rate)
        waveform = resample_poly(audio, TARGET_RATE // factor, sample_rate // factor).astype(np.float32)
        with self.lock:
            scores, _, _ = self.model(waveform)
            return sound_candidates(scores.numpy())


class YAMNetSocket:
    """One explicitly selected audio source; reply gates the next upload, preventing backlog."""
    def __init__(self, model=None):
        self.model = model if model is not None else YAMNet()
        self.active = False

    async def handle(self, request):
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1_152_000)
        await ws.prepare(request)
        if self.active:
            await ws.send_json({"type": "error", "error": "YAMNet already has an audio source. Stop it before connecting another."})
            await ws.close()
            return ws
        self.active = True
        peer = request.remote or 'unknown'
        print(f'[yamnet] client connected from {peer}', flush=True)
        try:
            hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
            if not isinstance(hello, dict) or hello.get("type") != "start":
                raise ValueError("expected start message")
            rate = validate_rate(hello.get("sampleRate"))
            gate = EventGate()
            await ws.send_json({"type": "status", "message": "Loading YAMNet on the server…"})
            await asyncio.to_thread(self.model.load)
            await ws.send_json({"type": "ready"})
            previous_event_id = object()
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    candidates = await asyncio.to_thread(self.model.classify, msg.data, rate)
                    event = gate.update(candidates)
                    event_id = event['id'] if event else None
                    if event_id != previous_event_id:
                        detail = ', '.join(f"{item['id']}={item['score']:.2f}" for item in candidates[:3]) or 'none'
                        print(f'[yamnet] display={event_id or "clear"} candidates={detail}', flush=True)
                        previous_event_id = event_id
                    await ws.send_json({"type": "sound-event", "event": event})
                elif msg.type == WSMsgType.TEXT:
                    raise ValueError("expected binary audio")
        except (ConnectionError, asyncio.CancelledError):
            raise
        except Exception as exc:
            print(f'[yamnet] client error: {exc}', flush=True)
            if not ws.closed:
                await ws.send_json({"type": "error", "error": str(exc)})
        finally:
            self.active = False
            print(f'[yamnet] client disconnected from {peer}', flush=True)
            await ws.close()
        return ws
