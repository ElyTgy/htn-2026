// Microphone-only smoke test (?stt=mic-test).
//
// This intentionally does not send audio anywhere or create captions. The normal
// app microphone monitor still opens the selected browser microphone, draws its
// live level in the debug HUD, and logs a five-second peak to the Jetson server.
// It lets camera + microphone setup be tested without an STT API key.
import { registerProvider } from './provider.js';

function create({ onStatus }) {
  return {
    needsMic: true,

    async start(stream) {
      const track = stream?.getAudioTracks?.()[0];
      if (!track || track.readyState !== 'live') {
        throw new Error('no live microphone track');
      }
      onStatus('mic test running — speak and watch the mic meter');
    },

    stop() {
      onStatus('stopped');
    },
  };
}

registerProvider('mic-test', 'Microphone test (no API key)', create);
