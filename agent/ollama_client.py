"""Thin client for a local Ollama server with model-fallback."""
import threading
import time

import requests

from .trace import TRACE


class OllamaClient:
    def __init__(self, cfg):
        o = cfg["ollama"]
        self.host = o["host"].rstrip("/")
        self.preferred = o["model"]
        self.fallback_any = o.get("fallback_to_any_model", True)
        self.timeout = o.get("request_timeout_seconds", 120)
        self._model = None
        self._lock = threading.Lock()
        self.last_error = None

    # ------------------------------------------------------------ discovery

    def installed_models(self):
        try:
            r = requests.get(self.host + "/api/tags", timeout=5)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception as e:
            self.last_error = f"ollama unreachable: {e}"
            return []

    def resolve_model(self):
        """Preferred model if installed, else first non-embedding model."""
        with self._lock:
            if self._model:
                return self._model
            names = self.installed_models()
            if not names:
                return None
            for n in names:
                if n == self.preferred or n.split(":")[0] == self.preferred:
                    self._model = n
                    break
            else:
                if self.fallback_any:
                    chat_models = [n for n in names if "embed" not in n.lower()]
                    if chat_models:
                        self._model = chat_models[0]
                        print(f"[ollama] preferred model not installed; falling back to {self._model}")
            return self._model

    def chat_models(self):
        """Installed models minus embedding models — the pickable list."""
        return [n for n in self.installed_models() if "embed" not in n.lower()]

    def set_model(self, name):
        """Pin the active model explicitly (from the in-game picker)."""
        with self._lock:
            self._model = name
            self.preferred = name
            self.last_error = None

    def available(self):
        return self.resolve_model() is not None

    # ------------------------------------------------------------ inference

    def chat(self, messages, json_format=False, temperature=0.9, num_predict=900,
             timeout=None, tag="chat"):
        """Non-streaming chat completion. Returns text or None on failure.
        `tag` names the caller (director/forge/console) in the session trace."""
        model = self.resolve_model()
        if not model:
            TRACE.log("llm_error", tag=tag, error="no model resolved")
            return None
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if json_format:
            payload["format"] = "json"
        t0 = time.monotonic()
        try:
            r = requests.post(self.host + "/api/chat", json=payload,
                              timeout=timeout or self.timeout)
            r.raise_for_status()
            text = r.json().get("message", {}).get("content", "")
            TRACE.log("llm", tag=tag, model=model,
                      ms=int((time.monotonic() - t0) * 1000),
                      prompt=messages, response=text)
            return text
        except Exception as e:
            self.last_error = f"chat failed: {e}"
            print("[ollama]", self.last_error)
            TRACE.log("llm_error", tag=tag, model=model,
                      ms=int((time.monotonic() - t0) * 1000), error=str(e))
            return None
