// Downsample the selected microphone to the 16 kHz s16le stream YAMNet expects.
// AudioWorklet runs off the UI thread, so caption drawing stays smooth.
class Pcm16Worklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.position = 0;
  }

  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input || !input.length) return true;

    // Keep phase across 128-sample worklet blocks: this avoids timing drift when
    // the device sample rate is not an exact multiple of 16 kHz.
    const pcm = [];
    let position = this.position;
    while (position <= input.length - 1) {
      const lo = Math.floor(position);
      const hi = Math.min(lo + 1, input.length - 1);
      const value = input[lo] + (input[hi] - input[lo]) * (position - lo);
      pcm.push(Math.max(-32768, Math.min(32767, Math.round(value * 32767))));
      position += this.ratio;
    }
    this.position = position - input.length;
    if (pcm.length) {
      const chunk = Int16Array.from(pcm);
      this.port.postMessage(chunk, [chunk.buffer]);
    }

    // This node is connected through a muted gain purely to keep it alive.
    for (const channel of outputs[0] || []) channel.fill(0);
    return true;
  }
}

registerProcessor('pcm16-worklet', Pcm16Worklet);
