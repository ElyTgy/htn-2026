"""Luxonis OAK RGB camera through DepthAI.

The OAK supplies RGB frames; MediaPipe still performs face landmarks and lip
movement on the Jetson. This keeps the rest of the caption pipeline identical
to the Pi/USB-camera paths and works with both DepthAI 2 and 3.
"""
import threading
import time


class OakSource:
    # OAK is only the camera. Capture stays at display rate while Jetson inference consumes the
    # newest available frame at whatever rate it can sustain. There is never a frame backlog.
    WIDTH = 512
    HEIGHT = 384
    FPS = 60

    def __init__(self, cfg):
        self.cfg = cfg
        self._pipeline = None
        self._device = None
        self._queue = None
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = None
        self._latest = None
        self._latest_ts = 0.0
        self._sequence = 0
        self._read_sequence = -1
        self._error = None
        self.capture_fps = 0.0

    def start(self):
        try:
            import depthai as dai
        except ImportError as exc:
            raise RuntimeError(
                "DepthAI is not installed; on the Jetson run scripts/jetson_install.sh"
            ) from exc

        major = int(dai.__version__.split(".", 1)[0])
        if major >= 3:
            self._start_v3(dai)
        else:
            self._start_v2(dai)
        self._stop.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="oak-capture", daemon=True)
        self._thread.start()
        print(f"OAK RGB camera opened with DepthAI {dai.__version__}")

    def _start_v3(self, dai):
        pipeline = dai.Pipeline()
        camera = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        output = camera.requestOutput(
            size=(self.WIDTH, self.HEIGHT),
            type=dai.ImgFrame.Type.BGR888p,
            resizeMode=dai.ImgResizeMode.LETTERBOX,
            fps=self.FPS,
        )
        self._queue = output.createOutputQueue(maxSize=1, blocking=False)
        pipeline.start()
        self._pipeline = pipeline

    def _start_v2(self, dai):
        pipeline = dai.Pipeline()
        camera = pipeline.create(dai.node.ColorCamera)
        camera.setBoardSocket(dai.CameraBoardSocket.CAM_A)
        camera.setPreviewSize(self.WIDTH, self.HEIGHT)
        camera.setPreviewKeepAspectRatio(True)
        camera.setFps(self.FPS)
        output = pipeline.create(dai.node.XLinkOut)
        output.setStreamName("rgb")
        camera.preview.link(output.input)
        device = dai.Device(pipeline)
        self._queue = device.getOutputQueue("rgb", maxSize=1, blocking=False)
        self._device = device
        self._pipeline = pipeline

    def read(self):
        with self._condition:
            self._condition.wait_for(
                lambda: ((self._latest is not None and self._sequence != self._read_sequence)
                         or self._error or self._stop.is_set())
            )
            if self._error:
                raise RuntimeError(f"OAK capture failed: {self._error}")
            if self._latest is None:
                return None
            self._read_sequence = self._sequence
            return self._latest, self._latest_ts

    def latest_frame(self):
        with self._condition:
            return self._latest

    def _capture_loop(self):
        frames = 0
        window_start = time.monotonic()
        try:
            while not self._stop.is_set():
                packet = self._queue.get()
                bgr = packet.getCvFrame()
                if bgr is None:
                    continue
                now = time.monotonic()
                frames += 1
                elapsed = now - window_start
                if elapsed >= 1.0:
                    self.capture_fps = frames / elapsed
                    frames = 0
                    window_start = now
                # Mounted with its cable exiting at the top: rotate 180 degrees and convert
                # BGR -> RGB in one copy so display and inference see identical upright pixels.
                rgb = bgr[::-1, ::-1, ::-1].copy()
                with self._condition:
                    self._latest = rgb
                    self._latest_ts = now
                    self._sequence += 1
                    self._condition.notify_all()
        except Exception as exc:
            if not self._stop.is_set():
                with self._condition:
                    self._error = exc
                    self._condition.notify_all()

    def stop(self):
        self._stop.set()
        if self._device is not None:
            self._device.close()
            self._device = None
        elif self._pipeline is not None:
            stop = getattr(self._pipeline, "stop", None)
            if stop is not None:
                stop()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._queue = None
        self._pipeline = None
