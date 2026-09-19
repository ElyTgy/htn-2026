// Batch mono float32 PCM into ~40 ms packets, without playing the microphone back.
class CaptionPCM extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(Math.round(sampleRate * 0.04));
    this.used = 0;
  }

  process(inputs) {
    const channels = inputs[0];
    if (!channels || !channels.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i];
      this.buffer[this.used++] = sample / channels.length;
      if (this.used === this.buffer.length) {
        this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
        this.buffer = new Float32Array(Math.round(sampleRate * 0.04));
        this.used = 0;
      }
    }
    return true;
  }
}

registerProcessor('caption-pcm', CaptionPCM);
