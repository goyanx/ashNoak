"""Background story-outline generation on Sanderson's promise/progress/payoff.

At boot the forge fills N slots asynchronously; the story-select screen
reads slot snapshots each frame. Hand-written fallbacks guarantee the
game is playable even with no LLM at all.
"""
import copy
import threading

from .framework import extract_json

THEMES = ("forest", "castle", "volcano")
SPEAKERS = ("knight", "princess", "dragon", "narrator")

FALLBACK_STORIES = [
    {
        "title": "The Ashen Vow",
        "logline": "A disgraced knight escorts a princess who hired the dragon that ruined him.",
        "theme": "forest",
        "promise": "Ser Kael will learn who really burned Greyhollow — and make them answer for it.",
        "beats": [
            "Maren hires Kael under a false name to cross the Thornwood.",
            "Raider ambushes grow too organized to be chance; someone is herding them.",
            "A dying cultist recognizes Maren and laughs with his last breath.",
            "Maren confesses: she paid Vexuragh to burn Greyhollow to hide her father's crime.",
            "Vexuragh comes to collect the other half of the payment: Maren herself.",
        ],
        "payoff": "Kael's vengeance is standing beside him. He chooses who burns: the dragon, the princess, or the vow itself.",
        "dragon_role": "villain",
        "opening_lines": [
            {"speaker": "narrator", "text": "The Thornwood keeps its dead. Kael intends to add some."},
            {"speaker": "princess", "text": "Walk faster, knight. The wood is patient and I am not."},
            {"speaker": "knight", "text": "You're paying for my sword, not my hurry."},
        ],
    },
    {
        "title": "Crown of Cinders",
        "logline": "The princess is the usurper; the dragon is the rightful heir.",
        "theme": "castle",
        "promise": "Someone in Castle Vael is lying about the succession, and blood will out.",
        "beats": [
            "Kael is summoned to defend Princess Maren from 'assassins' in her own keep.",
            "The assassins are palace guards — men Kael trained, now dead by his hand.",
            "Vexuragh lands on the throne tower and speaks: the old king's soul is in the dragon.",
            "Maren poisoned her father; the court mage bound his soul to the beast before it fled.",
            "Maren offers Kael the kingdom to finish the dragon and the truth with it.",
        ],
        "payoff": "Regicide or dragonslaying — the same sword stroke cannot be both loyal and just.",
        "dragon_role": "tragic",
        "opening_lines": [
            {"speaker": "narrator", "text": "Castle Vael, midnight. The bells are ringing for a king three days dead."},
            {"speaker": "princess", "text": "They came into my bedchamber with knives, Ser Kael. I want them dead twice."},
            {"speaker": "knight", "text": "Once is all I can promise. Stay behind me."},
        ],
    },
    {
        "title": "The Last Ember",
        "logline": "Knight and dragon must ally to pull the princess out of a cult's volcano before she becomes its god.",
        "theme": "volcano",
        "promise": "Maren went into Mount Karrach willingly. Getting her out will cost Kael his certainties.",
        "beats": [
            "Vexuragh, wounded and furious, offers Kael a truce: the cult stole her last egg too.",
            "Cultists throw themselves on Kael's sword smiling; the mountain is chanting.",
            "Maren is found unchained and radiant — she is the volunteer, not the victim.",
            "The cult means to hatch the egg inside a living crown-bearer to bind a new god.",
            "The eruption begins; Kael can carry the egg or the princess up, not both.",
        ],
        "payoff": "The promise breaks honestly: Kael saves what chooses to be saved, and the dragon repays her debt in fire.",
        "dragon_role": "ally",
        "opening_lines": [
            {"speaker": "narrator", "text": "Mount Karrach has been singing for nine nights. Tonight it gets an answer."},
            {"speaker": "dragon", "text": "Little knight. Sheathe that or lose the arm. I need you breathing."},
            {"speaker": "knight", "text": "Gods. It talks. And it wants a favor."},
        ],
    },
]

STORY_PROMPT = """You are a story architect for a 90s-style dark-fantasy side-scroller.
{content_directive}

Fixed cast (do not add main characters):
- Ser Kael, the knight (the player)
- Princess Maren (never a mere damsel; give her agency, secrets, or menace)
- Vexuragh, the dragon (may be villain, ally, or tragic figure — your choice)

Design ONE story outline using Brandon Sanderson's structure:
- PROMISE: what the opening vows the story is about (tone + stakes + a question).
- PROGRESS: exactly 5 escalating beats that visibly move toward the answer.
- PAYOFF: an ending that pays the promise, ideally with a twist that recontextualizes it.

Reply with ONLY this JSON object:
{{
  "title": "short evocative title",
  "logline": "one gripping sentence",
  "theme": "forest" | "castle" | "volcano",
  "dragon_role": "villain" | "ally" | "tragic",
  "promise": "one or two sentences",
  "payoff": "one or two sentences",
  "beats": ["beat 1", "beat 2", "beat 3", "beat 4", "beat 5"],
  "opening_lines": [{{"speaker": "narrator|knight|princess|dragon", "text": "..."}}, ... 3 lines]
}}

BE TERSE. Every beat is ONE sentence under 22 words, no "beat N:" prefixes.
Promise, payoff and each opening line under 30 words. The whole reply must
stay under 300 words of content — punchy, not padded.
{variety}"""


