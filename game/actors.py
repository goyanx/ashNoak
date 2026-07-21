"""Walkers for the adventure stage: player, companions, foes. Feet-anchored,
y-sorted by the engine, movement is click-to-walk."""
import math
import random
from dataclasses import dataclass

import pygame

from .rooms import FLOOR_BOT, FLOOR_TOP
from .settings import IW


@dataclass
class Item:
    name: str
    desc: str


class Actor:
    speed = 55.0
    max_hp = 6
    step_freq = 2.6   # walk-cycle bounces per second (procedural juice)

    def __init__(self, frames, x, y, scale=1):
        self.frames = frames
        self.scale = scale
        self.x, self.y = float(x), float(y)  # feet position
        self.tx, self.ty = self.x, self.y
        self.facing = 1
        self.hp = self.max_hp
        self.hurt_t = 0.0
        self.anim_t = random.random() * 10
        self.dead = False
        self.attack_t = 0.0

    @property
    def moving(self):
        # must stay consistent with update()'s stop threshold (euclidean 2),
        # or actors freeze mid-walk with pending actions never firing
        dx, dy = self.tx - self.x, self.ty - self.y
        return (dx * dx + dy * dy) ** 0.5 > 2.5

    def set_target(self, x, y):
        self.tx = max(8.0, min(float(x), IW - 8.0))
        self.ty = max(float(FLOOR_TOP), min(float(y), float(FLOOR_BOT)))

    def stop(self):
        self.tx, self.ty = self.x, self.y

    def update(self, dt):
        self.anim_t += dt
        self.hurt_t = max(0.0, self.hurt_t - dt)
        self.attack_t = max(0.0, self.attack_t - dt)
        dx, dy = self.tx - self.x, self.ty - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 2:
            step = min(self.speed * dt, dist)
            self.x += dx / dist * step
            self.y += dy / dist * step
            if abs(dx) > 1:
                self.facing = 1 if dx > 0 else -1

    def hurt(self, dmg):
        if self.hurt_t > 0 or self.dead:
            return False
        self.hp -= dmg
        self.hurt_t = 0.55
        if self.hp <= 0:
            self.dead = True
        return True

    def dist_to(self, other):
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5

    # ------------------------------------------------------------ drawing

    def current_frame(self):
        f = self.frames
        if self.hurt_t > 0.4 and "hurt" in f:
            return f["hurt"]
        if self.attack_t > 0 and "attack" in f:
            return f["attack"]
        if self.moving:
            # swap feet on each half of the bounce so frame and hop stay in step
            phase = int(self.anim_t * self.step_freq * 2) % 2
            key = "walk0" if phase else "walk1"
            if key not in f:  # wolf sheet
                key = "run0" if phase else "run1"
            return f.get(key, f.get("idle0", f.get("idle")))
        for key in ("idle0", "idle"):
            if key in f:
                if key == "idle0" and int(self.anim_t * 2) % 2 and "idle1" in f:
                    return f["idle1"]
                return f[key]
        return next(iter(f.values()))

    def _pose(self):
        """Procedural animation layered on the base frame, feet-anchored:
        returns (offx, offy, sx, sy). Gives idle breathing, a springy walk
        with squash/stretch, an attack lunge and a hurt recoil — all from a
        couple of sines and the existing timers, no extra art. This is what
        sells the 'alive' pixel look (à la Yes Your Grace)."""
        t = self.anim_t
        offx = offy = 0.0
        sx = sy = 1.0
        if self.attack_t > 0:
            p = self.attack_t / 0.25              # 1 -> 0 across the swing
            offx += self.facing * 5.0 * p         # lunge into the blow
            sy += 0.12 * p                        # rear up, then settle
            sx += 0.05 * p
        elif self.hurt_t > 0:
            k = self.hurt_t / 0.55
            offx += math.sin(t * 55.0) * 1.8 * k  # rattled recoil
            sx += 0.05 * k
        elif self.moving:
            step = math.sin(t * self.step_freq * math.tau)
            a = abs(step)
            offy -= a * 2.4                        # hop on the push-off
            sy += (a - 0.5) * 0.07                 # stretch up / squash on plant
            sx -= (a - 0.5) * 0.07
            offx += self.facing * 0.6             # a hair of forward lean
        else:
            breath = math.sin(t * 1.7)            # slow, calm idle breathing
            sy += breath * 0.028
            sx -= breath * 0.020
            offy -= max(0.0, breath) * 0.6
        return offx, offy, sx, sy

    def draw(self, surf):
        img = self.current_frame()
        offx, offy, sx, sy = self._pose()
        w, h = img.get_width(), img.get_height()
        tw = max(1, int(round(w * self.scale * sx)))
        th = max(1, int(round(h * self.scale * sy)))
        if (tw, th) != (w, h):
            img = pygame.transform.scale(img, (tw, th))  # nearest-neighbour: stays crisp
        if self.facing < 0:
            img = pygame.transform.flip(img, True, False)
        r = img.get_rect(midbottom=(int(round(self.x + offx)), int(round(self.y + offy))))
        surf.blit(img, r.topleft)
        return r

    @property
    def rect(self):
        img = self.current_frame()
        w = img.get_width() * self.scale
        h = img.get_height() * self.scale
        return pygame.Rect(int(self.x - w / 2), int(self.y - h), w, h)


class Player(Actor):
    speed = 72.0
    max_hp = 10

    def __init__(self, frames, x, y):
        super().__init__(frames, x, y)
        self.stats = {"vigor": 4, "wit": 3, "presence": 3}
        self.inventory = []
        self.kills = 0

    def has_item(self, name):
        return any(i.name.lower() == name.lower() for i in self.inventory)

    def remove_item(self, name):
        for i in list(self.inventory):
            if i.name.lower() == name.lower():
                self.inventory.remove(i)
                return True
        return False


class Foe(Actor):
    STATS = {
        "raider":  {"hp": 4, "dmg": 1, "speed": 34, "reach": 14, "cool": 1.6},
        "wolf":    {"hp": 3, "dmg": 1, "speed": 62, "reach": 12, "cool": 1.2},
        "cultist": {"hp": 3, "dmg": 1, "speed": 28, "reach": 16, "cool": 2.0},
        "dragon":  {"hp": 30, "dmg": 2, "speed": 26, "reach": 34, "cool": 2.2},
    }

    def __init__(self, frames, kind, x, y):
        st = self.STATS[kind]
        self.max_hp = st["hp"]
        super().__init__(frames, x, y, scale=2 if kind == "dragon" else 1)
        self.kind = kind
        self.dmg = st["dmg"]
        self.speed = st["speed"]
        self.reach = st["reach"]
        self.cool = st["cool"]
        self.swing_t = random.uniform(0.6, 1.4)
        self.step_freq = {"wolf": 3.8, "dragon": 1.4}.get(kind, 2.6)

    def think(self, dt, player):
        """Chase and strike. Returns True on a landed hit attempt."""
        self.swing_t = max(0.0, self.swing_t - dt)
        d = self.dist_to(player)
        if d > self.reach:
            self.set_target(player.x, player.y)
        else:
            self.stop()
            self.facing = 1 if player.x > self.x else -1
            if self.swing_t <= 0:
                self.swing_t = self.cool
                self.attack_t = 0.25
                return True
        return False
