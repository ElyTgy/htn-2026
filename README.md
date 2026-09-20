# Caption Glasses

Live captions floating above whoever is speaking, seen through XREAL One glasses.

```
Pi 5 + Pi camera, or Jetson + OAK/CSI/USB camera   Beam Pro (Chrome, fullscreen live video)
  camera → faces → who is moving their lips   ──►    mic → Speechmatics → timestamped words
  serves the page + streams face data (WebSocket)    matches words to the face that was talking
                                                     draws the caption above that face
                                                       ↓
                                        XREAL One, head-locked video + overlays
```

The camera decides **who** is speaking (lip movement, backed up by the transcription service's
voice labels). The Beam Pro's browser does the **what** (speech to text). Speech with no matching
face on camera is dropped rather than displayed as an unattributed global subtitle.

Built at Hack the North 2026. Captions are the primary system. The Jetson build also includes the
coarse two-sensor directional haptic path; it is intentionally separate from transcription audio.

**Just want it running?** [docs/SETUP.md](docs/SETUP.md) is the Raspberry Pi runbook. The parallel
Jetson build, including camera, Arduino sensors, TITAN haptics, wiring, firmware, and staged tests, is
in [docs/JETSON_SETUP.md](docs/JETSON_SETUP.md).

**Contents:** [Quick start](#1-try-it-on-a-laptop-first-no-pi-no-glasses) ·
[Pi setup](#2-raspberry-pi-5-setup) · [Jetson setup](#2b-jetson-orin-nano-8-gb-setup) · [Beam Pro](#4-on-the-beam-pro) ·
[How it works](#how-it-works) · [Two people talking](#two-people-talking) ·
[Transcription options](#transcription-options) · [Mic arrays and audio-visual fusion](#mic-arrays-and-audio-visual-fusion-rev-2) ·
[Hardware notes](#hardware-notes) · [Tuning](#tuning-piconfigpy-webattributionjs) · [Known limits](#known-limits)

## 1. Try it on a laptop first (no Pi, no glasses)

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r pi/requirements.txt
.venv/bin/python pi/main.py --backend fake
```

Open <http://localhost:8080/?debug=1&stt=mic-test>. You get two synthetic faces and a live
microphone meter, but never fake transcript text. Then use your webcam and live speech (needs a
Speechmatics key, step 3):

```bash
.venv/bin/python pi/main.py --backend mediapipe --source opencv
```

Open <http://localhost:8080/?debug=1&video=1>. `video=1` shows the camera feed behind the
captions; `debug=1` shows face boxes, each face's speaking score (0-1), a mic level bar and the
voice-label table. On macOS the first run asks for camera permission for your terminal app.

The page also reports to the server's terminal as `[page] ...` lines: which mic opened, its level
every 5 s, transcription status and errors, and every attribution decision, e.g.

```
[page] caption final chars=30 → face #4 (lips) voice=0 lips[#4=0.44] lag=619ms
```

That is the main debugging tool on the Beam Pro, where the browser console is hard to reach.

## 2. Raspberry Pi 5 setup

Needs 64-bit **Raspberry Pi OS Bookworm** (Python 3.11). If the SD card has the QNX image, reflash it.

```bash
sudo apt install -y python3-picamera2
python3 -m venv --system-site-packages .venv      # so the venv can see picamera2
.venv/bin/pip install -r pi/requirements.txt
rpicam-hello -t 2000                              # check the camera works
.venv/bin/python pi/main.py --backend mediapipe --source picamera2
```

The terminal shows frames per second; aim for 15 or more. If it's low, try `--width 960 --height 540`.
The face model downloads itself on first run (needs internet once).
If the camera is mounted sideways, tick "Camera is sideways" in the page's Settings; the Pi
remembers it in `settings.json`. Check the result at `http://<pi>:8080/video`.

## 2b. Jetson Orin Nano 8 GB setup

The Jetson is a parallel host, not a replacement for the Pi files. It uses the same `pi/main.py` and
web page with an OAK-1, Jetson CSI, or USB camera source, plus a separate Arduino-to-TITAN bridge for coarse
directional haptics.

```bash
sh scripts/jetson_check.sh
sh scripts/jetson_install.sh
```

For an isolated camera + browser-microphone test with no API key or extra electronics, run
`sh scripts/jetson_video_mic_test.sh oak` and open the HTTPS URL it prints. Use `csi` or `usb` for those cameras.

Do not wire from the old Pi pin numbers: the Jetson developer kit has different power and UART rules.
Follow the complete [Jetson wiring, firmware, calibration, and test runbook](docs/JETSON_SETUP.md).

## 3. Speechmatics key

Copy `.env.example` to `.env` and paste a key from <https://portal.speechmatics.com/>.

## 4. On the Beam Pro

1. Put the Pi and the Beam Pro on the **same network with internet**. Event Wi-Fi usually blocks
   device-to-device traffic; a phone hotspot works.
   **Address to use.** Phone hotspots are often IPv6-only for laptops and Android devices, so the Pi's
   `172.20.10.x` / `192.168.x.x` address may be unreachable from the Beam Pro. Use the Pi's name
   instead, `http://<pi-hostname>.local:8080/` (run `hostname` on the Pi; if another device already
   claimed the name it becomes `<name>-2`), or its global IPv6 address in brackets,
   `http://[2605:...]:8080/` (from `hostname -I`). Wherever this README says `<pi-ip>`, use that.
2. **Mic permission.** Browsers only allow the mic on `https://` or `localhost`, so over plain
   `http://<pi>:8080` the page says it cannot use the microphone. Pick one:
   - **HTTPS (recommended).** On the Pi run `sh scripts/make_cert.sh` once and restart the server. It then
     also serves `https://<pi-hostname>.local:8443/`. Open that, and accept the browser's certificate
     warning once (Advanced → Proceed). Works in any browser, nothing to configure per device.
   - **Chrome flag.** Open `chrome://flags`, search "Insecure origins treated as secure", add the exact
     origin you type in the address bar, e.g. `http://caption-pi-2.local:8080` (no trailing slash or
     path), set the dropdown to Enabled, and relaunch Chrome. It must be done in the browser on the
     device that opens the page.
3. Open the page **with nothing after the `/`** (`https://<pi-ip>:8443/`), tap **Start captions**, allow
   the mic. The page goes fullscreen and landscape in the dark HUD mode with caption overlays.
   If the address bar comes back (back swipe, screen lock), tap anywhere.
   The bottom-left `B` toggles boxes; the adjacent menu contains calibration and a persisted
   **Debug camera feed** checkbox. `?video=1&debug=1` forces feed plus diagnostics. `?debug=1` and
   `?debug=0` only apply to that visit; the Boxes button is what the device remembers.
4. Put the glasses in head-locked ("follow") mode so the screen stays fixed to your view.

### Calibrate (once)
Tap the top-left corner → Settings → **Show face boxes** → **XREAL starting point**. Look at someone
and nudge with the arrows / Bigger / Smaller until the box sits on their real face. It's saved on the device.
If boxes move the opposite way to the person, tick **Mirror horizontally**.

### Face boxes on/off
The dim **Boxes** button in the bottom-left corner shows or hides the boxes around faces and the status
text. The **B** key and the Settings checkbox do the same; the choice is remembered on the device.

### Which mic
Settings → Microphone. Test the glasses' mics first: if people 1-2 m away come through quiet or choppy
(they're tuned for the wearer's own voice), switch to the Beam Pro's mic and keep it on the table.

## How it works

### Pi side (`pi/`)
1. **Camera → faces.** A `VisionBackend` reports, per frame, each face's box and `mouth_open`
   (inner-lip gap ÷ forehead-to-chin distance, from MediaPipe Face Landmarker, up to 4 faces).
   The camera itself sits behind a smaller `FrameSource` interface (Pi camera, any OpenCV camera,
   a video file). These two seams are what make the Jetson / OAK-1 port a backend swap.
2. **Stable IDs.** `tracking.py` matches each detection to the nearest previous face so a person keeps
   the same ID from frame to frame.
3. **Remembering people.** `identity.py` maps each track to a *person*. Tracks break whenever a face
   is lost for a moment (head turn, blur, a hand in the way) and come back with a new track ID. So
   about once a second each tracked face gets a signature (a 128-number embedding from OpenCV's SFace
   model, aligned using five landmarks), and a new track is compared with everyone seen this session:
   a match (cosine similarity ≥ 0.363) gets its old person ID back. Two faces in view can never share
   an ID, and a face whose first frame was too blurry to match is merged into the right person within
   3 s once a clear frame arrives. The page only sees person IDs, so caption colour and the learned
   voice label survive dropouts. Signatures are anonymous numbers held in memory only: never saved,
   never sent anywhere, never tied to a name, and gone when the program exits. `--no-face-memory` turns it off.
4. **Who is talking.** `active_speaker.py` keeps 0.6 s of `mouth_open` per face. A talking mouth opens
   and closes several times a second, so the *spread* (standard deviation) is high; a closed mouth, or
   one held open in a smile, has low spread. Spread is scaled to a 0-1 speaking score with on/off
   thresholds and a short hold so it doesn't flicker. Measured on a laptop webcam: ~0.02 at rest, 0.4-1.0 while talking.
5. **Server.** `server.py` (aiohttp) serves the page, pushes one JSON message per frame over a WebSocket
   (rate-limited to 15 Hz), hands out short-lived transcription credentials so API keys stay in `.env`,
   and offers an MJPEG debug feed. The camera loop owns the main thread and the server runs in a
   background thread; macOS only delivers camera frames on the main thread, and the Pi doesn't care.

### Page side (`web/`)
1. **Transcription.** Speechmatics Realtime Enhanced streams the mic and emits one normalised event:
   text, final/interim, start and end time on the page's clock, and optionally per-word timings and a
   voice label per word.
2. **Attribution** (`attribution.js`, unit-tested under Node). Face messages are timestamped on arrival
   and kept for 12 s. For each stretch of words by one voice, the page averages every face's speaking
   score over the time those words were *spoken* (shifted by ~250 ms for camera and scoring lag), not
   when the text arrived. Then, in order:
   - a learned voice label (≥ 3 votes and twice its second choice) keeps its face through brief
     lip-score spikes at turn changes; sustained clear contradictory lips can correct it;
   - one face clearly ahead (score ≥ 0.40 and ≥ 0.15 above the runner-up) → that face;
   - otherwise the best visible lip candidate, so heard speech stays attached to a person.
   Only finalized, non-duplicate audio stretches of at least 250 ms train voice bindings.
   A new short voice isn't assigned to a face already bound to another voice, and missing historical
   frames aren't replaced with unrelated current frames.
   A voice that keeps speaking while nobody's lips move is learned as "the wearer / off-screen" and
   is not displayed unless a visible face can be selected. Clear lip evidence can correct a
   stale voice label within 250 ms.
3. **Drawing.** Camera and display are both fixed to the head, so camera→screen is four numbers (scale
   about the centre, offset) set once in Settings and stored on the device. Captions are smoothed,
   coloured per person, use a fixed-width two-line panel with left-aligned text, fade 4 s after the
   last word, and are pinned to the
   screen edge with an arrow when the camera can see a face the display can't reach.
   Small camera movements stay inside an 8 px dead zone; larger movements follow smoothly.
   Text updates at most ten times per second, and finalizing a prefix preserves remaining interim words.

## Two people talking

Both get transcribed. One mic hears everyone; the provider returns one stream with a voice label on
every word; the page splits it where the voice changes and places each stretch above whoever's lips
were moving then. Two captions in two colours can be up at once.

Where it struggles:
- **Talking over each other.** One mic can't separate two voices; the words come out merged or garbled.
- **Very short replies** ("yeah", "mm-hm"): often the wrong voice label and too little lip movement.
- **Your own or off-camera speech** is transcribed but not displayed because no visible person can own it.
- **A new voice** needs a few sentences before its label is trusted.
- **Lost tracking** used to give a returning face a new number (new colour, voice relearned). Face
  memory (`pi/identity.py`) now gives it the old number back, as long as the face is big and frontal
  enough for a signature (at least ~48 px wide).

Test without a second person: point the webcam at a screen playing a two-person interview with sound on.

## Transcription options

### Try Speechmatics Enhanced

1. Create an API key at <https://portal.speechmatics.com/> and add
   `SPEECHMATICS_API_KEY=your-key` to `.env` on the machine serving the page.
2. Restart the Python server after installing this code, then open
   `https://<pi-hostname>.local:8443/?stt=speechmatics&debug=1` (or
   `http://localhost:8080/?stt=speechmatics&debug=1` on a laptop).
3. Tap **Start captions**. You can also select **Speechmatics Enhanced (live + speakers)**
   in Settings → transcription provider.

This uses Speechmatics' highest-accuracy Realtime model (`enhanced`), live speaker
diarization, word timestamps, and partial transcripts. Finalization is configured at
`max_delay: 0.7` with `max_delay_mode: fixed`; this is a server processing target,
not a guarantee of total microphone-to-display latency. For more accuracy at the cost
of slower final captions, try `max_delay: 1.5` in `web/stt/speechmatics.js`.

The browser sends mono raw PCM in approximately 40 ms packets directly to Speechmatics;
the Pi only supplies a 60-second temporary credential, never the Speechmatics API key.
The global endpoint chooses the closest service region. Microphone capture requires
HTTPS or localhost and AudioWorklet support. If the connection drops or upload stalls,
switch to another provider and back to reconnect.

Try two people taking turns, short replies, and a person speaking off-camera. Debug
logs show the voice label and face selected for finalized text; `lag` measures final
transcript arrival, not first partial visibility. Voice-to-face learning uses final
results only and resets for a new transcription session. Unknown Speechmatics labels
(`UU`) are not learned as a person. Learned voice labels survive brief lip-score conflicts;
sustained clear lips can correct them. No live accuracy or latency benchmark is implied by this integration.

References: [models](https://docs.speechmatics.com/speech-to-text/models),
[latency](https://docs.speechmatics.com/speech-to-text/realtime/output),
[diarization](https://docs.speechmatics.com/speech-to-text/realtime/realtime-diarization).

### Provider interface

Everything speech-to-text lives in `web/stt/`. Each provider is one file that turns mic audio into one
normalised event (see the top of `web/stt/provider.js`). To add one: follow `speechmatics.js`, import it in
`web/app.js`, and if it needs a secret add a handler to `TOKEN_HANDLERS` in `pi/server.py`. Select it
in Settings or with `?stt=<name>`. APIs that only return whole phrases (no word timings or speaker
labels) still work; captions then appear a phrase at a time and the voice-label backup is skipped.
Every registered transcription provider is required to consume a currently live microphone track;
scripted/no-microphone providers are rejected by the shared provider boundary.

### Running a model locally
Local models give no speaker labels, so attribution runs on lips alone (which held up well in testing).
- **On the Pi 5:** small streaming models (Moonshine, sherpa-onnx, Vosk) run in real time but are
  less accurate than a cloud Enhanced model and compete with face tracking for CPU.
- **On a Jetson Orin Nano or a laptop:** faster-whisper or NVIDIA Parakeet can be competitive
  with no internet. Whisper-type models work in 1-3 s chunks, so they feel *less* live, not more.
- **Wiring:** the page streams mic audio to that machine over a WebSocket and a `local.js` provider
  returns the same event format. See [docs/PORTING.md](docs/PORTING.md) section D.

## Mic arrays and audio-visual fusion (rev 2)

Would a head-mounted mic array fix overlapping speech? It settles *who* is speaking; it only partly
untangles two people talking at once.

**The fusion idea.** The camera already knows the exact direction of every face. So the array doesn't
search for sound sources: it aims a listening beam at each known face and asks how much speech energy
comes from each direction. That gives
- **who is speaking** as a choice among two or three known directions, which works even when lips are
  hidden or two mouths are moving; and
- **one audio stream per person**, each sent to transcription separately. Attribution is then
  automatic: stream 1 is face 1.

**Is head width enough?**
- *Finding direction: yes.* ~15 cm between mics gives timing differences that resolve direction to
  roughly 5-10°. Choosing between known faces only needs people to be 20° or more apart.
- *Separating overlapping voices: partly.* How narrow a beam can be depends on array width versus the
  sound's wavelength, and most speech energy is between 300 Hz and 3 kHz. A simple (delay-and-sum) beam
  across 15 cm has almost no directivity at 1 kHz and is about 40° wide at 3 kHz. Two people who both fit
  in the glasses' ~44° view are closer together than that.
- *Adaptive beamformers* (MVDR, null-steering) do better because they aim a dead spot at the other
  talker. With 4-6 mics expect about 10-15 dB of suppression in a quiet room, much less in an echoey,
  noisy hall. That cleans up crosstalk noticeably but won't give two clean transcripts from people
  sitting close together. It works well when talkers are 40-60° or more apart (either side of a table).
- Hearing aids and smart glasses with a "conversation focus" feature work this way: helpful, not total isolation.

**Planned rev 2 build.** 4-6 digital MEMS mics (I2S/PDM) spread across the glasses frame or a headband,
on one board that samples them together (ESP32-S3 in TDM mode, Teensy 4, or similar); one camera-steered
adaptive beam per face; one transcription stream per face. The same array gives the sound direction
for the haptics. Shortcut: a ReSpeaker 4-mic Pi HAT (~$25) gives four synchronised channels straight
into the Pi, but its mics are only ~6 cm apart: fine for direction-finding, weaker at separating voices.
ODAS (open-source) does localisation, tracking and separation for arrays like these.

## Hardware notes

What this was built with, and what we learned about it:

- **XREAL One.** 1080p per eye, ~50° diagonal field of view, 3DoF head tracking done in the glasses,
  no camera, additive display (black = transparent). Needs a USB-C DisplayPort source, so a Raspberry
  Pi (HDMI) or a Jetson (full-size DisplayPort) can't drive it directly; hence the web page shown by the Beam Pro.
- **Beam Pro.** Android handheld; runs the caption page in Chrome and supplies the microphone. Mid-range
  chip, roughly 3 hours of battery while driving the glasses.
- **Audio source.** The Pi never touches audio. The mic is whichever input the device showing the page
  selects (Settings → Microphone): the Beam Pro's own mic, or the glasses' mics if they appear as a USB
  audio device. The glasses' mics are likely tuned for the wearer's voice; test before relying on them.
  Optional 5-minute check: if they expose two *raw* channels, a left/right timing cue across the head
  could be fused with the camera.
- **Raspberry Pi 5 + Pi camera.** Runs face tracking comfortably. The Pi has no analog input, so analog
  "sound sensor" modules can't feed it audio.
- **Sound sensor modules + Arduino** (from the hackathon kit). They output a rough loudness signal, not
  clean audio, and an Arduino can't sample several channels fast enough or at the same instant. No good
  for transcription, beamforming or timing-based direction. The Jetson build independently calibrates
  one SEN-12642 and one KY-038 for coarse left/right loudness: useful for loud nearby alerts, unreliable
  for quiet speech or precise direction. A future matched, synchronised array is the real solution.
- **Jetson Orin Nano.** The OAK-1, CSI, and USB-camera paths are implemented, with separate Arduino sound
  sensing and TITAN haptic services. The OAK-1 supplies 60 fps RGB input only; MediaPipe runs through
  the Jetson GPU delegate. See [docs/JETSON_SETUP.md](docs/JETSON_SETUP.md).
- **MediaPipe versions.** The portable Pi/macOS requirements stay on 0.10.18. The Jetson installer
  replaces that package with the checksum-verified 0.10.23 GPU wheel and its matching OpenCV 4.12 ABI.

## Tuning (pi/config.py, web/attribution.js)

| Symptom | Change |
|---|---|
| Speaking score stays low while someone talks | lower `speak_std_full` |
| Smiles/chewing count as speaking | raise `speak_on`, or lengthen `speak_window` |
| Captions land on the previous speaker | raise `visionLatencyMs` in `web/attribution.js` |
| Captions jump to a listener who nods or mouths along | raise `confident` / `margin` |
| Faces not found beyond ~2 m | raise resolution (`--width 1920 --height 1080`), costs fps |

## Tests

```bash
node --test tests/attribution.test.mjs
python3 tests/test_hardware_bridge.py
python3 tests/test_jetson_camera.py
```

## Known limits
- Only people inside the glasses' ~44° view get a floating caption; off-camera speech is not displayed.
- Lip detection needs a mostly frontal face. When someone turns away, their voice label takes over once it has been learned (a few sentences).
- Text trails speech by roughly half a second to a second.
- Tell people you're transcribing them.

Jetson wiring and haptics: [docs/JETSON_SETUP.md](docs/JETSON_SETUP.md). Other ports:
[docs/PORTING.md](docs/PORTING.md).
