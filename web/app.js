import { Attributor } from './attribution.js';
import { CaptionBuffer, captionLines, smoothAnchor } from './captions.js';
import { Calibration, bindCalibrationUi } from './calibrate.js';
import { createProvider, listProviders } from './stt/provider.js';
import { openMic, closeMic, listMics } from './stt/mic.js';
import './stt/speechmatics.js';
import './stt/mic-test.js';
import { bindSoundUi } from './sound.js';

const params = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

// Older builds remembered the selected provider. That allowed the scripted mock provider to
// survive a reload and look like a real conversation. Keep only non-audio display calibration;
// microphone, provider and any unknown legacy state are deliberately session-only.
function purgeLegacyClientState() {
  try {
    const keep = new Set(['caption-glasses-calibration', 'debug', 'camera-feed']);
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (key && !keep.has(key)) localStorage.removeItem(key);
    }
  } catch {}
}
purgeLegacyClientState();

const COLOURS = ['#ffe14d', '#5ef0ff', '#7dff8a', '#ff9df0', '#ffb36b'];
const CAPTION_HOLD_MS = 2500;   // old words disappear quickly; this is a live aid, not a transcript
const FINAL_KEEP_MS = 3500;
const MAX_TRANSCRIPT_AGE_MS = 8000; // reject replays, not valid Enhanced-model finalization latency
const FACE_GONE_MS = 1000;
const SMOOTH = 0.35;

// Query parameters override the saved display mode. The normal first-run mode is the dark HUD.
// ?debug=1 / ?debug=0 apply to this visit only; the Boxes button is what gets remembered.
let showVideo = params.has('video') ? params.get('video') !== '0' : store.get('camera-feed') === '1';
const debugParam = params.has('debug') ? params.get('debug') !== '0' : null;
const state = {
  debug: debugParam ?? store.get('debug') === '1',
  faces: new Map(),      // id → { target:{x,y,w,h}, x,y,w,h (smoothed), score, speaking, seen, box }
  captions: new Map(),   // face id → caption DOM and smoothed anchor
  wsStatus: 'connecting', sttStatus: 'idle', fps: 0, captureFps: 0, visionLatencyMs: 0,
  provider: null, mic: null,
};
// Send status, errors and attribution decisions to the server's terminal (see /log in pi/server.py).
function report(text) {
  fetch('/log', { method: 'POST', body: text, keepalive: true }).catch(() => {});
}
addEventListener('error', (e) => report(`JS error: ${e.message} (${e.filename}:${e.lineno})`));
addEventListener('unhandledrejection', (e) => report(`JS rejection: ${e.reason && e.reason.message || e.reason}`));

const attributor = new Attributor();
const captionBuffer = new CaptionBuffer();
const textMeasure = document.createElement('canvas').getContext('2d');
let lastRender = performance.now(), nextTextPaint = 0;
const cal = new Calibration({ forceIdentity: showVideo });

// ---- face data from the Pi -------------------------------------------------------------
function connectWs() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { state.wsStatus = 'connected'; setStartStatus(); };
  ws.onclose = () => { state.wsStatus = 'reconnecting'; setStartStatus(); setTimeout(connectWs, 1000); };
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.type !== 'frame') return;
    const now = performance.now();
    state.fps = msg.fps;
    state.captureFps = msg.captureFps || msg.fps;
    state.visionLatencyMs = msg.latencyMs || 0;
    attributor.addFrame(now, msg.faces);
    for (const f of msg.faces) {
      let face = state.faces.get(f.id);
      if (!face) state.faces.set(f.id, (face = { x: f.x, y: f.y, w: f.w, h: f.h }));
      Object.assign(face, { target: f, score: f.score, speaking: f.speaking, seen: now });
    }
  };
}

