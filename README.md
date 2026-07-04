# Ash & Oath — knight / princess / dragon

A 90s-style **pixel point-and-click adventure** where a **local LLM is the
game master**. Darkside Detective looks, Quest for Glory play (adventure +
stats + fights), Gabriel Knight mood. Stories are generated in the background
on Brandon Sanderson's promise → progress → payoff structure; every minute
(configurable) — and immediately after anything important you do — the
Director agent answers with dialogue, choices, items, skill checks and
trouble. Dialogue is voiced with offline TTS. Adults only. See [PRD.md](PRD.md).

## Requirements

- Python 3.12+ (tested on 3.14), Windows
- [Ollama](https://ollama.com) running locally (optional — the game falls back
  to built-in stories without it)

```
pip install -r requirements.txt
ollama pull defyma85/gemma-4-E4B-it-ultra-uncensored-heretic-Q4_K_M_gguf
python main.py
```

Pixel art is generated on first launch (`assets/generate_assets.py`).

## Controls

| Input | Action |
|---|---|
| Left-click | walk / search prop / talk / attack foe / take exit / pick choice |
| Right-click | examine what's under the cursor |
| Click inventory slot | arm an item, then click a target to use it on |
| E | skip dialogue line |
| F5 | force a director tick now |
| F6 / F7 | quicksave / load (C on the title screen continues a save) |
| M | mute/unmute TTS |
| Esc | pause — shows the full key reference (Q abandons the story) |
| R (story select) | re-forge all three stories |

Saves land in `saves/quicksave.json` and include the Director's memory of
your deeds, so the game master picks up the thread instead of restarting the
tale. One slot, Sierra-style — save before doing something brave.

## How a run works

1. **Story select** — three outlines forge in the background; pick one
   (its *promise* shows on the selected card). `[SCRIBE'S RESERVE]` marks a
   built-in fallback used when the LLM was unavailable or too slow.
2. **Five beats across six rooms** — each beat gates the next room behind an
   objective (talk / search / slay / story). Everything you click is reported
   to the Director, and important deeds (conversations, item uses, choices,
   deaths) make it respond immediately — with dialogue, choice menus, items,
   skill checks (VIG/WIT/PRE + d6) or an ambush.
3. **Payoff** — the lair opens; the dragon is a boss, an ally, or a tragedy,
   per the story's `dragon_role`. The promise gets paid. Epilogue card.

When the story earns it, the game master can stage an **intimate scene** —
the room dims to firelight, an embrace plays out in pixels, and the model's
narration carries the moment (usually offered to you as a choice first).
It heals, and it deepens a bond the story remembers.

### Modding the intimate scene

The scene plays whatever spritesheet it finds — drop your own art at
`assets/sprites/embrace_custom.png` and it overrides the shipped embrace:
square frames laid side by side (frame width = sheet height), any frame
count, played on a loop under the firelight veil. The shipped art stays at
an embrace; what you put in the override file is up to you.

The green/yellow lamp in the bottom-right corner is the Director: yellow while
the model is thinking. Blood stays where it was spilled.

## Configuration — `config.json`

| Key | Meaning |
|---|---|
| `ollama.model` | preferred model; falls back to any installed chat model |
| `director_interval_seconds` | director tick cadence (default 60) |
| `story_count` | outlines forged at boot (min 3) |
| `content_directive` | narrative tone instructions sent with every LLM call — edit to taste; the shipped default is gritty adult dark-fantasy |
| `tts_enabled` / `tts_rate_base` | voice output |
| `scale` | window = 320×180 × scale |

## Content note

This is a game for adults: the default directive asks the model for violence,
harsh language and mature themes. What your chosen local model produces with
that directive is your prerogative — tune `content_directive` and the model in
`config.json`.
