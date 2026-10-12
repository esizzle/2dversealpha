"""Lightweight always-on frame profiler for 2dverse.

Design goals:
  * Near-zero overhead so it can stay on permanently (a handful of
    perf_counter() calls per frame, NOT per cell).
  * Coarse per-SYSTEM frame timing (physics, sim loop, render, ...),
    reported as a rolling mean over `window` frames.
  * An on-demand deep dive: request_deep_profile() runs the *next* frame
    under cProfile for per-function attribution, without paying that cost
    every frame.
  * Purely observational: never touches RNG or simulation state, so it
    cannot affect determinism.

Usage:
    prof = Profiler()
    ...
    with prof.section("physics"):
        space.step(dt)
    with prof.section("sim_loop"):
        for cell in cells: ...
    prof.frame()                      # once per frame, after all sections
    prof.draw_overlay(surface, font)  # optional, when prof.overlay is True
"""

import time
from collections import deque, OrderedDict

_now = time.perf_counter


class _Section:
    __slots__ = ("prof", "name", "start")

    def __init__(self, prof, name):
        self.prof = prof
        self.name = name
        self.start = 0.0

    def __enter__(self):
        self.start = _now()
        return self

    def __exit__(self, *exc):
        acc = self.prof._accum
        acc[self.name] = acc.get(self.name, 0.0) + (_now() - self.start)
        return False


class Profiler:
    def __init__(self, window=60):
        self.window = window
        self.overlay = False              # draw the on-screen overlay?
        self._accum = OrderedDict()       # name -> seconds this frame
        self._hist = {}                   # name -> deque of per-frame seconds
        self._frame_hist = deque(maxlen=window)
        self._timers = {}                 # cached _Section objects (no alloc/frame)
        self._start = 0.0
        self._frame_start = _now()
        self.frames = 0
        # deep (cProfile) one-shot
        self._want_deep = False

    # -- timing -------------------------------------------------------
    def section(self, name):
        t = self._timers.get(name)
        if t is None:
            t = self._timers[name] = _Section(self, name)
            self._hist[name] = deque(maxlen=self.window)
        return t

    def frame(self):
        """Call once per frame after all sections have closed."""
        now = _now()
        total = now - self._frame_start
        self._frame_start = now
        self._frame_hist.append(total)
        # push accumulated section times into rolling history, then reset
        for name, hist in self._hist.items():
            hist.append(self._accum.get(name, 0.0))
        self._accum.clear()
        self.frames += 1

    # -- reporting ----------------------------------------------------
    def _mean_ms(self, samples):
        return (sum(samples) / len(samples) * 1000.0) if samples else 0.0

    def frame_ms(self):
        return self._mean_ms(self._frame_hist)

    def report(self):
        """Return list of (name, mean_ms) sorted desc, plus ('FRAME', total)."""
        rows = [(n, self._mean_ms(h)) for n, h in self._hist.items()]
        rows.sort(key=lambda r: r[1], reverse=True)
        return rows

    def report_str(self):
        fps = 1000.0 / self.frame_ms() if self.frame_ms() > 0 else 0.0
        lines = [f"FRAME {self.frame_ms():6.2f} ms  (~{fps:4.0f} fps)"]
        for name, ms in self.report():
            lines.append(f"  {name:<14} {ms:6.2f} ms")
        return "\n".join(lines)

    def draw_overlay(self, surface, font, topleft=(8, 8),
                     color=(0, 255, 0), bg=(6, 6, 8)):
        if not self.overlay:
            return
        import pygame
        x, y = topleft
        for line in self.report_str().split("\n"):
            img = font.render(line, True, color)
            rect = img.get_rect(topleft=(x, y))
            pygame.draw.rect(surface, bg, rect.inflate(6, 2))
            surface.blit(img, rect)
            y += 18

    # -- on-demand deep profile --------------------------------------
    def request_deep_profile(self):
        self._want_deep = True

    def maybe_deep_profile(self, fn, *args, top=15, **kwargs):
        """If a deep profile was requested, run fn under cProfile once and
        print the top functions; otherwise just call fn normally."""
        if not self._want_deep:
            return fn(*args, **kwargs)
        self._want_deep = False
        import cProfile, pstats, io
        pr = cProfile.Profile()
        pr.enable()
        result = fn(*args, **kwargs)
        pr.disable()
        s = io.StringIO()
        pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(top)
        print("==== DEEP PROFILE (single frame) ====")
        print(s.getvalue())
        return result
