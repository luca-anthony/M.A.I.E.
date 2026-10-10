import ast
import os
import shutil
import subprocess
import sys
import time

from .config import ROOT, resolve
from .textutil import best_match

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


class Projector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.library = resolve(cfg["library"])
        self.cache = resolve(cfg["cache"])
        self.library.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.process = None
        self.log = None

    def files(self):
        allowed = IMAGE_EXTENSIONS | {".pdf"}
        return sorted(p for p in self.library.iterdir() if p.suffix.lower() in allowed)

    def find(self, query):
        return best_match(query, self.files(), self.cfg["match_threshold"])

    def prepare(self, path):
        if path.suffix.lower() != ".pdf":
            return path
        converter = shutil.which("pdftoppm")
        if not converter:
            raise RuntimeError("pdftoppm is not installed")
        prefix = self.cache / path.stem
        subprocess.run(
            [converter, "-png", "-r", "150", "-f", "1", "-l", "1", "-singlefile", str(path), str(prefix)],
            check=True,
            capture_output=True,
        )
        return prefix.with_suffix(".png")

    def resolution(self):
        configured = self.cfg.get("resolution")
        if configured:
            return int(configured[0]), int(configured[1])
        if not self.cfg["fullscreen"]:
            return 1280, 720
        query = "import pygame; pygame.display.init(); print(pygame.display.get_desktop_sizes())"
        out = subprocess.run([sys.executable, "-c", query], capture_output=True, text=True, timeout=20)
        sizes = ast.literal_eval(out.stdout.strip().splitlines()[-1])
        index = max(0, min(self.cfg["display_index"], len(sizes) - 1))
        return int(sizes[index][0]), int(sizes[index][1])

    def show(self, path, raw=False):
        image = self.prepare(path)
        self.clear()
        command = [
            sys.executable,
            "-m",
            "maie.projector_window",
            "--image",
            str(image),
            "--display",
            str(self.cfg["display_index"]),
            "--rotate",
            str(self.cfg["rotate"]),
            "--scale",
            str(self.cfg["scale"]),
            "--offset-x",
            str(self.cfg["offset_x"]),
            "--offset-y",
            str(self.cfg["offset_y"]),
        ]
        if self.cfg["flip"]:
            command.append("--flip")
        if not self.cfg["fullscreen"]:
            command.append("--windowed")
        if raw:
            command.append("--raw")
        self.log = open(self.cache / "projector.log", "w")
        self.process = subprocess.Popen(
            command, cwd=str(ROOT), stdout=self.log, stderr=self.log, env=os.environ.copy()
        )
        time.sleep(0.8)
        if self.process.poll() not in (None, 0):
            self.process = None
            raise RuntimeError("projector window failed, see cache/projector.log")

    def clear(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None
