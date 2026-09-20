// Run with: node --test tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import { Attributor } from '../web/attribution.js';

const LAT = 50;

test('provisional text can use lip evidence without training voice mappings', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  feed(a, 0, 1000, { 1: 0.8 });
  for (let i = 0; i < 10; i++) {
    assert.equal(a.attribute(100, 900, 'S1', false).faceId, 1);
  }
  assert.equal(a.votes.size, 0);
  a.attribute(100, 900, 'S1', true);
  assert.equal(a.votes.get('S1').get(1), 1);
});

test('provisional off-camera text does not learn an unknown speaker as the wearer', () => {
  const a = new Attributor();
  a.attribute(0, 100, 'S1', false);
  assert.equal(a.votes.size, 0);
});

// Feed frames every 66 ms over [from, to] (audio time); scores = { faceId: score }.
function feed(a, from, to, scores) {
  for (let t = from; t <= to; t += 66) {
    a.addFrame(t + LAT, Object.entries(scores).map(([id, score]) => ({ id: Number(id), score })));
  }
}

test('clear lip movement wins', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  feed(a, 0, 1000, { 1: 0.8, 2: 0.05 });
  assert.deepEqual(a.attribute(100, 900), { faceId: 1, how: 'lips' });
});

test('weak lip evidence still attaches to the best visible face', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  feed(a, 0, 1000, { 1: 0.03, 2: 0.05 });
  assert.deepEqual(a.attribute(100, 900), { faceId: 2, how: 'best-visible' });
});

test('two nearly equal mouths still produce a deterministic visible-face assignment', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  feed(a, 0, 1000, { 1: 0.50, 2: 0.49 });
  assert.deepEqual(a.attribute(100, 900), { faceId: 1, how: 'best-visible' });
});

test('attribution uses the lips at the time the words were spoken, not when text arrives', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  feed(a, 0, 1000, { 1: 0.8, 2: 0.0 });
  feed(a, 1066, 2000, { 1: 0.0, 2: 0.8 }); // by the time the text shows up, face 2 is talking
  assert.equal(a.attribute(100, 900).faceId, 1);
});

test('voice label learns its face, then decides when lips are hidden', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  let t = 0;
  for (let i = 0; i < 4; i++) { // speaker "A" is clearly face 1, four times
    feed(a, t, t + 800, { 1: 0.8, 2: 0.0 });
    assert.equal(a.attribute(t, t + 800, 'A').how, 'lips');
    t += 1000;
  }
  assert.equal(a.boundFace('A'), 1);
  // Face 1 turns away (still tracked, mouth not visible); face 2 fidgets a little.
  feed(a, t, t + 800, { 1: 0.05, 2: 0.3 });
  assert.deepEqual(a.attribute(t, t + 800, 'A'), { faceId: 1, how: 'voice' });
});

test('quiet speech is still attached to the sole visible face', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  let t = 0;
  for (let i = 0; i < 4; i++) {
    feed(a, t, t + 800, { 1: 0.02 });
    a.attribute(t, t + 800, 'me');
    t += 1000;
  }
  assert.equal(a.boundFace('me'), 1);
  feed(a, t, t + 800, { 1: 0.3 }); // weak lip movement from the listener (nodding, "mm-hm")
  assert.equal(a.attribute(t, t + 800, 'me').faceId, 1);
});

test('sustained clear lip evidence can correct a mistaken voice label', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  let t = 0;
  for (let i = 0; i < 4; i++) { feed(a, t, t + 800, { 1: 0.8, 2: 0 }); a.attribute(t, t + 800, 'A'); t += 1000; }
  feed(a, t, t + 800, { 1: 0.0, 2: 0.9 }); // diarization mislabels face 2's speech as "A"
  assert.deepEqual(a.attribute(t, t + 800, 'A'), { faceId: 2, how: 'lips' });
});

test('known voice whose face has left the view is dropped, never shown globally', () => {
  const a = new Attributor({ visionLatencyMs: LAT });
  let t = 0;
  for (let i = 0; i < 4; i++) { feed(a, t, t + 800, { 1: 0.8, 2: 0 }); a.attribute(t, t + 800, 'A'); t += 1000; }
  feed(a, t, t + 800, { 2: 0.3 }); // face 1 gone
  assert.deepEqual(a.attribute(t, t + 800, 'A'), { faceId: null, how: 'voice' });
});

test('splitRuns: by voice label with words, single run without', () => {
  const a = new Attributor();
  const w = (text, s, speaker) => ({ text, startMs: s, endMs: s + 100, speaker });
  const runs = a.splitRuns({ text: 'hi there oh hello', startMs: 0, endMs: 400,
    words: [w('hi', 0, 0), w('there', 100, 0), w('oh', 200, 1), w('hello', 300, 1)] });
  assert.deepEqual(runs.map((r) => [r.text, r.speaker, r.startMs, r.endMs]),
    [['hi there', 0, 0, 200], ['oh hello', 1, 200, 400]]);
  const phrase = a.splitRuns({ text: 'whole phrase', startMs: 5, endMs: 900 });
  assert.deepEqual(phrase, [{ text: 'whole phrase', startMs: 5, endMs: 900, speaker: undefined }]);
});

test('strong new lip evidence corrects a learned voice within 300 ms', () => {
  const a = new Attributor();
  for (let t = 0; t < 3000; t += 1000) {
    feed(a, t, t + 800, { 1: 0.8, 2: 0 });
    a.attribute(t, t + 800, 'S1');
  }
  // A diarization label can lag a turn change; strong current lips win quickly.
  feed(a, 3000, 3300, { 1: 0.01, 2: 0.9 });
  assert.deepEqual(a.attribute(3000, 3300, 'S1'), { faceId: 2, how: 'lips' });
});

test('a new short voice does not bind to a face already associated with another voice', () => {
  const a = new Attributor();
  for (let t = 0; t < 3000; t += 1000) {
    feed(a, t, t + 800, { 1: 0.8, 2: 0 });
    a.attribute(t, t + 800, 'S1');
  }
  feed(a, 3000, 3300, { 1: 0.8, 2: 0.2 });
  assert.equal(a.attribute(3000, 3300, 'S2').faceId, 1);
  assert.equal(a.votes.get('S2').get(1), 1);
});

test('missing historical frames cannot attribute old words to the current speaker', () => {
  const a = new Attributor();
  feed(a, 5000, 6000, { 2: 0.9 });
  assert.deepEqual(a.attribute(0, 500, 'S1'), { faceId: null, how: 'offscreen' });
  assert.equal(a.votes.size, 0);
});

test('the same finalized interval cannot repeatedly train a voice binding', () => {
  const a = new Attributor();
  feed(a, 0, 1000, { 1: 0.8 });
  for (let i = 0; i < 10; i++) a.attribute(0, 800, 'S1');
  assert.equal(a.boundFace('S1'), null);
  assert.equal(a.votes.get('S1').get(1), 1);
});
