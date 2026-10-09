import collections
import queue

import numpy as np
import sounddevice as sd

JUNK = {"you", "thank you", "thanks", "thanks for watching", "bye"}


class Listener:
    def __init__(self, listen_cfg, stt_cfg, device, muted):
        self.cfg = listen_cfg
        self.stt = stt_cfg
        self.device = device
        self.muted = muted
        self.rate = 16000
        self.model = None
        self.ambient = None

    def load(self):
        if self.model is not None:
            return
        from faster_whisper import WhisperModel

        print(f"[loading speech model {self.stt['model']}]")
        try:
            self.model = WhisperModel(
                self.stt["model"],
                device=self.stt["device"],
                compute_type=self.stt["compute_type"],
            )
        except Exception as exc:
            print(f"[speech model failed ({exc}); using {self.stt['fallback_model']} on cpu]")
            self.model = WhisperModel(
                self.stt["fallback_model"], device="cpu", compute_type="int8"
            )

    def threshold(self):
        return max(self.cfg["min_level"], self.ambient * self.cfg["level_multiplier"])

    def record(self, stop):
        block_seconds = self.cfg["block_seconds"]
        block = int(self.rate * block_seconds)
        blocks = queue.Queue()

        def callback(indata, frames, time_info, status):
            blocks.put(indata[:, 0].copy())

        preroll = collections.deque(maxlen=max(1, int(self.cfg["preroll_seconds"] / block_seconds)))
        frames = []
        speaking = False
        silent = 0
        voiced = 0
        calibration = []

        with sd.InputStream(
            samplerate=self.rate,
            channels=1,
            dtype="float32",
            blocksize=block,
            device=self.device,
            callback=callback,
        ):
            while not stop.is_set():
                try:
                    chunk = blocks.get(timeout=0.25)
                except queue.Empty:
                    continue
                level = float(np.sqrt(np.mean(chunk ** 2)))
                if self.muted():
                    preroll.clear()
                    frames = []
                    speaking = False
                    silent = 0
                    voiced = 0
                    continue
                if self.ambient is None:
                    calibration.append(level)
                    if len(calibration) * block_seconds >= self.cfg["ambient_seconds"]:
                        self.ambient = float(np.median(calibration))
                    continue
                limit = self.threshold()
                if not speaking:
                    preroll.append(chunk)
                    if level > limit:
                        speaking = True
                        frames = list(preroll)
                        voiced = 1
                        silent = 0
                    else:
                        self.ambient = 0.95 * self.ambient + 0.05 * level
                    continue
                frames.append(chunk)
                if level > limit:
                    voiced += 1
                    silent = 0
                else:
                    silent += 1
                if (
                    silent * block_seconds >= self.cfg["silence_seconds"]
                    or len(frames) * block_seconds >= self.cfg["max_seconds"]
                ):
                    break

        if stop.is_set() or not speaking:
            return None
        if voiced * block_seconds < self.cfg["min_speech_seconds"]:
            return None
        return np.concatenate(frames)

    def transcribe(self, audio):
        self.load()
        segments, _ = self.model.transcribe(
            audio,
            language=self.stt["language"],
            beam_size=self.stt["beam_size"],
            vad_filter=True,
            condition_on_previous_text=False,
        )
        parts = [
            segment.text.strip()
            for segment in segments
            if segment.no_speech_prob < self.stt["no_speech_max"]
        ]
        text = " ".join(part for part in parts if part).strip()
        if text.lower().strip(" .!?,") in JUNK:
            return ""
        return text

    def listen(self, stop):
        audio = self.record(stop)
        if audio is None:
            return ""
        return self.transcribe(audio)
