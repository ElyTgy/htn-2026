"""Raspberry Pi camera via picamera2 (works for camera modules v1, v2, v3 and HQ).

picamera2 is installed with apt on Raspberry Pi OS, not pip, so the virtualenv
must be created with --system-site-packages.
"""
import time


class Picamera2Source:
    def __init__(self, cfg):
        self.cfg = cfg
        self._cam = None

    def start(self):
        from picamera2 import Picamera2

        self._cam = Picamera2()
        config = self._cam.create_video_configuration(
            # picamera2's "RGB888" is BGR byte order in memory; "BGR888" gives true RGB arrays.
            main={"size": (self.cfg.width, self.cfg.height), "format": "BGR888"},
            controls={"FrameRate": self.cfg.fps},
            buffer_count=2,
        )
        self._cam.configure(config)
        if "AfMode" in self._cam.camera_controls:
            # Camera Module 3 has a focus motor and starts in manual focus, which leaves faces
            # blurry. Continuous autofocus keeps people sharp as they move. (v1/v2 are fixed-focus.)
            from libcamera import controls
            self._cam.set_controls({"AfMode": controls.AfModeEnum.Continuous,
                                    "AfSpeed": controls.AfSpeedEnum.Fast})
        self._cam.start()

    def read(self):
        frame = self._cam.capture_array("main")
        return frame, time.monotonic()

    def stop(self):
        if self._cam is not None:
            self._cam.stop()
            self._cam.close()
            self._cam = None
