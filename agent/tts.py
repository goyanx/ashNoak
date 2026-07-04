"""Offline TTS on a worker thread (pyttsx3 / Windows SAPI5).

One queue in, speech out. Per-character voice + rate so the cast sounds
distinct. The game never blocks on speech; muting drops queued lines.
"""
import queue
import threading

CHARACTER_STYLE = {
    # rate delta, preferred voice index (into the installed SAPI voice list)
    "knight":   {"rate": -25, "voice": 0},
    "princess": {"rate": +15, "voice": 1},
    "dragon":   {"rate": -55, "voice": 0},
    "narrator": {"rate": 0,   "voice": 1},
}


class Speaker:
    def __init__(self, cfg):
        self.enabled = bool(cfg.get("tts_enabled", True))
        self.base_rate = int(cfg.get("tts_rate_base", 170))
        self.muted = False
        self._q = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def say(self, speaker, text):
        if self.enabled and not self.muted and text:
            self._q.put((speaker, text))

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
        return self.muted

    def _run(self):
        if not self.enabled:
            return
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
        except Exception as e:
            print("[tts] unavailable:", e)
            self.enabled = False
            return
        while True:
            speaker, text = self._q.get()
            if self.muted:
                continue
            style = CHARACTER_STYLE.get(speaker, CHARACTER_STYLE["narrator"])
            try:
                engine.setProperty("rate", self.base_rate + style["rate"])
                if voices:
                    engine.setProperty("voice", voices[style["voice"] % len(voices)].id)
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print("[tts] speak failed:", e)
