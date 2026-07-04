"""The Story Director: an Agent that runs the show on a timer.

A worker thread ticks every `director_interval_seconds` (and on nudges
from gameplay events, debounced). Each tick it asks the LLM for tool
calls and pushes the validated calls into `out` for the game thread to
execute. The render loop never waits on the model.
"""
import queue
import threading
import time

from .framework import Agent, Tool
from .trace import TRACE

DIRECTOR_TOOLS = [
    Tool("say", "Speak a line of dialogue, shown on screen and voiced by TTS.",
         {"speaker": "knight|princess|dragon|narrator, or a minor NPC's name",
          "text": "the line, under 500 chars"}),
    Tool("narrate", "Narrator prose over the scene — describe, foreshadow, react.",
         {"text": "the prose, under 500 chars"}),
    Tool("offer_choices", "Present the player 2-4 dialogue/action choices. Their pick comes back to you as an event.",
         {"prompt": "what Kael is responding to", "options": "array of 2-4 short first-person options"}),
    Tool("give_item", "Put an item in Kael's inventory (clue, key, weapon, trophy).",
         {"name": "short item name", "desc": "one-line description"}),
    Tool("take_item", "Remove an item from Kael's inventory (used up, stolen, given).",
         {"name": "item name"}),
    Tool("skill_check", "Make Kael roll a stat. The engine rolls and you learn the outcome as an event.",
         {"stat": "vigor|wit|presence", "difficulty": "2-9", "reason": "what is being attempted"}),
    Tool("set_objective", "Set the current beat's on-screen objective.",
         {"kind": "slay|search|talk|story", "value": "count for slay/search; npc name for talk; ignored for story",
          "text": "objective text shown to the player"}),
    Tool("advance_beat", "Declare the current beat resolved; the way forward opens.", {}),
    Tool("spawn_encounter", "Start a fight in the current room.",
         {"kind": "raider|wolf|cultist", "count": "1-4"}),
    Tool("move_actor", "Bring a cast member into the current room, or send them away.",
         {"who": "princess|dragon", "place": "here|away"}),
    Tool("intimate_scene", "Stage lovemaking between Kael and a partner: the room dims, "
         "an embrace plays out in pixels, and your `text` narration carries the moment.",
         {"partner": "princess, or a named NPC", "text": "the narration, under 500 chars"}),
    Tool("harm", "Wound someone (story consequence).", {"target": "knight|princess", "amount": "1-4"}),
    Tool("heal", "Restore hit points.", {"target": "knight|princess", "amount": "1-5"}),
]

PERSONA = """You are the GAME MASTER of a point-and-click adult adventure game —
the investigative mood of Gabriel Knight, the heroics of Quest for Glory,
in gritty retro pixels.
{content_directive}

Cast: Ser Kael the knight (the player clicks him around), Princess Maren,
Vexuragh the dragon. You may voice minor NPCs by name with say().
You are running this story outline (Sanderson promise/progress/payoff):
TITLE: {title}
PROMISE: {promise}
BEATS: {beats}
PAYOFF: {payoff}
DRAGON ROLE: {dragon_role}

Game-mastering rules:
- The events list shows what the player DID: rooms entered, props searched,
  people spoken to, items used, choices picked, fights, deaths, skill results.
  React to those deeds specifically — that is what makes the world feel alive.
- When Kael talks to someone, answer with say() in their voice and usually
  offer_choices() so the player steers the conversation.
- When the player searches or uses things, reward curiosity: narrate what it
  MEANS, give_item clues, or call skill_check for risky acts.
- Serve the CURRENT beat; escalate pressure as beats advance. Call
  advance_beat when the beat's business feels done — that unlocks new rooms.
- On the final beat, stage the payoff in the lair per the dragon's role and
  pay the promise.
- Desire is part of adult stories. When the story has EARNED it — trust built,
  a beat of stillness, both willing — you may call intimate_scene; its
  narration register is your judgment per the content directive. Usually let
  the player opt in through offer_choices first. Never mid-combat, never
  unearned; intimacy that costs or reveals something serves the promise best.
- Kael: terse, dry. Maren: sharp, secretive. Vexuragh: ancient, contemptuous.
- Do not repeat lines from recent events. 2-4 tool calls is the sweet spot."""


