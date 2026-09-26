"""Mutation Journal: a persistent, tabbed log of mutations the player has
discovered.

Design intent
-------------
The Journal is a *dumb display + storage* widget. It knows nothing about
genomes, environments, decision models, or how a mutation is discovered -- the
game hands it two strings (a pressure and the mutation it produced) and the
journal stores and draws them. This is the same separation the rest of the
project favours (see decision_models.py's "what do I want" vs "how does my body
do it" split): the mutation system decides *what* was discovered, the journal
only decides *how it looks*.

Two tabs, one visible at a time:
    * Environmental -- rows of  (environment / pressure) -> (mutation)
    * Behavioural   -- rows of  (behaviour  / pressure) -> (mutation)

Public API (all the game needs):
    journal = Journal(font)                       # reuse Game.font
    journal.add_environmental_mutation(env, mut)  # returns True if newly added
    journal.add_behavioural_mutation(beh, mut)    # returns True if newly added
    journal.handle_click(local_pos)               # switch tabs on a tab click
    surface = journal.render()                    # -> pygame.Surface to blit

The journal never mutates game state and does no per-cell work, so it is safe
to call render() once per frame from Game.render().
"""

import pygame

from colors import BLACK
from colors import BORDER

# UI text colours. These mirror the literals main.py already uses for panel
# text (create_box_label uses (0, 255, 0); draw_mut_box uses (0, 255, 0) /
# (100, 100, 100) / white) so the journal reads as part of the same UI, not a
# bolted-on widget. Swap these for named colours from colors.py when polishing.
_OUTLINE = BORDER   # panel border + separators, like every other box
_ACTIVE = (0, 255, 0)          # selected tab + column headers (matches labels)
_INACTIVE = (100, 100, 100)    # unselected tab, empty-state + overflow text
_ROW = (255, 255, 255)         # discovered-mutation rows


