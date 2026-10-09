import os

from .config import resolve
from .textutil import best_match


class PrinterBridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.library = resolve(cfg["library"])
        self.library.mkdir(parents=True, exist_ok=True)
        self.printer = None

    def files(self):
        return sorted(p for p in self.library.iterdir() if p.name.lower().endswith(".3mf"))

    def find(self, query):
        return best_match(query, self.files(), self.cfg["match_threshold"])

    def connect(self):
        if self.printer is not None:
            return
        if not self.cfg["enabled"]:
            raise RuntimeError("printer is disabled in config.json")
        code = os.environ.get(self.cfg["access_code_env"], "")
        if not (self.cfg["ip"] and self.cfg["serial"] and code):
            raise RuntimeError("printer ip, serial, or access code is missing")
        import bambulabs_api as bl

        printer = bl.Printer(self.cfg["ip"], code, self.cfg["serial"])
        printer.connect()
        self.printer = printer

    def status(self):
        self.connect()
        return {
            "state": str(self.printer.get_state()),
            "progress": self.printer.get_percentage(),
            "bed": self.printer.get_bed_temperature(),
            "nozzle": self.printer.get_nozzle_temperature(),
        }

    def print_file(self, path):
        self.connect()
        with open(path, "rb") as handle:
            self.printer.upload_file(handle, path.name)
        self.printer.start_print(path.name, self.cfg["plate"])

    def close(self):
        if self.printer is not None:
            try:
                self.printer.disconnect()
            finally:
                self.printer = None
