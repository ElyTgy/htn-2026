import { registerProvider, fetchToken } from './provider.js';

export const TRANSCRIPTION_CONFIG = {
  language: 'en', operating_point: 'enhanced', diarization: 'speaker',
  enable_partials: true, max_delay: 0.7, max_delay_mode: 'fixed',
};

// Normalize punctuation and unknown speakers before the shared attribution code sees them.
export function normalizeTranscript(msg, t0, receivedAt = performance.now()) {
  if (!['AddTranscript', 'AddPartialTranscript'].includes(msg.message)) return null;
  const words = [];
  for (const result of msg.results || []) {
    const alt = result.alternatives?.[0];
    if (!alt) continue;
    if (result.type === 'punctuation') {
      if (words.length) words[words.length - 1].text += alt.content;
    } else if (result.type === 'word') {
      words.push({
        text: alt.content,
        startMs: t0 + result.start_time * 1000,
        endMs: t0 + result.end_time * 1000,
        speaker: alt.speaker === 'UU' ? undefined : alt.speaker,
      });
    }
  }
  // Speechmatics partials do not consistently include metadata start/end times. Falling back
  // to zero made every partial look older as the session continued, until the UI discarded all
  // captions. Word timings are authoritative; only an empty partial uses its arrival time.
  const timedStart = words.length ? words[0].startMs : receivedAt;
  const timedEnd = words.length ? words[words.length - 1].endMs : receivedAt;
  return {
    text: msg.metadata?.transcript || words.map(w => w.text).join(' '),
    isFinal: msg.message === 'AddTranscript',
    startMs: msg.metadata?.start_time == null ? timedStart : t0 + msg.metadata.start_time * 1000,
    endMs: msg.metadata?.end_time == null ? timedEnd : t0 + msg.metadata.end_time * 1000,
    words,
  };
}

function create({ onTranscript, onStatus, onSessionStart = () => {} }) {
  let ctx, source, node, ws, timer, cancelStart;
  let stopped = true, ready = false, t0 = null;

  function stop() {
    stopped = true;
    ready = false;
    clearTimeout(timer);
    cancelStart?.(new Error('Transcription stopped'));
    cancelStart = null;
    if (node) { node.port.onmessage = null; node.disconnect(); node = null; }
    if (source) { source.disconnect(); source = null; }
    if (ctx) { ctx.close().catch(() => {}); ctx = null; }
    if (ws) { ws.onclose = null; ws.close(); ws = null; }
  }

  return {
    needsMic: true,
    async start(stream) {
      const track = stream?.getAudioTracks?.()[0];
      if (!track || track.readyState !== 'live') throw new Error('no live microphone track');
      stopped = false;
      t0 = null;
      try {
        ctx = new AudioContext();
        if (!ctx.audioWorklet) throw new Error('AudioWorklet requires HTTPS or localhost');
        await ctx.resume();
        await ctx.audioWorklet.addModule(new URL('./pcm-worklet.js', import.meta.url));
        if (stopped) return;
        onStatus('getting token');
        const token = await fetchToken('speechmatics');
        if (stopped) return;
        onStatus('connecting');
        const url = new URL('wss://global.rt.speechmatics.com/v2/');
        url.searchParams.set('jwt', token.credential);
        ws = new WebSocket(url);
        await new Promise((resolve, reject) => {
          cancelStart = reject;
          timer = setTimeout(() => reject(new Error('Speechmatics connection timed out')), 15000);
          ws.onopen = () => ws.send(JSON.stringify({
            message: 'StartRecognition',
            audio_format: { type: 'raw', encoding: 'pcm_f32le', sample_rate: ctx.sampleRate },
            transcription_config: TRANSCRIPTION_CONFIG,
          }));
          ws.onmessage = ({ data }) => {
            if (stopped) return;
            try {
              const msg = JSON.parse(data);
              if (msg.message === 'RecognitionStarted') {
                onSessionStart();
                ready = true;
                clearTimeout(timer);
                cancelStart = null;
                onStatus('listening (Enhanced, diarization, 40 ms PCM)');
                resolve();
              } else if (msg.message === 'Error') {
                throw new Error(`Speechmatics ${msg.type}: ${msg.reason || 'request failed'}`);
              } else if (t0 !== null) {
                const event = normalizeTranscript(msg, t0, performance.now());
                if (event) onTranscript(event);
              }
            } catch (e) {
              reject(e);
              stop();
              onStatus(`${e.message}; switch providers to reconnect`);
            }
          };
          ws.onerror = () => {
            reject(new Error('Could not connect to Speechmatics'));
            stop();
            onStatus('connection error; switch providers to reconnect');
          };
          ws.onclose = () => {
            reject(new Error('Speechmatics disconnected'));
            stop();
            onStatus('disconnected; switch providers to reconnect');
          };
        });
        if (stopped) return;
        source = ctx.createMediaStreamSource(stream);
        node = new AudioWorkletNode(ctx, 'caption-pcm', { channelCount: 1 });
        node.port.onmessage = ({ data }) => {
          if (!ready || !ws || ws.readyState !== WebSocket.OPEN) return;
          // Bound queueing delay instead of allowing stale captions to accumulate.
          if (ws.bufferedAmount > ctx.sampleRate * 4) {
            stop();
            onStatus('audio upload stalled; switch providers to reconnect');
            return;
          }
          if (t0 === null) t0 = performance.now() - data.byteLength / 4 / ctx.sampleRate * 1000;
          ws.send(data);
        };
        source.connect(node);
        node.connect(ctx.destination); // worklet output remains silent
      } catch (e) {
        stop();
        throw e;
      }
    },
    stop,
  };
}

registerProvider('speechmatics', 'Speechmatics Enhanced (live + speakers)', create);
