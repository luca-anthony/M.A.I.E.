import time

import cv2

from .config import resolve

ROTATIONS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


class Camera:
    def __init__(self, cfg):
        self.cfg = cfg
        self.save_dir = resolve(cfg["save_dir"])
        self.kind = None
        self.device = None

    def open(self):
        if self.device is not None:
            return
        if self.cfg["backend"] == "picamera2":
            try:
                self._open_picamera()
                return
            except Exception as exc:
                print(f"[picamera2 unavailable ({exc}); trying opencv]")
        self._open_opencv()

    def _open_picamera(self):
        from picamera2 import Picamera2

        camera = Picamera2()
        size = (self.cfg["width"], self.cfg["height"])
        camera.configure(camera.create_still_configuration(main={"size": size, "format": "RGB888"}))
        camera.start()
        try:
            from libcamera import controls

            camera.set_controls({"AfMode": controls.AfModeEnum.Continuous})
        except Exception:
            pass
        time.sleep(self.cfg["warmup_seconds"])
        self.device = camera
        self.kind = "picamera2"

    def _open_opencv(self):
        capture = cv2.VideoCapture(self.cfg["index"])
        if not capture.isOpened():
            raise RuntimeError("no camera found")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg["width"])
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg["height"])
        for _ in range(5):
            capture.read()
        self.device = capture
        self.kind = "opencv"

    def read(self):
        if self.kind == "picamera2":
            return self.device.capture_array()
        ok, frame = self.device.read()
        if not ok:
            raise RuntimeError("camera returned no frame")
        return frame

    def capture(self):
        self.open()
        frame = self.read()
        height, width = frame.shape[:2]
        scale = min(1.0, self.cfg["max_side"] / max(height, width))
        if scale < 1.0:
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
        rotation = ROTATIONS.get(self.cfg["rotate"])
        if rotation is not None:
            frame = cv2.rotate(frame, rotation)
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise RuntimeError("could not encode frame")
        data = buffer.tobytes()
        self.save_dir.mkdir(parents=True, exist_ok=True)
        (self.save_dir / "last.jpg").write_bytes(data)
        return data

    def close(self):
        if self.device is None:
            return
        try:
            if self.kind == "picamera2":
                self.device.stop()
                self.device.close()
            else:
                self.device.release()
        finally:
            self.device = None
            self.kind = None
