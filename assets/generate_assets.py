"""Generate all pixel art for Ash & Oath as PNGs.

Everything is authored as character grids + palettes (sprites) or drawn
procedurally with a fixed seed (backgrounds, tiles). No anti-aliasing
anywhere; the game scales with nearest-neighbor so it stays chunky.

Run:  python assets/generate_assets.py
"""
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITES = os.path.join(HERE, "sprites")
BACKGROUNDS = os.path.join(HERE, "backgrounds")
TILES = os.path.join(HERE, "tiles")

# ---------------------------------------------------------------- helpers

def grid_surface(rows, palette, w, h):
    """Build a Surface from strings of palette keys. '.' = transparent.
    Rows are padded/truncated to w, the row list to h, so authoring is
    forgiving."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    rows = list(rows)[:h] + ["." * w] * max(0, h - len(rows))
    for y, row in enumerate(rows):
        row = (row + "." * w)[:w]
        for x, ch in enumerate(row):
            if ch != ".":
                surf.set_at((x, y), palette.get(ch, (255, 0, 255, 255)))
    return surf


def sheet(frames, path):
    """Concatenate equally sized frames horizontally and save."""
    w, h = frames[0].get_size()
    out = pygame.Surface((w * len(frames), h), pygame.SRCALPHA)
    for i, f in enumerate(frames):
        out.blit(f, (i * w, 0))
    pygame.image.save(out, path)
    print("wrote", os.path.relpath(path, HERE), f"({len(frames)} frames {w}x{h})")


def bob(surf, dy=1):
    """Shift a frame down by dy px (cheap breathing/idle second frame)."""
    out = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    out.blit(surf, (0, dy))
    return out


def mirror_rows(rows):
    return [r[::-1] for r in rows]


# ---------------------------------------------------------------- palettes

OUT = (18, 20, 30, 255)         # outline
SKIN = (232, 180, 138, 255)

KNIGHT_PAL = {
    "O": OUT, "F": SKIN,
    "R": (192, 48, 48, 255),     # plume
    "H": (168, 178, 194, 255),   # helmet
    "S": (138, 150, 168, 255),   # armor
    "D": (86, 96, 114, 255),     # dark armor
    "G": (216, 168, 50, 255),    # gold trim
    "B": (60, 52, 60, 255),      # boots
    "W": (222, 228, 238, 255),   # sword steel
}

# Palette-swap enemies (classic 90s trick): same grids, different colors.
RAIDER_PAL = dict(KNIGHT_PAL, **{
    "R": (74, 58, 44, 255),      # hood instead of plume
    "H": (110, 86, 62, 255),     # leather
    "S": (128, 100, 70, 255),
    "D": (78, 60, 44, 255),
    "G": (150, 150, 150, 255),
    "W": (160, 150, 130, 255),   # crude iron
})
CULTIST_PAL = dict(KNIGHT_PAL, **{
    "R": (60, 34, 84, 255),
    "H": (76, 44, 106, 255),
    "S": (94, 56, 128, 255),
    "D": (52, 30, 74, 255),
    "G": (196, 60, 60, 255),     # blood sigils
    "W": (120, 220, 130, 255),   # green magic
    "F": (196, 190, 200, 255),   # pallid skin
})

PRINCESS_PAL = {
    "O": OUT, "F": SKIN,
    "Y": (222, 186, 90, 255),    # hair
    "G": (216, 168, 50, 255),    # tiara
    "P": (172, 62, 128, 255),    # dress
    "Q": (128, 40, 96, 255),     # dress shade
    "B": (60, 52, 60, 255),
}

DRAGON_PAL = {
    "O": OUT,
    "D": (150, 44, 44, 255),     # scales
    "E": (104, 28, 34, 255),     # scale shade
    "L": (222, 170, 80, 255),    # belly
    "W": (94, 24, 30, 255),      # wing membrane
    "T": (230, 228, 210, 255),   # teeth / claws / horns
    "Y": (250, 210, 60, 255),    # eye
    "R": (240, 110, 40, 255),    # fire glow
}

WOLF_PAL = {
    "O": OUT,
    "G": (108, 110, 120, 255),
    "D": (70, 72, 82, 255),
    "T": (230, 228, 210, 255),
    "R": (200, 60, 50, 255),
}

# ---------------------------------------------------------------- knight (16x24)

KNIGHT_TORSO = [
    "................",
    "......RRRR......",
    ".....RRR........",
    "....OHHHHO......",
    "....OHFFHO......",
    "....OHFFHO......",
    "....OHHHHO......",
    ".....OSSO.......",
    "...OSSSSSSO.....",
    "..OSOGSSGOSO....",
    "..OSOSSSSOSO....",
    "..OSOSSSSOSO....",
    "..OOOSSSSOOO....",
    "..OWOSSSSOFO....",
    "..OWOSGGSO......",
    "..OW.OSSO.......",
    "..OW.ODDO.......",
]
KNIGHT_LEGS_IDLE = [
    ".....ODDDDO.....",
    "....ODO..ODO....",
    "....ODO..ODO....",
    "....ODO..ODO....",
    "...OBBO..OBBO...",
    "...OBBO..OBBO...",
    "..OBBBO..OBBBO..",
]
KNIGHT_LEGS_STRIDE = [
    ".....ODDDDO.....",
    ".....ODOODDO....",
    "....ODO..ODO....",
    "...ODO....ODO...",
    "...OBBO...OBBO..",
    "..OBBO....OBBO..",
    "..OBBBO...OBBBO.",
]
# attack: sword raised across the right side
KNIGHT_TORSO_ATK = [
    "..........OWWO..",
    "......RRRROWWO..",
    ".....RRR..OWWO..",
    "....OHHHHOOWWO..",
    "....OHFFHOOWWO..",
    "....OHFFHO.OGO..",
    "....OHHHHO.OFO..",
    ".....OSSOOOSO...",
    "...OSSSSSSSO....",
    "..OSOGSSGOSO....",
    "..OSOSSSSOO.....",
    "..OSOSSSSO......",
    "..OOOSSSSO......",
    "..OF.OSSSO......",
    ".....OSGGSO.....",
    ".....OSSO.......",
    ".....ODDO.......",
]

# ---------------------------------------------------------------- princess (16x24)

PRINCESS_TORSO = [
    "................",
    ".....YYYYY......",
    "....YYYYYYY.....",
    "....YGYYGYY.....",
    "....OFFFFYY.....",
    "....OFFFFOY.....",
    ".....OFFO.Y.....",
    "......OO..Y.....",
    ".....OPPO.......",
    "....OPPPPO......",
    "...OPPPPPPO.....",
    "...OFPPPPFO.....",
    "...OPPQPPPO.....",
    "..OPPPPPPPPO....",
    "..OPPQPPPQPO....",
    ".OPPPPPPPPPPO...",
    ".OPPPQPPPQPPO...",
]
PRINCESS_LEGS_A = [
    ".OPPPPPPPPPPO...",
    "OPPQPPPPPPQPPO..",
    "OPPPPPQPPPPPPO..",
    "OQPPPPPPPPPQPO..",
    ".OOOOOOOOOOOO...",
    "....OFF.OFF.....",
    "....OBB.OBB.....",
]
PRINCESS_LEGS_B = [
    ".OPPPPPPPPPPO...",
    ".OPPQPPPPQPPO...",
    "OPPPPPQPPPPPPO..",
    "OPQPPPPPPPPQPO..",
    ".OOOOOOOOOOOO...",
    ".....OFFOFF.....",
    ".....OBBOBB.....",
]

# ---------------------------------------------------------------- dragon (48x32)

DRAGON_BODY = [
    "................................................",
    "..............................OTO....OTO.......",
    "...............................ODO..ODO........",
    "...............................ODDDDDDO........",
    "..............................ODDDDDDDDO.......",
    "..............................ODYODDDDDO.......",
    "..............................ODDDDDDDDDO......",
    "...............................ODDOTTTTO.......",
    "...............................ODDDOOOO........",
    "..............................ODDLDDO..........",
    ".........................OODDDDDLLDDO..........",
    "....................ODDDDDDDDDDDLLDDDO.........",
    "..................ODDDDDDDDDDDDDLLLDDO.........",
    ".................ODDDEDDDDDDDDDDLLLDDO.........",
    "................ODDDDDDDDDDDDDDDLLLDDO.........",
    "...............ODDEDDDDDDDDDDDDDLLDDO..........",
    "..............ODDDDDDDDDDDDDDDDLLLDDO..........",
    ".............ODDDDEDDDDDDDDDDDDLLDDDO..........",
    "..OO.........ODDDDDDDDDDDDDDDLLLDDDO...........",
    "...ODO........ODDDDDDDDDDDDDLLDDDDO............",
    "....ODDO.......ODDDDDDDDDDDLLDDDDO.............",
    ".....ODDDO......ODDDDDDDDDDDDDDO...............",
    "......ODDDDOO....ODDDDDDDDDDDO.................",
    ".......ODDDDDDOOODDDDDDDDDDDO..................",
    "........OODDDDDDDDDDDDDDDDDO...................",
    "..........OODDDDDDODDDDDODDO...................",
    "..............OOOODDO..ODDO....................",
    "..................ODO....ODO...................",
    ".................OTTO....OTTO..................",
    "................................................",
    "................................................",
    "................................................",
]
DRAGON_WING = [
    "..........OO....................",
    ".......OODWWOO..................",
    ".....ODWWWWWWWOO................",
    "...ODWWWWWWWWWWWOO..............",
    "..ODWWWWWWWWWWWWWWOO............",
    ".ODWWWWWWWWWWWWWWWWWOO..........",
    "ODWWWWWWWWWWWWWWWWWWWWO.........",
    ".OWWWWWWWWWWWWWWWWWWWO..........",
    "..OOWWWWWOWWWWWOWWWOO...........",
    "....OOOOO.OOOOO.OOO.............",
]

# breathe: open jaw + fire tongue start (fire projectile drawn in-game)
DRAGON_HEAD_FIRE = [
    "..............................OTO....OTO.......",
    "...............................ODO..ODO........",
    "...............................ODDDDDDO........",
    "..............................ODDDDDDDDO.......",
    "..............................ODYODDDDDO.......",
    "..............................ODDDDDDDDDORRR...",
    "...............................ODDOTTTTORRRR...",
    "..............................ODDDDOOOTORRR....",
    "..............................ODDDOTTTTO.......",
    "...............................ODDDOOOO........",
]

# ---------------------------------------------------------------- wolf (24x16)

WOLF_A = [
    "........................",
    "..OO....................",
    ".ODDO..............OO...",
    ".ODDDOOOOOOOOOOOOODDO...",
    "ODGDGGGGGGGGGGGGGDDDDO..",
    "ORDGGGGGGGGGGGGGGGDDO...",
    "OTTDGGGGGGGGGGGGGGDO....",
    ".ODGGGGGGGGGGGGGGGO.....",
    "..OGGDGGGGGGGDGGGO......",
    "..ODGGGGGGGGGGGDO.......",
    "..ODO.OGO..OGO.ODO......",
    "..ODO..OGO..OGO.ODO.....",
    ".ODO....ODO..ODO.ODO....",
    ".OTO....OTO...OTO.OTO...",
    "........................",
    "........................",
]
WOLF_B = [
    "........................",
    "..OO....................",
    ".ODDO..............OO...",
    ".ODDDOOOOOOOOOOOOODDO...",
    "ODGDGGGGGGGGGGGGGDDDDO..",
    "ORDGGGGGGGGGGGGGGGDDO...",
    "OTTDGGGGGGGGGGGGGGDO....",
    ".ODGGGGGGGGGGGGGGGO.....",
    "..OGGDGGGGGGGDGGGO......",
    "..ODGGGGGGGGGGGDO.......",
    "...OGO..OGO.OGO.OGO.....",
    "..OGO..OGO...OGO.OGO....",
    ".ODO..ODO.....ODO.ODO...",
    ".OTO..OTO......OTO.OTO..",
    "........................",
    "........................",
]

# ---------------------------------------------------------------- small props

MISC_PAL = {
    "O": OUT,
    "R": (214, 60, 60, 255), "r": (150, 30, 40, 255),
    "F": (250, 170, 40, 255), "f": (250, 230, 90, 255),
    "G": (120, 220, 130, 255), "g": (60, 140, 80, 255),
    "W": (240, 240, 250, 255),
    "B": (110, 80, 50, 255),
    "P": (172, 62, 128, 255),
}
HEART = [
    ".OO.OO..",
    "ORRORRO.",
    "ORRRRRO.",
    ".ORRRO..",
    "..ORO...",
    "...O....",
]
FIREBALL = [
    "..ff....",
    ".fFFf...",
    "fFFFFf..",
    "fFFrFf..",
    ".fFFf...",
    "..ff....",
]
BOLT = [
    ".gG.",
    "gGGg",
    ".Gg.",
]
FLAG = [
    "OB..........",
    "OBPPPPPPP...",
    "OBPPWWPPP...",
    "OBPPPPPPP...",
    "OB..........",
    "OB..........",
    "OB..........",
    "OB..........",
    "OB..........",
    "OB..........",
    "OB..........",
    "OB..........",
]

# ---------------------------------------------------------------- builders

def build_humanoid(torso, legs_a, legs_b, atk_torso, pal, path, with_attack):
    def compose(t, l):
        return grid_surface(list(t) + list(l), pal, 16, 24)

    idle0 = compose(torso, legs_a)
    idle1 = bob(idle0)
    walk0 = compose(torso, legs_b)
    walk1 = compose(torso, mirror_rows(legs_b))
    frames = [idle0, idle1, walk0, walk1]
    if with_attack:
        frames.append(compose(atk_torso, legs_a))
    # hurt frame: white-out silhouette
    hurt = idle0.copy()
    px = pygame.PixelArray(hurt)
    del px
    white = pygame.Surface(idle0.get_size(), pygame.SRCALPHA)
    white.blit(idle0, (0, 0))
    white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)
    frames.append(white)
    sheet(frames, path)


def build_dragon(path):
    body = grid_surface(DRAGON_BODY, DRAGON_PAL, 48, 32)
    wing = grid_surface(DRAGON_WING, DRAGON_PAL, 32, 10)

    def with_wing(dy):
        f = body.copy()
        f.blit(wing, (8, 6 + dy))
        return f

    idle = with_wing(2)
    fly0 = with_wing(-2)
    fly1 = with_wing(5)
    breathe = with_wing(2)
    head = grid_surface(DRAGON_HEAD_FIRE, DRAGON_PAL, 48, 10)
    breathe.fill((0, 0, 0, 0), pygame.Rect(28, 1, 20, 9))
    breathe.blit(head, (0, 0))
    sheet([idle, fly0, fly1, breathe], path)


def build_wolf(path):
    a = grid_surface(WOLF_A, WOLF_PAL, 24, 16)
    b = grid_surface(WOLF_B, WOLF_PAL, 24, 16)
    sheet([a, b], path)


# ---------------------------------------------------------------- backgrounds

THEMES = {
    "forest": {
        "sky": [(24, 30, 66), (46, 58, 100), (86, 100, 140), (150, 140, 150)],
        "far": (38, 62, 74), "near": (24, 42, 46),
        "ground_top": (74, 128, 58), "ground": (86, 62, 44), "ground_dark": (62, 44, 32),
        "orb": ((240, 230, 190), 60, 30),  # sun
    },
    "castle": {
        "sky": [(16, 14, 36), (34, 26, 60), (66, 44, 88), (110, 70, 100)],
        "far": (40, 32, 58), "near": (26, 20, 40),
        "ground_top": (110, 108, 120), "ground": (78, 76, 90), "ground_dark": (56, 54, 66),
        "orb": ((220, 220, 235), 250, 28),  # moon
    },
    "volcano": {
        "sky": [(20, 8, 10), (48, 14, 12), (92, 26, 14), (150, 52, 20)],
        "far": (54, 22, 20), "near": (34, 14, 14),
        "ground_top": (96, 42, 30), "ground": (56, 30, 28), "ground_dark": (40, 20, 20),
        "orb": ((250, 120, 40), 160, 24),  # ember sun
    },
}
W, H = 320, 180


def make_sky(theme, spec, rng):
    s = pygame.Surface((W, H))
    bands = spec["sky"]
    band_h = H // len(bands)
    for i, c in enumerate(bands):
        s.fill(c, pygame.Rect(0, i * band_h, W, band_h + (H % band_h if i == len(bands) - 1 else 0)))
        # dithered band edge, very 90s
        if i:
            for x in range(0, W, 2):
                s.set_at(((x + i) % W, i * band_h - 1 + (x // 2) % 2), c)
    if theme != "forest":  # stars
        for _ in range(70):
            x, y = rng.randrange(W), rng.randrange(H * 2 // 3)
            s.set_at((x, y), (200 + rng.randrange(55),) * 3)
    color, ox, oy = spec["orb"]
    pygame.draw.circle(s, color, (ox, oy), 11)
    pygame.draw.circle(s, bands[0], (ox + (4 if theme == "castle" else 0), oy - (3 if theme == "castle" else 0)),
                       7 if theme == "castle" else 0)
    return s


def silhouette_layer(theme, color, rng, base, jag, step, holes=False):
    """A transparent 320x180 strip of jagged silhouettes (mountains/keeps/spires)."""
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    y = base
    x = 0
    while x < W:
        y = max(60, min(H - 20, y + rng.randrange(-jag, jag + 1)))
        w = rng.randrange(step, step * 2)
        pygame.draw.rect(s, color, (x, y, w, H - y))
        if theme == "castle" and rng.random() < 0.5:
            # crenellated tower
            tw = rng.randrange(8, 16)
            th = rng.randrange(18, 44)
            tx = x + rng.randrange(max(1, w - tw))
            pygame.draw.rect(s, color, (tx, y - th, tw, th))
            for bx in range(tx, tx + tw, 4):
                pygame.draw.rect(s, color, (bx, y - th - 3, 2, 3))
            if holes and rng.random() < 0.7:
                gl = (250, 200, 90) if theme != "volcano" else (250, 120, 40)
                s.fill(gl, (tx + tw // 2 - 1, y - th + 4, 2, 3))
        if theme == "volcano" and rng.random() < 0.35:
            # glowing fissure
            fx = x + rng.randrange(max(1, w))
            for fy in range(y, min(H, y + rng.randrange(10, 30))):
                s.set_at((fx + rng.randrange(-1, 2), fy), (240, 90 + rng.randrange(60), 30))
        x += w
    return s


def tree_layer(color, rng):
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    for _ in range(16):
        x = rng.randrange(W)
        h = rng.randrange(40, 90)
        top = H - h
        pygame.draw.rect(s, color, (x - 2, top + h // 3, 4, h))
        for i in range(4):
            r = 14 - i * 3 + rng.randrange(3)
            pygame.draw.circle(s, color, (x + rng.randrange(-4, 5), top + i * (h // 6)), r)
    return s


def make_far(theme, spec, rng):
    if theme == "forest":
        return silhouette_layer(theme, spec["far"], rng, base=95, jag=14, step=18)
    if theme == "castle":
        return silhouette_layer(theme, spec["far"], rng, base=100, jag=10, step=22, holes=True)
    lay = silhouette_layer(theme, spec["far"], rng, base=100, jag=18, step=16)
    # volcano cone with crater glow
    pygame.draw.polygon(lay, spec["far"], [(190, 180), (245, 62), (300, 180)])
    pygame.draw.rect(lay, (250, 140, 40), (240, 60, 12, 3))
    return lay


def make_near(theme, spec, rng):
    if theme == "forest":
        return tree_layer(spec["near"], rng)
    if theme == "castle":
        return silhouette_layer(theme, spec["near"], rng, base=120, jag=8, step=26, holes=True)
    return silhouette_layer(theme, spec["near"], rng, base=125, jag=24, step=12)


def make_tiles(spec, rng):
    """Two 16x16 tiles side by side: surface tile, fill tile."""
    t = pygame.Surface((32, 16))
    t.fill(spec["ground"])
    # fill tile speckle
    for _ in range(26):
        t.set_at((16 + rng.randrange(16), rng.randrange(16)), spec["ground_dark"])
    # surface tile: top fringe
    t.fill(spec["ground"], (0, 0, 16, 16))
    for _ in range(20):
        t.set_at((rng.randrange(16), rng.randrange(5, 16)), spec["ground_dark"])
    t.fill(spec["ground_top"], (0, 0, 16, 4))
    for x in range(16):
        if rng.random() < 0.5:
            t.set_at((x, 4), spec["ground_top"])
        if rng.random() < 0.35:
            t.set_at((x, 0), tuple(min(255, c + 30) for c in spec["ground_top"]))
    return t


# ---------------------------------------------------------------- intimacy (24x24, 2 frames)
# Kael out of his armor (undershirt) and Maren, close. The scene treatment
# (warm veil, embers, narration) happens at runtime; these stay chaste pixels.

EMBRACE_PAL = {
    "O": OUT, "F": SKIN,
    "K": (92, 64, 40, 255),      # Kael's hair
    "W": (222, 216, 200, 255),   # undershirt
    "D": (60, 52, 60, 255),      # trousers
    "Y": (222, 186, 90, 255),    # Maren's hair
    "P": (172, 62, 128, 255),    # dress
    "Q": (128, 40, 96, 255),     # dress shade
}

EMBRACE_0 = [
    "........................",
    ".....KKK....YYYY........",
    "....KKKKK..YYYYYY.......",
    "....OFFFO.OYFFFYY.......",
    "....OFFFFOFFFFOYY.......",
    ".....OFFOOOFFO.Y........",
    "......OO...OO...........",
    ".....OWWWOPPPO..........",
    "....OWWWWPPPPPO.........",
    "...OWWWWWPPPPPPO........",
    "...OWFWWWPPPPFPO........",
    "...OWWWWWPPPPPPO........",
    "...OFWWWWPPPPPFO........",
    "....OWWWPPPPPPO.........",
    "....OWWWPPQPPPO.........",
    "....OWWOPPPPPPO.........",
    "....OWWOPPQPPPPO........",
    "....ODDOPPPPPPPO........",
    "....ODDOPPPPPPPPO.......",
    "....ODDOPPPPPPPPO.......",
    "....ODDO.OOOOOOO........",
    "....ODDO..OFF.OFF.......",
    "...ODDDDO.................",
    "........................",
]
EMBRACE_1 = [
    "........................",
    "........................",
    ".....KKK...YYYY.........",
    "....KKKKK.YYYYYY........",
    "....OFFFOOYFFFYY........",
    "....OFFFFFFFFOYY........",
    ".....OFFOOOFFO.Y........",
    "......OO..OO............",
    ".....OWWWOPPPO..........",
    "....OWWWWPPPPPO.........",
    "...OWWWWWPPPPPPO........",
    "...OWFWWWPPPPFPO........",
    "...OWWWWWPPPPPPO........",
    "...OFWWWWPPPPPFO........",
    "....OWWWPPPPPPO.........",
    "....OWWWPPQPPPO.........",
    "....OWWOPPPPPPO.........",
    "....OWWOPPQPPPPO........",
    "....ODDOPPPPPPPO........",
    "....ODDOPPPPPPPPO.......",
    "....ODDO.OOOOOOO........",
    "....ODDO..OFF.OFF.......",
    "...ODDDDO.................",
    "........................",
]


def build_embrace():
    frames = [grid_surface(EMBRACE_0, EMBRACE_PAL, 24, 24),
              grid_surface(EMBRACE_1, EMBRACE_PAL, 24, 24)]
    sheet(frames, os.path.join(SPRITES, "embrace.png"))


# ---------------------------------------------------------------- props (point-and-click hotspots)

PROP_PAL = {
    "O": OUT,
    "B": (110, 82, 52, 255), "b": (76, 56, 36, 255),      # wood
    "S": (128, 126, 140, 255), "s": (88, 86, 100, 255),   # stone
    "G": (216, 168, 50, 255),                              # gold
    "T": (226, 222, 204, 255), "t": (170, 166, 150, 255), # bone
    "R": (140, 30, 34, 255), "r": (90, 18, 24, 255),      # gore
    "F": (250, 170, 40, 255), "f": (250, 230, 90, 255),   # flame
    "K": (40, 36, 48, 255),                                # dark
    "P": (94, 56, 128, 255),                               # cloth
}

PROPS = {
    "chest": (16, 12, [
        "..OOOOOOOOOO....",
        ".OBBBBBBBBBBO...",
        "OBbBBBBBBBBbBO..",
        "OBBBBGGBBBBBBO..",
        "OOOOOOOOOOOOOO..",
        "OBbBBBGGBBBbBO..",
        "OBBBBBGGBBBBBO..",
        "OBbBBBBBBBBbBO..",
        "OOOOOOOOOOOOOO..",
    ]),
    "corpse": (24, 10, [
        "........................",
        "......OOO......OO.......",
        ".....OKKKOOOOOOKKOO.....",
        "..OOOKKKKKKKKKKKKKKO....",
        ".OKKKKKKKKKKKKKKKKKKO...",
        ".ORKKKKKKKRRKKKKKKKOO...",
        "..ORRrRRRRRrrRRROOO.....",
        "...ORrRRrRRRrRRRO.......",
        "....OOOOOOOOOOOO........",
    ]),
    "altar": (20, 16, [
        "....OOOOOOOOOOOO....",
        "...OSSSSSSSSSSSSO...",
        "...OSsRRsSSsRRsSO...",
        "....OSSSSSSSSSSO....",
        ".....OSsSSSSsSO.....",
        ".....OSSSSSSSSO.....",
        ".....OSsSSSSsSO.....",
        "....OSSSSSSSSSSO....",
        "...OSSsSSSSSSsSSO...",
        "..OOOOOOOOOOOOOOOO..",
    ]),
    "barrel": (12, 14, [
        "..OOOOOOOO..",
        ".OBbBBBBbBO.",
        "OBBBBBBBBBBO",
        "ObOOOOOOOObO",
        "OBBBBBBBBBBO",
        "OBbBBBBBBbBO",
        "ObOOOOOOOObO",
        "OBBBBBBBBBBO",
        ".OBbBBBBbBO.",
        "..OOOOOOOO..",
    ]),
    "bookshelf": (16, 24, [
        "OOOOOOOOOOOOOOO.",
        "OBBBBBBBBBBBBBO.",
        "OBPKGPKPGKPPKBO.",
        "OBPKGPKPGKPPKBO.",
        "OBOOOOOOOOOOOBO.",
        "OBKPGKPPKGPKPBO.",
        "OBKPGKPPKGPKPBO.",
        "OBOOOOOOOOOOOBO.",
        "OBGPKPGKPKPGKBO.",
        "OBGPKPGKPKPGKBO.",
        "OBOOOOOOOOOOOBO.",
        "OBBBBBBBBBBBBBO.",
        "OOOOOOOOOOOOOOO.",
    ]),
    "brazier": (12, 16, [
        "....Off.....",
        "...OFFfO....",
        "...OFFFO....",
        "..OFFFFFO...",
        "..OSSSSSO...",
        "...OSsSO....",
        "....OSO.....",
        "....OSO.....",
        "...OSsSO....",
        "..OSSSSSO...",
    ]),
    "statue": (14, 22, [
        "....OOOO......",
        "...OSSSSO.....",
        "...OSsSSO.....",
        "....OSSO......",
        "..OOSSSSOO....",
        ".OSSSSSSSSO...",
        ".OSsSSSSsSO...",
        ".OSSSSSSSSO...",
        "..OSsSSsSO....",
        "..OSSSSSSO....",
        "..OSsSSsSO....",
        ".OOSSSSSSOO...",
        "OSSSSSSSSSSO..",
        "OOOOOOOOOOOO..",
    ]),
    "bones": (16, 8, [
        "................",
        "..OTO...OttO....",
        ".OTTTO.OtTTtO...",
        "..OTOOOOOTTO....",
        "...OTTTTTO......",
        "..OtTOOOTtO.....",
        "................",
    ]),
    "door": (16, 24, [
        ".OOOOOOOOOOOO...",
        "OBbBBBBBBBBbBO..",
        "OBBBbBBBBbBBBO..",
        "OBObBBBBBBbOBO..",
        "OBBBBBBBBBBBBO..",
        "OBbBBBBBBBBbBO..",
        "OBBBBBOOBBBBBO..",
        "OBBBBBOGBBBBBO..",
        "OBbBBBBBBBBbBO..",
        "OBBBbBBBBbBBBO..",
        "OBBBBBBBBBBBBO..",
        "OBbBBBBBBBBbBO..",
    ]),
    "well": (20, 16, [
        "....OOOOOOOOO.......",
        "...OBbBBBBBbBO......",
        "....OOOOOOOOO.......",
        "....OB.....BO.......",
        "....OB.....BO.......",
        "..OOSSSSSSSSSOO.....",
        ".OSsSSSSSSSSSsSO....",
        ".OSSSKKKKKKSSSO.....",
        ".OSsSKKKKKKSsSO.....",
        ".OOOOOOOOOOOOOO.....",
    ]),
    "bed": (26, 14, [
        "OBO.....................",
        "OBOOOOOOOOOOOOOOOOOOOOO.",
        "OBPPPPPPPPPPPPPPPPPPPBO.",
        "OBPPWWWPPPPPPPPPPPPPPBO.",
        "OBPWWWWWPPPPPPPPPPPPPBO.",
        "OBPPWWWPPPPPPPPPPPPPPBO.",
        "OBOOOOOOOOOOOOOOOOOOOBO.",
        "OBBBBBBBBBBBBBBBBBBBBBO.",
        ".OB.................BO..",
        ".OB.................BO..",
    ]),
}

# scale door/bookshelf/statue rows to full height by repeating middle rows at build time


def build_props():
    propdir = os.path.join(SPRITES, "props")
    os.makedirs(propdir, exist_ok=True)
    for name, (w, h, rows) in PROPS.items():
        # stretch authored rows to target height by repeating the middle
        rows = list(rows)
        while len(rows) < h:
            rows.insert(len(rows) // 2, rows[len(rows) // 2])
        pygame.image.save(grid_surface(rows, PROP_PAL, w, h),
                          os.path.join(propdir, name + ".png"))
    print("wrote", len(PROPS), "props")


# ---------------------------------------------------------------- rooms (full scenes)

FLOOR_Y = 118  # top of walkable floor band in every room

INTERIORS = {
    "forest":  {"wall": (44, 40, 36), "wall_d": (32, 29, 26), "floor": (78, 60, 44),
                "floor_d": (58, 44, 32), "accent": (250, 170, 40)},
    "castle":  {"wall": (58, 54, 70), "wall_d": (42, 39, 52), "floor": (92, 90, 104),
                "floor_d": (68, 66, 78), "accent": (250, 200, 90)},
    "volcano": {"wall": (52, 30, 28), "wall_d": (38, 20, 20), "floor": (66, 38, 32),
                "floor_d": (46, 26, 22), "accent": (250, 120, 40)},
}


def draw_floor(s, spec, rng):
    """Flagstone floor band with mild perspective (rows get taller downward)."""
    y = FLOOR_Y
    row_h = 8
    while y < H:
        s.fill(spec["floor"], (0, y, W, row_h))
        s.fill(spec["floor_d"], (0, y, W, 1))
        off = rng.randrange(30)
        for x in range(-off, W, 26 + row_h):
            s.fill(spec["floor_d"], (x + row_h, y, 1, row_h))
        y += row_h
        row_h += 3


def draw_torch(s, x, y, accent):
    s.fill((60, 56, 66), (x - 1, y, 3, 8))
    s.fill(accent, (x - 1, y - 4, 3, 4))
    s.fill((255, 240, 180), (x, y - 3, 1, 2))
    glow = pygame.Surface((40, 30), pygame.SRCALPHA)
    pygame.draw.ellipse(glow, (*accent[:3], 26), glow.get_rect())
    s.blit(glow, (x - 20, y - 18))


def room_exterior(theme, spec, rng):
    s = pygame.Surface((W, H))
    s.blit(pygame.image.load(os.path.join(BACKGROUNDS, f"{theme}_sky.png")), (0, 0))
    s.blit(pygame.image.load(os.path.join(BACKGROUNDS, f"{theme}_far.png")), (0, 0))
    s.blit(pygame.image.load(os.path.join(BACKGROUNDS, f"{theme}_near.png")), (0, 0))
    g = THEMES[theme]
    s.fill(g["ground_top"], (0, FLOOR_Y, W, 4))
    s.fill(g["ground"], (0, FLOOR_Y + 4, W, H - FLOOR_Y - 4))
    for _ in range(240):
        x, y = rng.randrange(W), rng.randrange(FLOOR_Y + 3, H)
        s.set_at((x, y), g["ground_dark"])
    # a worn path
    for y in range(FLOOR_Y, H, 2):
        cx = W // 2 + rng.randrange(-6, 7)
        wpath = 14 + (y - FLOOR_Y)
        s.fill(g["ground_dark"], (cx - wpath // 2, y, wpath, 1))
    return s


def room_interior(theme, spec, rng, style):
    s = pygame.Surface((W, H))
    ispec = INTERIORS[theme]
    dark = style == "crypt"
    wall = tuple(max(0, c - (14 if dark else 0)) for c in ispec["wall"])
    wall_d = tuple(max(0, c - (14 if dark else 0)) for c in ispec["wall_d"])
    s.fill(wall)
    # brick courses
    for y in range(0, FLOOR_Y, 10):
        s.fill(wall_d, (0, y, W, 1))
        off = (y // 10 % 2) * 14
        for x in range(off, W, 28):
            s.fill(wall_d, (x, y, 1, 10))
    draw_floor(s, ispec, rng)
    # pillars
    for px in (40, 160, 280):
        s.fill(wall_d, (px - 6, 0, 12, FLOOR_Y + 4))
        s.fill(wall, (px - 4, 0, 8, FLOOR_Y + 2))
        s.fill(wall_d, (px - 8, FLOOR_Y - 2, 16, 4))
    if style == "hall":
        for wx in (95, 215):  # arched windows with the theme sky visible
            sky = pygame.image.load(os.path.join(BACKGROUNDS, f"{theme}_sky.png"))
            s.blit(sky, (wx, 18), pygame.Rect(wx, 0, 26, 52))
            pygame.draw.rect(s, wall_d, (wx - 1, 17, 28, 54), 2)
            s.fill(wall_d, (wx + 12, 18, 2, 52))
    if style == "crypt":
        for nx in (70, 190, 250):  # dark niches
            pygame.draw.rect(s, (14, 12, 18), (nx, 40, 22, 46))
            pygame.draw.rect(s, wall_d, (nx - 1, 39, 24, 48), 1)
    if style == "lair":
        glow = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*ispec["accent"][:3], 36), (60, 70, 200, 90))
        s.blit(glow, (0, 0))
        for _ in range(120):  # hoard glitter
            x, y = rng.randrange(90, 230), rng.randrange(FLOOR_Y, H - 10)
            s.set_at((x, y), (216, 168, 50))
    for tx in (20, 120, 240, 300):
        if rng.random() < 0.8:
            draw_torch(s, tx, 34, ispec["accent"])
    return s


ROOM_ARCHETYPES = ["exterior", "hall", "crypt", "hall", "exterior", "lair"]


def build_rooms():
    roomdir = os.path.join(BACKGROUNDS, "rooms")
    os.makedirs(roomdir, exist_ok=True)
    for theme, spec in THEMES.items():
        for i, style in enumerate(ROOM_ARCHETYPES):
            rng = random.Random((hash(theme) ^ (i * 7919)) & 0xFFFF)
            if style == "exterior":
                img = room_exterior(theme, spec, rng)
            else:
                img = room_interior(theme, spec, rng, style)
            pygame.image.save(img, os.path.join(roomdir, f"{theme}_{i}.png"))
        print("wrote 6 rooms for", theme)


# ---------------------------------------------------------------- main

def main():
    pygame.init()
    for d in (SPRITES, BACKGROUNDS, TILES):
        os.makedirs(d, exist_ok=True)

    build_humanoid(KNIGHT_TORSO, KNIGHT_LEGS_IDLE, KNIGHT_LEGS_STRIDE, KNIGHT_TORSO_ATK,
                   KNIGHT_PAL, os.path.join(SPRITES, "knight.png"), with_attack=True)
    build_humanoid(KNIGHT_TORSO, KNIGHT_LEGS_IDLE, KNIGHT_LEGS_STRIDE, KNIGHT_TORSO_ATK,
                   RAIDER_PAL, os.path.join(SPRITES, "raider.png"), with_attack=True)
    build_humanoid(KNIGHT_TORSO, KNIGHT_LEGS_IDLE, KNIGHT_LEGS_STRIDE, KNIGHT_TORSO_ATK,
                   CULTIST_PAL, os.path.join(SPRITES, "cultist.png"), with_attack=True)
    build_humanoid(PRINCESS_TORSO, PRINCESS_LEGS_A, PRINCESS_LEGS_B, PRINCESS_TORSO,
                   PRINCESS_PAL, os.path.join(SPRITES, "princess.png"), with_attack=False)
    build_dragon(os.path.join(SPRITES, "dragon.png"))
    build_wolf(os.path.join(SPRITES, "wolf.png"))
    build_embrace()

    for name, rows, w, h in (("heart", HEART, 8, 6), ("fireball", FIREBALL, 8, 6),
                             ("bolt", BOLT, 4, 3), ("flag", FLAG, 12, 12)):
        pygame.image.save(grid_surface(rows, MISC_PAL, w, h), os.path.join(SPRITES, name + ".png"))
        print("wrote sprites/" + name + ".png")

    for theme, spec in THEMES.items():
        rng = random.Random(hash(theme) & 0xFFFF)
        pygame.image.save(make_sky(theme, spec, rng), os.path.join(BACKGROUNDS, f"{theme}_sky.png"))
        pygame.image.save(make_far(theme, spec, rng), os.path.join(BACKGROUNDS, f"{theme}_far.png"))
        pygame.image.save(make_near(theme, spec, rng), os.path.join(BACKGROUNDS, f"{theme}_near.png"))
        pygame.image.save(make_tiles(spec, rng), os.path.join(TILES, f"{theme}.png"))
        print("wrote backgrounds/tiles for", theme)

    build_props()
    build_rooms()
    print("done.")


if __name__ == "__main__":
    main()
