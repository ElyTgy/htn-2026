"""NVIDIA Jetson CSI camera through Argus, nvvidconv, GStreamer, and OpenCV.

The Jetson Orin Nano carrier exposes two CSI connectors, but the Argus sensor id is not
the connector number on every JetPack release. With no source argument this source tries
ids 0 and 1 and keeps the first one that actually returns a frame.
"""
import time


def gstreamer_pipeline(sensor_id: int, width: int, height: int, fps: int) -> str:
    """Return an appsink pipeline that delivers BGR frames to OpenCV."""
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM),width=(int){width},height=(int){height},"
        f"format=(string)NV12,framerate=(fraction){fps}/1 ! "
        "nvvidconv ! video/x-raw,format=(string)BGRx ! "
        "videoconvert ! video/x-raw,format=(string)BGR ! "
        "appsink drop=true max-buffers=1 sync=false"
    )


class JetsonCsiSource:
    def __init__(self, arg: str, cfg):
        self.cfg = cfg
        if arg and not arg.isdigit():
            raise ValueError("Jetson CSI --source-arg must be a sensor id such as 0 or 1")
        self.sensor_ids = [int(arg)] if arg else [0, 1]
        self.sensor_id = None
        self._cap = None
        self._first_frame = None
        self._cv2 = None

    def start(self):
        import cv2

        self._cv2 = cv2
        gst_line = next(
            (line for line in cv2.getBuildInformation().splitlines() if "GStreamer:" in line), ""
        )
        if "YES" not in gst_line:
            raise RuntimeError(
                "OpenCV has no GStreamer support. Use JetPack's apt-installed python3-opencv; "
                "do not install an opencv pip wheel in the Jetson virtual environment."
            )

        failures = []
        for sensor_id in self.sensor_ids:
            pipeline = gstreamer_pipeline(
                sensor_id, self.cfg.width, self.cfg.height, self.cfg.fps
            )
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if not cap.isOpened():
                failures.append(f"sensor-id {sensor_id}: pipeline did not open")
                cap.release()
                continue

            # isOpened() can succeed even when Argus has no camera at this id. Require a frame.
            deadline = time.monotonic() + 4.0
            ok, frame = False, None
            while time.monotonic() < deadline:
                ok, frame = cap.read()
                if ok:
                    break
                time.sleep(0.05)
            if ok:
                self.sensor_id = sensor_id
                self._cap = cap
                self._first_frame = frame
                print(f"Jetson CSI camera opened as Argus sensor-id {sensor_id}")
                return
            failures.append(f"sensor-id {sensor_id}: opened but returned no frame")
            cap.release()

        detail = "; ".join(failures)
        raise RuntimeError(
            "no Jetson CSI camera returned frames (" + detail + "). Run scripts/jetson_check.sh, "
            "verify the ribbon orientation and sensor driver, or use --source opencv for a USB camera."
        )

    def read(self):
        if self._first_frame is not None:
            bgr, self._first_frame = self._first_frame, None
            return self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2RGB), time.monotonic()

        ok, bgr = self._cap.read()
        if not ok:
            return None
        return self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2RGB), time.monotonic()

    def stop(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
