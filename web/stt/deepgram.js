// Deepgram live streaming: words arrive while the person is still talking, each with
// a timestamp and (with diarize) a voice-based speaker label.
import { registerProvider, fetchToken } from './provider.js';

const PARAMS = new URLSearchParams({
  model: 'nova-3',
  language: 'en',
  interim_results: 'true',
  smart_format: 'true',
  diarize: 'true',
  endpointing: '300',
});
const MIME = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];

function create({ onTranscript, onStatus }) {
  let ws = null, recorder = null, stream = null, t0 = 0, stopped = false, retryTimer = null;
  let bytesSent = 0;
  let useKey = false; // set if a short-lived token is refused, so the retry uses the API key instead

  async function connect() {
    if (stopped) return;
    onStatus('getting token');
    let token;
    try {
      token = await fetchToken('deepgram', useKey ? { scheme: 'token' } : {});
    } catch (e) {
      onStatus(`token error: ${e.message}`);
      return retry(3000);
    }
    onStatus('connecting');
    // Browsers can't set an Authorization header on a WebSocket; Deepgram accepts the
    // credential as a sub-protocol pair instead: ['bearer', <jwt>] or ['token', <api key>].
    const sock = new WebSocket(`wss://api.deepgram.com/v1/listen?${PARAMS}`, [token.scheme, token.credential]);
    ws = sock;
    let opened = false;
    sock.onopen = () => { opened = true; startRecorder(); };
    sock.onmessage = (m) => handle(JSON.parse(m.data));
    sock.onerror = () => onStatus('connection error');
    sock.onclose = (e) => {
      if (sock !== ws) return; // a stale socket; a newer connection owns the recorder now
      stopRecorder();
      if (!opened && token.scheme === 'bearer') useKey = true;
      if (stopped) return;
      // Deepgram says why it hung up in the close reason (e.g. no audio received, bad audio data).
      onStatus(`disconnected (${e.code} ${e.reason || 'no reason given'}) after sending ${bytesSent} bytes, retrying`);
      retry(1000);
    };
  }

  function retry(ms) {
    clearTimeout(retryTimer);
    retryTimer = setTimeout(connect, ms);
  }

  function startRecorder() {
    const track = stream.getAudioTracks()[0];
    if (!track || track.readyState !== 'live') {
      // Recording a dead track throws, and Deepgram would hang up for lack of audio anyway.
      // The app watches for this and reopens the microphone.
      onStatus('microphone track has ended');
      return;
    }
    // A fresh recorder per connection: the stream must begin with the container header.
    const mimeType = MIME.find((m) => MediaRecorder.isTypeSupported(m));
    bytesSent = 0;
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = (e) => {
        if (e.data.size && ws && ws.readyState === WebSocket.OPEN) { ws.send(e.data); bytesSent += e.data.size; }
      };
      recorder.onerror = (e) => onStatus(`recorder error: ${e.error && e.error.name}`);
      recorder.start(250);
    } catch (e) {
      onStatus(`could not record from the microphone: ${e.message}`);
      return;
    }
    t0 = performance.now(); // Deepgram's timestamps count from the first audio byte
    onStatus(`listening (${mimeType || 'default format'})`);
  }

  function stopRecorder() {
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    recorder = null;
  }

  function handle(msg) {
    if (msg.type !== 'Results') return;
    const alt = msg.channel && msg.channel.alternatives && msg.channel.alternatives[0];
    if (!alt || !alt.transcript) return;
    onTranscript({
      text: alt.transcript,
      isFinal: !!msg.is_final,
      startMs: t0 + msg.start * 1000,
      endMs: t0 + (msg.start + msg.duration) * 1000,
      words: (alt.words || []).map((w) => ({
        text: w.punctuated_word || w.word,
        startMs: t0 + w.start * 1000,
        endMs: t0 + w.end * 1000,
        speaker: w.speaker,
      })),
    });
  }

  return {
    needsMic: true,
    async start(micStream) { stream = micStream; stopped = false; await connect(); },
    stop() {
      stopped = true;
      clearTimeout(retryTimer);
      stopRecorder();
      if (ws) {
        try { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'CloseStream' })); } catch {}
        ws.close();
        ws = null;
      }
      onStatus('stopped');
    },
  };
}

registerProvider('deepgram', 'Deepgram (live, word-by-word)', create);
