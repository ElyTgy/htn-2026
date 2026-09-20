// A second consumer of the same microphone stream used by transcription. It
// sends raw audio to the Pi; the Pi runs YAMNet and returns selected labels.
const socketUrl = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/sound/ws`;

export async function startEnvironmentalAudio(stream, { onStatus = () => {} } = {}) {
  if (!stream || !window.AudioContext || !window.AudioWorkletNode) {
    onStatus('environmental audio unavailable in this browser');
    return { stop() {} };
  }

  let stopped = false;
  let terminalError = false;
  let socket = null;
  let retryTimer = null;
  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  const muted = ctx.createGain();
  muted.gain.value = 0;

  try {
    await ctx.audioWorklet.addModule('/sound-worklet.js');
    const worklet = new AudioWorkletNode(ctx, 'pcm16-worklet');
    source.connect(worklet).connect(muted).connect(ctx.destination);
    worklet.port.onmessage = ({ data }) => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(data.buffer);
    };
    await ctx.resume();

    const connect = () => {
      if (stopped) return;
      socket = new WebSocket(socketUrl());
      socket.onopen = () => onStatus('environmental audio connected');
      socket.onmessage = ({ data }) => {
        try {
          const message = JSON.parse(data);
          if (message.type === 'error') {
            terminalError = true;
            onStatus(`environmental audio unavailable: ${message.error}`);
          }
        } catch {}
      };
      socket.onclose = () => {
        if (!stopped && !terminalError) {
          onStatus('environmental audio reconnecting');
          retryTimer = setTimeout(connect, 1000);
        }
      };
      socket.onerror = () => onStatus('environmental audio connection error');
    };
    connect();

    return {
      stop() {
        stopped = true;
        clearTimeout(retryTimer);
        if (socket) socket.close();
        source.disconnect();
        worklet.disconnect();
        muted.disconnect();
        ctx.close().catch(() => {});
      },
    };
  } catch (error) {
    source.disconnect();
    muted.disconnect();
    ctx.close().catch(() => {});
    onStatus(`environmental audio unavailable: ${error.message}`);
    return { stop() {} };
  }
}
