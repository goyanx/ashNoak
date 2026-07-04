"""Minimal agentic framework: perceive -> reason -> act with typed tools.

The Agent builds a prompt from its persona + rolling memory + a fresh
observation, asks the LLM for a JSON list of tool calls, validates them
against the registry, and returns them. Execution is the caller's job
(the game thread owns all game state), which keeps the loop pure and
thread-safe by construction.
"""
import json
import re
from collections import deque
from dataclasses import dataclass, field

from .trace import TRACE


@dataclass
class Tool:
    name: str
    description: str
    params: dict = field(default_factory=dict)  # param name -> description

    def signature(self):
        args = ", ".join(f"{k}: {v}" for k, v in self.params.items())
        return f"- {self.name}({args}) — {self.description}"


class Memory:
    def __init__(self, limit=24):
        self.events = deque(maxlen=limit)

    def add(self, text):
        self.events.append(text)

    def render(self):
        if not self.events:
            return "(nothing yet)"
        return "\n".join(f"- {e}" for e in self.events)


def extract_json(text):
    """Tolerantly pull the first JSON value out of model output."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text).strip()
    # try verbatim first
    for candidate in (text,):
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            pass
    # scan for the first balanced JSON value, whichever bracket comes first
    pairs = sorted((p for p in (("[", "]"), ("{", "}")) if text.find(p[0]) >= 0),
                   key=lambda p: text.find(p[0]))
    for opener, closer in pairs:
        start = text.find(opener)
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == opener:
                    depth += 1
                elif c == closer:
                    depth -= 1
                    if depth == 0:
                        chunk = text[start:i + 1]
                        chunk = re.sub(r",\s*([\]}])", r"\1", chunk)  # trailing commas
                        try:
                            return json.loads(chunk)
                        except ValueError:
                            break
    return None


class Agent:
    def __init__(self, name, persona, tools, client, memory_limit=24):
        self.name = name
        self.persona = persona
        self.tools = {t.name: t for t in tools}
        self.client = client
        self.memory = Memory(memory_limit)

    def system_prompt(self):
        toollist = "\n".join(t.signature() for t in self.tools.values())
        return (
            f"{self.persona}\n\n"
            f"You act ONLY by calling tools. Available tools:\n{toollist}\n\n"
            'Reply with a JSON array of tool calls, nothing else, e.g.\n'
            '[{"tool": "say", "args": {"speaker": "knight", "text": "..."}}]\n'
            "Use 1 to 5 tool calls per reply. An empty array [] is allowed if "
            "nothing should happen."
        )

    def step(self, observation):
        """One perceive->reason->act cycle. Returns validated tool calls."""
        messages = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content":
                f"RECENT EVENTS:\n{self.memory.render()}\n\n"
                f"CURRENT OBSERVATION:\n{observation}\n\n"
                "Respond with your JSON array of tool calls now."},
        ]
        raw = self.client.chat(messages, json_format=False, temperature=0.9,
                               tag=self.name)
        data = extract_json(raw)
        if isinstance(data, dict):  # single call or {"calls": [...]}
            data = data.get("calls", [data])
        if not isinstance(data, list):
            # distinguish "model returned garbage" from "model chose to do nothing"
            TRACE.log("agent_step", agent=self.name, outcome="parse_failed",
                      raw_chars=len(raw) if raw else 0)
            return []
        calls = []
        rejected = []
        for item in data:
            if not isinstance(item, dict):
                rejected.append(item)
                continue
            name = item.get("tool") or item.get("name")
            args = item.get("args") or item.get("arguments") or {}
            if name in self.tools and isinstance(args, dict):
                calls.append({"tool": name, "args": args})
            else:
                rejected.append(item)
        TRACE.log("agent_step", agent=self.name, outcome="ok",
                  calls=calls[:5], rejected=rejected,
                  overflow=max(0, len(calls) - 5))
        return calls[:5]
