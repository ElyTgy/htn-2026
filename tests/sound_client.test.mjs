import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function harness() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      value: '', textContent: '', disabled: false, listeners: {},
      addEventListener(name, fn) { this.listeners[name] = fn; },
      replaceChildren() {}, add() {},
    });
    return elements.get(id);
  };
  const speech = { stopped: false, getSettings: () => ({ deviceId: 'phone' }), addEventListener() {} };
  const glasses = {
    label: 'XREAL USB', stopped: false,
    getSettings: () => ({ deviceId: 'glasses' }),
    addEventListener() {}, stop() { this.stopped = true; },
  };
  const stream = { getTracks: () => [glasses], getAudioTracks: () => [glasses] };
  const calls = [], sockets = [], nodes = [];
  class Socket {
    static OPEN = 1;
    constructor() { this.readyState = 1; this.bufferedAmount = 0; this.sent = []; sockets.push(this); }
    send(data) { this.sent.push(data); }
    close() { this.onclose?.(); }
    message(msg) { this.onmessage({ data: JSON.stringify(msg) }); }
  }
  class Context {
    constructor() { this.sampleRate = 16000; this.audioWorklet = { addModule: async () => {} }; }
    async resume() {}
    async close() {}
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  }
  class Node {
    constructor() { this.port = {}; nodes.push(this); }
    connect() {} disconnect() {}
  }
  const context = vm.createContext({
    document: { getElementById: element },
    navigator: { mediaDevices: { getUserMedia: async constraints => { calls.push(constraints); return stream; } } },
    location: { protocol: 'https:', host: 'jetson:8443', hostname: 'jetson', search: '?soundPort=8444' },
    URLSearchParams,
    AudioContext: Context, AudioWorkletNode: Node, WebSocket: Socket,
    addEventListener() {}, setTimeout: () => 1, clearTimeout() {},
    fetch: async () => ({ ok: true }),
    Float32Array, ArrayBuffer, DataView,
  });
  vm.runInContext(readFileSync(new URL('../web/sound.js', import.meta.url), 'utf8').replace('export function', 'function'), context);
  const controls = context.bindSoundUi({ speechTrack: () => speech });
  return { element, calls, sockets, nodes, glasses, speech, controls,
    click: id => element(id).listeners.click() };
}

test('requires an explicit independent microphone and never falls back to default', async () => {
  const h = harness();
  await h.click('sound-start');
  assert.match(h.element('sound-status').textContent, /choose an input/);
  h.element('sound-mic').value = 'phone';
  await h.click('sound-start');
  assert.match(h.element('sound-status').textContent, /already used for speech/);
  assert.equal(h.calls.length, 0);
});

test('uploads chosen mic PCM only after ready, bounds backlog, and releases only its own input', async () => {
  const h = harness();
  h.element('sound-mic').value = 'glasses';
  await h.click('sound-start');
  assert.equal(h.calls[0].audio.deviceId.exact, 'glasses');
  assert.equal(h.calls[0].audio.noiseSuppression, false);
  const ws = h.sockets[0], node = h.nodes[0];
  ws.onopen();
  assert.equal(JSON.parse(ws.sent[0]).sampleRate, 16000);
  const audio = new Float32Array(16000).fill(.25).buffer;
  node.port.onmessage({ data: audio });
  assert.equal(ws.sent.length, 1);
  ws.message({ type: 'ready' });
  node.port.onmessage({ data: audio });
  assert.equal(ws.sent[1].byteLength, 64000);
  assert.equal(new DataView(ws.sent[1]).getFloat32(0, true), .25);
  node.port.onmessage({ data: audio });
  assert.equal(ws.sent.length, 2);
  ws.message({ type: 'sound-event', event: {
    id: 'vehicle-horn', label: 'Vehicle horn', emoji: '🚗', urgency: 'urgent',
  } });
  assert.equal(h.element('sound-results').textContent, '🚗  [car honking]');
  assert.equal(h.element('sound-results').className, 'sound-card urgent');
  h.controls.speechChanging();
  assert.equal(h.glasses.stopped, true);
  assert.equal(h.speech.stopped, false);
  assert.equal(h.element('sound-results').textContent, '');
});

test('shares speech stream without stopping it and connects to configured classifier port', async () => {
  const h = harness();
  const speechStream = { getTracks: () => [h.speech], getAudioTracks: () => [h.speech] };
  await h.controls.startWithSpeech(speechStream);
  assert.equal(h.calls.length, 0);
  assert.equal(h.sockets.length, 1);
  h.controls.speechChanging();
  assert.equal(h.speech.stopped, false);
});
