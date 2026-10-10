import time

import cv2
import numpy as np
import sounddevice as sd

NAMES = ["center", "top-left", "top-right", "bottom-left", "bottom-right"]
FRACTIONS = {
    "center": (0.5, 0.5),
    "top-left": (0.15, 0.15),
    "top-right": (0.85, 0.15),
    "bottom-left": (0.15, 0.85),
    "bottom-right": (0.85, 0.85),
}


def checker(width, height, square):
    ys, xs = np.indices((height, width))
    return ((((xs // square) + (ys // square)) % 2) * 255).astype(np.uint8)


class FocusAssist:
    def __init__(self, cfg, camera, projector, calibration, device):
        self.cfg = cfg
        self.camera = camera
        self.projector = projector
        self.calibration = calibration
        self.device = device

    def boxes(self, shape):
        height, width = shape
        half = max(8, int(min(width, height) * 0.06))
        calibration = self.calibration()
        points = {}
        if calibration is None:
            points["center"] = (0.5, 0.5)
        else:
            size_w, size_h = calibration.size
            for name in NAMES:
                fx, fy = FRACTIONS[name]
                points[name] = calibration.to_camera(size_w * fx, size_h * fy)
        boxes = {}
        for name, (u, v) in points.items():
            cx = int(min(max(u * width, half), width - half))
            cy = int(min(max(v * height, half), height - half))
            boxes[name] = (slice(cy - half, cy + half), slice(cx - half, cx + half))
        return boxes

    def scores(self, gray):
        return {
            name: float(cv2.Laplacian(gray[box], cv2.CV_64F).var())
            for name, box in self.boxes(gray.shape).items()
        }

    def beep(self, ratio):
        rate = 22050
        duration = 0.12
        t = np.arange(int(rate * duration)) / rate
        frequency = 250 + 900 * ratio ** 3
        wave = np.sin(2 * np.pi * frequency * t)
        fade = np.minimum(1.0, np.minimum(t, duration - t) / 0.01)
        sd.play((0.25 * wave * fade).astype(np.float32), rate, device=self.device)

    def run(self, stop, report):
        size = self.projector.resolution()
        square = max(6, size[0] // 160)
        file = self.projector.cache / "focus_pattern.png"
        cv2.imwrite(str(file), checker(size[0], size[1], square))
        self.projector.show(file, raw=True)
        time.sleep(1.5)
        try:
            self.camera.open()
            self.camera.lock_focus()
            peaks = {}
            deadline = time.time() + self.cfg["timeout_seconds"]
            while not stop.is_set() and time.time() < deadline:
                frame = self.camera.frame()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                current = self.scores(gray)
                for name, value in current.items():
                    peaks[name] = max(peaks.get(name, 1e-6), value)
                ratios = {name: current[name] / peaks[name] for name in current}
                report(ratios)
                if self.cfg["tone"]:
                    self.beep(ratios["center"])
                time.sleep(self.cfg["interval"])
        finally:
            self.projector.clear()
