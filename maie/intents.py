import re

MODE_WORDS = {
    "online": "online",
    "cloud": "online",
    "pc": "pc",
    "computer": "pc",
    "desktop": "pc",
    "local": "local",
    "offline": "local",
    "fallback": "local",
}

MODE_RE = re.compile(
    r"\b(?:switch|change|go|set)\s+(?:over\s+)?(?:to\s+)?(?:the\s+)?(online|cloud|pc|computer|desktop|local|offline|fallback)\b",
    re.I,
)
RESET_RE = re.compile(
    r"\b(?:reset|clear|forget)\b.*\b(?:conversation|memory|history|chat|everything)\b", re.I
)
CALIBRATE_RE = re.compile(r"\b(?:re-?calibrate|calibrate|calibration)\b", re.I)
UNPROJECT_RE = re.compile(
    r"\b(?:stop|clear|hide|turn off|close|remove)\b.*\b(?:projection|projecting|projector|blueprint|schematic|display)\b",
    re.I,
)
PROJECT_RE = re.compile(
    r"^\W*(?:please\s+)?(?:project|display|show|put up|pull up)\s+(?:me\s+)?(?:the\s+|my\s+|a\s+)?(.+?)\W*$",
    re.I,
)


def parse(text, triggers):
    match = MODE_RE.search(text)
    if match:
        return ("mode", MODE_WORDS[match.group(1).lower()])
    if RESET_RE.search(text):
        return ("reset", None)
    if UNPROJECT_RE.search(text):
        return ("unproject", None)
    if CALIBRATE_RE.search(text):
        return ("calibrate", None)
    lowered = text.lower()
    if any(trigger in lowered for trigger in triggers):
        return ("see", None)
    match = PROJECT_RE.match(text)
    if match:
        return ("project", match.group(1))
    return None


class WakeGate:
    def __init__(self, cfg):
        words = "|".join(cfg["words"])
        self.pattern = re.compile(
            r"^\W*(?:(?:hey|hi|hello|ok|okay)\W+)?(?:" + words + r")\b\W*", re.I
        )

    def match(self, text):
        found = self.pattern.match(text)
        if not found:
            return False, text
        return True, text[found.end():].strip()
