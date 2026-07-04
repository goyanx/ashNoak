"""Adventure UI, all at the internal 320x180 resolution, no anti-aliasing.

Layout: dialogue box along the TOP (so it never covers the actors),
Darkside-Detective-style bottom bar with inventory/stats/objective, and a
centered choice panel when the Director offers dialogue options."""
import queue

import pygame

from .settings import IH, IW

SPEAKER_COLORS = {
    "knight":   (168, 178, 194),
    "princess": (222, 140, 190),
    "dragon":   (240, 110, 60),
    "narrator": (200, 196, 170),
}
SPEAKER_NAMES = {"knight": "SER KAEL", "princess": "MAREN", "dragon": "VEXURAGH",
                 "narrator": ""}
BAR_H = 26


class Fonts:
    def __init__(self):
        self.small = pygame.font.SysFont("Consolas", 9)
        self.big = pygame.font.SysFont("Consolas", 14, bold=True)

    def text(self, s, color, big=False):
        return (self.big if big else self.small).render(s, False, color)


def wrap(font, text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.size(trial)[0] <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class DialogueBox:
    """Top-of-screen dialogue. Typewriter reveal, TTS on line start.

    Long text is never cut: push() paginates it into pages of MAX_LINES
    wrapped lines, and the pages play out one after another (a » marker
    shows when a line continues on the next page)."""
    CPS = 42.0
    HOLD = 2.4
    MAX_LINES = 3

    def __init__(self, fonts, speaker_tts):
        self.fonts = fonts
        self.tts = speaker_tts
        self.queue = []
        self.current = None   # (speaker, page_text, continues_next_page)
        self.shown = 0.0
        self.hold_t = 0.0

    def push(self, speaker, text):
        lines = wrap(self.fonts.small, text, IW - 26)
        for i in range(0, len(lines), self.MAX_LINES):
            page = " ".join(lines[i:i + self.MAX_LINES])
            self.queue.append((speaker, page, i + self.MAX_LINES < len(lines)))

    def skip(self):
        if not self.current:
            return
        text = self.current[1]
        if self.shown < len(text):
            self.shown = len(text)
        else:
            self.current = None

    def update(self, dt):
        if self.current is None and self.queue:
            self.current = self.queue.pop(0)
            self.shown = 0.0
            self.hold_t = 0.0
            self.tts.say(self.current[0], self.current[1])
        if self.current:
            text = self.current[1]
            if self.shown < len(text):
                self.shown = min(len(text), self.shown + self.CPS * dt)
            else:
                self.hold_t += dt
                lines_bonus = 0.5 * (len(text) // 60)
                if self.hold_t > self.HOLD + lines_bonus and self.queue:
                    self.current = None
                elif self.hold_t > (self.HOLD + lines_bonus) * 2:
                    self.current = None

    @property
    def active(self):
        return self.current is not None

    def draw(self, surf):
        if not self.current:
            return
        speaker, text, more = self.current
        lines = wrap(self.fonts.small, text[:int(self.shown)], IW - 26)[:self.MAX_LINES]
        name = SPEAKER_NAMES.get(speaker, speaker.upper()[:14])
        h = 8 + (11 if name else 0) + max(1, len(wrap(
            self.fonts.small, text, IW - 26)[:self.MAX_LINES])) * 10
        box = pygame.Surface((IW - 8, h), pygame.SRCALPHA)
        box.fill((10, 12, 22, 215))
        pygame.draw.rect(box, (90, 100, 130), box.get_rect(), 1)
        col = SPEAKER_COLORS.get(speaker, (214, 190, 130))
        y = 4
        if name:
            box.blit(self.fonts.text(name, col), (6, y))
            y += 11
        for line in lines:
            box.blit(self.fonts.text(line, (230, 230, 220)), (6, y))
            y += 10
        if more and self.shown >= len(text):
            box.blit(self.fonts.text("»", (216, 168, 50)), (box.get_width() - 10, h - 11))
        surf.blit(box, (4, 4))


class ChoicePanel:
    """Director-offered dialogue options. Blocks play input while open."""

    def __init__(self, fonts):
        self.fonts = fonts
        self.prompt = ""
        self.options = []
        self.open = False
        self.hover = -1

    def set(self, prompt, options):
        self.prompt = prompt[:120]
        self.options = [str(o)[:70] for o in options[:4]]
        self.open = bool(self.options)
        self.hover = -1

    def rects(self):
        y0 = 58
        out = []
        for i, _ in enumerate(self.options):
            out.append(pygame.Rect(24, y0 + i * 16, IW - 48, 14))
        return out

    def mouse(self, pos, click):
        """Returns chosen option text or None."""
        if not self.open:
            return None
        self.hover = -1
        for i, r in enumerate(self.rects()):
            if r.collidepoint(pos):
                self.hover = i
                if click:
                    self.open = False
                    return self.options[i]
        return None

    def draw(self, surf):
        if not self.open:
            return
        panel = pygame.Rect(18, 40, IW - 36, 20 + len(self.options) * 16)
        pygame.draw.rect(surf, (12, 14, 26), panel)
        pygame.draw.rect(surf, (216, 168, 50), panel, 1)
        for i, line in enumerate(wrap(self.fonts.small, self.prompt, panel.w - 12)[:1]):
            surf.blit(self.fonts.text(line, (216, 168, 50)), (panel.x + 6, panel.y + 4))
        for i, r in enumerate(self.rects()):
            sel = i == self.hover
            if sel:
                pygame.draw.rect(surf, (34, 32, 58), r)
            surf.blit(self.fonts.text(("> " if sel else "  ") + self.options[i],
                                      (235, 230, 215) if sel else (170, 175, 195)),
                      (r.x + 2, r.y + 3))


class Console:
    """Quake-style drop-down console for talking to the Director out of
    character. Toggled with ` / ~; owns the keyboard while open."""
    H = 106

    def __init__(self, fonts):
        self.fonts = fonts
        self.open = False
        self.input = ""
        self.lines = []   # pre-wrapped (color, text) display lines
        self.scroll = 0   # how many lines we are scrolled up from the bottom
        self._inbox = queue.Queue()  # posts from worker threads

    def post(self, text, color=(200, 205, 215)):
        """Thread-safe log: queue the text; the game loop pumps it in."""
        self._inbox.put((text, color))

    def pump(self):
        """Main thread, once per frame: move posted lines into the log."""
        while True:
            try:
                text, color = self._inbox.get_nowait()
            except queue.Empty:
                return
            self.log(text, color)

    def log(self, text, color=(200, 205, 215)):
        for chunk in str(text).split("\n"):
            for line in wrap(self.fonts.small, chunk, IW - 16) or [""]:
                self.lines.append((color, line))
        self.lines = self.lines[-400:]
        self.scroll = 0

    def toggle(self):
        self.open = not self.open
        self.input = ""

    def rows(self):
        return (self.H - 16) // 9

    def key(self, ev):
        """Handle a KEYDOWN while open. Returns submitted text or None."""
        if ev.key == pygame.K_ESCAPE:
            self.open = False
        elif ev.key == pygame.K_RETURN:
            text, self.input = self.input.strip(), ""
            return text or None
        elif ev.key == pygame.K_BACKSPACE:
            self.input = self.input[:-1]
        elif ev.key == pygame.K_PAGEUP:
            self.scroll = min(max(0, len(self.lines) - self.rows()), self.scroll + 3)
        elif ev.key == pygame.K_PAGEDOWN:
            self.scroll = max(0, self.scroll - 3)
        elif ev.unicode and ev.unicode.isprintable() and len(self.input) < 240:
            self.input += ev.unicode
        return None

    def draw(self, surf):
        if not self.open:
            return
        panel = pygame.Surface((IW, self.H), pygame.SRCALPHA)
        panel.fill((8, 10, 18, 235))
        pygame.draw.line(panel, (216, 168, 50), (0, self.H - 1), (IW, self.H - 1))
        rows = self.rows()
        start = max(0, len(self.lines) - rows - self.scroll)
        y = 2
        for color, line in self.lines[start:start + rows]:
            panel.blit(self.fonts.text(line, color), (4, y))
            y += 9
        caret = "_" if pygame.time.get_ticks() // 400 % 2 else " "
        panel.blit(self.fonts.text("] " + self.input[-56:] + caret, (235, 225, 200)),
                   (4, self.H - 12))
        surf.blit(panel, (0, 0))


class BottomBar:
    """HP, stats, beat, inventory, hover label — the whole cockpit."""

    def __init__(self, fonts, art):
        self.fonts = fonts
        self.heart = art["sprites"]["heart"]
        self.slot_rects = [pygame.Rect(150 + i * 15, IH - BAR_H + 12, 13, 12)
                           for i in range(8)]

    def slot_at(self, pos):
        for i, r in enumerate(self.slot_rects):
            if r.collidepoint(pos):
                return i
        return None

    def draw(self, surf, player, beat_label, objective_text, director_status,
             selected_item, hover_label):
        bar = pygame.Rect(0, IH - BAR_H, IW, BAR_H)
        pygame.draw.rect(surf, (12, 12, 22), bar)
        pygame.draw.line(surf, (90, 100, 130), (0, bar.y), (IW, bar.y))
        # hearts
        for i in range(player.max_hp // 2):
            if player.hp >= (i + 1) * 2:
                surf.blit(self.heart, (4 + i * 9, bar.y + 3))
            elif player.hp == i * 2 + 1:
                half = self.heart.copy()
                half.set_alpha(110)
                surf.blit(half, (4 + i * 9, bar.y + 3))
        # stats + beat
        st = player.stats
        surf.blit(self.fonts.text(
            f"VIG {st['vigor']}  WIT {st['wit']}  PRE {st['presence']}", (150, 160, 185)),
            (4, bar.y + 13))
        surf.blit(self.fonts.text(beat_label, (216, 168, 50)), (100, bar.y + 3))
        # objective
        if objective_text:
            line = wrap(self.fonts.small, objective_text, 160)[0]
            surf.blit(self.fonts.text(line, (200, 210, 230)), (150, bar.y + 3))
        # inventory slots
        for i, r in enumerate(self.slot_rects):
            pygame.draw.rect(surf, (26, 26, 44), r)
            border = (216, 168, 50) if selected_item == i else (60, 66, 92)
            pygame.draw.rect(surf, border, r, 1)
            if i < len(player.inventory):
                ch = player.inventory[i].name[:1].upper()
                surf.blit(self.fonts.text(ch, (230, 220, 190)), (r.x + 4, r.y + 2))
        # director lamp
        col = {"thinking": (250, 210, 60), "summoned": (250, 160, 40),
               "error": (200, 70, 60)}.get(director_status, (90, 160, 90))
        pygame.draw.rect(surf, col, (IW - 8, bar.y + 4, 4, 4))
        # hover label (what the cursor is over / selected item hint)
        if hover_label:
            lab = self.fonts.text(hover_label[:44], (235, 225, 200))
            surf.blit(lab, (IW - lab.get_width() - 14, bar.y + 13))


def draw_cursor(surf, pos, mode, fonts, item_name=None):
    x, y = pos
    if mode == "hot":
        col = (216, 168, 50)
    elif mode == "item":
        col = (140, 220, 150)
    else:
        col = (230, 230, 240)
    pygame.draw.line(surf, col, (x - 4, y), (x - 1, y))
    pygame.draw.line(surf, col, (x + 1, y), (x + 4, y))
    pygame.draw.line(surf, col, (x, y - 4), (x, y - 1))
    pygame.draw.line(surf, col, (x, y + 1), (x, y + 4))
    if mode == "item" and item_name:
        surf.blit(fonts.text(item_name[:12], col), (x + 5, y + 3))


class StorySelect:
    def __init__(self, fonts):
        self.fonts = fonts
        self.index = 0

    def draw(self, surf, slots):
        surf.fill((16, 14, 30))
        surf.blit(self.fonts.text("CHOOSE YOUR STORY", (216, 168, 50), big=True), (86, 8))
        surf.blit(self.fonts.text("UP/DOWN select   ENTER play   R re-forge all", (140, 145, 165)), (54, 168))
        card_h = 44
        for i, slot in enumerate(slots[:3]):
            r = pygame.Rect(12, 28 + i * (card_h + 3), IW - 24, card_h)
            sel = i == self.index
            pygame.draw.rect(surf, (28, 26, 50) if sel else (18, 18, 34), r)
            pygame.draw.rect(surf, (216, 168, 50) if sel else (70, 76, 100), r, 1)
            story = slot["story"]
            if story is None:
                dots = "." * (1 + (pygame.time.get_ticks() // 400) % 3)
                surf.blit(self.fonts.text(f"The forge glows{dots}", (140, 130, 110)), (r.x + 8, r.y + 16))
                continue
            tag = {"ready": "", "fallback": " [SCRIBE'S RESERVE]"}.get(slot["status"], "")
            surf.blit(self.fonts.text(story["title"].upper() + tag, (230, 225, 210)), (r.x + 8, r.y + 5))
            for j, line in enumerate(wrap(self.fonts.small, story["logline"], r.w - 16)[:2]):
                surf.blit(self.fonts.text(line, (150, 155, 175)), (r.x + 8, r.y + 17 + j * 10))
            surf.blit(self.fonts.text(story["theme"].upper(), (110, 120, 150)),
                      (r.x + r.w - 60, r.y + 5))
            if sel:
                for line in wrap(self.fonts.small, story["promise"], r.w - 16)[:1]:
                    surf.blit(self.fonts.text(line, (216, 168, 50)), (r.x + 8, r.y + 35))
