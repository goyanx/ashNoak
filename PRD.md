# PRD — *Ash & Oath*: An LLM-Driven Retro Point-and-Click Adventure

> **v2 (2026-07-04).** Pivoted from side-scroller to point-and-click adventure:
> the pixel look of *The Darkside Detective*, the play of Sierra's *Quest for
> Glory* (adventure + light RPG stats), the mood of *Gabriel Knight*. The story
> engine (StoryForge, Director agent, Ollama client, TTS) is **locked** — v2
> changed only the Director's toolset/persona and the entire game layer.
> Superseded v1 sections are marked; §15 specifies v2.

| | |
|---|---|
| **Working title** | Ash & Oath (Knight, Princess, Dragon) |
| **Genre** | 2D point-and-click adventure with RPG-lite stats (QFG-style), story-driven, investigative noir mood (Gabriel Knight) |
| **Aesthetic** | 1990s pixel adventure (Darkside Detective register), 4× nearest-neighbor scaling, moody palettes |
| **Platform** | Windows desktop (Python 3.12+, pygame-ce) |
| **Audience** | Adults (18+). Mature narrative: sex, gore and violence as the story needs — steered by the user-editable content directive and the local model |
| **LLM backend** | Local Ollama — default model: `defyma85/gemma-4-E4B-it-ultra-uncensored-heretic-Q4_K_M_gguf` (configurable) |

---

## 1. Vision

A playable 90s-style side-scroller where the *story is not authored — it is directed live by a local LLM*. Three fixed cast members — the **Knight** (player), the **Princess**, and the **Dragon** — are actors; the LLM is the dungeon-master. On a configurable cadence (default: every 60 seconds) a **Story Director agent** observes the game state and issues dialogue, actions, and beat progression. Stories are generated in the background at boot, structured on Brandon Sanderson's **Promise → Progress → Payoff** model, and the player picks one of at least three before playing.

## 2. Goals / Non-Goals

**Goals**
- G1. A complete, runnable game loop: menu → story select → play → payoff ending.
- G2. LLM-generated stories (≥3) populated asynchronously in the background; the game is never blocked waiting on the model.
- G3. Periodic LLM "director ticks" (configurable interval, default 60 s) that inject dialogue and world actions via a tool-calling agent loop.
- G4. All-original retro pixel art: animated spritesheets for the three leads plus enemies, and themed parallax backgrounds — everything pixelated.
- G5. Offline TTS voicing of dialogue (Windows SAPI via `pyttsx3`), with distinct voice parameters per character.
- G6. Fully offline: no cloud calls; Ollama runs locally.
- G7. Graceful degradation: if Ollama or the preferred model is unavailable, fall back to any installed model, then to built-in canned stories — the game always runs.

**Non-Goals**
- Multiplayer, save systems, controller support, level editors (v1).
- Photorealistic or high-res art. Everything stays chunky.
- Streaming voice cloning; SAPI voices are sufficient for v1.

## 3. Content Rating & Safety

The game targets adults. The narrative tone directive sent to the LLM is **user-editable in `config.json`** (`content_directive`). The shipped default requests a gritty, mature dark-fantasy register: real stakes, moral ambiguity, blood-and-steel violence, harsh language, adult relationships handled with fade-to-black discretion. What the local model produces beyond that directive is between the user, their model choice, and their machine — the engine does not filter model output, and the directive is the user's prerogative to edit. Explicit content is **not** shipped as a default; violence and dark themes are.

## 4. The Cast

| Character | Role | Sprite | Voice |
|---|---|---|---|
| **Ser Kael, the Knight** | Player character. Sword combat, run/jump. | 16×24 px, 4× scale; idle/walk/attack/hurt frames | Low pitch, slow rate |
| **Princess Maren** | Companion NPC. Follows, comments, has her own agenda per story. | 16×24 px; idle/walk frames | Higher pitch, normal rate |
| **Vexuragh, the Dragon** | Antagonist *or* ally — story-dependent. Boss-scale sprite. | 48×32 px; idle/fly/breathe frames | Lowest pitch, slowest rate |

The LLM decides each run whether the Dragon is villain, victim, or third protagonist. The Princess is never guaranteed to be a damsel — the outline generator is explicitly told to subvert at will.

## 5. Story System (Promise / Progress / Payoff)

### 5.1 Structure
Every story is a JSON outline:

```json
{
  "title": "...", "logline": "...",
  "theme": "forest | castle | volcano",
  "promise": "what the opening scene vows to the player",
  "beats": ["beat 1", "beat 2", "beat 3", "beat 4", "beat 5"],
  "payoff": "how the promise is paid off, twist included",
  "dragon_role": "villain | ally | tragic",
  "opening_lines": [{"speaker": "knight", "text": "..."}]
}
```

- **Promise** — surfaced verbatim to the player on the story-select screen and dramatized in the opening dialogue.
- **Progress** — the 5 beats map to level zones; advancing a zone requires satisfying the beat objective (kill quota, reach marker, survive timer — chosen by the director).
- **Payoff** — final zone triggers the payoff scene: scripted dialogue + dragon confrontation/resolution, then an epilogue card.

