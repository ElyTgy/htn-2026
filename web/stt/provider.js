// Transcription providers are interchangeable. To try a different API:
//   1. add web/stt/<name>.js that calls registerProvider() (see speechmatics.js)
//   2. import it in web/app.js
//   3. if it needs a secret, add a token handler in pi/server.py (TOKEN_HANDLERS)
// then pick it in Settings or with ?stt=<name>.
//
// A provider is created with { onTranscript, onStatus } and must implement:
// Optional callback onSessionStart() resets learned voice labels on each new audio session.
//   needsMic            must be true; non-microphone/scripted providers are rejected
//   async start(stream) begin transcribing the verified-live MediaStream
//   stop()              stop and release everything
//
// It reports text by calling onTranscript(event) with ONE normalised shape:
//   {
//     text:     string   the whole segment so far
//     isFinal:  boolean  false = interim, will be replaced by the next event
//     startMs:  number   when the segment's audio started, on the page clock (performance.now())
//     endMs:    number   when it ended
//     words?:   [{ text, startMs, endMs, speaker? }]   optional, enables per-word timing
//   }                                                   and voice labels (speaker = any stable id)
// Providers that only give phrase-level text just omit `words`; attribution then uses
// startMs/endMs for the whole phrase and skips voice labels.
//
// onStatus(text) is a short human-readable state for the debug HUD.

const registry = new Map();

export function registerProvider(name, label, factory) {
  registry.set(name, { label, factory });
}

export function listProviders() {
  return [...registry].map(([name, { label }]) => ({ name, label }));
}

export function createProvider(name, callbacks) {
  const entry = registry.get(name);
  if (!entry) throw new Error(`unknown transcription provider "${name}"`);
  const provider = entry.factory(callbacks);
  if (provider.needsMic !== true) {
    throw new Error(`transcription provider "${name}" is not live-microphone-backed`);
  }
  return provider;
}

// Shared helper for providers that fetch credentials from the Pi.
export async function fetchToken(provider, extra = {}) {
  const r = await fetch(`/stt-token?${new URLSearchParams({ provider, ...extra })}`, { cache: 'no-store' });
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || `token request failed (${r.status})`);
  return body;
}
