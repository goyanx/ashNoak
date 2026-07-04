"""Load and slice the generated pixel art. Run assets/generate_assets.py first
(main.py does it automatically if the PNGs are missing)."""
import os

import pygame

from .settings import ASSETS

FRAME_LAYOUTS = {
    # name: (frame_w, frame_h, frame names in sheet order)
    "knight":   (16, 24, ["idle0", "idle1", "walk0", "walk1", "attack", "hurt"]),
    "raider":   (16, 24, ["idle0", "idle1", "walk0", "walk1", "attack", "hurt"]),
    "cultist":  (16, 24, ["idle0", "idle1", "walk0", "walk1", "attack", "hurt"]),
    "princess": (16, 24, ["idle0", "idle1", "walk0", "walk1", "hurt"]),
    "dragon":   (48, 32, ["idle", "fly0", "fly1", "breathe"]),
    "wolf":     (24, 16, ["run0", "run1"]),
}
SINGLES = ["heart", "fireball", "bolt", "flag"]
PROPS = ["chest", "corpse", "altar", "barrel", "bookshelf", "brazier",
         "statue", "bones", "door", "well", "bed"]
THEMES = ["forest", "castle", "volcano"]
ROOMS_PER_THEME = 6


def assets_exist():
    return os.path.exists(os.path.join(ASSETS, "sprites", "props", "chest.png")) \
        and os.path.exists(os.path.join(ASSETS, "backgrounds", "rooms", "forest_5.png"))


def load_intimacy_frames():
    """Frames for the intimate scene, as a list, any count.

    Mod hook: if assets/sprites/embrace_custom.png exists it wins over the
    shipped embrace.png. Sheets are laid out as square frames side by side
    (frame width == sheet height), so drop in a strip of any length and the
    scene will cycle it. User-supplied art is played as-is.
    """
    for name in ("embrace_custom.png", "embrace.png"):
        path = os.path.join(ASSETS, "sprites", name)
        if os.path.exists(path):
            sheet = pygame.image.load(path).convert_alpha()
            fh = sheet.get_height()
            fw = fh  # square frames
            count = max(1, sheet.get_width() // fw)
            return [sheet.subsurface(pygame.Rect(i * fw, 0, fw, fh))
                    for i in range(count)]
    raise FileNotFoundError("no embrace spritesheet; run assets/generate_assets.py")


def load_all():
    art = {"sprites": {}, "backgrounds": {}, "tiles": {}}
    for name, (fw, fh, labels) in FRAME_LAYOUTS.items():
        sheet = pygame.image.load(os.path.join(ASSETS, "sprites", name + ".png")).convert_alpha()
        frames = {}
        for i, label in enumerate(labels):
            frames[label] = sheet.subsurface(pygame.Rect(i * fw, 0, fw, fh))
        art["sprites"][name] = frames
    for name in SINGLES:
        art["sprites"][name] = pygame.image.load(
            os.path.join(ASSETS, "sprites", name + ".png")).convert_alpha()
    art["sprites"]["props"] = {
        name: pygame.image.load(
            os.path.join(ASSETS, "sprites", "props", name + ".png")).convert_alpha()
        for name in PROPS
    }
    art["sprites"]["embrace"] = load_intimacy_frames()
    for theme in THEMES:
        art["backgrounds"][theme] = {
            layer: pygame.image.load(
                os.path.join(ASSETS, "backgrounds", f"{theme}_{layer}.png")).convert_alpha()
            for layer in ("sky", "far", "near")
        }
        tiles = pygame.image.load(os.path.join(ASSETS, "tiles", theme + ".png")).convert()
        art["tiles"][theme] = {
            "top": tiles.subsurface(pygame.Rect(0, 0, 16, 16)),
            "fill": tiles.subsurface(pygame.Rect(16, 0, 16, 16)),
        }
    return art
