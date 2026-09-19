// Microphone access shared by every provider.

export function micSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

export async function openMic(deviceId) {
  if (!micSupported()) {
    throw new Error('This page cannot use the microphone. Chrome only allows it on https:// or localhost; see README "Mic permission".');
  }
  return navigator.mediaDevices.getUserMedia({
    audio: {
      deviceId: deviceId ? { exact: deviceId } : undefined,
      channelCount: 1,
      // The browser's noise suppression is tuned for a voice right at the mic and tends to
      // erase people a metre or two away, who are exactly who we want to hear.
      noiseSuppression: false,
      echoCancellation: false,
      autoGainControl: true,
    },
  });
}

// Device labels are only filled in after mic permission has been granted once.
export async function listMics() {
  if (!micSupported()) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((d) => d.kind === 'audioinput')
    .map((d, i) => ({ id: d.deviceId, label: d.label || `Microphone ${i + 1}` }));
}

export function closeMic(stream) {
  if (stream) stream.getTracks().forEach((t) => t.stop());
}
