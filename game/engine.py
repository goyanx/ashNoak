"""Point-and-click scene machine + the wiring between play and the Director.

Flow of a click: hover resolve -> walk-to -> arrival executes the action ->
the deed is written into the Director's memory -> the Director answers on
its next tick (or a forced one) with dialogue, choices, items, checks."""
import array
import json
import math
import os
import random
import sys

import pygame

from agent.director import Director
from agent.ollama_client import OllamaClient
from agent.storyforge import StoryForge
from agent.trace import TRACE
from agent.tts import Speaker

from . import assets as assets_mod
from .actors import Actor, Foe, Item, Player
from .rooms import FLOOR_TOP, NPC_EXAMINE, Stage
from .settings import CONFIG, FPS, IH, IW, ROOT, SCALE
from .ui import (BAR_H, BottomBar, ChoicePanel, Console, DialogueBox, Fonts,
                 ModelSelect, StorySelect, draw_cursor, wrap)

BEATS = 5
ENEMY_KINDS = ("raider", "wolf", "cultist")
DEFAULT_OBJECTIVES = [
    ("talk", "princess", "Speak with Maren"),
    ("reach", 1, "Press on — the road is the only way through"),
    ("slay", 3, "Blood has been called. Answer it"),
    ("search", 2, "Dig deeper. Something is missing"),
    ("slay", 4, "They know. They are coming"),
]
# Drama-manager pacing (ms): the story must always be moving. A beat that
# lingers past STALL nudges the director to push; past HARD_CAP it advances
# itself so play never deadlocks. MIN_BEAT keeps auto-completion from blitzing
# through a beat before its dialogue lands. PAYOFF_CAP guarantees an ending.
BEAT_MIN_MS = 8_000
BEAT_STALL_MS = int(float(CONFIG.get("beat_stall_seconds", 45)) * 1000)
BEAT_HARD_CAP_MS = int(float(CONFIG.get("beat_hard_cap_seconds", 170)) * 1000)
PAYOFF_CAP_MS = int(float(CONFIG.get("payoff_hard_cap_seconds", 150)) * 1000)
STAT_NAMES = ("vigor", "wit", "presence")
SAVE_PATH = os.path.join(ROOT, "saves", "quicksave.json")

KEY_HELP = [
    ("MOUSE", ""),
    ("  left-click", "walk / search / talk / attack / exit"),
    ("  right-click", "examine what's under the cursor"),
    ("  inventory", "arm an item, then click its target"),
    ("KEYS", ""),
    ("  E", "skip the current dialogue line"),
    ("  TAB (hold)", "the story beats so far"),
    ("  ` / ~", "console — talk to the game master"),
    ("  F5", "force the game master to act now"),
    ("  F6", "save the story (quicksave)"),
    ("  F7", "load the saved story"),
    ("  M", "mute / unmute the voices"),
    ("  ESC", "pause / resume"),
    ("  Q", "abandon the story (while paused)"),
]


