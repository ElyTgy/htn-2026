import test from 'node:test';
import assert from 'node:assert/strict';
import { CaptionBuffer, captionLines, smoothAnchor } from '../web/captions.js';

const word = (text, startMs, endMs) => ({ text, startMs, endMs });
const run = (faceId, words) => ({ faceId, words, text: words.map(w => w.text).join(' '),
  startMs: words[0].startMs, endMs: words.at(-1).endMs });

test('finalizing a prefix preserves remaining interim words without duplication', () => {
  const buffer = new CaptionBuffer();
  const hello = word('hello', 0, 300), there = word('there', 300, 600);
  buffer.update({ isFinal: false }, [run(1, [hello, there])], 1000);
  buffer.update({ isFinal: true, endMs: 300 }, [run(1, [hello])], 1100);
  assert.equal(buffer.textFor(1), 'hello there');
  buffer.update({ isFinal: false }, [run(1, [there])], 1200);
  assert.equal(buffer.textFor(1), 'hello there');
  buffer.update({ isFinal: true, endMs: 600 }, [run(1, [there])], 1300);
  assert.equal(buffer.textFor(1), 'hello there');
  assert.equal(buffer.partial.length, 0);
});

test('a finalized speaker correction removes old provisional placement', () => {
  const buffer = new CaptionBuffer();
  const words = [word('my turn', 0, 300)];
  buffer.update({ isFinal: false }, [run(1, words)], 1000);
  buffer.update({ isFinal: true, endMs: 300 }, [run(2, words)], 1100);
  assert.equal(buffer.textFor(1), '');
  assert.equal(buffer.textFor(2), 'my turn');
});

test('a final from one speaker does not erase another speaker’s unfinished words', () => {
  const buffer = new CaptionBuffer();
  const first = run(1, [word('yes', 0, 300)]), next = run(2, [word('and', 350, 500)]);
  buffer.update({ isFinal: false }, [first, next], 1000);
  buffer.update({ isFinal: true, endMs: 300 }, [first], 1100);
  assert.equal(buffer.textFor(1), 'yes');
  assert.equal(buffer.textFor(2), 'and');
});

test('old text resets after a pause and duplicate finals do not append twice', () => {
  const buffer = new CaptionBuffer();
  const first = run(1, [word('first', 0, 300)]);
  buffer.update({ isFinal: true, endMs: 300 }, [first], 1000);
  buffer.update({ isFinal: true, endMs: 300 }, [first], 1100);
  assert.equal(buffer.textFor(1), 'first');
  buffer.update({ isFinal: true, endMs: 5400 }, [run(1, [word('next', 5000, 5400)])], 6000);
  assert.equal(buffer.textFor(1), 'next');
});

test('appending text leaves existing line breaks stable and rolls whole lines', () => {
  const measure = text => text.length;
  assert.equal(captionLines('one two three', 10, measure), 'one two\nthree');
  assert.equal(captionLines('one two three four', 10, measure), 'one two\nthree four');
  assert.equal(captionLines('one two three four five', 10, measure), 'three four\nfive');
});

test('small camera movements leave the anchor still, larger ones follow smoothly', () => {
  const anchor = { x: 100, y: 100 };
  assert.deepEqual(smoothAnchor(anchor, 104, 102, 16), anchor);
  const following = smoothAnchor(anchor, 160, 100, 16);
  assert.ok(following.x > 100 && following.x < 110);
  assert.equal(following.y, 100);
});

test('long conversations can drop old lines without shifting visible words', () => {
  const buffer = new CaptionBuffer();
  const text = 'one two three four five six seven eight '.repeat(100);
  buffer.update({ isFinal: true, endMs: 500 }, [run(1, [word(text, 0, 500)])], 1000);
  const measure = text => text.length;
  const before = captionLines(buffer.textFor(1), 20, measure);
  buffer.compact(1, 20, measure);
  assert.equal(captionLines(buffer.textFor(1), 20, measure), before);
  assert.ok(buffer.textFor(1).length < 200);
});
