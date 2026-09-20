"""YAMNet inference for the four environmental sounds shown in the glasses.

The browser supplies signed 16-bit little-endian, mono PCM at 16 kHz over a
WebSocket. Keeping inference here keeps the model and CPU work on the Pi,
while the Beam Pro browser remains a small display client.
"""
from __future__ import annotations

import queue
import threading
import urllib.request
from dataclasses import dataclass

import numpy as np

from config import MODEL_DIR


# TensorFlow Hub's TFLite classification model. It emits one 521-score vector
# for each 0.975-second waveform.
MODEL_URL = "https://tfhub.dev/google/lite-model/yamnet/classification/tflite/1?lite-format=tflite"
MODEL_PATH = MODEL_DIR / "yamnet-classification.tflite"
SAMPLE_RATE = 16_000
WINDOW_SAMPLES = 15_600  # 0.975 s; the model's required input length
HOP_SAMPLES = 7_680     # 0.48 s, matching YAMNet's standard hop


@dataclass(frozen=True)
class Target:
    index: int
    key: str
    label: str
    priority: int


# Indices are from Google's yamnet_class_map.csv for the model above.
TARGETS = (
    Target(70, "bark", "Barking", 1),
    Target(289, "waves", "Waves", 0),
    Target(302, "honk", "Honking", 2),
    Target(394, "fire-alarm", "Fire alarm", 3),
)


def selected_events(scores: np.ndarray, threshold: float) -> list[dict]:
    """Return the requested classes over threshold, highest-priority first."""
    events = [
        {"id": target.key, "label": target.label, "score": round(float(scores[target.index]), 3),
         "priority": target.priority}
        for target in TARGETS
        if float(scores[target.index]) >= threshold
    ]
    return sorted(events, key=lambda event: (-event["priority"], -event["score"]))


class SoundDetector:
    """Buffers PCM, runs TFLite off the aiohttp loop, and publishes target events."""

    def __init__(self, cfg, publish):
        self.cfg = cfg
        self.publish = publish
        self._interpreter = None
        self._input = None
        self._scores_output = None
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=24)
        self._stop = threading.Event()
        self._thread = None
        self.error = None
        self.ready = False

    def describe(self):
        return {
            "ready": self.ready,
            "error": self.error,
            "targets": [target.label for target in TARGETS],
        }

    def start(self):
        """Load the model before accepting audio. Captioning still works on failure."""
        try:
            self._load_interpreter()
        except Exception as e:
            self.error = str(e)
            print(f"environmental audio disabled ({self.error})")
            return False
        self.ready = True
        self._thread = threading.Thread(target=self._run, name="yamnet", daemon=True)
        self._thread.start()
        print("environmental audio ready (YAMNet: barking, waves, honking, fire alarm)")
        return True

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def push_pcm(self, data: bytes):
        """Accept one little-endian s16le PCM chunk without blocking aiohttp."""
        if not self.ready or not data or len(data) % 2:
            return
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            # Prefer newest audio to an ever-growing, stale queue.
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(data)
            except queue.Full:
                pass

    def _load_interpreter(self):
        if not MODEL_PATH.exists():
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            temporary = MODEL_PATH.with_suffix(".part")
            print(f"downloading YAMNet model to {MODEL_PATH} ...")
            urllib.request.urlretrieve(MODEL_URL, temporary)
            temporary.replace(MODEL_PATH)

        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            # Handy for a laptop with full TensorFlow; the Pi installs the smaller
            # tflite-runtime package from pi/requirements.txt.
            try:
                from tensorflow.lite import Interpreter
            except ImportError as e:
                raise RuntimeError("install pi/requirements.txt so tflite-runtime is available") from e

        self._interpreter = Interpreter(model_path=str(MODEL_PATH), num_threads=self.cfg.sound_threads)
        self._interpreter.allocate_tensors()
        self._input = self._interpreter.get_input_details()[0]
        if self._input["dtype"] != np.float32:
            raise RuntimeError(f"unexpected YAMNet input type {self._input['dtype']}")
        shape = tuple(int(value) for value in self._input["shape"])
        if shape not in {(WINDOW_SAMPLES,), (1, WINDOW_SAMPLES)}:
            raise RuntimeError(f"unexpected YAMNet input shape {shape}")

        outputs = self._interpreter.get_output_details()
        self._scores_output = next((output for output in outputs
                                    if int(np.prod(output["shape"])) == 521), None)
        if self._scores_output is None:
            raise RuntimeError("could not find YAMNet's 521-class score output")

    def _infer(self, waveform: np.ndarray) -> np.ndarray:
        data = waveform if len(self._input["shape"]) == 1 else waveform[np.newaxis, :]
        self._interpreter.set_tensor(self._input["index"], data)
        self._interpreter.invoke()
        scores = self._interpreter.get_tensor(self._scores_output["index"]).reshape(-1)
        if len(scores) != 521:
            raise RuntimeError(f"unexpected YAMNet score shape {scores.shape}")
        return scores

    def _run(self):
        pending = np.empty(0, dtype=np.float32)
        while not self._stop.is_set():
            try:
                raw = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            pending = np.concatenate((pending, samples))
            while len(pending) >= WINDOW_SAMPLES:
                try:
                    scores = self._infer(pending[:WINDOW_SAMPLES])
                except Exception as e:
                    self.error = f"YAMNet inference failed: {e}"
                    self.ready = False
                    print(f"environmental audio disabled ({self.error})")
                    self.publish({"type": "sound-status", "ready": False, "error": self.error})
                    return
                events = selected_events(scores, self.cfg.sound_threshold)
                self.publish({"type": "sound", "events": events})
                pending = pending[HOP_SAMPLES:]
