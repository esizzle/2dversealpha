"""Settings: a HUD panel (plus its top-right tab) for runtime options.

Design intent
-------------
Same shape as journal.py: a *dumb widget* that owns its surface, layout and
input, and knows nothing about the simulation. The game gives it a font, a
size, and a handful of callbacks; the panel draws itself and calls back when
a control changes. Nothing in here touches audio, pygame.quit, or game state
directly -- that stays in main.py, wired through the callbacks.

Two pieces:
    * SettingsTab   -- the small fixed "Settings" bar in the top-right corner
                       of the screen. Clicking it toggles the panel.
    * SettingsPanel -- the panel itself. It is meant to be blitted into the
                       same screen slot the Player Stats box uses, so while it
                       is open it *replaces* that box (the game decides which
                       of the two to draw; see Game.render).

Controls are a flat list of widgets laid out top-to-bottom, so adding a new
option is one `add_slider(...)` / `add_button(...)` call in Game (or a new
widget class following the same three-method contract: layout / draw /
handle_event). Fullscreen toggles, resolution pickers, sim-speed sliders,
UI scaling etc. can all be added that way without touching the panel logic.

Public API (all the game needs):
    tab = SettingsTab(font, rect)                    # rect in SCREEN coords
    tab.hit(screen_pos) -> bool
    tab.render(screen, mouse_pos, is_open)

    panel = SettingsPanel(font, width, height)
    panel.add_slider(label, get, set)                # get() -> 0..1, set(v)
    panel.add_button(label, on_click)
    panel.toggle() / panel.open() / panel.close()
    panel.is_open -> bool
    panel.handle_event(event, origin) -> bool        # True if it ate the event
    surface = panel.render()                         # -> pygame.Surface to blit

Coordinates: like Journal.handle_click, the panel works in *panel-local*
pixels. handle_event takes the panel's screen `origin` and converts once, so
the caller never has to.
"""

import pygame

from colors import BLACK
from colors import BORDER
# UI colours -- the same literals journal.py / main.py already use so the
# panel reads as part of the existing HUD.
_OUTLINE = BORDER   # panel border, slider track outline
_ACTIVE = (0, 255, 0)          # labels, slider fill, tab text
_INACTIVE = (100, 100, 100)    # dim text (values), idle tab text
_TEXT = (255, 255, 255)        # control labels
_HOVER_BG = (20, 20, 24)       # subtle hover fill for the tab / button
_DANGER = (255, 0, 0)          # quit button accent (matches stat-bar red)


