"""Append-only JSONL session trace for offline analysis.

One file per run in logs/session_<stamp>.jsonl, one JSON object per line:
LLM exchanges (prompt, response, latency), parse/validation outcomes,
gameplay deeds, director actions, errors. Safe to tail while playing;
feed a finished session to an LLM or a notebook to study pacing, prompt
failure rates, tool-usage patterns and where the story machinery stalls.

Disable with "trace_log": false in config.json.
"""
import json
import os
import threading
import time


class Trace:
    def __init__(self):
        self._lock = threading.Lock()
        self._f = None
        self._t0 = 0.0
        self.path = None

    def start(self, root, enabled=True):
        if not enabled or self._f:
            return
        try:
            log_dir = os.path.join(root, "logs")
            os.makedirs(log_dir, exist_ok=True)
            self.path = os.path.join(
                log_dir, time.strftime("session_%Y%m%d_%H%M%S.jsonl"))
            self._f = open(self.path, "a", encoding="utf-8")
        except OSError as e:
            print("[trace] disabled:", e)
            self._f = None
            return
        self._t0 = time.monotonic()
        self.log("session_start", stamp=time.strftime("%Y-%m-%d %H:%M:%S"))

    def log(self, kind, **data):
        """Thread-safe append. `t` is seconds since session start."""
        if not self._f:
            return
        rec = {"t": round(time.monotonic() - self._t0, 2), "kind": kind}
        rec.update(data)
        try:
            line = json.dumps(rec, ensure_ascii=False, default=str)
            with self._lock:
                self._f.write(line + "\n")
                self._f.flush()
        except (OSError, ValueError, TypeError):
            pass  # the trace must never hurt the game


TRACE = Trace()