class Director:
    def __init__(self, client, cfg):
        self.client = client
        self.cfg = cfg
        self.interval = max(10, int(cfg.get("director_interval_seconds", 60)))
        self.out = queue.Queue()
        self.agent = None
        self.snapshot_provider = None  # set by the game: () -> str
        self._nudge = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._last_tick = 0.0
        self._busy = False
        self.status = "idle"

    # ------------------------------------------------------------ lifecycle

    def start(self, story):
        self.stop()
        persona = PERSONA.format(
            content_directive=self.cfg.get("content_directive", ""),
            title=story["title"], promise=story["promise"],
            beats=" | ".join(f"{i+1}. {b}" for i, b in enumerate(story["beats"])),
            payoff=story["payoff"], dragon_role=story["dragon_role"])
        self.agent = Agent("director", persona, DIRECTOR_TOOLS, self.client,
                           memory_limit=int(self.cfg.get("director_memory_limit", 48)))
        self._stop.clear()
        self._nudge.clear()
        self._last_tick = time.monotonic()  # opening lines cover the first minute
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._nudge.set()
        self._thread = None

    # ------------------------------------------------------------ game-side API

    def remember(self, event_text):
        """Feed a gameplay event into the agent's memory (game thread)."""
        if self.agent:
            self.agent.memory.add(event_text)
            TRACE.log("event", text=event_text)

    def request_tick(self, reason, force=False):
        """Event nudge (beat done, near-death, boss). Debounced to 15 s
        unless forced (still rate-limited to one tick per 5 s)."""
        if force or time.monotonic() - self._last_tick >= 15:
            if self.agent:
                self.agent.memory.add(f"URGENT: {reason}")
            if not self._busy:
                self.status = "summoned"
            self._nudge.set()

    def converse(self, text, callback):
        """Out-of-character console chat with the director. Runs on its own
        thread; `callback(reply_text)` fires when the LLM answers. The
        message also enters the agent's memory so the next tick can act."""
        if not self.agent:
            callback("(no story is running)")
            return
        self.agent.memory.add(
            f'CONSOLE: the player spoke to you directly, out of character: "{text}"')

        def work():
            messages = [
                {"role": "system", "content":
                    self.agent.persona + "\n\nThe player has opened a debug console "
                    "to talk to YOU, the game master, out of character. Answer in "
                    "plain text (no JSON, no tool calls), under 100 words. If they "
                    "give an instruction, acknowledge it and carry it into the "
                    "story on your next turn."},
                {"role": "user", "content":
                    f"RECENT EVENTS:\n{self.agent.memory.render()}\n\n"
                    "CURRENT GAME STATE:\n"
                    f"{self.snapshot_provider() if self.snapshot_provider else '?'}\n\n"
                    f"PLAYER (console): {text}"},
            ]
            reply = self.client.chat(messages, temperature=0.7, num_predict=300,
                                     tag="console")
            callback((reply or "").strip() or "(silence — the LLM did not answer)")
            self._nudge.set()  # let any instruction reach the story promptly

        threading.Thread(target=work, daemon=True).start()

    def drain(self):
        """Game thread: pop all pending tool calls."""
        calls = []
        while True:
            try:
                calls.append(self.out.get_nowait())
            except queue.Empty:
                return calls

    # ------------------------------------------------------------ worker

    def _run(self):
        while not self._stop.is_set():
            timeout = max(0.5, self.interval - (time.monotonic() - self._last_tick))
            nudged = self._nudge.wait(timeout=timeout)
            self._nudge.clear()
            if self._stop.is_set():
                return
            if time.monotonic() - self._last_tick < 5 or self._busy:
                if nudged:  # don't drop the request (this ate F5 presses):
                    self._nudge.set()  # keep it armed and retry shortly
                    time.sleep(1.0)
                continue
            self._tick()

    def _tick(self):
        if not (self.agent and self.snapshot_provider):
            return
        self._busy = True
        self.status = "thinking"
        self._last_tick = time.monotonic()
        try:
            observation = self.snapshot_provider()
            calls = self.agent.step(observation)
            for c in calls:
                self.out.put(c)
                if c["tool"] in ("say", "narrate"):
                    who = c["args"].get("speaker", "narrator")
                    self.agent.memory.add(f'{who} said: "{c["args"].get("text", "")}"')
                else:
                    self.agent.memory.add(f"director did {c['tool']} {c['args']}")
            self.status = f"acted ({len(calls)} calls)" if calls else "idle"
        except Exception as e:  # never let the director kill the game
            print("[director] tick failed:", e)
            TRACE.log("director_error", error=str(e))
            self.status = "error"
        finally:
            self._last_tick = time.monotonic()
            self._busy = False