def _clamp01(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


# ----------------------------------------------------------------------
# Widgets (panel-local coordinates)
# ----------------------------------------------------------------------
class Slider:
    """Horizontal 0..100% slider bound to a getter/setter pair.

    `get()` returns the current value in 0..1 (so the slider always shows the
    real state, even if something else changed it); `set(v)` is called with
    0..1 whenever the user drags/clicks -- changes take effect immediately.
    """
    HEIGHT = 40           # vertical space this control takes in the panel
    _TRACK_H = 10
    _KNOB_W = 6
    _KNOB_H = 16

    def __init__(self, label, get, set):
        self.label = label
        self.get = get
        self.set = set
        self.rect = pygame.Rect(0, 0, 0, self.HEIGHT)   # set by layout()
        self.track = pygame.Rect(0, 0, 0, self._TRACK_H)
        self.dragging = False

    def layout(self, x, y, w):
        self.rect = pygame.Rect(x, y, w, self.HEIGHT)
        # label on the first line, track on the second
        self.track = pygame.Rect(x, y + 22, w, self._TRACK_H)

    def _value_from_x(self, mx):
        if self.track.width <= 0:
            return 0.0
        return _clamp01((mx - self.track.x) / self.track.width)

    def handle_event(self, event, pos):
        """`pos` is the event's panel-local position (or None for events
        without one). Returns True if the event was consumed."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # generous hitbox: the track plus the knob's overhang
            if self.track.inflate(0, self._KNOB_H).collidepoint(pos):
                self.dragging = True
                self.set(self._value_from_x(pos[0]))
                return True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self.set(self._value_from_x(pos[0]))
            return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.dragging = False
            return True
        return False

    def draw(self, surf, font):
        value = _clamp01(self.get())
        # label + percentage on one line (same layout as draw_stat_bar)
        label = font.render(self.label + ":", True, _TEXT)
        surf.blit(label, (self.rect.x, self.rect.y))
        pct = font.render(f"{round(value * 100)}%", True, _INACTIVE)
        surf.blit(pct, (self.rect.right - pct.get_width(), self.rect.y))

        # track outline + fill, knob on top
        t = self.track
        pygame.draw.rect(surf, _OUTLINE, t, 1)
        fill_w = int(t.width * value)
        if fill_w > 0:
            pygame.draw.rect(surf, _ACTIVE, (t.x, t.y, fill_w, t.height))
        knob_x = t.x + fill_w - self._KNOB_W // 2
        knob = pygame.Rect(knob_x, t.centery - self._KNOB_H // 2,
                           self._KNOB_W, self._KNOB_H)
        knob.clamp_ip(pygame.Rect(t.x - self._KNOB_W // 2, knob.y,
                                  t.width + self._KNOB_W, knob.height))
        pygame.draw.rect(surf, BLACK, knob)
        pygame.draw.rect(surf, _OUTLINE if not self.dragging else _ACTIVE, knob, 1)


class Button:
    """A full-width text button that fires `on_click()` on release."""
    HEIGHT = 28

    def __init__(self, label, on_click, accent=_ACTIVE):
        self.label = label
        self.on_click = on_click
        self.accent = accent
        self.rect = pygame.Rect(0, 0, 0, self.HEIGHT)
        self.hovered = False
        self.pressed = False

    def layout(self, x, y, w):
        self.rect = pygame.Rect(x, y, w, self.HEIGHT)

    def handle_event(self, event, pos):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(pos)
            return False                      # motion is never "consumed" here
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(pos):
                self.pressed = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.pressed:
            self.pressed = False
            if self.rect.collidepoint(pos):
                self.on_click()
            return True
        return False

    def draw(self, surf, font):
        if self.hovered or self.pressed:
            pygame.draw.rect(surf, _HOVER_BG, self.rect)
        pygame.draw.rect(surf, self.accent, self.rect, 1)
        text = font.render(self.label, True, self.accent)
        surf.blit(text, text.get_rect(center=self.rect.center))


# ----------------------------------------------------------------------
# The panel
# ----------------------------------------------------------------------
class SettingsPanel:
    _PAD = 10           # inner padding
    _TOP = 25           # first control's y (matches the stat box's first bar)
    _GAP = 8            # vertical gap between controls

    def __init__(self, font, width=200, height=300):
        self.font = font
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))
        self.is_open = False
        self._controls = []
        self._bottom_controls = []     # anchored to the bottom (e.g. Quit)
        self._dirty_layout = True

    # -- building ------------------------------------------------------
    def add_slider(self, label, get, set):
        s = Slider(label, get, set)
        self._controls.append(s)
        self._dirty_layout = True
        return s

    def add_button(self, label, on_click, accent=_ACTIVE, bottom=False):
        b = Button(label, on_click, accent)
        (self._bottom_controls if bottom else self._controls).append(b)
        self._dirty_layout = True
        return b

    def _layout(self):
        x = self._PAD
        w = self.width - 2 * self._PAD
        y = self._TOP
        for c in self._controls:
            c.layout(x, y, w)
            y += c.HEIGHT + self._GAP
        y = self.height - self._PAD
        for c in reversed(self._bottom_controls):
            y -= c.HEIGHT
            c.layout(x, y, w)
            y -= self._GAP
        self._dirty_layout = False

    # -- open / close --------------------------------------------------
    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False
        # drop any half-finished drag / press so nothing fires on reopen
        for c in self._all_controls():
            if isinstance(c, Slider):
                c.dragging = False
            elif isinstance(c, Button):
                c.pressed = False
                c.hovered = False

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self.open()

    def _all_controls(self):
        return self._controls + self._bottom_controls

    # -- input ----------------------------------------------------------
    def handle_event(self, event, origin):
        """Feed one pygame event. `origin` is the panel's top-left on screen.
        Returns True if the panel consumed the event, in which case the
        caller should NOT pass it on to the camera / simulation. While the
        panel is open, every mouse event inside it is consumed (so clicks and
        scroll-wheel never leak into the world); a drag that started on a
        slider is followed even after the cursor leaves the panel."""
        if not self.is_open:
            return False
        if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                              pygame.MOUSEMOTION):
            return False
        if self._dirty_layout:
            self._layout()

        pos = (event.pos[0] - origin[0], event.pos[1] - origin[1])
        inside = 0 <= pos[0] < self.width and 0 <= pos[1] < self.height

        consumed = False
        for c in self._all_controls():
            if c.handle_event(event, pos):
                consumed = True
                break
        return consumed or inside

    # -- rendering ------------------------------------------------------
    def render(self):
        if self._dirty_layout:
            self._layout()
        surf = self.surface
        surf.fill(BLACK)
        for c in self._all_controls():
            c.draw(surf, self.font)
        pygame.draw.rect(surf, _OUTLINE, (0, 0, self.width, self.height), 1)
        return surf


# ----------------------------------------------------------------------
# The tab (fixed to the screen, top-right)
# ----------------------------------------------------------------------
class SettingsTab:
    def __init__(self, font, rect, label="Settings"):
        self.font = font
        self.rect = pygame.Rect(rect)
        self.label = label

    def hit(self, screen_pos):
        return self.rect.collidepoint(screen_pos)

    def render(self, screen, mouse_pos, is_open):
        hovered = self.rect.collidepoint(mouse_pos)
        pygame.draw.rect(screen, _HOVER_BG if (hovered or is_open) else BLACK, self.rect)
        pygame.draw.rect(screen, _OUTLINE if (hovered or is_open) else _INACTIVE, self.rect, 1)
        text = self.font.render(self.label, True, _ACTIVE if (hovered or is_open) else _INACTIVE)
        screen.blit(text, text.get_rect(center=self.rect.center))
        if is_open:
            # underline, same cue the journal uses for its selected tab
            pygame.draw.line(screen, _ACTIVE,
                             (self.rect.x + 2, self.rect.bottom - 2),
                             (self.rect.right - 3, self.rect.bottom - 2), 2)