### 5.2 Background generation
- At boot, a `StoryForge` worker thread requests **3 outlines** (count configurable) from Ollama, one request each, JSON-schema-constrained (`format: json`).
- The story-select screen renders immediately with placeholder cards ("forging…") that fill in as outlines arrive.
- Three hand-written fallback outlines ship in `stories/fallback.py`; they are used per-slot if generation fails or times out (45 s per story).
- Regeneration: pressing **R** on story select re-forges all slots.

## 6. Director Agent (the "agentic framework")

A purpose-built lightweight agent loop (`agent/framework.py`) — perceive → reason → act with typed tools, in the style of a minimal ReAct loop. It is small, dependency-free, and inspectable, which beats dragging a heavyweight orchestration dependency into a 60 FPS game.

- **Agent**: system prompt (persona: "Game Director"), rolling memory of the last N events, tool registry.
- **Perceive**: each tick receives a compact world snapshot — beat index/objective, HP, positions, kills, recent player deeds, recent dialogue.
- **Act**: model must reply with a JSON list of tool calls. Registered tools:

| Tool | Effect |
|---|---|
| `say(speaker, text)` | Queue dialogue (typewriter box + TTS) |
| `spawn(kind, count)` | Spawn enemies: `raider`, `wolf`, `cultist` |
| `set_objective(kind, value, text)` | Set beat objective: `kill_count`, `reach_marker`, `survive` |
| `advance_beat()` | Force the story to the next beat |
| `dragon(action)` | `appear`, `leave`, `attack`, `land` |
| `heal(target, amount)` | Restore HP (mercy or story reasons) |
| `narrate(text)` | On-screen narrator caption |

- **Cadence**: a timer thread fires every `director_interval_seconds` (default **60**, configurable) and also on high-value events (beat completed, player near death, boss engaged) with a 15 s debounce. LLM calls run off the main thread; results land in a thread-safe queue drained by the game loop. **The render loop never blocks on the model.**
- Malformed model output → tolerant JSON repair, else the tick is skipped silently.

## 7. Gameplay

- **Controls**: ←/→ or A/D move · Space/W jump · J/X attack · E interact · Esc pause · F5 force director tick · M mute TTS.
- **Combat**: sword arc hitbox, enemy contact damage, knockback, i-frames, hearts HUD (Knight 10 HP). Princess can be hurt in escort beats; her death fails back to the beat checkpoint.
- **World**: each story theme selects a tileset + 3-layer parallax background (sky / far / near). Levels are long horizontal strips (~12 screens) segmented into 5 beat-zones plus a payoff arena. Camera follows with lookahead.
- **Enemies**: raider (walker), wolf (fast lunger), cultist (ranged bolt). Dragon has fly-by fire-breath and grounded phases.
- **Feel targets**: 60 FPS, 320×180 internal resolution scaled ×4 to 1280×720, chunky screenshake on hits, palette-flash damage feedback.

## 8. Art

All assets are generated as PNGs by `assets/generate_assets.py` (procedural pixel art from hand-authored pixel grids + palette): character spritesheets, enemy sheets, tilesets, and three themed parallax background sets (forest / castle / volcano). No external downloads, no licensing risk, everything crisply pixelated (no anti-aliasing; nearest-neighbor scaling only). Regenerating is one command, and grids are human-editable for reskinning.

## 9. Audio

- **TTS**: `pyttsx3` (SAPI5) on a dedicated worker thread with a speech queue; per-character rate/pitch/voice mapping; dialogue box advances independently of speech; mute toggle.
- **SFX** (v1, procedural): square/noise bleeps generated at runtime for sword, hit, jump, death — 90s-authentic.

## 10. Configuration (`config.json`)

```json
{
  "ollama": {
    "host": "http://127.0.0.1:11434",
    "model": "defyma85/gemma-4-E4B-it-ultra-uncensored-heretic-Q4_K_M_gguf",
    "fallback_to_any_model": true,
    "request_timeout_seconds": 120
  },
  "director_interval_seconds": 60,
  "story_count": 3,
  "content_directive": "<user-editable narrative tone instructions>",
  "tts_enabled": true,
  "scale": 4
}
```

## 11. Architecture

```
main.py
├─ game/            pygame-ce engine
│   ├─ engine.py    fixed-step loop, scene stack (Menu → StorySelect → Play → Epilogue)
│   ├─ entities.py  Knight, Princess, Dragon, enemies, physics
│   ├─ world.py     tiles, camera, parallax, beat zones
│   └─ ui.py        dialogue box, HUD, menus
├─ agent/           LLM side (all off the main thread)
│   ├─ framework.py minimal Agent/Tool/Memory loop
│   ├─ director.py  Story Director agent + tick scheduler
│   ├─ storyforge.py background story outline generation
│   ├─ ollama_client.py
│   └─ tts.py
└─ assets/generate_assets.py
```

Threading contract: game thread owns all game state; agent threads communicate **only** via queues (`director_out`, `story_out`, `tts_in`).

