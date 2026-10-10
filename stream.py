import argparse
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from maie import config

PAGE = b"""<!doctype html>
<html><head><meta charset="utf-8"><title>MAIE camera</title>
<style>html,body{margin:0;height:100%;background:#111}img{width:100%;height:100%;object-fit:contain}</style>
</head><body><img src="/stream.mjpg"></body></html>"""


class Latest:
    def __init__(self):
        self.condition = threading.Condition()
        self.jpeg = None
        self.count = 0

    def put(self, jpeg):
        with self.condition:
            self.jpeg = jpeg
            self.count += 1
            self.condition.notify_all()

    def wait(self, seen):
        with self.condition:
            self.condition.wait_for(lambda: self.count != seen, timeout=5)
            return self.jpeg, self.count


def capture_loop(grab, latest, width, quality, fps, stop):
    delay = 1.0 / fps
    while not stop.is_set():
        started = time.time()
        try:
            frame = grab()
        except Exception as exc:
            print(f"camera error: {exc}")
            time.sleep(2)
            continue
        height, full = frame.shape[:2]
        if full > width:
            frame = cv2.resize(frame, (width, int(height * width / full)))
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok:
            latest.put(buffer.tobytes())
        time.sleep(max(0.0, delay - (time.time() - started)))


def make_handler(latest):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(PAGE)))
                self.end_headers()
                self.wfile.write(PAGE)
            elif self.path.startswith("/snapshot.jpg"):
                jpeg, _ = latest.wait(-1)
                if jpeg is None:
                    self.send_error(503)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg)
            elif self.path.startswith("/stream.mjpg"):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                seen = 0
                try:
                    while True:
                        jpeg, count = latest.wait(seen)
                        if jpeg is None or count == seen:
                            continue
                        seen = count
                        head = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                        self.wfile.write(head + jpeg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
            else:
                self.send_error(404)

        def log_message(self, *args):
            pass

    return Handler


def lan_address():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def marker_grab(camera):
    from maie.calibration import detect

    def grab():
        frame = camera.frame()
        corners, ids = detect(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        count = 0 if ids is None else len(ids)
        if count:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        cv2.putText(frame, f"markers: {count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 2)
        return frame

    return grab


def parse():
    parser = argparse.ArgumentParser(prog="stream.py")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--quality", type=int, default=80)
    parser.add_argument("--markers", action="store_true")
    parser.add_argument("--profile", choices=["pc", "pi"])
    parser.add_argument("--config")
    return parser.parse_args()


def main():
    args = parse()
    cfg = config.load(args.config, args.profile)
    
        # 1. Safely update the camera index inside the configuration dictionary
    if isinstance(cfg.get("camera"), dict):
        # Update whichever key your config uses (commonly 'index' or 'device')
        if "index" in cfg["camera"]:
            cfg["camera"]["index"] = 8
        elif "device" in cfg["camera"]:
            cfg["camera"]["device"] = 8
        else:
            # If the key name is unknown, force an 'index' key
            cfg["camera"]["index"] = 8
    
    from maie.vision import Camera

    camera = Camera(cfg["camera"])
    camera.open()
    grab = marker_grab(camera) if args.markers else camera.frame
    latest = Latest()
    stop = threading.Event()
    threading.Thread(
        target=capture_loop, args=(grab, latest, args.width, args.quality, args.fps, stop), daemon=True
    ).start()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(latest))
    server.daemon_threads = True
    host = socket.gethostname()
    print("Camera view is live. Open one of these in a browser on your PC:")
    print(f"  http://{host}.local:{args.port}")
    print(f"  http://{host}:{args.port}   (over Tailscale)")
    print(f"  http://{lan_address()}:{args.port}")
    print("Press Ctrl+C to stop. Stop this before running main.py, since only one program can use the camera.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        camera.close()


if __name__ == "__main__":
    main()