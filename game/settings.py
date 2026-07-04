"""Config loading and shared constants."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

DEFAULTS = {
    "ollama": {
        "host": "http://127.0.0.1:11434",
        "model": "defyma85/gemma-4-E4B-it-ultra-uncensored-heretic-Q4_K_M_gguf",
        "fallback_to_any_model": True,
        "request_timeout_seconds": 120,
    },
    "director_interval_seconds": 60,
    "story_count": 3,
    "story_timeout_seconds": 240,
    "content_directive": "",
    "tts_enabled": True,
    "tts_rate_base": 170,
    "scale": 4,
    "internal_width": 320,
    "internal_height": 180,
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    path = os.path.join(ROOT, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    except FileNotFoundError:
        print("[config] config.json not found, using defaults")
    except ValueError as e:
        print("[config] config.json invalid, using defaults:", e)
    return cfg


CONFIG = load_config()
IW = int(CONFIG["internal_width"])
IH = int(CONFIG["internal_height"])
SCALE = int(CONFIG["scale"])
GROUND_Y = IH - 30
GRAVITY = 620.0
FPS = 60
