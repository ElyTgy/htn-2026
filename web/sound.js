// Independent browser input -> Jetson TF Hub YAMNet. Never changes the speech input.
export function bindSoundUi({ speechTrack = () => null } = {}) {
  const $ = id => document.getElementById(id);
  const select = $('sound-mic');
  const status = $('sound-status');
  const results = $('sound-results');
  let session = null;
  let busy = false;

  function socketUrl() {
    const configuredPort = new URLSearchParams(location.search).get('soundPort');
    const host = configuredPort ? `${location.hostname}:${configuredPort}` : location.host;
    return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${host}/sound-ws`;
  }

  const subtitleLabels = {
    'fire-alarm': 'fire alarm ringing',
    siren: 'siren wailing',
    'vehicle-horn': 'car honking',
    'breaking-glass': 'glass breaking',
    doorbell: 'doorbell ringing',
    knocking: 'knocking',
    'phone-ringing': 'phone ringing',
    'baby-crying': 'baby crying',
    shouting: 'someone shouting',
    'dog-barking': 'dogs barking',
    'vehicle-nearby': 'vehicle nearby',
    'running-water': 'water running',
  };

  function say(message) {
    status.textContent = message;
    const endpoint = location.port === '8444' ? '/client-log' : '/log';
    fetch(endpoint, { method: 'POST', body: `sound: ${message}` }).catch(() => {});
  }

  function stop(message = 'Sound classification stopped.') {
    const old = session;
    session = null;
    if (old) {
      if (old.ownsStream) old.stream?.getTracks().forEach(t => t.stop());
      old.node?.disconnect();
      old.source?.disconnect();
      old.ctx?.close().catch(() => {});
      old.ws?.close();
    }
    results.textContent = '';
    results.className = '';
    say(message);
    $('sound-stop').disabled = true;
  }

  async function refresh() {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone access needs HTTPS or localhost.');
    // Request permission only when no speech input is already open.
    if (!speechTrack()) {
      const permission = await navigator.mediaDevices.getUserMedia({ audio: true });
      permission.getTracks().forEach(t => t.stop());
    }
    const exposed = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'audioinput');
    // Some Android builds expose labels such as "USB audio" but give those rows no deviceId.
    // They cannot be passed back to getUserMedia; Android's "default" route is the only usable
    // handle and follows the currently connected USB headset/glasses.
    const devices = exposed.filter(d => d.deviceId);
    const previous = select.value;
    select.replaceChildren(new Option('Choose the XREAL / USB microphone', ''));
    for (const d of devices) {
      const routedDefault = d.deviceId === 'default' || d.label.toLowerCase() === 'default';
      const label = routedDefault ? 'Default (Android route; XREAL while connected)' : (d.label || 'Unnamed microphone');
      select.add(new Option(label, d.deviceId));
    }
    if (devices.some(d => d.deviceId === previous)) select.value = previous;
    const unusable = exposed.filter(d => !d.deviceId).map(d => d.label || '(unnamed)');
    const labels = devices.map(d => d.label || '(unnamed)').join(', ');
    say(`${devices.length} usable input(s): ${labels || 'none'}.` +
      (unusable.length ? ` Android also named ${unusable.join(', ')}, but supplied no selectable device ID.` : '') +
      ' With XREAL connected, use Default and verify routing by comparing sound near the glasses versus the phone.');
  }

  async function start(sharedStream = null) {
    if (!sharedStream && !select.value) throw new Error('Check microphones and choose an input first.');
    if (!sharedStream && select.value === speechTrack()?.getSettings().deviceId) {
      throw new Error('That input is already used for speech. Select the separate glasses microphone.');
    }
    stop('Opening the selected microphone…');
    const s = { ready: false };
    session = s;
    $('sound-stop').disabled = false;
    // Create/resume from the tap, before asynchronous microphone permission.
    s.ctx = new AudioContext();
    await s.ctx.resume();
    if (session !== s) return;
    const stream = sharedStream || await navigator.mediaDevices.getUserMedia({ audio: {
        deviceId: { exact: select.value }, channelCount: 1,
        echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      } });
    if (session !== s) { stream.getTracks().forEach(t => t.stop()); return; }
    s.stream = stream;
    s.ownsStream = !sharedStream;
    const track = stream.getAudioTracks()[0];
    say(`${sharedStream ? 'Sharing speech input' : 'Opened input'} “${track.label || 'unnamed input'}”; connecting to YAMNet…`);
    if (!sharedStream && track.getSettings().deviceId === speechTrack()?.getSettings().deviceId) {
      throw new Error('The phone selected the speech input again; separate capture is unavailable.');
    }
    track.addEventListener('ended', () => { if (session === s) stop('Glasses microphone disconnected.'); });
    track.addEventListener('mute', () => { if (session === s) stop('Phone muted the glasses input. Check whether simultaneous capture is supported.'); });
    await s.ctx.audioWorklet.addModule('/stt/pcm-worklet.js');
    if (session !== s) return;
    s.source = s.ctx.createMediaStreamSource(stream);
    s.node = new AudioWorkletNode(s.ctx, 'caption-pcm', { channelCount: 1 });
    const size = Math.round(s.ctx.sampleRate * 1.0);
    let samples = new Float32Array(size), used = 0;
    s.ws = new WebSocket(socketUrl());
    s.ws.onopen = () => {
      if (session === s) s.ws.send(JSON.stringify({ type: 'start', sampleRate: s.ctx.sampleRate }));
    };
    s.ws.onmessage = ({ data }) => {
      if (session !== s) return;
      try {
        const msg = JSON.parse(data);
        if (msg.type === 'error') { stop(msg.error); return; }
        if (msg.type === 'status') { say(msg.message); return; }
        if (msg.type === 'ready' || msg.type === 'sound-event') {
          s.ready = true;
          // Start a fresh window after each reply; never upload old queued audio.
          used = 0;
          if (msg.type === 'ready') {
            say(`Listening: ${track.label || 'unnamed input'}. Environmental alerts are active.`);
          }
        }
        if (msg.type === 'sound-event') {
          const label = msg.event && (subtitleLabels[msg.event.id] || msg.event.label.toLowerCase());
          results.textContent = msg.event ? `${msg.event.emoji}  [${label}]` : '';
          results.className = msg.event ? `sound-card ${msg.event.urgency}` : '';
        }
      } catch (e) { stop(`Sound classifier error: ${e.message}`); }
    };
    s.ws.onerror = () => { if (session === s) stop('Could not connect to the sound classifier.'); };
    s.ws.onclose = () => { if (session === s) stop('Sound classifier disconnected. Tap Start sounds to retry.'); };
    s.node.port.onmessage = ({ data }) => {
      if (session !== s || !s.ready) return;
      for (const value of new Float32Array(data)) {
        samples[used++] = value;
        if (used === size) {
          if (s.ws.readyState !== WebSocket.OPEN || s.ws.bufferedAmount) {
            stop('Audio upload stalled. Tap Start sounds to retry.');
            return;
          }
          // Explicit little-endian encoding matches the server on every browser platform.
          const bytes = new ArrayBuffer(size * 4), view = new DataView(bytes);
          for (let i = 0; i < size; i++) view.setFloat32(i * 4, samples[i], true);
          s.ws.send(bytes);
          s.ready = false;
          used = 0;
          return;
        }
      }
    };
    s.source.connect(s.node);
    s.node.connect(s.ctx.destination); // the PCM worklet emits silence
  }

  async function action(fn) {
    if (busy) return;
    busy = true;
    $('sound-start').disabled = $('sound-refresh').disabled = true;
    try { await fn(); } catch (e) { stop(`${e.name || 'Error'}: ${e.message}`); }
    finally { busy = false; $('sound-start').disabled = $('sound-refresh').disabled = false; }
  }
  $('sound-refresh').addEventListener('click', () => action(refresh));
  $('sound-start').addEventListener('click', () => action(start));
  $('sound-stop').addEventListener('click', () => stop());
  select.addEventListener('change', () => { if (session) stop('Input changed. Tap Start sounds.'); });
  addEventListener('pagehide', () => stop());
  return {
    speechChanging() {
      if (session) stop('Speech input restarting. Verify both microphone selections, then tap Start sounds.');
    },
    startWithSpeech(stream) {
      return action(() => start(stream));
    },
  };
}
