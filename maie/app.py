import queue
import re
import threading
import time

from audio import Listener
from brain import MODES, Brain, BrainUnavailable
from intents import WakeGate, parse
from printer import PrinterBridge
from projector import Projector
from speech import Speaker
from textutil import SentenceBuffer, clean
from vision import Camera

HELP = """Commands
  /mode online|pc|local   choose where the model runs
  /status                 show which backends are reachable
  /see [question]         look through the camera and answer
  /files                  list projection and print files
  /project name           project a file onto the desk
  /unproject              stop projecting
  /print name             send a .3mf to the printer (asks to confirm)
  /printer                show printer status
  /voice on|off           turn spoken replies on or off
  /reset                  forget the conversation
  /exit                   quit

Spoken examples
  "MAIE, what is this?"            looks through the camera
  "MAIE, project the bracket"      projects a matching file
  "MAIE, stop projecting"
  "MAIE, switch to local mode"
"""

YES = re.compile(r"^\W*(?:yes|yeah|yep|yup|confirm|confirmed|do it|go ahead|affirmative)\b", re.I)


class App:
    def __init__(self, cfg, text_only=False, no_tts=False):
        self.cfg = cfg
        self.name = cfg["assistant_name"]
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.responding = threading.Event()
        self.pending = None
        self.awake_until = 0.0
        self.last_active = None
        self.text_only = text_only

        tts_cfg = dict(cfg["tts"])
        if no_tts:
            tts_cfg["enabled"] = False
        self.speaker = Speaker(tts_cfg, cfg["audio"]["output_device"])
        self.brain = Brain(cfg)
        self.camera = Camera(cfg["camera"])
        self.projector = Projector(cfg["projector"])
        self.printer = PrinterBridge(cfg["printer"])
        self.wake = WakeGate(cfg["wake"])
        self.sentences = SentenceBuffer(tts_cfg["min_sentence_chars"])
        self.listener = None
        if not text_only:
            self.listener = Listener(
                cfg["listen"],
                cfg["stt"],
                cfg["audio"]["input_device"],
                self.is_muted,
            )

    def is_muted(self):
        return self.responding.is_set() or self.speaker.busy()

    def notify(self, message):
        print(f"{self.name}: {message}")
        self.speaker.say(clean(message))
        self.awake_until = time.time() + self.cfg["wake"]["follow_up_seconds"]

    def keyboard_loop(self):
        while not self.stop.is_set():
            try:
                line = input()
            except (EOFError, OSError):
                return
            line = line.strip()
            if line:
                self.events.put(("text", line))

    def voice_loop(self):
        try:
            self.listener.load()
        except Exception as exc:
            print(f"[voice input unavailable: {exc}]")
            return
        print("[voice input ready]")
        failures = 0
        while not self.stop.is_set():
            try:
                text = self.listener.listen(self.stop)
                failures = 0
            except Exception as exc:
                failures += 1
                print(f"[microphone error: {exc}]")
                if failures >= 5:
                    print("[voice input stopped]")
                    return
                time.sleep(2)
                continue
            if text:
                self.events.put(("voice", text))

    def run(self):
        print(f"Starting {self.name} (profile {self.cfg['profile']}, mode {self.brain.mode})")
        self.speaker.start()
        threading.Thread(target=self.keyboard_loop, daemon=True).start()
        if self.listener is not None:
            threading.Thread(target=self.voice_loop, daemon=True).start()
        self.show_status()
        print("Type a message or speak. Type /help for commands.")
        while not self.stop.is_set():
            try:
                kind, text = self.events.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.handle(kind, text)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"[error: {exc}]")

    def shutdown(self):
        self.stop.set()
        self.projector.clear()
        self.camera.close()
        self.printer.close()

    def show_status(self):
        for row in self.brain.status():
            state = "reachable" if row["reachable"] else "unreachable"
            marker = "*" if row["name"] == self.brain.mode else " "
            print(f" {marker} {row['name']:7} {state:12} {row['model']} @ {row['host']}")

    def handle(self, kind, text):
        if kind == "voice":
            print(f"You (voice): {text}")
            text = self.apply_wake(text)
            if text is None:
                return
        if self.pending is not None:
            self.resolve_pending(text)
            return
        if text.startswith("/"):
            self.command(text)
            return
        intent = parse(text, self.cfg["vision_triggers"])
        if intent:
            action, argument = intent
            if action == "mode":
                self.set_mode(argument)
                return
            if action == "reset":
                self.brain.reset()
                self.notify("Conversation cleared.")
                return
            if action == "unproject":
                self.projector.clear()
                self.notify("Projection cleared.")
                return
            if action == "see":
                self.ask(text, with_image=True)
                return
            if action == "project":
                path = self.projector.find(argument)
                if path is not None:
                    self.project(path)
                    return
        self.ask(text)

    def apply_wake(self, text):
        if not self.cfg["wake"]["enabled"]:
            return text
        matched, rest = self.wake.match(text)
        awake = time.time() < self.awake_until
        if not matched and not awake:
            return None
        if matched and not rest:
            self.notify("Yes?")
            return None
        return rest if matched else text

    def set_mode(self, mode):
        self.brain.set_mode(mode)
        if mode != "local" and not self.brain.reachable(mode):
            self.notify(f"Switched to {mode} mode, but it is not reachable, so I will use the local model for now.")
        else:
            self.notify(f"Switched to {mode} mode.")

    def ask(self, text, with_image=False):
        self.responding.set()
        try:
            image = None
            if with_image:
                try:
                    image = self.camera.capture()
                except Exception as exc:
                    self.notify(f"I could not use the camera: {exc}")
                    return
            self.sentences.flush()
            started = False
            try:
                for piece in self.brain.stream(text, image):
                    if not started:
                        print(f"{self.name}: ", end="", flush=True)
                        started = True
                    print(piece, end="", flush=True)
                    for sentence in self.sentences.feed(piece):
                        self.speaker.say(clean(sentence))
            finally:
                tail = self.sentences.flush()
                if tail:
                    self.speaker.say(clean(tail))
                if started:
                    print()
            if self.brain.active != self.last_active:
                backend = self.brain.backends[self.brain.active]
                print(f"[{self.brain.active}: {backend['model']}]")
                self.last_active = self.brain.active
        except BrainUnavailable as exc:
            self.notify("I cannot reach any model right now.")
            print(f"[{exc}]")
        except Exception as exc:
            print(f"\n[error: {exc}]")
        finally:
            self.speaker.wait()
            self.awake_until = time.time() + self.cfg["wake"]["follow_up_seconds"]
            self.responding.clear()

    def project(self, path):
        try:
            self.projector.show(path)
            self.notify(f"Projecting {path.stem}.")
        except Exception as exc:
            self.notify(f"I could not project that: {exc}")

    def request_print(self, query):
        path = self.printer.find(query)
        if path is None:
            self.notify("I could not find a matching print file.")
            return
        self.pending = ("print", path)
        self.notify(f"Start printing {path.stem}? Say or type yes to confirm.")

    def resolve_pending(self, text):
        action, payload = self.pending
        self.pending = None
        if not YES.match(text):
            self.notify("Cancelled.")
            return
        if action == "print":
            try:
                self.printer.print_file(payload)
                self.notify(f"Sent {payload.stem} to the printer.")
            except Exception as exc:
                self.notify(f"Printing failed: {exc}")

    def command(self, line):
        parts = line.split(None, 1)
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        if command in ("/exit", "/quit"):
            self.stop.set()
        elif command == "/help":
            print(HELP)
        elif command == "/status":
            self.show_status()
        elif command == "/mode":
            if argument.lower() in MODES:
                self.set_mode(argument.lower())
            else:
                print("Usage: /mode online|pc|local")
        elif command == "/reset":
            self.brain.reset()
            self.notify("Conversation cleared.")
        elif command == "/see":
            self.ask(argument or "Describe what you see on the desk.", with_image=True)
        elif command == "/files":
            print("Projection files:", ", ".join(p.name for p in self.projector.files()) or "none")
            print("Print files:", ", ".join(p.name for p in self.printer.files()) or "none")
        elif command == "/project":
            path = self.projector.find(argument)
            if path is None:
                self.notify("I could not find a matching projection file.")
            else:
                self.project(path)
        elif command == "/unproject":
            self.projector.clear()
        elif command == "/print":
            self.request_print(argument)
        elif command == "/printer":
            try:
                print(self.printer.status())
            except Exception as exc:
                print(f"[printer error: {exc}]")
        elif command == "/voice":
            self.speaker.enabled = argument.lower() != "off"
            print(f"Spoken replies {'on' if self.speaker.enabled else 'off'}")
        else:
            print("Unknown command. Type /help.")