import re


def _valid_story(d):
    if not isinstance(d, dict):
        return None
    s = {}
    try:
        s["title"] = str(d["title"]).strip()[:48] or "Untitled"
        s["logline"] = str(d.get("logline", "")).strip()[:160]
        s["theme"] = d.get("theme") if d.get("theme") in THEMES else THEMES[hash(s["title"]) % 3]
        s["promise"] = str(d["promise"]).strip()
        beats, stray_payoff = [], None
        for b in d.get("beats", []):
            b = re.sub(r"^\s*beat\s*\d+\s*[:.-]\s*", "", str(b).strip(), flags=re.I)
            m = re.match(r"^\s*payoff\s*[:.-]\s*(.+)", b, flags=re.I | re.S)
            if m:  # some models smuggle the payoff into the beat list
                stray_payoff = m.group(1).strip()
            elif b:
                beats.append(b)
        if len(beats) < 3:
            return None
        s["beats"] = (beats + beats)[:5]
        s["payoff"] = str(d.get("payoff", "") or stray_payoff or "").strip()
        if not s["payoff"]:
            return None
        s["dragon_role"] = d.get("dragon_role") if d.get("dragon_role") in ("villain", "ally", "tragic") else "villain"
        lines = []
        for ln in d.get("opening_lines", []):
            if isinstance(ln, dict) and str(ln.get("text", "")).strip():
                sp = ln.get("speaker", "narrator")
                lines.append({"speaker": sp if sp in SPEAKERS else "narrator",
                              "text": str(ln["text"]).strip()[:220]})
        s["opening_lines"] = lines[:4] or [{"speaker": "narrator", "text": s["promise"]}]
        return s
    except (KeyError, TypeError):
        return None


class StoryForge:
    def __init__(self, client, cfg):
        self.client = client
        self.count = max(3, int(cfg.get("story_count", 3)))
        self.timeout = cfg.get("story_timeout_seconds", 90)
        self.directive = cfg.get("content_directive", "")
        self._lock = threading.Lock()
        self.slots = [{"status": "forging", "story": None} for _ in range(self.count)]
        self._gen = 0
        self._thread = None

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self.slots)

    def start(self):
        with self._lock:
            self._gen += 1
            gen = self._gen
            for s in self.slots:
                s["status"], s["story"] = "forging", None
        self._thread = threading.Thread(target=self._run, args=(gen,), daemon=True)
        self._thread.start()

    def _run(self, gen):
        if not self.client.available():
            print("[forge] LLM unavailable — using fallback stories")
            self._fill_all_fallback(gen)
            return
        used_titles = []
        for i in range(self.count):
            if self._stale(gen):
                return
            story = self._forge_one(i, used_titles)
            if story is None:
                story = dict(copy.deepcopy(FALLBACK_STORIES[i % len(FALLBACK_STORIES)]), fallback=True)
                status = "fallback"
            else:
                status = "ready"
            used_titles.append(story["title"])
            with self._lock:
                if self._gen == gen:
                    self.slots[i] = {"status": status, "story": story}
            print(f"[forge] slot {i}: {status} — {story['title']}")

    def _forge_one(self, i, used_titles):
        variety = ""
        if used_titles:
            variety = ("\nAlready used (make this one clearly different in theme and premise): "
                       + "; ".join(used_titles))
        prompt = STORY_PROMPT.format(content_directive=self.directive, variety=variety)
        for _attempt in range(2):
            raw = self.client.chat(
                [{"role": "user", "content": prompt}],
                json_format=True, temperature=1.0, num_predict=1200, timeout=self.timeout)
            story = _valid_story(extract_json(raw))
            if story:
                return story
        return None

    def _fill_all_fallback(self, gen):
        with self._lock:
            if self._gen != gen:
                return
            for i in range(self.count):
                st = dict(copy.deepcopy(FALLBACK_STORIES[i % len(FALLBACK_STORIES)]), fallback=True)
                self.slots[i] = {"status": "fallback", "story": st}

    def _stale(self, gen):
        with self._lock:
            return self._gen != gen
