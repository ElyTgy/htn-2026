import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { normalizeTranscript } from '../web/stt/speechmatics.js';
import { createProvider } from '../web/stt/provider.js';
import { Attributor } from '../web/attribution.js';

const word = (content, speaker, start, end) => ({
  type: 'word', start_time: start, end_time: end,
  alternatives: [{ content, speaker }],
});

test('word clocks, punctuation and speaker changes survive normalization', () => {
  const event = normalizeTranscript({
    message: 'AddTranscript', metadata: { transcript: 'Hello. Hi there', start_time: 0.1, end_time: 1.4 },
    results: [word('Hello', 'S1', 0.1, 0.5),
      { type: 'punctuation', alternatives: [{ content: '.' }] },
      word('Hi', 'S2', 0.7, 1), word('there', 'UU', 1.1, 1.4)],
  }, 1000);
  assert.equal(event.isFinal, true);
  assert.equal(event.startMs, 1100);
  assert.equal(event.endMs, 2400);
  assert.deepEqual(new Attributor().splitRuns(event), [
    { text: 'Hello.', startMs: 1100, endMs: 1500, speaker: 'S1' },
    { text: 'Hi', startMs: 1700, endMs: 2000, speaker: 'S2' },
    { text: 'there', startMs: 2100, endMs: 2400, speaker: undefined },
  ]);
});

test('empty partials clear provisional captions and control messages are ignored', () => {
  assert.equal(normalizeTranscript({ message: 'AudioAdded' }, 100), null);
  const event = normalizeTranscript({ message: 'AddPartialTranscript', results: [] }, 100);
  assert.equal(event.text, '');
  assert.equal(event.isFinal, false);
});

test('worklet batches audio and averages channels without audible output', () => {
  let Processor;
  const packets = [];
  vm.runInNewContext(readFileSync(new URL('../web/stt/pcm-worklet.js', import.meta.url), 'utf8'), {
    sampleRate: 48000,
    AudioWorkletProcessor: class { port = { postMessage: buffer => packets.push(new Float32Array(buffer)) }; },
    registerProcessor: (_, cls) => { Processor = cls; },
    Float32Array,
  });
  const processor = new Processor();
  for (let i = 0; i < 30; i++) processor.process([[new Float32Array(128).fill(1), new Float32Array(128).fill(-0.5)]]);
  assert.equal(packets.length, 2);
  assert.equal(packets[0].length, 1920);
  assert.ok(packets.every(packet => packet.every(sample => sample === 0.25)));
});

test('provider waits for recognition, sends PCM, and cleans up on disconnect', async t => {
  let socket, node, closed = false, sessions = 0;
  const events = [], statuses = [];
  class Socket {
    static OPEN = 1;
    readyState = 1;
    bufferedAmount = 0;
    sent = [];
    constructor(url) { socket = this; assert.ok(String(url).includes('jwt=temporary')); }
    send(data) { this.sent.push(data); }
    close() { this.readyState = 3; }
  }
  class Context {
    sampleRate = 48000;
    audioWorklet = { addModule: async () => {} };
    async resume() {}
    async close() { closed = true; }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  }
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => ({ credential: 'temporary' }) }));
  const previous = Object.fromEntries(['WebSocket', 'AudioContext', 'AudioWorkletNode'].map(k => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
  t.after(() => {
    for (const [k, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, k, descriptor);
      else delete globalThis[k];
    }
  });
  globalThis.WebSocket = Socket;
  globalThis.AudioContext = Context;
  globalThis.AudioWorkletNode = class {
    port = {};
    constructor() { node = this; }
    connect() {}
    disconnect() {}
  };
  const provider = createProvider('speechmatics', {
    onTranscript: e => events.push(e), onStatus: s => statuses.push(s), onSessionStart: () => sessions++,
  });
  t.after(() => provider.stop());
  const liveStream = { getAudioTracks: () => [{ readyState: 'live' }] };
  const starting = provider.start(liveStream);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(node, undefined);
  socket.onopen();
  const config = JSON.parse(socket.sent[0]);
  assert.equal(config.transcription_config.operating_point, 'enhanced');
  assert.equal('model' in config.transcription_config, false);
  assert.equal(config.transcription_config.diarization, 'speaker');
  assert.equal(config.audio_format.sample_rate, 48000);
  socket.onmessage({ data: JSON.stringify({ message: 'RecognitionStarted' }) });
  await starting;
  assert.equal(sessions, 1);
  node.port.onmessage({ data: new Float32Array(1920).buffer });
  assert.equal(socket.sent[1].byteLength, 7680);
  socket.onmessage({ data: JSON.stringify({ message: 'AddPartialTranscript', results: [word('hello', 'S1', 0, 0.04)] }) });
  assert.equal(events[0].text, 'hello');
  socket.onclose();
  assert.ok(closed);
  assert.equal(node.port.onmessage, null);
  assert.match(statuses.at(-1), /disconnected/);

  // A missing server credential must reject startup and release the audio context.
  closed = false;
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: false, json: async () => ({ error: 'SPEECHMATICS_API_KEY is not set' }),
  }));
  const failing = createProvider('speechmatics', { onTranscript() {}, onStatus() {} });
  await assert.rejects(failing.start(liveStream), /SPEECHMATICS_API_KEY/);
  assert.ok(closed);
});