def synth(f0, f1, dur, vol=0.2, noise=False, sr=22050):
    n = int(sr * dur)
    buf = array.array("h")
    rng = random.Random(int(f0))
    for i in range(n):
        t = i / sr
        f = f0 + (f1 - f0) * (i / max(1, n))
        v = (rng.random() * 2 - 1) if noise else (1.0 if math.sin(2 * math.pi * f * t) >= 0 else -1.0)
        env = 1 - i / n
        buf.append(int(v * env * vol * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


class Game:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Ash & Oath — knight / princess / dragon")
        self.window = pygame.display.set_mode((IW * SCALE, IH * SCALE))
        self.screen = pygame.Surface((IW, IH))
        self.clock = pygame.time.Clock()
        pygame.mouse.set_visible(False)
        pygame.key.set_repeat(320, 45)  # held keys repeat (console typing)
        self.fonts = Fonts()
        self.art = assets_mod.load_all()
        TRACE.start(ROOT, CONFIG.get("trace_log", True))

        self.sfx = {
            "slash": synth(900, 300, 0.09),
            "hit": synth(200, 80, 0.12, noise=True),
            "die": synth(400, 60, 0.4, noise=True),
            "beat": synth(520, 1040, 0.25, vol=0.15),
            "pick": synth(620, 940, 0.12, vol=0.15),
            "step": synth(160, 140, 0.03, vol=0.05, noise=True),
            "check": synth(300, 800, 0.2, vol=0.12),
        }

        self.speaker = Speaker(CONFIG)
        self.client = OllamaClient(CONFIG)
        self.forge = StoryForge(self.client, CONFIG)
        self.forge.start()
        self.director = Director(self.client, CONFIG)
        self.select = StorySelect(self.fonts)
        self.models = ModelSelect(self.fonts)
        self.console = Console(self.fonts)
        self.console.log("Director console. Type to speak with the game master; "
                         "/help for commands.", (140, 145, 165))

        self.state = "menu"
        self.paused = False
        self.snapshot_text = "The story has not started."
        self.director.snapshot_provider = lambda: self.snapshot_text
        self.story = None

    # ================================================================ loop

    def run(self):
        while True:
            dt = min(0.05, self.clock.tick(FPS) / 1000.0)
            click = rclick = False
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.quit()
                elif ev.type == pygame.KEYDOWN:
                    self.keydown(ev)
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    if ev.button == 1:
                        click = True
                    elif ev.button == 3:
                        rclick = True
            self.mouse = (pygame.mouse.get_pos()[0] // SCALE,
                          pygame.mouse.get_pos()[1] // SCALE)
            self.console.pump()
            if self.console.open:
                pass  # the console owns input; the world holds its breath
            elif self.state == "play" and not self.paused:
                self.update_play(dt, click, rclick)
            elif click:
                self.menu_click()
            self.draw()
            pygame.transform.scale(self.screen, self.window.get_size(), self.window)
            pygame.display.flip()

    def quit(self):
        TRACE.log("session_end")
        self.director.stop()
        pygame.quit()
        sys.exit(0)

    def keydown(self, ev):
        key = ev.key
        if key == pygame.K_BACKQUOTE or ev.unicode in ("`", "~"):
            self.console.toggle()
            return
        if self.console.open:
            text = self.console.key(ev)
            if text:
                self.console.log("] " + text, (235, 225, 200))
                self.console_command(text)
            return
        if key == pygame.K_m:
            self.speaker.toggle_mute()
        if self.state == "menu":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = "select"
            elif key == pygame.K_l:
                self.open_models()
            elif key in (pygame.K_c, pygame.K_F7):
                self.load_game()
            elif key == pygame.K_ESCAPE:
                self.quit()
        elif self.state == "models":
            if key in (pygame.K_UP, pygame.K_w):
                self.models.move(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.models.move(1)
            elif key == pygame.K_r:
                self.open_models()
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.choose_model(self.models.selected())
            elif key == pygame.K_ESCAPE:
                self.state = "menu"
        elif self.state == "select":
            if key in (pygame.K_UP, pygame.K_w):
                self.select.index = (self.select.index - 1) % 3
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.select.index = (self.select.index + 1) % 3
            elif key == pygame.K_r:
                self.forge.start()
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                slot = self.forge.snapshot()[self.select.index]
                if slot["story"]:
                    self.start_story(slot["story"])
            elif key == pygame.K_ESCAPE:
                self.state = "menu"
        elif self.state == "play":
            if key == pygame.K_ESCAPE:
                self.paused = not self.paused
            elif self.paused and key == pygame.K_q:
                self.director.stop()
                self.paused = False
                self.state = "menu"
            elif key == pygame.K_F6:
                self.save_game()
                self.paused = False
            elif key == pygame.K_F7:
                self.load_game()
            elif key == pygame.K_e:
                self.dialogue.skip()
            elif key == pygame.K_F5:
                self.director.request_tick("the player demands the story move", force=True)
                self.console.log("* F5 — director tick requested", (140, 145, 165))
        elif self.state == "epilogue":
            if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.state = "menu"

    def console_command(self, text):
        low = text.lower().strip()
        if low in ("/help", "help", "?"):
            self.console.log("Type anything — it goes to the director LLM, which "
                             "answers here and folds instructions into the story.")
            self.console.log("/events  what the director remembers (its rolling memory)")
            self.console.log("/state   the game-state snapshot it sees every tick")
            self.console.log("/beats   story beats (same as holding TAB)")
            return
        if low == "/events":
            events = list(self.director.agent.memory.events) if self.director.agent else []
            self.console.log(f"-- director memory ({len(events)} events) --", (216, 168, 50))
            for e in events or ["(nothing yet)"]:
                self.console.log("  " + str(e), (150, 155, 175))
            return
        if low == "/state":
            self.console.log("-- snapshot sent to the LLM each tick --", (216, 168, 50))
            self.console.log(self.snapshot_text, (150, 155, 175))
            return
        if low == "/beats":
            if self.story is None:
                self.console.log("(no story is running)", (200, 120, 80))
                return
            for i, b in enumerate(self.story["beats"]):
                mark = "DONE" if i < self.beat else ("NOW " if i == self.beat else "... ")
                self.console.log(f"{mark} {i + 1}. {b if i <= self.beat else '(not yet revealed)'}",
                                 (110, 160, 110) if i < self.beat else (150, 155, 175))
            return
        if self.director.agent is None:
            self.console.log("(no story is running — start one first)", (200, 120, 80))
            return
        self.console.log("(the director considers...)", (140, 145, 165))
        self.director.converse(
            text, lambda reply: self.console.post("DIRECTOR: " + reply, (216, 168, 50)))

    def menu_click(self):
        if self.state == "menu":
            if pygame.Rect(0, IH - 24, IW, 24).collidepoint(self.mouse):
                self.open_models()
            else:
                self.state = "select"
        elif self.state == "models":
            chosen = self.models.mouse(self.mouse, True)
            if chosen:
                self.choose_model(chosen)
        elif self.state == "select":
            for i in range(3):
                if pygame.Rect(12, 28 + i * 47, IW - 24, 44).collidepoint(self.mouse):
                    if self.select.index == i:
                        slot = self.forge.snapshot()[i]
                        if slot["story"]:
                            self.start_story(slot["story"])
                    else:
                        self.select.index = i
        elif self.state == "epilogue":
            self.state = "menu"

    # ================================================================ model picker

    def open_models(self):
        """Fetch the installed chat models and show the picker (blocks briefly
        on the Ollama query — a deliberate menu action)."""
        self.models.load(self.client.chat_models(), self.client.resolve_model())
        self.state = "models"

    def choose_model(self, name):
        if not name:
            return
        self.client.set_model(name)
        self.persist_model(name)
        self.models.active = name
        self.forge.start()  # re-forge the outlines with the new game master
        self.state = "select"

    def persist_model(self, name):
        """Write the choice back to config.json so it survives a restart."""
        path = os.path.join(ROOT, "config.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("ollama", {})["model"] = name
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            CONFIG.setdefault("ollama", {})["model"] = name
        except (OSError, ValueError) as e:
            print("[config] could not persist model:", e)

    # ================================================================ story setup

    def start_story(self, story):
        self.story = story
        TRACE.log("story_start", story=story)
        spr = self.art["sprites"]
        self.stage = Stage(story["theme"], self.art, seed=hash(story["title"]) & 0xFFFF)
        self.player = Player(spr["knight"], 60, FLOOR_TOP + 28)
        self.princess = Actor(spr["princess"], 90, FLOOR_TOP + 24)
        self.princess_room = 0
        self.dragon_actor = Actor(spr["dragon"], IW - 90, FLOOR_TOP + 30, scale=2)
        self.dragon_room = None  # None = away
        self.foes = {}           # room index -> [Foe]
        self.particles = []
        self.embers = []
        self.scene = None        # {"t", "dur", "partner"} while intimacy plays
        self.bond = 0
        self.beat = 0
        self.deaths = 0
        self.beat_kills = 0
        self.beat_searches = 0
        self.talked_this_beat = set()
        self.payoff_done = False
        self.payoff_talk_t = None
        self.payoff_started_t = None
        self.epilogue_text = None
        # drama-manager pacing clocks (ms). progress_t resets on any real
        # story movement; beat_started_t bounds how long one beat may run.
        now = pygame.time.get_ticks()
        self.beat_started_t = now
        self.progress_t = now
        self.stall_nudged = False
        self.pending = None      # deferred click action, runs on arrival
        self.selected_item = None
        self.hover_label = ""
        self.dialogue = DialogueBox(self.fonts, self.speaker)
        self.choices = ChoicePanel(self.fonts)
        self.bar = BottomBar(self.fonts, self.art)
        self.objective = None
        self.set_default_objective()
        for line in story["opening_lines"]:
            self.dialogue.push(line["speaker"], line["text"])
        self.director.start(story)
        self.director.remember(f"Story began in {self.stage.room.name}. "
                               f"Opening promise: {story['promise']}")
        self.state = "play"
        self.paused = False

    # ================================================================ save / load

    def save_game(self):
        if self.state != "play" or self.story is None:
            return
        data = {
            "version": 1,
            "story": self.story,
            "beat": self.beat,
            "objective": self.objective,
            "current": self.stage.current,
            "unlocked": self.stage.unlocked,
            "player": {"x": self.player.x, "y": self.player.y, "hp": self.player.hp,
                       "kills": self.player.kills, "stats": self.player.stats,
                       "inventory": [{"name": i.name, "desc": i.desc}
                                     for i in self.player.inventory]},
            "princess": {"hp": self.princess.hp, "room": self.princess_room},
            "dragon_room": self.dragon_room,
            "dragon_villain_pending": getattr(self, "dragon_villain_pending", False),
            "bond": self.bond,
            "deaths": self.deaths,
            "beat_kills": self.beat_kills,
            "beat_searches": self.beat_searches,
            "talked": sorted(self.talked_this_beat),
            "payoff_talked": self.payoff_talk_t is not None,
            "foes": {str(idx): [{"kind": f.kind, "hp": f.hp, "x": f.x, "y": f.y}
                                for f in lst if not f.dead]
                     for idx, lst in self.foes.items()},
            "hotspot_uses": {str(i): [h.uses for h in room.hotspots]
                             for i, room in enumerate(self.stage.rooms)},
            "director_memory": list(self.director.agent.memory.events)
                               if self.director.agent else [],
        }
        try:
            os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
            self.dialogue.push("narrator", "Saved. The ink dries.")
            TRACE.log("save", beat=self.beat, room=self.stage.room.name)
        except OSError as e:
            self.dialogue.push("narrator", f"The scribe's hand failed: {e}")

    def load_game(self):
        try:
            with open(SAVE_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            if self.state == "play":
                self.dialogue.push("narrator", "No saved story to return to.")
            return False
        # start_story rebuilds the stage/actors/director for this outline,
        # then the saved state is laid over the top
        self.start_story(data["story"])
        self.dialogue.queue.clear()
        self.dialogue.current = None
        self.beat = int(data["beat"])
        self.objective = data["objective"]
        self.stage.current = int(data["current"])
        self.stage.unlocked = int(data["unlocked"])
        p = data["player"]
        self.player.x, self.player.y = float(p["x"]), float(p["y"])
        self.player.stop()
        self.player.hp = int(p["hp"])
        self.player.kills = int(p["kills"])
        self.player.stats = {k: int(v) for k, v in p["stats"].items()}
        self.player.inventory = [Item(i["name"], i["desc"]) for i in p["inventory"]]
        self.princess.hp = int(data["princess"]["hp"])
        self.princess_room = data["princess"]["room"]
        if self.princess_room == self.stage.current:
            self.princess.x, self.princess.y = self.player.x + 30, self.player.y
            self.princess.stop()
        self.dragon_room = data["dragon_room"]
        self.dragon_villain_pending = bool(data.get("dragon_villain_pending"))
        self.bond = int(data.get("bond", 0))
        self.deaths = int(data.get("deaths", 0))
        self.beat_kills = int(data.get("beat_kills", 0))
        self.beat_searches = int(data.get("beat_searches", 0))
        self.talked_this_beat = set(data.get("talked", []))
        self.payoff_talk_t = pygame.time.get_ticks() if data.get("payoff_talked") else None
        # restart the pacing clocks fresh so a resumed beat gets its full run
        now = pygame.time.get_ticks()
        self.beat_started_t = now
        self.progress_t = now
        self.stall_nudged = False
        self.payoff_started_t = now if self.beat >= BEATS else None
        spr = self.art["sprites"]
        self.foes = {}
        for idx, lst in data.get("foes", {}).items():
            self.foes[int(idx)] = [
                self._restore_foe(spr, f) for f in lst]
        for idx, uses in data.get("hotspot_uses", {}).items():
            for h, u in zip(self.stage.rooms[int(idx)].hotspots, uses):
                h.uses = int(u)
        # give the director back its memory of the run so far
        if self.director.agent:
            for event in data.get("director_memory", []):
                self.director.agent.memory.add(event)
            self.director.remember("The player resumed this story from a saved game. "
                                   "Pick up the thread; do not restart the tale.")
        self.state = "play"
        self.paused = False
        self.dialogue.push("narrator",
                           f"The story takes you back. {self.stage.room.name}.")
        TRACE.log("load", beat=self.beat, room=self.stage.room.name)
        return True

    def _restore_foe(self, spr, f):
        foe = Foe(spr[f["kind"]] if f["kind"] != "dragon" else spr["dragon"],
                  f["kind"], float(f["x"]), float(f["y"]))
        foe.hp = int(f["hp"])
        return foe

    # ================================================================ objectives & beats

    def set_default_objective(self):
        self.beat_kills = 0
        self.beat_searches = 0
        self.talked_this_beat = set()
        if self.beat >= BEATS:
            if self.story["dragon_role"] == "villain":
                self.objective = {"kind": "slay_dragon", "value": 1,
                                  "text": "Vexuragh waits in the lair. End it."}
            else:
                self.objective = {"kind": "talk_dragon", "value": 1,
                                  "text": "Face Vexuragh. Hear the truth."}
            return
        kind, value, text = DEFAULT_OBJECTIVES[self.beat % len(DEFAULT_OBJECTIVES)]
        self.objective = {"kind": kind, "value": value, "text": text}
        if kind == "slay":
            self.ensure_foes(value)

    def ensure_foes(self, want):
        cur = self.foes.setdefault(self.stage.current, [])
        alive = [f for f in cur if not f.dead]
        for _ in range(min(4, want) - len(alive)):
            self.spawn_foe(random.choice(ENEMY_KINDS))

    def spawn_foe(self, kind):
        spr = self.art["sprites"]
        edge = random.choice((14, IW - 14))
        f = Foe(spr[kind] if kind != "dragon" else spr["dragon"], kind,
                edge, random.randrange(FLOOR_TOP + 8, IH - 20))
        self.foes.setdefault(self.stage.current, []).append(f)
        return f

    def objective_complete(self):
        o = self.objective
        if o is None:
            return False
        if o["kind"] == "slay":
            return self.beat_kills >= o["value"]
        if o["kind"] == "search":
            return self.beat_searches >= o["value"]
        if o["kind"] == "talk":
            return str(o["value"]).lower() in self.talked_this_beat
        if o["kind"] == "reach":
            # arriving at the newest-unlocked room resolves the beat: places
            # push the story forward. (frontier 0 = the opening room; skip it.)
            frontier = self.stage.unlocked - 1
            return frontier > 0 and self.stage.current >= frontier
        if o["kind"] == "slay_dragon":
            return any(f.kind == "dragon" and f.dead
                       for fl in self.foes.values() for f in fl)
        if o["kind"] == "talk_dragon":
            # give the Director room to stage the scene after the talk
            return (self.payoff_talk_t is not None
                    and pygame.time.get_ticks() - self.payoff_talk_t > 25000)
        return False  # "story": only advance_beat resolves it

    def _beat_age(self):
        return pygame.time.get_ticks() - self.beat_started_t

    def mark_progress(self):
        """Something moved the story: reset the stall clock so the drama
        manager only intervenes when play has genuinely gone quiet."""
        self.progress_t = pygame.time.get_ticks()
        self.stall_nudged = False

    def check_progress(self):
        """Drama-manager heartbeat (per frame). Guarantees the story keeps
        moving: nudge a stalled director, hard-advance a beat that overstays,
        and force an ending if the payoff drags. Paused while a scene or a
        choice owns the screen."""
        if self.scene or self.choices.open or self.state != "play":
            return
        now = pygame.time.get_ticks()
        if self.beat >= BEATS:
            # payoff failsafe: the tale MUST end, by fight or by word
            if not self.payoff_done and self.payoff_started_t is not None \
                    and now - self.payoff_started_t > PAYOFF_CAP_MS:
                self.director.remember(
                    "The payoff has run long. End it now — through the fight if it "
                    "is joined, otherwise through words: call end_story.")
                self.finish_payoff()
            return
        idle = now - self.progress_t
        if idle > BEAT_HARD_CAP_MS:
            # nothing has moved for too long — advance ourselves so play never
            # deadlocks (the director gets to voice the new beat right after)
            self.console.log("* drama manager: beat overstayed — advancing",
                             (150, 120, 90))
            self.complete_beat()
        elif idle > BEAT_STALL_MS and not self.stall_nudged:
            self.stall_nudged = True
            self.director.remember(
                f"The story has STALLED on beat {self.beat + 1} "
                f"({self.story['beats'][self.beat]}). Push it: reveal something, "
                "raise the stakes, or call advance_beat.")
            self.director.request_tick("the beat has stalled", force=True)

    def complete_beat(self, via_director=False):
        self.sfx["beat"].play()
        if self.beat < BEATS:
            src = "the director advanced the story" if via_director else "objective completed"
            self.director.remember(
                f"Beat {self.beat + 1} resolved ({src}): {self.story['beats'][self.beat]}")
            self.beat += 1
            self.stage.unlocked = min(len(self.stage.rooms), self.beat + 1)
            self.beat_started_t = pygame.time.get_ticks()
            self.mark_progress()
            self.set_default_objective()
            if self.beat >= BEATS:
                self.enter_payoff()
            else:
                self.dialogue.push("narrator", "The way forward is open.")
                self.director.request_tick(f"beat {self.beat + 1} has begun", force=True)
        elif not self.payoff_done:
            self.finish_payoff()

    def enter_payoff(self):
        self.stage.unlocked = len(self.stage.rooms)
        self.payoff_started_t = pygame.time.get_ticks()
        self.director.remember("FINAL PHASE: stage the payoff in the lair. "
                               f"Payoff to deliver: {self.story['payoff']}. "
                               "When it is paid, call end_story to land the ending.")
        self.director.request_tick("the payoff phase has begun", force=True)
        self.dragon_room = len(self.stage.rooms) - 1
        if self.story["dragon_role"] == "villain":
            self.dragon_villain_pending = True
        self.dialogue.push("narrator", "The last door is open. Something old is waiting behind it.")

    def finish_payoff(self, text=None):
        if self.payoff_done:
            return
        self.payoff_done = True
        self.director.remember("The payoff was delivered. The story is over.")
        self.state = "epilogue"
        self.director.stop()
        self.epilogue_text = (text or "").strip() or self.story["payoff"]
        self.speaker.say("narrator", self.epilogue_text)

    # ================================================================ director dispatch

    def dispatch(self, call):
        tool, a = call["tool"], call["args"]
        if tool in ("say", "narrate"):
            gist = f'{a.get("speaker", "narrator")}: {str(a.get("text", ""))[:90]}'
        else:
            gist = " ".join(f"{k}={v}" for k, v in a.items())[:90]
        self.console.log(f"* {tool} {gist}", (110, 120, 150))
        TRACE.log("dispatch", tool=tool, args=a, beat=self.beat,
                  room=self.stage.room.name)
        try:
            if tool == "say":
                self.dialogue.push(str(a.get("speaker", "narrator")).lower()[:16],
                                   str(a.get("text", ""))[:600])
            elif tool == "narrate":
                self.dialogue.push("narrator", str(a.get("text", ""))[:600])
            elif tool == "offer_choices":
                opts = a.get("options", [])
                if isinstance(opts, str):
                    opts = [o.strip() for o in opts.split("|") if o.strip()]
                if opts:
                    self.choices.set(str(a.get("prompt", ""))[:120], opts)
            elif tool == "give_item":
                name = str(a.get("name", "")).strip()[:24]
                if name and not self.player.has_item(name) and len(self.player.inventory) < 8:
                    self.player.inventory.append(Item(name, str(a.get("desc", ""))[:90]))
                    self.dialogue.push("narrator", f"Taken: {name}.")
                    self.sfx["pick"].play()
            elif tool == "take_item":
                if self.player.remove_item(str(a.get("name", ""))):
                    self.selected_item = None
            elif tool == "skill_check":
                self.do_skill_check(a)
            elif tool == "set_objective":
                kind = a.get("kind")
                if kind in ("slay", "search", "talk", "reach", "story") and self.beat < BEATS:
                    value = a.get("value", 3)
                    if kind in ("slay", "search"):
                        value = max(1, min(8, int(float(value or 3))))
                    self.objective = {"kind": kind, "value": value,
                                      "text": str(a.get("text", ""))[:80] or "New purpose"}
                    self.beat_kills = self.beat_searches = 0
                    self.talked_this_beat = set()
                    self.mark_progress()
                    if kind == "slay":
                        self.ensure_foes(value)
            elif tool == "advance_beat":
                self.complete_beat(via_director=True)
            elif tool == "end_story":
                self.finish_payoff(str(a.get("text", "")))
            elif tool == "spawn_encounter":
                kind = a.get("kind") if a.get("kind") in ENEMY_KINDS else "raider"
                for _ in range(max(1, min(4, int(float(a.get("count", 2)))))):
                    self.spawn_foe(kind)
                self.dialogue.push("narrator", "Steel out. You are not alone.")
            elif tool == "intimate_scene":
                self.start_intimacy(a)
            elif tool == "move_actor":
                who, place = a.get("who"), a.get("place", "here")
                if who == "princess":
                    self.princess_room = self.stage.current if place == "here" else None
                    if place == "here":
                        self.princess.x, self.princess.y = self.player.x + 40, self.player.y
                elif who == "dragon":
                    self.dragon_room = self.stage.current if place == "here" else None
            elif tool in ("harm", "heal"):
                target = self.player if a.get("target") != "princess" else self.princess
                amount = max(1, min(5, int(float(a.get("amount", 2)))))
                if tool == "heal":
                    target.hp = min(target.max_hp, target.hp + amount)
                else:
                    target.hp = max(1, target.hp - amount)
                    target.hurt_t = 0.8
                    self.blood_burst(target.x, target.y - 10, 6)
        except (ValueError, TypeError) as e:
            print("[dispatch] bad args for", tool, a, e)
            TRACE.log("dispatch_error", tool=tool, args=a, error=str(e))

    def start_intimacy(self, a):
        alive = [f for f in self.foes.get(self.stage.current, []) if not f.dead]
        if alive or self.scene:
            self.director.remember("intimate_scene refused: blades are out or a scene is playing.")
            return
        partner = str(a.get("partner", "princess")).strip()[:16] or "princess"
        if partner.lower() in ("princess", "maren"):
            partner = "princess"
            self.princess_room = self.stage.current
        self.scene = {"t": 0.0, "dur": 11.0, "partner": partner}
        self.choices.open = False
        self.pending = None
        self.player.stop()
        self.princess.stop()
        text = str(a.get("text", ""))[:600]
        if text:
            self.dialogue.push("narrator", text)

    def end_intimacy(self):
        scene, self.scene = self.scene, None
        self.bond += 1
        self.player.hp = min(self.player.max_hp, self.player.hp + 2)
        self.princess.hp = min(self.princess.max_hp, self.princess.hp + 2)
        self.embers.clear()
        who = "Maren" if scene["partner"] == "princess" else scene["partner"]
        self.director.remember(
            f"Kael and {who} made love in {self.stage.room.name} (bond is now "
            f"{self.bond}). Let the morning after carry consequences or tenderness.")
        self.dialogue.push("narrator", "After, the quiet is a different kind of quiet.")

    def update_intimacy(self, dt):
        self.scene["t"] += dt
        if random.random() < 0.3:
            self.embers.append([self.player.x + random.uniform(-24, 24),
                                self.player.y - random.uniform(0, 20),
                                random.uniform(8, 22), random.uniform(1.2, 2.6)])
        for e in self.embers:
            e[1] -= e[2] * dt
            e[3] -= dt
        self.embers = [e for e in self.embers if e[3] > 0]
        self.dialogue.update(dt)
        self.drain_director()
        if self.scene["t"] >= self.scene["dur"] and not self.dialogue.queue:
            self.end_intimacy()

    def do_skill_check(self, a):
        stat = a.get("stat") if a.get("stat") in STAT_NAMES else "vigor"
        try:
            dc = max(2, min(9, int(float(a.get("difficulty", 5)))))
        except (ValueError, TypeError):
            dc = 5
        reason = str(a.get("reason", "the attempt"))[:80]
        roll = self.player.stats[stat] + random.randint(1, 6)
        ok = roll >= dc + 3
        self.sfx["check"].play()
        self.dialogue.push("narrator",
                           f"[{stat.upper()} {roll} vs {dc + 3}] " +
                           (f"Kael's {stat} holds." if ok else f"Kael's {stat} betrays him."))
        if not ok and stat == "vigor":
            self.player.hurt(1)
            self.blood_burst(self.player.x, self.player.y - 12, 5)
        self.director.remember(
            f"SKILL CHECK {'SUCCEEDED' if ok else 'FAILED'}: {stat} vs {reason}. "
            "Continue the story from that result.")
        self.director.request_tick("a skill check resolved", force=True)

    # ================================================================ play update

    def update_play(self, dt, click, rclick):
        # an intimate scene owns the screen until it resolves
        if self.scene:
            self.update_intimacy(dt)
            return
        # choice panel eats input and pauses the world
        if self.choices.open:
            picked = self.choices.mouse(self.mouse, click)
            if picked:
                self.dialogue.push("knight", picked)
                self.director.remember(f'Kael chose: "{picked}"')
                self.director.request_tick("the player made a choice", force=True)
            self.dialogue.update(dt)
            self.drain_director()
            return

        self.hover_label, hover_target = self.resolve_hover()
        if click:
            self.handle_click(hover_target)
        if rclick:
            self.handle_examine(hover_target)

        self.player.update(dt)
        if self.pending and not self.player.moving:
            act = self.pending
            self.pending = None
            self.execute(act)

        # companions
        if self.princess_room == self.stage.current:
            if random.random() < 0.004:
                self.princess.set_target(self.player.x + random.randrange(-60, 60),
                                         self.player.y + random.randrange(-10, 10))
            self.princess.update(dt)

        # combat
        room_foes = [f for f in self.foes.get(self.stage.current, []) if not f.dead]
        for f in room_foes:
            if f.think(dt, self.player):
                if self.player.hurt(f.dmg):
                    self.sfx["hit"].play()
                    self.blood_burst(self.player.x, self.player.y - 12, 7)
            f.update(dt)
        if self.player.hp <= 0:
            self.player_died()

        self.update_particles(dt)
        self.dialogue.update(dt)

        # auto-advance on a met objective, but give the beat's dialogue a beat
        # to land first so the story never blitzes past its own scenes
        if self.objective_complete() and self._beat_age() >= BEAT_MIN_MS:
            self.complete_beat()
        self.check_progress()
        self.drain_director()
        self.update_snapshot(room_foes)

    def drain_director(self):
        for call in self.director.drain():
            self.dispatch(call)

    # ------------------------------------------------------------ mouse

    def resolve_hover(self):
        """Returns (label, target descriptor) for whatever is under the cursor."""
        m = self.mouse
        slot = self.bar.slot_at(m)
        if slot is not None:
            if slot < len(self.player.inventory):
                it = self.player.inventory[slot]
                return f"{it.name}: {it.desc}"[:44], ("slot", slot)
            return "", ("slot", slot)
        if m[1] >= IH - BAR_H:
            return "", None
        for f in self.foes.get(self.stage.current, []):
            if not f.dead and f.rect.collidepoint(m):
                return ("Vexuragh" if f.kind == "dragon" else f.kind), ("foe", f)
        if self.dragon_room == self.stage.current and self.dragon_actor.rect.collidepoint(m) \
                and not any(f.kind == "dragon" for f in self.foes.get(self.stage.current, [])):
            return "Vexuragh", ("npc", "dragon")
        if self.princess_room == self.stage.current and self.princess.rect.collidepoint(m):
            return "Maren", ("npc", "princess")
        h = self.stage.room.hotspot_at(m)
        if h:
            return h.kind, ("hotspot", h)
        for d in (-1, 1):
            if self.stage.exit_zone(d).collidepoint(m):
                ok, nxt = self.stage.can_go(d)
                if nxt is None:
                    return "", None
                name = self.stage.rooms[nxt].name if ok else "the way is shut"
                return name, ("exit", d)
        return "", ("walk", m)

    def handle_click(self, target):
        if target is None:
            return
        kind = target[0]
        if kind == "slot":
            i = target[1]
            if i < len(self.player.inventory):
                self.selected_item = None if self.selected_item == i else i
            return
        if kind == "walk":
            self.selected_item = None if self.selected_item is None else self.selected_item
            self.player.set_target(*target[1])
            self.pending = None
            return
        # walk toward the thing, act on arrival
        if kind == "foe":
            f = target[1]
            self.player.set_target(f.x - 14 * (1 if f.x > self.player.x else -1), f.y)
        elif kind == "hotspot":
            h = target[1]
            self.player.set_target(h.x + 12, min(max(h.y, FLOOR_TOP + 4), IH - 12))
        elif kind == "npc":
            a = self.dragon_actor if target[1] == "dragon" else self.princess
            self.player.set_target(a.x - 20 * (1 if a.x > self.player.x else -1), a.y)
        elif kind == "exit":
            z = self.stage.exit_zone(target[1])
            self.player.set_target(z.centerx, self.player.y)
        self.pending = target

    def handle_examine(self, target):
        if not target:
            return
        kind = target[0]
        if kind == "hotspot":
            h = target[1]
            self.dialogue.push("narrator", h.examine_line())
            self.director.remember(f"Kael examined the {h.kind} in {self.stage.room.name}.")
        elif kind == "npc":
            self.dialogue.push("narrator", NPC_EXAMINE[target[1]])
        elif kind == "foe":
            f = target[1]
            self.dialogue.push("narrator", f"A {f.kind}. It means to kill you.")

    # ------------------------------------------------------------ arrival actions

    def execute(self, target):
        kind = target[0]
        room = self.stage.room
        if kind == "hotspot":
            h = target[1]
            h.uses += 1
            if self.selected_item is not None and self.selected_item < len(self.player.inventory):
                item = self.player.inventory[self.selected_item]
                self.selected_item = None
                self.dialogue.push("narrator", f"You try the {item.name} on the {h.kind}...")
                self.mark_progress()
                self.director.remember(
                    f"Kael USED the item '{item.name}' on the {h.kind} in {room.name}. "
                    "Decide what happens; narrate it.")
                self.director.request_tick("an item was used", force=True)
            else:
                self.beat_searches += 1
                self.mark_progress()
                self.dialogue.push("narrator", h.examine_line())
                self.director.remember(
                    f"Kael searched the {h.kind} in {room.name} "
                    f"(search #{h.uses} of that {h.kind}).")
                self.director.request_tick("the player searched something")
        elif kind == "npc":
            who = target[1]
            self.talked_this_beat.add(who)
            self.mark_progress()
            if who == "dragon" and self.beat >= BEATS and self.payoff_talk_t is None:
                self.payoff_talk_t = pygame.time.get_ticks()
            pretty = "Maren" if who == "princess" else "Vexuragh"
            self.dialogue.push("narrator", f"{pretty} turns to you.")
            self.director.remember(
                f"Kael SPEAKS TO {pretty} in {room.name}. Respond in their voice "
                "with say(), and usually offer_choices() so the player can answer.")
            self.director.request_tick("the player started a conversation", force=True)
        elif kind == "foe":
            f = target[1]
            if not f.dead and self.player.dist_to(f) < f.reach + 10:
                self.attack(f)
        elif kind == "exit":
            self.try_exit(target[1])

    def attack(self, f):
        self.player.attack_t = 0.2
        self.player.facing = 1 if f.x > self.player.x else -1
        self.sfx["slash"].play()
        dmg = 2 + (1 if random.random() < self.player.stats["vigor"] * 0.06 else 0)
        if f.hurt(dmg):
            self.sfx["hit"].play()
            self.blood_burst(f.x, f.y - 10, 9)
            if f.dead:
                self.sfx["die"].play()
                self.blood_pool(f.x, f.y, big=(f.kind == "dragon"))
                self.player.kills += 1
                self.beat_kills += 1
                self.mark_progress()
                label = "Vexuragh" if f.kind == "dragon" else f"a {f.kind}"
                self.director.remember(f"Kael KILLED {label} in {self.stage.room.name}.")
                if f.kind == "dragon":
                    self.director.request_tick("the dragon is slain", force=True)
        # keep swinging if they clicked a live foe
        if not f.dead:
            self.pending = ("foe", f)

    def try_exit(self, direction):
        ok, nxt = self.stage.can_go(direction)
        if nxt is None:
            return
        if not ok:
            self.dialogue.push("narrator", "The way is shut. This story is not done with this place.")
            self.director.remember("Kael tried to leave for a locked area; the beat is not resolved.")
            return
        alive = [f for f in self.foes.get(self.stage.current, []) if not f.dead]
        if alive:
            self.director.remember(f"Kael FLED a fight, leaving {len(alive)} foes behind.")
        self.stage.current = nxt
        room = self.stage.room
        self.player.x = 20 if direction > 0 else IW - 20
        self.player.y = FLOOR_TOP + 26
        self.player.stop()
        self.pending = None
        if self.princess_room is not None:
            self.princess_room = nxt  # she keeps pace between rooms
            self.princess.x = self.player.x + (24 if direction > 0 else -24)
            self.princess.y = self.player.y + 4
            self.princess.stop()
        # dragon boss materializes on first entry to the lair
        if self.beat >= BEATS and nxt == len(self.stage.rooms) - 1 \
                and self.story["dragon_role"] == "villain" \
                and getattr(self, "dragon_villain_pending", False):
            self.dragon_villain_pending = False
            self.dragon_room = None
            f = self.spawn_foe("dragon")
            f.x, f.y = IW - 60, FLOOR_TOP + 34
        self.mark_progress()  # travel is momentum: places push the story on
        props = ", ".join(h.kind for h in room.hotspots)
        frontier = nxt >= self.stage.unlocked - 1 and nxt > 0
        note = " This is the FRONTIER — a charged place to escalate or resolve the beat." \
            if frontier else ""
        self.director.remember(
            f"Kael entered {room.name} ({room.style}). Props: {props}.{note}")
        self.director.request_tick("the player entered a new place",
                                   force=frontier)

    def player_died(self):
        self.deaths += 1
        self.sfx["die"].play()
        self.blood_pool(self.player.x, self.player.y)
        self.player.hp = self.player.max_hp
        self.player.hurt_t = 2.0
        self.player.dead = False
        self.foes[self.stage.current] = []  # the field is cleared, the cost is remembered
        if self.stage.current > 0:
            self.stage.current -= 1
            self.player.x, self.player.y = IW - 30, FLOOR_TOP + 26
        self.player.stop()
        self.pending = None
        self.director.remember(f"Ser Kael DIED (death #{self.deaths}) and dragged himself "
                               "back. The story should acknowledge the cost.")
        self.director.request_tick("the knight just died", force=True)
        self.dialogue.push("narrator", "Kael wakes with dirt in his mouth. Dying is a habit he can't afford.")

    # ------------------------------------------------------------ gore

    def blood_burst(self, x, y, n):
        for _ in range(n):
            self.particles.append([x, y, random.uniform(-40, 40), random.uniform(-70, -10),
                                   random.uniform(0.4, 0.9)])

    def blood_pool(self, x, y, big=False):
        w, h = (30, 10) if big else (18, 6)
        blood = self.stage.room.blood
        pygame.draw.ellipse(blood, (110, 16, 20, 230),
                            (int(x) - w // 2, int(y) - h // 2, w, h))
        for _ in range(24 if big else 12):  # spatter
            blood.set_at(
                (max(0, min(IW - 1, int(x) + random.randrange(-w, w + 1))),
                 max(0, min(IH - 1, int(y) + random.randrange(-h, h + 1)))),
                (90, 12, 16, 220))
        for _ in range(3):  # drag streaks
            sx = int(x) + random.randrange(-w // 2, w // 2)
            pygame.draw.line(blood, (100, 14, 18, 210), (sx, int(y)),
                             (sx + random.randrange(-10, 11), int(y) + random.randrange(2, 6)))
        if big:  # what the dragon leaves of you, or you of it
            for _ in range(6):
                blood.set_at(
                    (max(0, min(IW - 1, int(x) + random.randrange(-w, w + 1))),
                     max(0, min(IH - 1, int(y) + random.randrange(-h, h + 1)))),
                    (226, 222, 204, 230))

    def update_particles(self, dt):
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 260 * dt
            p[4] -= dt
            if p[4] <= 0 or p[1] > IH - 10:
                if p[1] > FLOOR_TOP:
                    self.stage.room.blood.set_at(
                        (max(0, min(IW - 1, int(p[0]))), max(0, min(IH - 1, int(p[1])))),
                        (120, 18, 22, 220))
        self.particles = [p for p in self.particles if p[4] > 0 and p[1] <= IH - 10]

    # ------------------------------------------------------------ snapshot

    def update_snapshot(self, room_foes):
        o = self.objective or {}
        room = self.stage.room
        if self.beat < BEATS:
            beat_txt = self.story["beats"][self.beat]
            beat_lab = f"{self.beat + 1}/{BEATS}"
        else:
            beat_txt = "PAYOFF PHASE: " + self.story["payoff"]
            beat_lab = "payoff"
        frontier = self.stage.unlocked - 1
        prog = {"slay": f"{self.beat_kills}/{o.get('value')}",
                "search": f"{self.beat_searches}/{o.get('value')}",
                "talk": f"spoken to: {', '.join(self.talked_this_beat) or 'no one'}",
                "reach": f"at room {self.stage.current}, frontier is {frontier}",
                }.get(o.get("kind"), "-")
        # pacing the director can act on: how long this beat has run, whether it
        # is stalling, and where we are on the rising arc
        if self.beat < BEATS:
            age_s = self._beat_age() // 1000
            idle_s = (pygame.time.get_ticks() - self.progress_t) // 1000
            stall = "  STALLING — push it or advance_beat!" if idle_s * 1000 > BEAT_STALL_MS else ""
            tension = "rising" if self.beat < BEATS - 1 else "CLIMAX — head for the payoff"
            pacing = (f"Pacing: beat running {age_s}s, {idle_s}s since anything moved."
                      f"{stall} Arc tension: {tension} (beat {self.beat + 1}/{BEATS}).")
        else:
            pay_s = ((pygame.time.get_ticks() - self.payoff_started_t) // 1000
                     if self.payoff_started_t else 0)
            pacing = (f"Pacing: PAYOFF running {pay_s}s. Pay the promise and call "
                      "end_story to land the ending.")
        cast = []
        if self.princess_room == self.stage.current:
            cast.append("Maren")
        if self.dragon_room == self.stage.current or any(f.kind == "dragon" for f in room_foes):
            cast.append("Vexuragh")
        inv = ", ".join(i.name for i in self.player.inventory) or "empty"
        self.snapshot_text = (
            f"Beat {beat_lab}: {beat_txt}\n"
            f"Objective: {o.get('kind')} ({o.get('text')}), progress {prog}\n"
            f"Location: {room.name} ({room.style}), props: "
            f"{', '.join(h.kind for h in room.hotspots)}\n"
            f"Present: {', '.join(cast) or 'Kael alone'}. Foes here: "
            f"{', '.join(f.kind for f in room_foes) or 'none'}\n"
            f"Kael: HP {self.player.hp}/{self.player.max_hp}, deaths {self.deaths}, "
            f"kills {self.player.kills}, stats VIG {self.player.stats['vigor']} "
            f"WIT {self.player.stats['wit']} PRE {self.player.stats['presence']}\n"
            f"Inventory: {inv}\n"
            f"Bond with Maren: {self.bond}\n"
            f"Rooms unlocked: {self.stage.unlocked}/{len(self.stage.rooms)}\n"
            f"{pacing}")

    # ================================================================ drawing

    def draw(self):
        s = self.screen
        if self.state == "menu":
            self.draw_menu(s)
        elif self.state == "models":
            self.models.draw(s)
        elif self.state == "select":
            self.select.draw(s, self.forge.snapshot())
        elif self.state == "play":
            self.draw_play(s)
        elif self.state == "epilogue":
            self.draw_epilogue(s)
        if self.state != "play":
            draw_cursor(s, getattr(self, "mouse", (0, 0)), "normal", self.fonts)
        self.console.draw(s)

    def draw_menu(self, s):
        s.fill((14, 12, 28))
        t = pygame.time.get_ticks() / 1000
        s.blit(self.fonts.text("ASH & OATH", (216, 168, 50), big=True), (118, 30))
        s.blit(self.fonts.text("a story directed by a machine that dreams", (140, 145, 165)), (62, 50))
        spr = self.art["sprites"]
        bobby = int(math.sin(t * 3) * 2)
        s.blit(pygame.transform.scale_by(spr["knight"]["idle0"], 2), (86, 86 + bobby))
        s.blit(pygame.transform.scale_by(spr["princess"]["idle0"], 2), (146, 86 - bobby))
        s.blit(pygame.transform.scale_by(spr["dragon"]["idle"], 2), (190, 74 + bobby))
        model = self.client.resolve_model()
        status = f"LLM: {model.split(':')[0][:34]}" if model else "LLM offline — scribe's reserve stories"
        s.blit(self.fonts.text(status, (110, 160, 110) if model else (200, 120, 80)), (8, IH - 22))
        hint = self.fonts.text("L — change model", (150, 150, 175))
        s.blit(hint, (IW - hint.get_width() - 6, IH - 22))
        if int(t * 2) % 2:
            s.blit(self.fonts.text("CLICK OR PRESS ENTER", (230, 225, 210)), (108, 150))
        if os.path.exists(SAVE_PATH):
            s.blit(self.fonts.text("C — continue the saved story", (216, 168, 50)), (108, 136))

    def draw_intimacy(self, s):
        room = self.stage.room
        s.blit(room.bg, (0, 0))
        s.blit(room.blood, (0, 0))
        for h in room.hotspots:
            h.draw(s)
        # night falls on the room
        veil = pygame.Surface((IW, IH), pygame.SRCALPHA)
        veil.fill((8, 4, 12, 165))
        s.blit(veil, (0, 0))
        cx, cy = int(self.player.x), int(self.player.y)
        glow = pygame.Surface((120, 70), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (250, 150, 60, 34), glow.get_rect())
        s.blit(glow, (cx - 60, cy - 50))
        frames = self.art["sprites"]["embrace"]  # list; supports embrace_custom.png mods
        img = frames[int(self.scene["t"] * 1.5) % len(frames)]
        r = img.get_rect(midbottom=(cx, cy))
        s.blit(img, r.topleft)
        for e in self.embers:
            col = (250, 200, 90) if int(e[0] + e[1]) % 2 else (240, 140, 50)
            s.set_at((max(0, min(IW - 1, int(e[0]))), max(0, min(IH - 1, int(e[1])))), col)
        self.dialogue.draw(s)
        beat_lab = f"BEAT {min(self.beat + 1, BEATS)}/{BEATS}" if self.beat < BEATS else "PAYOFF"
        self.bar.draw(s, self.player, beat_lab, "", self.director.status, None, "")

    def draw_play(self, s):
        if self.scene:
            self.draw_intimacy(s)
            return
        room = self.stage.room
        s.blit(room.bg, (0, 0))
        s.blit(room.blood, (0, 0))
        # exit chevrons
        for d in (-1, 1):
            ok, nxt = self.stage.can_go(d)
            if nxt is None:
                continue
            col = (216, 168, 50) if ok else (70, 66, 80)
            x = 6 if d < 0 else IW - 6
            for i in range(3):
                y = 128 + i * 10
                pygame.draw.polygon(s, col, [(x - 3 * d, y), (x + 2 * d, y + 3), (x - 3 * d, y + 6)])
        # y-sorted drawables
        drawables = [(h.y, "prop", h) for h in room.hotspots]
        if self.princess_room == self.stage.current:
            drawables.append((self.princess.y, "actor", self.princess))
        if self.dragon_room == self.stage.current and not any(
                f.kind == "dragon" for f in self.foes.get(self.stage.current, [])):
            drawables.append((self.dragon_actor.y, "actor", self.dragon_actor))
        for f in self.foes.get(self.stage.current, []):
            if not f.dead:
                drawables.append((f.y, "actor", f))
        drawables.append((self.player.y, "actor", self.player))
        for _, kind, obj in sorted(drawables, key=lambda d: d[0]):
            obj.draw(s)
        # blood spray
        for p in self.particles:
            s.set_at((max(0, min(IW - 1, int(p[0]))), max(0, min(IH - 1, int(p[1])))),
                     (200, 30, 34))
        # room name
        s.blit(self.fonts.text(room.name.upper(), (150, 155, 175)),
               (IW - self.fonts.small.size(room.name.upper())[0] - 6, IH - BAR_H - 12))
        # UI
        beat_lab = f"BEAT {min(self.beat + 1, BEATS)}/{BEATS}" if self.beat < BEATS else "PAYOFF"
        sel = self.selected_item if (self.selected_item is not None
                                     and self.selected_item < len(self.player.inventory)) else None
        self.bar.draw(s, self.player, beat_lab,
                      self.objective["text"] if self.objective else "",
                      self.director.status, sel, self.hover_label)
        self.dialogue.draw(s)
        self.choices.draw(s)
        if self.paused:
            veil = pygame.Surface((IW, IH), pygame.SRCALPHA)
            veil.fill((8, 8, 16, 215))
            s.blit(veil, (0, 0))
            s.blit(self.fonts.text("PAUSED — THE STORY WAITS", (216, 168, 50), big=True), (66, 8))
            y = 30
            for key, desc in KEY_HELP:
                if not desc:  # section header
                    s.blit(self.fonts.text(key, (140, 145, 165)), (24, y))
                else:
                    s.blit(self.fonts.text(key.strip().upper().ljust(12), (216, 168, 50)), (32, y))
                    s.blit(self.fonts.text(desc, (210, 210, 200)), (110, y))
                y += 11
            saved = "quicksave present" if os.path.exists(SAVE_PATH) else "no save yet"
            s.blit(self.fonts.text(saved, (110, 120, 150)), (24, y + 2))
        if not self.console.open and pygame.key.get_pressed()[pygame.K_TAB]:
            self.draw_beats(s)
        mode = "item" if sel is not None else ("hot" if self.hover_label else "normal")
        item_name = self.player.inventory[sel].name if sel is not None else None
        draw_cursor(s, self.mouse, mode, self.fonts, item_name)

    def draw_beats(self, s):
        """Held-TAB overlay: the story's beats, achieved / current / unrevealed."""
        veil = pygame.Surface((IW, IH), pygame.SRCALPHA)
        veil.fill((8, 8, 16, 210))
        s.blit(veil, (0, 0))
        s.blit(self.fonts.text("THE STORY SO FAR", (216, 168, 50), big=True), (20, 6))
        y = 26
        for i, beat in enumerate(self.story["beats"]):
            if i < self.beat:
                mark, col = "DONE", (110, 160, 110)
            elif i == self.beat:
                mark, col = "NOW", (216, 168, 50)
            else:
                mark, col = "...", (80, 86, 110)
            text = beat if i <= self.beat else "(not yet revealed)"
            s.blit(self.fonts.text(mark, col), (20, y))
            for line in wrap(self.fonts.small, f"{i + 1}. {text}", IW - 78)[:2]:
                s.blit(self.fonts.text(line, col), (52, y))
                y += 10
            y += 3
        if self.beat >= BEATS:
            col = (110, 160, 110) if self.payoff_done else (230, 220, 190)
            for line in wrap(self.fonts.small, "PAYOFF: " + self.story["payoff"], IW - 78)[:2]:
                s.blit(self.fonts.text(line, col), (52, y))
                y += 10
        else:
            s.blit(self.fonts.text("PAYOFF: ...", (80, 86, 110)), (52, y))

    def draw_epilogue(self, s):
        s.fill((10, 10, 20))
        story = self.story
        s.blit(self.fonts.text(story["title"].upper(), (216, 168, 50), big=True), (20, 18))
        y = 44
        s.blit(self.fonts.text("THE PROMISE", (140, 145, 165)), (20, y)); y += 11
        for line in wrap(self.fonts.small, story["promise"], IW - 40)[:3]:
            s.blit(self.fonts.text(line, (210, 210, 200)), (20, y)); y += 10
        y += 8
        s.blit(self.fonts.text("THE PAYOFF", (140, 145, 165)), (20, y)); y += 11
        for line in wrap(self.fonts.small, story["payoff"], IW - 40)[:4]:
            s.blit(self.fonts.text(line, (230, 220, 190)), (20, y)); y += 10
        y += 8
        # the director's own closing line, when it chose to end through words
        closing = getattr(self, "epilogue_text", None)
        if closing and closing.strip() != story["payoff"].strip():
            s.blit(self.fonts.text("HOW IT ENDED", (140, 145, 165)), (20, y)); y += 11
            for line in wrap(self.fonts.small, closing, IW - 40)[:4]:
                s.blit(self.fonts.text(line, (200, 205, 220)), (20, y)); y += 10
        y += 10
        s.blit(self.fonts.text(f"deaths: {self.deaths}   kills: {self.player.kills}",
                               (150, 150, 170)), (20, y))
        s.blit(self.fonts.text("ENTER — back to the fire", (230, 225, 210)), (20, IH - 20))
