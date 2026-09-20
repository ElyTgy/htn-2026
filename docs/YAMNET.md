# XREAL microphone → phone → Jetson YAMNet

The glasses remain plugged into the Beam phone. The phone browser captures an explicitly selected
microphone and sends mono audio to `/sound-ws` on the Jetson. The Jetson runs the same TF Hub YAMNet
model as the supplied Python script, resampling to 16 kHz and averaging scores over each 1.5-second
window. The phone displays the top five class names and scores along the bottom of the glasses view.
These are model scores, not calibrated probabilities or confirmed alerts.

Speech captions keep their existing microphone and Speechmatics path. Classification is opt-in,
and returns results only to the browser sending audio. It does not control TITAN motors yet.

## Jetson dependencies

Install TensorFlow appropriate to the Jetson's exact JetPack/Python version into the app's `.venv`,
following [NVIDIA's installation guide](https://docs.nvidia.com/deeplearning/frameworks/install-tf-jetson-platform/index.html)
and [compatibility table](https://docs.nvidia.com/deeplearning/frameworks/install-tf-jetson-platform-release-notes/tf-jetson-rel.html).
The optional classifier also requires `tensorflow-hub` and `scipy`; use a `tf-keras` version compatible
with that TensorFlow runtime if required by TensorFlow Hub. Preserve the existing `numpy<2` constraint.
These optional dependencies are not installed automatically by the vision setup script.

Before restarting the existing caption server, check in the project directory:

```bash
.venv/bin/python -c 'import tensorflow, tensorflow_hub, scipy; print(tensorflow.__version__)'
```

The first **Start sounds** downloads `https://tfhub.dev/google/yamnet/1` and needs internet access.
Loading and inference run off the web event loop. Actual performance alongside vision must be
measured on the Jetson. The browser waits for each inference response before capturing the next
window, so there are capture gaps during inference and no growing upload backlog. This is a
classification prototype, not continuous alarm monitoring.

## Phone setup and hardware check

1. Keep the glasses connected to the phone. Open the Jetson's HTTPS caption URL on the phone.
2. Start captions and select the phone's built-in input under **Settings → Speech microphone**.
3. Under **Environmental sounds**, tap **Check microphones** and allow permission if prompted.
4. Select the XREAL/USB input under **Glasses microphone**, then tap **Start sounds**.
5. Confirm the displayed input name. Make a sound close to the glasses, then close to the phone,
   to check the physical source. Confirm the speech microphone meter/captions still work too.
6. **Stop sounds** releases the classification microphone. To change the speech input, stop sounds
   first, select the new speech input, then restart classification with a different input.

## Isolated test while the main Jetson app runs

Use a separate directory, such as `~/yamnet-test`, containing this modified code. These changes
must be copied from the Mac; pulling the repository does not include unpushed local edits.
Do not run `jetson_start.sh` in the live checkout: it stops the existing app processes.

The dedicated `pi/yamnet_test_server.py` serves just microphone selection and classification, with
HTTPS on port 8444. It never opens the OAK camera, speech service, or TITAN. In the test directory:

```bash
sh scripts/make_cert.sh
# Use a Python environment with aiohttp, numpy, scipy, TensorFlow and tensorflow-hub installed.
CUDA_VISIBLE_DEVICES=-1 /path/to/python -u pi/yamnet_test_server.py
```

`CUDA_VISIBLE_DEVICES=-1` keeps this test's TensorFlow off the Jetson GPU, though CPU and RAM
are still shared with the live app. Use the existing environment only if imports already work;
install missing dependencies in a separate test environment, not the teammate's running environment.
TensorFlow setup remains dependent on the JetPack/Python versions as described above.

On the phone, open `https://<JETSON_IP>:8444/`, accept the local test certificate, and use
**Check microphones → select XREAL/USB → Start sounds**. Test with speech, clapping, and a recording
of a recognizable sound. A working test shows changing class names/scores from actual audio.
Ctrl+C in the test terminal stops only this server.

Using another tab on the same Beam phone can pause its existing caption tab or affect microphone
routing. Coordinate that phone test with your teammate; a separate server does not remove this
phone limitation. A Mac microphone can smoke-test Jetson inference first, but does not validate
the XREAL microphone path.

USB connection alone does not establish that the phone exposes the glasses microphone. If no
separate input appears, or starting one microphone mutes the other, this browser/OS setup has not
provided the two independent inputs needed. Do not interpret a generic/default input as proof of
XREAL capture. Native Android audio routing may need investigation, or the audio hardware/path
must change. The code does not silently fall back to the phone's default microphone.

Only one browser can supply YAMNet audio at once. A Mac opening the caption page does not receive
the phone's classification results in this version. Stop the phone capture before testing another
microphone from a Mac browser.

## Validation

```bash
.venv/bin/python tests/test_yamnet_stream.py
```

Tests exercise PCM validation, class ranking, WebSocket upload/results, exclusive input ownership,
and error recovery using a fake model. They do not establish XREAL microphone availability,
dual-input support, real YAMNet inference, or Jetson runtime compatibility.

References: [YAMNet input and classes](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio),
[browser device selection](https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/deviceId).
