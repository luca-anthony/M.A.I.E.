import io
import queue
import shutil
import subprocess
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from .config import resolve


class Speaker:
    def __init__(self, cfg, device):
        self.cfg = cfg
        self.device = device
        self.enabled = cfg["enabled"]
        self.jobs = queue.Queue()
        self.synth = None
        self.backend = None
        self.pending = 0
        self.lock = threading.Lock()
        self.last_end = 0.0

    def start(self):
        if not self.enabled:
            return
        for name in self.cfg["order"]:
            try:
                self.synth = getattr(self, "_" + name)()
                self.backend = name
                break
            except Exception as exc:
                print(f"[speech output {name} unavailable: {exc}]")
        if self.synth is None:
            self.enabled = False
            print("[speech output disabled]")
            return
        print(f"[speech output: {self.backend}]")
        threading.Thread(target=self._run, daemon=True).start()

    def _kokoro(self):
        from kokoro import KPipeline

        pipeline = KPipeline(lang_code=self.cfg["kokoro_lang"])
        voice = self.cfg["kokoro_voice"]

        def synth(text):
            parts = []
            for _, _, audio in pipeline(text, voice=voice):
                if audio is None:
                    continue
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                parts.append(np.asarray(audio, dtype="float32"))
            return (np.concatenate(parts) if parts else None), 24000

        return synth

    def _piper(self):
        from piper import PiperVoice

        voice = PiperVoice.load(str(resolve(self.cfg["piper_model"])))

        def synth(text):
            parts = []
            rate = 22050
            for chunk in voice.synthesize(text):
                parts.append(np.asarray(chunk.audio_float_array, dtype="float32"))
                rate = chunk.sample_rate
            return (np.concatenate(parts) if parts else None), rate

        return synth

    def _espeak(self):
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise RuntimeError("espeak is not installed")

        def synth(text):
            out = subprocess.run([binary, "--stdout", text], capture_output=True, check=True).stdout
            data, rate = sf.read(io.BytesIO(out), dtype="float32")
            return data, rate

        return synth

    def _run(self):
        while True:
            text = self.jobs.get()
            try:
                data, rate = self.synth(text)
                if data is not None and len(data):
                    sd.play(data, rate, device=self.device)
                    sd.wait()
            except Exception as exc:
                print(f"[speech error: {exc}]")
            finally:
                self.last_end = time.time()
                with self.lock:
                    self.pending -= 1
                self.jobs.task_done()

    def say(self, text):
        if not self.enabled or self.synth is None or not text:
            return
        with self.lock:
            self.pending += 1
        self.jobs.put(text)

    def busy(self):
        if self.pending > 0:
            return True
        return time.time() - self.last_end < self.cfg["mute_tail_seconds"]

    def wait(self):
        if self.enabled and self.synth is not None:
            self.jobs.join()