// ---- transcript → captions ---------------------------------------------------------------
function captionFor(key) {
  let c = state.captions.get(key);
  if (!c) {
    const el = document.createElement('div');
    el.className = 'caption hidden';
    el.style.color = COLOURS[(key - 1) % COLOURS.length];
    $('stage').appendChild(el);
    el.innerHTML = '<span class="arrow"></span><span class="caption-text"></span>';
    state.captions.set(key, (c = { updated: 0, how: '', el, textEl: el.querySelector('.caption-text'), anchor: null }));
  }
  return c;
}

function onTranscript(event) {
  const now = performance.now();
  const age = now - event.endMs;
  if (!Number.isFinite(age) || age < -500 || age > MAX_TRANSCRIPT_AGE_MS) {
    report(`discarded stale transcription event age=${Math.round(age)}ms`);
    return;
  }
  const runs = attributor.splitRuns(event).filter(run => run.text.trim()).map(run => {
    let decision = attributor.attribute(run.startMs, run.endMs, run.speaker, event.isFinal);
    // Keep a provisional stretch on the same face while its wording is revised.
    // A final result or a changed voice label can correct that placement.
    const previous = captionBuffer.partial.find(p => p.speaker === run.speaker &&
      Math.abs(p.startMs - run.startMs) < 100 && p.endMs > run.startMs);
    if (!event.isFinal && previous?.faceId != null && state.faces.has(previous.faceId)) {
      decision = { faceId: previous.faceId, how: previous.how };
    }
    const { faceId, how } = decision;
    if (event.isFinal) {
      const lips = attributor.lipEvidence(run.startMs, run.endMs).map((e) => `#${e.id}=${e.score.toFixed(2)}`).join(' ');
      // Never write spoken words to server.log. The log contains only routing and latency metadata.
      report(`caption final chars=${run.text.length} → ${faceId === null ? 'dropped (no visible face)' : `face #${faceId}`} (${how}) voice=${run.speaker ?? '-'} lips[${lips}] lag=${Math.round(now - run.endMs)}ms`);
    }
    if (faceId === null) return null;
    const c = captionFor(faceId);
    if (now - c.updated >= CAPTION_HOLD_MS) c.anchor = null;
    c.updated = now;
    c.how = how;
    return { ...run, faceId, how,
      words: event.words?.filter(w => w.startMs >= run.startMs && w.endMs <= run.endMs) };
  }).filter(Boolean);
  captionBuffer.update(event, runs, now);
}

// ---- drawing --------------------------------------------------------------------------------
function render() {
  const now = performance.now();
  const dt = Math.min(now - lastRender, 100);
  lastRender = now;
  const paintText = now >= nextTextPaint;
  if (paintText) nextTextPaint = now + 100;

  for (const [id, f] of state.faces) {
    if (now - f.seen > FACE_GONE_MS) {
      if (f.box) f.box.remove();
      state.faces.delete(id);
      continue;
    }
    for (const k of ['x', 'y', 'w', 'h']) f[k] += (f.target[k] - f[k]) * SMOOTH;
    drawFaceBox(id, f);
  }

  for (const [key, c] of state.captions) {
    const face = state.faces.get(key);
    const live = now - c.updated < CAPTION_HOLD_MS && face;
    c.el.classList.toggle('hidden', !live);
    if (!live) {
      if (!face && now - c.updated > FINAL_KEEP_MS) { c.el.remove(); state.captions.delete(key); }
      continue;
    }
    if (paintText) {
      let text = captionBuffer.textFor(key);
      c.el.classList.toggle('empty', !text);
      const width = c.textEl.clientWidth;
      if (text !== c.sourceText || width !== c.textWidth) {
        const style = getComputedStyle(c.textEl);
        textMeasure.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        captionBuffer.compact(key, width, s => textMeasure.measureText(s).width);
        text = captionBuffer.textFor(key);
        const displayed = captionLines(text, width, s => textMeasure.measureText(s).width);
        if (c.textEl.textContent !== displayed) c.textEl.textContent = displayed;
        c.sourceText = text;
        c.textWidth = width;
      }
    }
    if (face) placeCaption(c, face, dt);
  }

  if (state.debug) {
    $('hud').textContent =
      `camera ${state.captureFps} fps  vision ${state.fps} fps  ${state.visionLatencyMs} ms  ${state.faces.size} face(s)\n` +
      `server ${state.wsStatus}  stt ${state.sttStatus}\n` +
      `mic ${'█'.repeat(Math.min(20, Math.round((state.micLevel || 0) * 100)))}\n` +
      [...attributor.votes].map(([l, v]) => `voice ${l} → ${attributor.boundFace(l) ?? '?'} ` +
        `[${[...v].map(([k, w]) => `${k}:${w.toFixed(1)}`).join(' ')}]`).join('\n');
  }
  requestAnimationFrame(render);
}

function placeCaption(c, f, dt) {
  const el = c.el;
  let [x, y] = cal.map(f.x + f.w / 2, f.y);
  y -= 18;
  // Faces the camera can see but the display can't reach: pin to the edge and point at them.
  const halfW = el.offsetWidth / 2, h = el.offsetHeight, m = 8;
  let arrow = '';
  if (x < halfW + m) { if (x < 0) arrow = '◀ '; x = halfW + m; }
  else if (x > innerWidth - halfW - m) { if (x > innerWidth) arrow = '▶ '; x = innerWidth - halfW - m; }
  if (y < h + m) { if (y < 0 && !arrow) arrow = '▲ '; y = h + m; }
  else if (y > innerHeight - m) { if (!arrow) arrow = '▼ '; y = innerHeight - m; }
  el.querySelector('.arrow').textContent = arrow;
  c.anchor = smoothAnchor(c.anchor, x, y, dt);
  el.style.transform = `translate(${c.anchor.x.toFixed(1)}px, ${c.anchor.y.toFixed(1)}px) translate(-50%, -100%)`;
}

function drawFaceBox(id, f) {
  if (!state.debug) { if (f.box) { f.box.remove(); f.box = null; } return; }
  if (!f.box) {
    f.box = document.createElement('div');
    $('stage').appendChild(f.box);
  }
  // Mirroring flips which edge is "left", so map the centre and size rather than a corner.
  const [cx, cy] = cal.map(f.x + f.w / 2, f.y + f.h / 2);
  const [w, h] = cal.mapSize(f.w, f.h);
  f.box.className = `facebox${f.speaking ? ' speaking' : ''}`;
  f.box.style.width = `${w}px`;
  f.box.style.height = `${h}px`;
  f.box.style.transform = `translate(${cx - w / 2}px, ${cy - h / 2}px)`;
  f.box.textContent = `#${id}  ${f.score.toFixed(2)}`;
}

// ---- transcription lifecycle ------------------------------------------------------------------
function resetTranscript() {
  attributor.resetVoices();
  captionBuffer.reset();
  for (const c of state.captions.values()) {
    c.updated = -Infinity;
    c.sourceText = '';
    c.textEl.textContent = '';
    c.anchor = null;
  }
}

// Calls are queued so two quick triggers (Start + a settings change, say) can't interleave
// and leave one provider recording from a microphone the other one just closed.
let sttQueue = Promise.resolve();
let sttGeneration = 0;
let soundControls;
function startStt() {
  sttQueue = sttQueue.catch(() => {}).then(startSttNow);
  return sttQueue;
}

async function startSttNow() {
  soundControls?.speechChanging();
  stopStt();
  resetTranscript();
  const generation = ++sttGeneration;
  const name = $('stt-select').value;
  const provider = createProvider(name, {
    onTranscript: (event) => { if (generation === sttGeneration) onTranscript(event); },
    onSessionStart: () => { if (generation === sttGeneration) resetTranscript(); },
    onStatus: (s) => {
      if (generation !== sttGeneration) return;
      if (state.sttStatus !== `${name}: ${s}`) report(`stt ${name}: ${s}`);
      state.sttStatus = `${name}: ${s}`;
    },
  });
  if (provider.needsMic) {
    try {
      state.mic = await openMic($('mic-select').value || store.get('mic') || undefined);
    } catch (e) {
      if (e.name !== 'OverconstrainedError') throw e;
      state.mic = await openMic();
    }
    await refreshMics(); // labels become available once permission is granted
    watchMic(state.mic);
  }
  state.provider = provider;
  try {
    await provider.start(state.mic);
    // Reuse the already-open microphone. Android often permits only one capture route, while an
    // AudioContext can safely fan the same MediaStream out to Speechmatics and Jetson YAMNet.
    soundControls?.startWithSpeech(state.mic);
  }
  catch (e) { stopStt(); throw e; }
}

function stopStt() {
  sttGeneration++;
  if (state.provider) state.provider.stop();
  state.provider = null;
  unwatchMic();
  closeMic(state.mic);
  state.mic = null;
}

// ---- microphone health ------------------------------------------------------------------------
// Shows whether the mic is actually hearing anything (HUD + server log), and reopens it if the
// browser ends the track (device unplugged, permission revoked, another app grabbed it).
let micWatch = null;

function watchMic(stream) {
  const track = stream.getAudioTracks()[0];
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  let peak = 0;

  const levelTimer = setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    const rms = Math.sqrt(sum / buf.length);
    state.micLevel = rms;
    peak = Math.max(peak, rms);
  }, 100);
  const reportTimer = setInterval(() => {
    report(`mic "${track.label}" ${track.readyState}${track.muted ? ' MUTED' : ''} peak level ${peak.toFixed(3)} (speech is roughly 0.02-0.3; 0.000 = silence)`);
    peak = 0;
  }, 5000);

  const onEnded = () => {
    report(`mic track ended: "${track.label}"; reopening`);
    setTimeout(() => startStt().catch(showSttError), 500);
  };
  const onMute = () => report(`mic track muted by the browser/OS: "${track.label}"`);
  track.addEventListener('ended', onEnded);
  track.addEventListener('mute', onMute);
  report(`mic opened: "${track.label}" ${JSON.stringify(track.getSettings())}`);

  micWatch = () => {
    clearInterval(levelTimer);
    clearInterval(reportTimer);
    track.removeEventListener('ended', onEnded);
    track.removeEventListener('mute', onMute);
    ctx.close().catch(() => {});
    state.micLevel = 0;
  };
}

