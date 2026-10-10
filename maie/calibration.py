import json
import time

import cv2
import numpy as np

from .config import resolve


class CalibrationError(Exception):
    pass


def dictionary():
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def marker_image(marker_id, size):
    if hasattr(cv2.aruco, "generateImageMarker"):
        return cv2.aruco.generateImageMarker(dictionary(), marker_id, size)
    image = np.zeros((size, size), np.uint8)
    cv2.aruco.drawMarker(dictionary(), marker_id, size, image, 1)
    return image


def make_pattern(width, height, cols, rows):
    image = np.full((height, width), 255, np.uint8)
    cell_w = width // cols
    cell_h = height // rows
    size = int(min(cell_w, cell_h) * 0.6)
    layout = {}
    for row in range(rows):
        for col in range(cols):
            marker_id = row * cols + col
            x0 = col * cell_w + (cell_w - size) // 2
            y0 = row * cell_h + (cell_h - size) // 2
            image[y0:y0 + size, x0:x0 + size] = marker_image(marker_id, size)
            corners = np.array(
                [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size]],
                dtype=np.float64,
            )
            layout[marker_id] = corners - 0.5
    return image, layout


def detect(gray):
    if hasattr(cv2.aruco, "ArucoDetector"):
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        detector = cv2.aruco.ArucoDetector(dictionary(), params)
        corners, ids, _ = detector.detectMarkers(gray)
    else:
        params = cv2.aruco.DetectorParameters_create()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary(), parameters=params)
    return corners, ids


def correspondences(corners, ids, layout, frame_size):
    if ids is None:
        return None, None, 0
    width, height = frame_size
    scale = np.array([width, height], dtype=np.float64)
    seen = []
    expected = []
    used = 0
    for quad, marker_id in zip(corners, ids.flatten()):
        marker_id = int(marker_id)
        if marker_id not in layout:
            continue
        seen.extend(quad.reshape(4, 2).astype(np.float64) / scale)
        expected.extend(layout[marker_id])
        used += 1
    if used == 0:
        return None, None, 0
    return np.array(seen), np.array(expected), used


def solve(corners, ids, layout, frame_size, threshold):
    seen, expected, used = correspondences(corners, ids, layout, frame_size)
    if used < 4:
        return None
    matrix, mask = cv2.findHomography(seen, expected, cv2.RANSAC, threshold)
    if matrix is None:
        return None
    inliers = mask.ravel().astype(bool)
    if inliers.sum() < 12:
        return None
    refined, _ = cv2.findHomography(seen[inliers], expected[inliers], 0)
    if refined is not None:
        matrix = refined
    mapped = cv2.perspectiveTransform(seen.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    errors = np.linalg.norm(mapped - expected, axis=1)
    rms = float(np.sqrt(np.mean(errors[inliers] ** 2)))
    return matrix, rms, used


class Calibration:
    def __init__(self, matrix, size, rms, markers, stamp=None):
        self.matrix = np.array(matrix, dtype=np.float64)
        self.inverse = np.linalg.inv(self.matrix)
        self.size = (int(size[0]), int(size[1]))
        self.rms = float(rms)
        self.markers = int(markers)
        self.stamp = float(stamp) if stamp else time.time()

    @staticmethod
    def map_point(matrix, a, b):
        out = cv2.perspectiveTransform(np.array([[[a, b]]], dtype=np.float64), matrix)[0][0]
        return float(out[0]), float(out[1])

    def to_projector(self, u, v):
        return self.map_point(self.matrix, u, v)

    def to_camera(self, x, y):
        return self.map_point(self.inverse, x, y)

    def area_in_camera(self):
        width, height = self.size
        return [self.to_camera(x, y) for x, y in ((0, 0), (width, 0), (width, height), (0, height))]

    def save(self, path):
        data = {
            "matrix": self.matrix.tolist(),
            "size": list(self.size),
            "rms": self.rms,
            "markers": self.markers,
            "stamp": self.stamp,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path):
        data = json.loads(path.read_text())
        return cls(data["matrix"], data["size"], data["rms"], data["markers"], data["stamp"])


class Calibrator:
    def __init__(self, cfg, camera, projector):
        self.cfg = cfg
        self.camera = camera
        self.projector = projector
        self.path = resolve(cfg["file"])

    def load(self):
        if not self.path.exists():
            return None
        try:
            return Calibration.load(self.path)
        except Exception:
            return None

    def show_pattern(self):
        size = self.projector.resolution()
        pattern, layout = make_pattern(size[0], size[1], self.cfg["cols"], self.cfg["rows"])
        file = self.projector.cache / "calibration_pattern.png"
        cv2.imwrite(str(file), pattern)
        self.projector.show(file, raw=True)
        time.sleep(self.cfg["settle_seconds"])
        return size, layout

    def observe(self, layout):
        frame = self.camera.frame()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids = detect(gray)
        height, width = gray.shape
        return frame, corners, ids, (width, height)

    def save_debug(self, frame, corners, ids):
        if frame is None:
            return
        shown = frame.copy()
        if ids is not None and len(ids):
            cv2.aruco.drawDetectedMarkers(shown, corners, ids)
        cv2.imwrite(str(self.projector.cache / "calibration_debug.jpg"), shown)

    def run(self):
        size, layout = self.show_pattern()
        try:
            self.camera.open()
            lens = self.camera.lock_focus() if self.cfg["autofocus"] else None
            best = None
            last = (None, None, None)
            for _ in range(self.cfg["attempts"]):
                frame, corners, ids, frame_size = self.observe(layout)
                last = (frame, corners, ids)
                result = solve(corners, ids, layout, frame_size, self.cfg["ransac_pixels"])
                if result is not None and (best is None or result[1] < best[1]):
                    best = result
                if best is not None and best[1] <= self.cfg["max_rms"] and best[2] >= self.cfg["min_markers"]:
                    break
                time.sleep(0.4)
            if best is None or best[2] < self.cfg["min_markers"]:
                self.save_debug(*last)
                found = 0 if last[2] is None else len(last[2])
                raise CalibrationError(
                    f"I could only see {found} markers. Make sure the camera sees the whole projected area "
                    f"and the room is not too bright. The camera view is saved in cache/calibration_debug.jpg."
                )
            calibration = Calibration(best[0], size, best[1], best[2])
            calibration.save(self.path)
            return calibration, lens
        finally:
            self.projector.clear()

    def verify(self, calibration):
        size, layout = self.show_pattern()
        try:
            if tuple(size) != calibration.size:
                return None
            self.camera.open()
            frame, corners, ids, frame_size = self.observe(layout)
            seen, expected, used = correspondences(corners, ids, layout, frame_size)
            if used < self.cfg["min_markers"]:
                return None
            mapped = cv2.perspectiveTransform(seen.reshape(-1, 1, 2), calibration.matrix).reshape(-1, 2)
            return float(np.median(np.linalg.norm(mapped - expected, axis=1)))
        finally:
            self.projector.clear()
