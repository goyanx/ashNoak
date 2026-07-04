"""Rooms, hotspots and canned examine flavor for the point-and-click stage.

Six connected rooms per theme; story beats unlock them left to right and
the last room is the payoff lair. Prop meaning is supplied live by the
Director — these canned lines are just the instant click feedback.
"""
import os
import random

import pygame

from .settings import ASSETS, IH, IW

FLOOR_TOP = 122
FLOOR_BOT = IH - 8
ARCHETYPES = ["exterior", "hall", "crypt", "hall", "exterior", "lair"]

ROOM_NAMES = {
    "forest": ["Thornwood Road", "Waystation Hall", "Barrow Crypt",
               "Hunting Lodge", "Blackmere Clearing", "The Wyrm Hollow"],
    "castle": ["Castle Gates", "The Great Hall", "The Undercroft",
               "Library Tower", "The Battlements", "Throne Ruin"],
    "volcano": ["Ashen Path", "Cult Refectory", "The Ossuary",
                "Chained Shrine", "Caldera Rim", "The Egg Chamber"],
}

PROP_POOL = {
    "exterior": ["well", "bones", "corpse", "barrel", "statue"],
    "hall": ["chest", "barrel", "bookshelf", "brazier", "door", "bed"],
    "crypt": ["altar", "bones", "corpse", "statue", "brazier"],
    "lair": ["altar", "bones", "chest", "corpse"],
}

EXAMINE = {
    "chest": ["Iron-banded and scarred. Somebody wanted it to stay shut.",
              "The lock has been forced before. Amateurs. Or the desperate."],
    "corpse": ["Days dead. Someone went through the pockets first and wasn't gentle.",
               "The wounds are wrong — too clean for beasts, too many for a duel."],
    "altar": ["The stains on the stone never dried all the way. They never do.",
              "Old god or new, whatever was worshipped here liked its offerings red."],
    "barrel": ["It smells of vinegar and, faintly, of something buried.",
               "Tap it: half full. Of what is another question."],
    "bookshelf": ["Ledgers, hymnals, and one spine with no title at all.",
                  "Someone shelved these in a hurry. Or searched them in one."],
    "brazier": ["The coals are warm. Someone fed this fire within the hour.",
                "Firelight is honest. It shows the scratches on the floor."],
    "statue": ["Its face was chiseled off. Deliberately. Recently.",
               "Whoever it honored, someone worked hard to make you forget."],
    "bones": ["Picked clean and cracked for the marrow. Not by wolves.",
              "A jawbone, human, with a coin wedged between the teeth."],
    "door": ["Heavy oak, iron hinges, and scratches around the keyhole.",
             "Barred from the other side. Someone is afraid of this room."],
    "well": ["The rope is cut. The bucket is down there with whatever else is.",
             "Drop a pebble: a long silence, then something other than water."],
    "bed": ["Slept in, and not by one. The room remembers what the sheets do.",
            "Warm linens in a cold keep. Somebody's sanctuary, or somebody's trap."],
}

NPC_EXAMINE = {
    "princess": "Maren. She watches everything, including you. Especially you.",
    "dragon": "Vexuragh. Even still, it looks like the end of a story.",
}


class Hotspot:
    def __init__(self, kind, image, x, feet_y):
        self.kind = kind
        self.image = image
        self.x = x
        self.y = feet_y  # bottom-center anchor
        self.uses = 0

    @property
    def rect(self):
        w, h = self.image.get_size()
        return pygame.Rect(self.x - w // 2, self.y - h, w, h)

    def examine_line(self):
        lines = EXAMINE.get(self.kind, ["Nothing you can use. Yet."])
        return lines[self.uses % len(lines)]

    def draw(self, surf):
        surf.blit(self.image, self.rect.topleft)


class Room:
    def __init__(self, theme, index, art, rng):
        self.index = index
        self.style = ARCHETYPES[index]
        self.name = ROOM_NAMES[theme][index]
        self.bg = pygame.image.load(os.path.join(
            ASSETS, "backgrounds", "rooms", f"{theme}_{index}.png")).convert()
        self.blood = pygame.Surface((IW, IH), pygame.SRCALPHA)  # persistent gore
        self.hotspots = []
        pool = list(PROP_POOL[self.style])
        rng.shuffle(pool)
        xs = rng.sample(range(50, IW - 50, 30), min(4, len(pool)))
        for kind, x in zip(pool, sorted(xs)):
            img = art["sprites"]["props"][kind]
            feet = rng.randrange(FLOOR_TOP + 12, FLOOR_TOP + 34)
            self.hotspots.append(Hotspot(kind, img, x, feet))

    def hotspot_at(self, pos):
        for h in self.hotspots:
            if h.rect.collidepoint(pos):
                return h
        return None


class Stage:
    """The six rooms plus which are unlocked (story-gated)."""

    def __init__(self, theme, art, seed=0):
        rng = random.Random(seed)
        self.theme = theme
        self.rooms = [Room(theme, i, art, rng) for i in range(len(ARCHETYPES))]
        self.current = 0
        self.unlocked = 1  # rooms 0..unlocked-1 reachable; beats push it up

    @property
    def room(self):
        return self.rooms[self.current]

    def can_go(self, direction):
        nxt = self.current + direction
        if not 0 <= nxt < len(self.rooms):
            return False, None
        if nxt >= self.unlocked:
            return False, nxt
        return True, nxt

    def exit_zone(self, direction):
        if direction < 0:
            return pygame.Rect(0, FLOOR_TOP - 30, 12, IH - FLOOR_TOP + 30)
        return pygame.Rect(IW - 12, FLOOR_TOP - 30, 12, IH - FLOOR_TOP + 30)