class Journal:
    # tab identifiers (also the argument you pass to select_tab)
    ENVIRONMENTAL = "environmental"
    BEHAVIOURAL = "behavioural"

    # panel-local layout constants (pixels). Tweak freely when refining visuals.
    _PAD = 8            # inner horizontal padding
    _TAB_H = 30         # height of the tab strip
    _HEADER_H = 22      # height reserved for the column-header row
    _ROW_PAD = 6        # extra vertical spacing per row

    def __init__(self, font, width=200, height=600):
        self.font = font
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))
        self._line_h = self.font.get_height()

        # Per-tab state. 'rows' is the ordered list of (left, right) string
        # pairs as discovered; 'seen' is the same pairs in a set so duplicates
        # are rejected in O(1). 'tab_label' is the (short) text on the tab
        # button; 'col_left' is that tab's left-column header. The right column
        # is always "Mutation".
        self._tabs = {
            self.ENVIRONMENTAL: {
                "tab_label": "ENVIRON.",
                "col_left": "Environment",
                "rows": [],
                "seen": set(),
            },
            self.BEHAVIOURAL: {
                "tab_label": "BEHAVE.",
                "col_left": "Behaviour",
                "rows": [],
                "seen": set(),
            },
        }
        # fixed left-to-right tab order
        self._order = [self.ENVIRONMENTAL, self.BEHAVIOURAL]
        self.active_tab = self.ENVIRONMENTAL

        # Tab hit-boxes in panel-local coordinates, refreshed every render().
        # Kept so handle_click() can test a click without re-deriving layout.
        self._tab_rects = {}

    # ------------------------------------------------------------------
    # Data API -- the only surface the mutation system needs to touch.
    # ------------------------------------------------------------------
    def add_environmental_mutation(self, environment, mutation):
        """Record that `environment` produced `mutation`. Returns True if it was
        newly added, False if that exact pair was already present."""
        return self._add(self.ENVIRONMENTAL, environment, mutation)

    def add_behavioural_mutation(self, behaviour, mutation):
        """Record that `behaviour` produced `mutation`. Returns True if it was
        newly added, False if that exact pair was already present."""
        return self._add(self.BEHAVIOURAL, behaviour, mutation)

    def _add(self, tab_key, left, right):
        left, right = str(left), str(right)
        tab = self._tabs[tab_key]
        key = (left, right)
        if key in tab["seen"]:
            return False            # duplicate -> ignore
        tab["seen"].add(key)
        tab["rows"].append(key)
        return True

    def clear(self):
        """Forget every discovered mutation (both tabs)."""
        for tab in self._tabs.values():
            tab["rows"].clear()
            tab["seen"].clear()

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def select_tab(self, tab_key):
        if tab_key in self._tabs:
            self.active_tab = tab_key

    def handle_click(self, local_pos):
        """`local_pos` is (x, y) relative to the journal panel's top-left
        (i.e. the caller has already subtracted the panel's screen offset).
        Switches tabs if the click landed on one. Returns True if it did."""
        for tab_key, rect in self._tab_rects.items():
            if rect.collidepoint(local_pos):
                self.select_tab(tab_key)
                return True
        return False

    # ------------------------------------------------------------------
    # Rendering  (returns the panel surface; the caller blits it)
    # ------------------------------------------------------------------
    def render(self):
        surf = self.surface
        surf.fill(BLACK)
        w, h = self.width, self.height

        self._draw_tabs(surf, w)
        headers_bottom = self._draw_headers(surf, w)
        self._draw_rows(surf, w, h, headers_bottom)

        # outline last so it frames everything cleanly (same as the other boxes)
        pygame.draw.rect(surf, _OUTLINE, (0, 0, w, h), 1)
        return surf

    # -- rendering helpers --------------------------------------------
    def _draw_tabs(self, surf, w):
        self._tab_rects = {}
        tab_w = w // len(self._order)
        for i, tab_key in enumerate(self._order):
            rect = pygame.Rect(i * tab_w, 0, tab_w, self._TAB_H)
            self._tab_rects[tab_key] = rect

            active = tab_key == self.active_tab
            color = _ACTIVE if active else _INACTIVE
            self._blit_clipped(self._tabs[tab_key]["tab_label"], color,
                               rect.x + 4, rect.y + 10, rect.width - 6)

            # highlight the selected tab with an underline bar
            if active:
                pygame.draw.line(surf, _ACTIVE,
                                 (rect.x + 2, self._TAB_H - 2),
                                 (rect.right - 2, self._TAB_H - 2), 2)
            # divider between tabs
            if i > 0:
                pygame.draw.line(surf, _OUTLINE,
                                 (rect.x, 2), (rect.x, self._TAB_H - 4), 1)

        # separator under the whole tab strip
        pygame.draw.line(surf, _OUTLINE, (0, self._TAB_H), (w, self._TAB_H), 1)

    def _draw_headers(self, surf, w):
        col1_x, col2_x = self._columns(w)
        y = self._TAB_H + 4
        tab = self._tabs[self.active_tab]
        self._blit_clipped(tab["col_left"], _ACTIVE, col1_x, y, col2_x - col1_x - 4)
        self._blit_clipped("Mutation", _ACTIVE, col2_x, y, w - col2_x - self._PAD)

        bottom = y + self._HEADER_H
        pygame.draw.line(surf, _INACTIVE,
                         (self._PAD, bottom), (w - self._PAD, bottom), 1)
        return bottom

    def _draw_rows(self, surf, w, h, headers_bottom):
        col1_x, col2_x = self._columns(w)
        rows = self._tabs[self.active_tab]["rows"]

        row_y0 = headers_bottom + 4
        row_h = self._line_h + self._ROW_PAD
        avail = h - row_y0 - self._PAD
        max_rows = max(0, avail // row_h)

        # empty state
        if not rows:
            self._blit_clipped("No mutations discovered yet", _INACTIVE,
                               col1_x, row_y0, w - 2 * self._PAD)
            return

        # If more rows exist than fit, keep the last visible line for a
        # "+N more" marker so nothing is silently dropped off the bottom.
        overflow = len(rows) > max_rows
        visible = (max_rows - 1) if (overflow and max_rows > 0) else max_rows

        for idx, (left, right) in enumerate(rows[:visible]):
            y = row_y0 + idx * row_h
            self._blit_clipped(left, _ROW, col1_x, y, col2_x - col1_x - 4)
            self._blit_clipped(right, _ROW, col2_x, y, w - col2_x - self._PAD)

        if overflow:
            y = row_y0 + visible * row_h
            self._blit_clipped(f"+{len(rows) - visible} more", _INACTIVE,
                               col1_x, y, w - 2 * self._PAD)

    def _columns(self, w):
        """(left-column x, right-column x) in panel-local pixels."""
        return self._PAD, w // 2 + 4

    def _blit_clipped(self, text, color, x, y, max_width):
        """Render `text` and blit it clipped to `max_width`, so long strings
        truncate at the column edge instead of spilling into the next column or
        past the panel. This is the journal's overflow-safety for wide entries."""
        img = self.font.render(str(text), True, color)
        prev = self.surface.get_clip()
        self.surface.set_clip(pygame.Rect(x, y, max_width, self._line_h + 2))
        self.surface.blit(img, (x, y))
        self.surface.set_clip(prev)