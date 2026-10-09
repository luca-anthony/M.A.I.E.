import difflib
import re

BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def clean(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#`>~|]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class SentenceBuffer:
    def __init__(self, min_chars):
        self.min_chars = min_chars
        self.buffer = ""

    def feed(self, piece):
        self.buffer += piece
        out = []
        while True:
            match = BOUNDARY.search(self.buffer, self.min_chars)
            if not match:
                break
            out.append(self.buffer[: match.start()])
            self.buffer = self.buffer[match.end():]
        return out

    def flush(self):
        rest = self.buffer.strip()
        self.buffer = ""
        return rest


def normalize(text):
    return re.sub(r"[\s_\-]+", " ", text.lower()).strip()


def best_match(query, paths, threshold):
    query = normalize(query)
    if not query:
        return None
    best = None
    best_score = 0.0
    for path in paths:
        name = normalize(path.name.split(".")[0])
        score = difflib.SequenceMatcher(None, query, name).ratio()
        if query in name or name in query:
            score = max(score, 0.9)
        if score > best_score:
            best = path
            best_score = score
    return best if best_score >= threshold else None