function unwatchMic() {
  if (micWatch) micWatch();
  micWatch = null;
}

async function refreshMics() {
  const sel = $('mic-select');
  const current = state.mic ? state.mic.getAudioTracks()[0].getSettings().deviceId : '';
  sel.innerHTML = '';
  for (const m of await listMics()) sel.add(new Option(m.label, m.id, false, m.id === current));
}

// ---- glasses view -----------------------------------------------------------------------------
// The glasses mirror the whole phone screen, so the address bar and a portrait layout would
// show up too. Must be called from a tap. Explicit debug pages stay windowed.
function enterGlassesView() {
  const root = document.documentElement;
  if (debugParam === true || document.fullscreenElement || !root.requestFullscreen) return;
  root.requestFullscreen({ navigationUI: 'hide' })
    .then(() => screen.orientation && screen.orientation.lock && screen.orientation.lock('landscape'))
    .catch((e) => report(`fullscreen/landscape refused: ${e.message}`));
}

// What the glasses are being handed, for the server log: a visible address bar or a portrait
// page both show up as a window floating in front of you.
function reportView() {
  report(`view ${location.pathname}${location.search} fullscreen=${!!document.fullscreenElement} ` +
    `page=${innerWidth}x${innerHeight} screen=${screen.width}x${screen.height} ` +
    `video=${showVideo} boxes=${state.debug} ua=${navigator.userAgent}`);
}
addEventListener('fullscreenchange', reportView);

