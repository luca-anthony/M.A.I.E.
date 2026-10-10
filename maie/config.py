import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


DEFAULTS = {
    "calibration": {
        "file": "calibration.json",
        "cols": 4,
        "rows": 3,
        "settle_seconds": 2.0,
        "attempts": 8,
        "min_markers": 6,
        "max_rms": 5.0,
        "ransac_pixels": 6.0,
        "autofocus": True,
        "auto_on_start": False,
    },
    "focus_assist": {"interval": 0.25, "timeout_seconds": 120, "tone": True},
    "projector": {"resolution": None},
}


def merge(base, extra):
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def detect_profile():
    try:
        model = Path("/proc/device-tree/model").read_text(errors="ignore")
    except OSError:
        return "pc"
    return "pi" if "Raspberry Pi" in model else "pc"


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def load(path=None, profile=None, mode=None):
    load_env(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.json"
    cfg = merge(DEFAULTS, json.loads(cfg_path.read_text()))
    chosen = profile or cfg.get("profile", "auto")
    if chosen == "auto":
        chosen = detect_profile()
    cfg = merge(cfg, cfg.get("profiles", {}).get(chosen, {}))
    cfg["profile"] = chosen
    if mode:
        cfg["mode"] = mode
    return cfg
