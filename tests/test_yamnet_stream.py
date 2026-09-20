"""Run .venv/bin/python tests/test_yamnet_stream.py (no model download or microphone)."""
import sys
import unittest
from pathlib import Path

import numpy as np
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pi"))
from yamnet_stream import (EventGate, YAMNet, YAMNetSocket, decode_audio,
                           sound_candidates, top_predictions, validate_rate)


class AudioTests(unittest.TestCase):
    def test_pcm_validation(self):
        audio = np.full(16000, 0.25, dtype="<f4")
        np.testing.assert_array_equal(decode_audio(audio.tobytes(), 16000), audio)
        # The previous 1.5 s client remains compatible during rolling updates.
        self.assertEqual(len(decode_audio(np.zeros(24000, dtype='<f4').tobytes(), 16000)), 24000)
        for raw in (b"", audio.tobytes()[:-1], np.full(16000, np.nan, dtype="<f4").tobytes()):
            with self.assertRaises(ValueError):
                decode_audio(raw, 16000)
        for rate in (True, 16000.0, None, 0, 200000):
            with self.assertRaises(ValueError):
                validate_rate(rate)

    def test_averages_all_frames_and_ranks_five_classes(self):
        scores = np.array([[0, 1, .6, .4, .3, .2], [0, 0, .6, .4, .3, .2]])
        result = top_predictions(scores, list("abcdef"))
        self.assertEqual([p["label"] for p in result], list("cbdef"))
        self.assertAlmostEqual(result[0]["score"], .6)

    def test_resamples_phone_audio_for_model(self):
        classifier = YAMNet()
        class Scores:
            def numpy(self):
                scores = np.zeros((1, 521), dtype=np.float32)
                scores[0, 70] = .9
                return scores
        def model(waveform):
            self.assertEqual(waveform.shape, (16000,))
            self.assertEqual(waveform.dtype, np.float32)
            self.assertAlmostEqual(float(waveform[1000]), .25, places=3)
            return Scores(), None, None
        classifier.model = model
        result = classifier.classify(np.full(48000, .25, dtype='<f4').tobytes(), 48000)
        self.assertEqual(result[0]['label'], 'Dog barking')

    def test_groups_classes_and_ignores_speech_music(self):
        scores = np.zeros((2, 521), dtype=np.float32)
        scores[:, 0] = .99       # Speech is intentionally suppressed.
        scores[:, 132] = .95     # Music is intentionally suppressed.
        scores[:, 302] = .21
        scores[:, 312] = .49     # Both horn classes become one event.
        scores[:, 70] = .30
        events = sound_candidates(scores)
        self.assertEqual([event['id'] for event in events], ['vehicle-horn', 'dog-barking'])
        self.assertEqual(events[0]['emoji'], '🚗')
        self.assertNotIn('score', EventGate().update(events, now=0))

    def test_event_gate_immediate_display_hold_cooldown_and_urgent_override(self):
        dog = {'id': 'dog-barking', 'label': 'Dog barking', 'emoji': '🐕',
               'urgency': 'awareness', 'priority': 1, 'score': .8}
        alarm = {'id': 'fire-alarm', 'label': 'Fire alarm', 'emoji': '🔥',
                 'urgency': 'urgent', 'priority': 3, 'score': .4}
        gate = EventGate(hold_seconds=3, cooldown_seconds=2)
        self.assertEqual(gate.update([dog], now=0)['id'], 'dog-barking')
        self.assertEqual(gate.update([dog], now=1)['id'], 'dog-barking')
        self.assertEqual(gate.update([], now=3)['id'], 'dog-barking')
        self.assertIsNone(gate.update([], now=4.1))
        self.assertIsNone(gate.update([dog], now=5))  # still cooling down
        self.assertEqual(gate.update([dog], now=6.2)['id'], 'dog-barking')
        self.assertEqual(gate.update([alarm], now=6.3)['urgency'], 'urgent')


class FakeModel:
    def load(self):
        pass

    def classify(self, raw, rate):
        decode_audio(raw, rate)
        return [{"id": "vehicle-horn", "label": "Vehicle horn", "emoji": "🚗",
                 "urgency": "urgent", "priority": 3, "score": .8}]


class SocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.handler = YAMNetSocket(FakeModel())
        app = web.Application()
        app.router.add_get('/sound-ws', self.handler.handle)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def connect(self):
        ws = await self.client.ws_connect('/sound-ws')
        await ws.send_json({"type": "start", "sampleRate": 16000})
        self.assertEqual((await ws.receive_json())["type"], "status")
        self.assertEqual((await ws.receive_json())["type"], "ready")
        return ws

    async def test_classifies_and_rejects_other_audio_source(self):
        ws = await self.connect()
        second = await self.client.ws_connect('/sound-ws')
        self.assertIn('already has', (await second.receive_json())["error"])
        await second.close()
        await ws.send_bytes(np.zeros(16000, dtype="<f4").tobytes())
        msg = await ws.receive_json()
        self.assertEqual(msg, {"type": "sound-event", "event": {
            "id": "vehicle-horn", "label": "Vehicle horn", "emoji": "🚗", "urgency": "urgent"
        }})
        await ws.close()
        # A new capture session must not inherit prior audio.
        again = await self.connect()
        await again.close()

    async def test_bad_audio_closes_session_with_visible_error(self):
        ws = await self.connect()
        await ws.send_bytes(b'bad')
        self.assertIn('float32-aligned', (await ws.receive_json())["error"])
        await ws.close()

    async def test_missing_model_dependencies_leave_server_usable(self):
        def fail():
            raise RuntimeError('dependencies missing')
        self.handler.model.load = fail
        ws = await self.client.ws_connect('/sound-ws')
        await ws.send_json({"type": "start", "sampleRate": 48000})
        await ws.receive_json()
        self.assertEqual((await ws.receive_json())["error"], 'dependencies missing')
        await ws.close()
        self.handler.model = FakeModel()
        again = await self.connect()
        await again.close()


if __name__ == '__main__':
    unittest.main()
