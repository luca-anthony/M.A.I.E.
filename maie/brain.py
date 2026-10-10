import os
import time
import urllib.request

import ollama

MODES = ("online", "pc", "local")
CHAINS = {
    "online": ("online", "local"),
    "pc": ("pc", "local"),
    "local": ("local",),
}


class BrainUnavailable(Exception):
    pass


class Brain:
    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = cfg["mode"]
        self.backends = cfg["backends"]
        self.system = cfg["system_prompt"]
        self.max_history = cfg["max_history"]
        self.keep_alive = cfg["keep_alive"]
        self.health_ttl = cfg["health_ttl"]
        self.probe_timeout = cfg["probe_timeout"]
        self.history = []
        self.active = None
        self.health = {}
        self.clients = {}

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError(mode)
        self.mode = mode
        self.health.clear()

    def headers(self, name):
        env = self.backends[name].get("api_key_env")
        key = os.environ.get(env) if env else None
        return {"Authorization": "Bearer " + key} if key else None

    def client(self, name):
        if name not in self.clients:
            backend = self.backends[name]
            self.clients[name] = ollama.Client(
                host=backend["host"],
                headers=self.headers(name),
                timeout=backend["timeout"],
            )
        return self.clients[name]

    def reachable(self, name):
        now = time.time()
        cached = self.health.get(name)
        if cached and now - cached[0] < self.health_ttl:
            return cached[1]
        url = self.backends[name]["host"].rstrip("/") + "/api/tags"
        request = urllib.request.Request(url, headers=self.headers(name) or {})
        try:
            with urllib.request.urlopen(request, timeout=self.probe_timeout) as response:
                ok = response.status == 200
        except Exception:
            ok = False
        self.health[name] = (now, ok)
        return ok

    def status(self):
        self.health.clear()
        rows = []
        for name in MODES:
            backend = self.backends[name]
            rows.append(
                {
                    "name": name,
                    "host": backend["host"],
                    "model": backend["model"],
                    "reachable": self.reachable(name),
                }
            )
        return rows

    def reset(self):
        self.history = []

    def remember(self, text, reply):
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": reply})
        overflow = len(self.history) - self.max_history
        if overflow > 0:
            self.history = self.history[overflow:]

    def messages(self, text, image):
        messages = [{"role": "system", "content": self.system}] + self.history
        user = {"role": "user", "content": text}
        if image:
            user["images"] = [image]
        messages.append(user)
        return messages

    def stream(self, text, image=None):
        errors = []
        for name in CHAINS[self.mode]:
            if not self.reachable(name):
                errors.append(f"{name}: unreachable")
                continue
            backend = self.backends[name]
            sent_text = text
            sent_image = image
            if image and not backend.get("vision"):
                sent_image = None
                sent_text = text + " (A camera image was captured but this model cannot view images.)"
            stored = ("[camera image] " + text) if image else text
            reply = []
            try:
                response = self.client(name).chat(
                    model=backend["model"],
                    messages=self.messages(sent_text, sent_image),
                    stream=True,
                    keep_alive=backend.get("keep_alive", self.keep_alive),
                    options=backend.get("options") or None,
                )
                for chunk in response:
                    piece = chunk["message"]["content"]
                    if not piece:
                        continue
                    if not reply:
                        self.active = name
                    reply.append(piece)
                    yield piece
            except Exception as exc:
                if reply:
                    self.remember(stored, "".join(reply))
                    raise
                self.health[name] = (time.time(), False)
                errors.append(f"{name}: {exc}")
                continue
            if not reply:
                errors.append(f"{name}: empty reply")
                continue
            self.remember(stored, "".join(reply))
            return
        raise BrainUnavailable("; ".join(errors))
