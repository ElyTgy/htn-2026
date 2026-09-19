// Scripted transcript for testing with no microphone or API key (?stt=mock).
// Emits word-by-word interims then a final, like a live provider would, with no
// speaker labels, so it also exercises the "phrase-level provider" code path when
// ?mockphrases=1 is set (final phrases only, no words array).
import { registerProvider } from './provider.js';

const PHRASES = [
  'So I was thinking we could test the captions like this.',
  'That sounds good, can you see the text above my head?',
  'Yes, it follows you when you move around.',
  'Nice. What happens when nobody on screen is talking?',
  'Then it should drop down into the bar at the bottom.',
];

function create({ onTranscript, onStatus }) {
  let timer = null, phrase = 0, word = 0, startMs = 0, words = [];
  const phraseOnly = new URLSearchParams(location.search).has('mockphrases');

  function tick() {
    const all = PHRASES[phrase % PHRASES.length].split(' ');
    const now = performance.now();
    if (word === 0) { startMs = now - 250; words = []; }
    words.push({ text: all[word], startMs: now - 250, endMs: now });
    word++;
    const done = word >= all.length;
    if (!phraseOnly || done) {
      onTranscript({
        text: words.map((w) => w.text).join(' '),
        isFinal: done,
        startMs,
        endMs: now,
        ...(phraseOnly ? {} : { words: words.slice() }),
      });
    }
    if (done) { word = 0; phrase++; }
    timer = setTimeout(tick, done ? 1200 : 280);
  }

  return {
    needsMic: false,
    async start() { onStatus('mock running'); tick(); },
    stop() { clearTimeout(timer); onStatus('stopped'); },
  };
}

registerProvider('mock', 'Mock (scripted, no mic)', create);
