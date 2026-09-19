"""Any camera OpenCV can open: a USB webcam, a laptop camera, a video file,
or (on a Jetson) a GStreamer pipeline string.

--source-arg examples:
  0                          first webcam
  clip.mp4                   a video file (loops)
  "nvarguscamerasrc ! ..."   Jetson CSI camera through GStreamer
"""
import time

import cv2


class OpenCvSource:
    def __init__(self, arg: str, cfg):
        self.cfg = cfg
        self.arg = arg or "0"
        self._cap = None
        self._is_file = False

    def start(self):
        self._open()

    def _open(self):
        if self._cap is not None:
            self._cap.release()
        if self.arg.isdigit():
            self._cap = cv2.VideoCapture(int(self.arg))
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
            self._cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        elif "!" in self.arg:
            self._cap = cv2.VideoCapture(self.arg, cv2.CAP_GSTREAMER)
        else:
            self._cap = cv2.VideoCapture(self.arg)
            self._is_file = True
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open camera/video: {self.arg}")

    def read(self):
        ok, bgr = self._cap.read()
        if not ok and self._is_file:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, bgr = self._cap.read()
        if not ok and not self._is_file:
            # Live cameras drop the odd frame, or stall briefly when another app touches them.
            # Keep trying for a while, reopening the device, before declaring the stream over.
            deadline = time.monotonic() + 10
            while not ok and time.monotonic() < deadline:
                print("\ncamera gave no frame; retrying...")
                time.sleep(0.5)
                try:
                    self._open()
                except RuntimeError:
                    continue
                ok, bgr = self._cap.read()
        if not ok:
            return None
        if self._is_file:
            time.sleep(1.0 / self.cfg.fps)  # play files at roughly real time
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), time.monotonic()

    def stop(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