// ---- page wiring ------------------------------------------------------------------------------------
function setStartStatus(extra) {
  $('start-status').textContent = extra || (state.wsStatus === 'connected' ? 'Connected to the camera.' : 'Connecting to the camera…');
}

async function init() {
  soundControls = bindSoundUi({ speechTrack: () => state.mic?.getAudioTracks()[0] });
  let config = { defaultStt: 'speechmatics' };
  try { config = await (await fetch('/config')).json(); } catch {}
  if (Number.isFinite(config.aspect) && config.aspect > 0) cal.videoAspect = config.aspect;

  const sttSel = $('stt-select');
  const providers = listProviders();
  const requested = params.get('stt');
  const wanted = providers.some((p) => p.name === requested) ? requested : config.defaultStt;
  for (const p of providers) sttSel.add(new Option(p.label, p.name, false, p.name === wanted));

  $('hud').hidden = !state.debug;
  $('debug-toggle').checked = state.debug;
  bindCalibrationUi(cal, $('settings'));
  connectWs();
  reportView();
  requestAnimationFrame(render);

  $('start-btn').addEventListener('click', async () => {
    $('start-btn').disabled = true;
    // Before the mic prompt: by the time it's answered the tap no longer counts as a user gesture.
    enterGlassesView();
    try {
      await startStt();
      $('start').hidden = true;
      reportView();
      if (navigator.wakeLock) navigator.wakeLock.request('screen').catch(() => {});
    } catch (e) {
      setStartStatus(e.message);
      $('start-btn').disabled = false;
    }
  });

  // Fullscreen drops out on a back swipe or when the screen turns off; any tap brings it back.
  addEventListener('click', () => { if ($('start').hidden) enterGlassesView(); });
  const setMenu = (open) => {
    $('settings').hidden = !open;
    $('menu-btn').setAttribute('aria-expanded', String(open));
  };
  $('menu-btn').addEventListener('click', (e) => { e.stopPropagation(); setMenu($('settings').hidden); });
  $('settings-close').addEventListener('click', () => setMenu(false));
  // Three ways to show/hide the face boxes (and status text), all kept in sync:
  // the corner button, the Settings checkbox, and the B key.
  const setDebug = (on, remember = true) => {
    state.debug = on;
    if (remember) store.set('debug', on ? '1' : '0');
    $('hud').hidden = !on;
    $('debug-toggle').checked = on;
    $('boxes-btn').setAttribute('aria-pressed', String(on));
  };
  setDebug(state.debug, false);
  $('debug-toggle').addEventListener('change', (e) => setDebug(e.target.checked));
  $('boxes-btn').addEventListener('click', () => setDebug(!state.debug));
  const setVideo = (on, remember = true) => {
    showVideo = on;
    if (remember) store.set('camera-feed', on ? '1' : '0');
    const video = $('video');
    if (on && !video.src) video.src = '/video';
    video.hidden = !on;
    $('video-toggle').checked = on;
    cal.forceIdentity = on;
    cal.onChange();
    reportView();
  };
  setVideo(showVideo, false);
  $('video-toggle').addEventListener('change', (e) => setVideo(e.target.checked));
  addEventListener('keydown', (e) => {
    const typing = e.target instanceof Element && e.target.closest('input, select, textarea');
    if (e.key && e.key.toLowerCase() === 'b' && !typing) setDebug(!state.debug);
  });
  // Rotation happens on the Pi (faces must be upright for detection), so it lives in the
  // server's settings rather than localStorage and applies to every page that connects.
  const rotateToggle = $('rotate-toggle');
  rotateToggle.checked = (config.settings && config.settings.rotate) === 90;
  rotateToggle.addEventListener('change', async () => {
    rotateToggle.disabled = true;
    try {
      const r = await fetch('/settings', { method: 'POST', body: JSON.stringify({ rotate: rotateToggle.checked ? 90 : 0 }) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      rotateToggle.checked = (await r.json()).rotate === 90;
    } catch (e) {
      rotateToggle.checked = !rotateToggle.checked;
      report(`rotate setting failed: ${e.message}`);
    } finally {
      rotateToggle.disabled = false;
    }
  });
  sttSel.addEventListener('change', () => { if (state.provider) startStt().catch(showSttError); });
  $('mic-select').addEventListener('change', () => { if (state.provider) startStt().catch(showSttError); });
}

function showSttError(e) { state.sttStatus = `error: ${e.message}`; }

init();