## 12. Milestones

1. **M1** — Asset generator + engine skeleton renders animated cast on parallax world. ✅ v1 scope
2. **M2** — Combat, enemies, beats/objectives, HUD, scene flow. ✅ v1 scope
3. **M3** — Ollama client, StoryForge background generation, story select. ✅ v1 scope
4. **M4** — Director agent ticks + tool dispatch + TTS. ✅ v1 scope
5. **M5** — Payoff arena, epilogue, polish (screenshake, SFX). ✅ v1 scope

## 13. Risks

| Risk | Mitigation |
|---|---|
| Preferred model not pulled / Ollama down | Fallback chain: configured model → any installed chat model → canned stories; game never blocks |
| Small models emit broken JSON | `format: json` + schema-in-prompt + tolerant repair + skip-on-fail |
| LLM latency > tick interval | Ticks are fire-and-forget; overlapping ticks are coalesced |
| TTS blocking the loop | Dedicated speech thread + queue |
| Model output tone drift | `content_directive` is re-sent every call; user-tunable |

## 14. Success Criteria

- Boots to menu in < 3 s with zero network access required.
- Three distinct LLM-forged stories selectable within ~2 min of boot on the target model (instantly via fallbacks).
- Director visibly changes the run (dialogue + spawns + objectives) at the configured cadence.
- A full story is completable in 10–20 minutes ending in a payoff scene that references its promise.

---

## 15. v2 — Point-and-Click Specification (current)

### 15.1 What replaced the platformer
Sections 4 (sprites reused), 6 (tools replaced), 7 (gameplay replaced): the
run-and-jump level strip is gone. The game is now mouse-driven adventure play
across **six connected rooms per theme** (exterior → hall → crypt → hall →
exterior → **lair**), each a full-screen pixel scene with 3–4 interactive
props. Story beats gate rooms left-to-right; the lair hosts the payoff.

### 15.2 Interaction model
- **Left-click**: walk; on a prop/NPC/foe/exit — walk there, then act
  (search / talk / strike / leave).
- **Right-click**: examine (instant canned GK-tone flavor line; logged for the
  Director).
- **Inventory** (bottom bar, 8 slots): click to arm an item, click a target to
  use it on that target — the Director decides what happens.
- **Dialogue box at the TOP of the screen** (v1 feedback: never covers actors),
  typewriter + TTS. **Choice panel**: when the Director calls
  `offer_choices`, 2–4 player responses appear; the pick is fed back to the
  Director and forces a tick — LLM-driven dialogue trees.
- **Stats (QFG-lite)**: VIG / WIT / PRE. The Director calls
  `skill_check(stat, difficulty, reason)`; the engine rolls stat + d6, narrates
  the result and feeds the outcome back to the story. Failed vigor draws blood.
- **Combat**: click a foe to close and swing; foes chase and strike on
  cooldowns. Blood sprays and **pools persist per room** for the gore register.
  Death costs a room and is written into the story, Sierra-style but merciful.

### 15.3 Every player deed is story input
Room entries, searches, examinations, item uses, conversations, choice picks,
kills, deaths and skill results are all written into the Director's memory;
significant deeds (talk, item use, choice, death, dragon events) force an
immediate tick so the world answers the player, not just the clock.

### 15.4 v2 Director toolset
`say` (any speaker, incl. named minor NPCs) · `narrate` · `offer_choices` ·
`give_item` / `take_item` · `skill_check` · `set_objective`
(slay / search / talk / story) · `advance_beat` · `spawn_encounter` ·
`move_actor` (princess/dragon here/away) · `harm` / `heal`.

### 15.5 Payoff staging
Final beat unlocks the lair. `dragon_role: villain` → boss fight (click
combat, dragon at 2× scale). `ally`/`tragic` → confront and *talk* to
Vexuragh; the Director stages the scene and the story resolves through it.
Epilogue card unchanged (promise vs payoff, deaths, kills).

### 15.6 Intimacy system (v2.1)
The Director has an `intimate_scene(partner, text)` tool for lovemaking when
the story has earned it (persona guidance: player consent via `offer_choices`
first, never mid-combat, must serve the promise). The engine plays a discreet
pixel treatment — the room dims to firelight, an embrace animation plays
(generated 24×24 two-frame sprite, Kael unarmored), embers rise, and the
model's narration carries the moment at whatever register the content
directive and model choose. Mechanically: +2 HP to both, and a **bond**
counter rises and is reported in every Director snapshot, so intimacy has
story memory and consequences. A `bed` prop seeds such scenes in halls.

### 15.7 Gore (v2.1)
Blood sprays on every wound and pools permanently per room; kills add spatter
and drag streaks; boss-scale deaths leave wide pools flecked with bone.

### 15.8 Content (v2)
The shipped `content_directive` states the game is 18+, permits sex, gore and
violence when the story calls for them, and leaves explicitness to the
narrator model's judgment. It is re-sent with every LLM call and remains fully
user-editable in `config.json`; the engine does not filter model output.
