import math
import pygame

from resources import resource_path

# ======================================================================
# Audio system
# ----------------------------------------------------------------------
# A single, load-once audio manager for background music and sound
# effects. There is exactly one AudioManager for the whole game (the
# `audio` singleton at the bottom of this file); Game wires it up at
# startup and the cell events import it directly to trigger sounds.
#
# Design goals:
#   * background music via pygame.mixer.music, looped, started once,
#     GLOBAL -- never affected by the spatial rules below
#   * short SFX loaded once, played on free mixer channels (non-blocking,
#     can overlap)
#   * SFX are SPATIAL: every organism/world sound carries a world
#     position and is heard from the camera's point of view (the
#     "listener"). Game calls audio.set_listener(...) once per frame with
#     the camera's world-space centre and zoom; each play request is then
#     culled / attenuated / panned against that cached listener state.
#   * a missing audio file (or no audio device) never crashes the game --
#     it just prints a warning and that sound becomes a silent no-op
#
# Volume model for a spatial sound:
#     final = base_volume[name] * sfx_volume * zoom_volume * distance_attenuation
#   - zoom_volume       : 1.0 when zoomed in, falls smoothly as you zoom out
#   - distance_attenuation: 1.0 near the listener, smooth curve to 0 at
#                           the edge of the audible radius
#   - audible radius (world units) grows as you zoom out, so zoomed out you
#     hear a large slice of the ecosystem faintly; zoomed in you hear only
#     the local area, loudly.
# ======================================================================

# ---- CONFIG: change these to tune audio -----------------------------
# Volumes are 0.0 (silent) .. 1.0 (full). Music and SFX are independent.
MUSIC_VOLUME = 0.4
SFX_VOLUME = 0.6            # master multiplier for every sound effect

# Audio asset paths, relative to the project root. They are resolved through
# resource_path() so they work from source AND from a PyInstaller build,
# regardless of the current working directory. Missing files fail gracefully.
MUSIC_PATH = resource_path("assets/audio/music/background.ogg")

SFX_PATHS = {
    "eat_cell":     resource_path("assets/audio/sfx/cell_death.mp3"),     # a cell eats another cell
    "eat_particle": resource_path("assets/audio/sfx/cell_consume.ogg"),   # a cell consumes a particle
    "split":        resource_path("assets/audio/sfx/cell_split.ogg"),     # a cell splits / reproduces
    "collide_sand": resource_path("assets/audio/sfx/sand_collide.wav"),   # a cell bumps into sand
}

# Per-sound base volume (0..1), applied before sfx_volume / zoom / distance.
# Sounds not listed here default to 1.0.
SFX_BASE_VOLUME = {
    "eat_cell":     1.0,
    "eat_particle": 0.5,
    "split":        0.9,
    "collide_sand": 0.7,
}

# --- Listening radius vs. zoom ---------------------------------------
# The audible radius in WORLD units is  AUDIBLE_RADIUS_AT_ZOOM_1 / zoom,
# clamped to [AUDIBLE_RADIUS_MIN, AUDIBLE_RADIUS_MAX]. Camera.zoom is the
# world->screen scale (zoom 1.0 == 1 world unit per pixel; the world
# window is 600px, so 300 world units to the edge of the screen at zoom 1).
# Zoom in (zoom > 1)  -> smaller world radius.
# Zoom out (zoom < 1) -> larger world radius.
AUDIBLE_RADIUS_AT_ZOOM_1 = 450.0    # a bit past the screen edge at zoom 1
AUDIBLE_RADIUS_MIN = 120.0          # never shrink below this when zoomed way in
AUDIBLE_RADIUS_MAX = 6000.0         # never grow beyond this when zoomed way out

# --- Overall loudness vs. zoom -----------------------------------------
# zoom_volume = clamp(zoom / ZOOM_FULL_VOLUME, 0, 1) ** ZOOM_VOLUME_CURVE,
# floored at ZOOM_VOLUME_MIN. Continuous, no discrete levels.
#   zoom >= ZOOM_FULL_VOLUME -> full volume
#   zoom -> 0                -> volume falls toward ZOOM_VOLUME_MIN
ZOOM_FULL_VOLUME = 1.0      # at or above this zoom, SFX are at full volume
ZOOM_VOLUME_CURVE = 0.5     # < 1 = gentle fall-off, > 1 = aggressive fall-off
ZOOM_VOLUME_MIN = 0.08      # faint ecosystem murmur when fully zoomed out

# --- Distance attenuation (inside the audible radius) ----------------
# Fraction of the radius that plays at full volume; beyond it a smoothstep
# curve falls to exactly 0 at the radius edge (no abrupt cutoff).
ATTENUATION_INNER_FRACTION = 0.25

# --- Stereo panning -------------------------------------------------
# Pan is computed from the sound's horizontal SCREEN offset relative to the
# listener, normalised by half the world window width (so a sound at the
# screen edge is fully panned). PAN_STRENGTH scales it: 0 = mono,
# 1 = hard pan. Keep it subtle.
PAN_STRENGTH = 0.6

# --- Concurrency / performance ------------------------------------
NUM_MIXER_CHANNELS = 32
# Max simultaneous playing copies of the SAME sound. When the limit is
# hit, a new request only plays if it is louder than the quietest copy
# already playing (which is stopped and replaced).
MAX_VOICES_PER_SOUND = {
    "eat_cell":     4,
    "eat_particle": 6,
    "split":        4,
    "collide_sand": 3,
}
DEFAULT_MAX_VOICES = 4
# Minimum milliseconds between two starts of the same sound. Stops a swarm
# of cells feeding on the same frame from stacking dozens of identical
# transients into one loud click.
MIN_RETRIGGER_MS = {
    "eat_cell":     40,
    "eat_particle": 35,
    "split":        40,
    "collide_sand": 60,
}
DEFAULT_MIN_RETRIGGER_MS = 40
# Sounds quieter than this are not worth a channel at all.
MIN_AUDIBLE_VOLUME = 0.01
# ---------------------------------------------------------------------


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _smoothstep(edge0, edge1, x):
    """Hermite smoothstep: 0 at edge0, 1 at edge1, smooth in between."""
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    t = _clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class AudioManager:
    def __init__(self):
        # Nothing touches the audio device until init() is called, so this
        # object is safe to construct at import time.
        self.enabled = False          # True only once the mixer is up
        self.sounds = {}              # name -> pygame.mixer.Sound (or absent)
        self.music_loaded = False
        self.music_volume = MUSIC_VOLUME
        self.sfx_volume = SFX_VOLUME

        # ---- listener state (refreshed once per frame by set_listener) ----
        self.listener_x = 0.0         # world-space centre of the camera view
        self.listener_y = 0.0
        self.zoom = 1.0
        self.half_view_w = 300.0      # half the world window width, in pixels
        # derived, cached so each play request does almost no work
        self.audible_radius = AUDIBLE_RADIUS_AT_ZOOM_1
        self._radius_sq = self.audible_radius ** 2
        self._inv_radius = 1.0 / self.audible_radius
        self.zoom_volume = 1.0
        self._pan_scale = PAN_STRENGTH / self.half_view_w   # per screen pixel

        # ---- concurrency bookkeeping ----
        # name -> list of [channel, volume] currently (believed) playing
        self._voices = {}
        # name -> tick (ms) of the last start
        self._last_play_ms = {}

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------
    def init(self):
        """Bring up pygame.mixer and load every audio file once. Call this
        after pygame.init(). Any failure here (no audio device, etc.) just
        disables audio -- the game keeps running silently."""
        try:
            pygame.mixer.init()
        except pygame.error as e:
            print(f"[audio] mixer unavailable, running without sound: {e}")
            self.enabled = False
            return

        # allow many SFX to overlap (music has its own reserved channel)
        pygame.mixer.set_num_channels(NUM_MIXER_CHANNELS)
        self.enabled = True

        self._load_sfx()
        self._load_music()

    def _load_sfx(self):
        """Load each sound effect once and cache it. A missing file is
        warned about and simply left out of the cache. Sound objects stay
        at volume 1.0 -- all volume shaping happens per-channel at play
        time so two copies of one sound can play at different loudness."""
        for name, path in SFX_PATHS.items():
            try:
                sound = pygame.mixer.Sound(path)
                sound.set_volume(1.0)
                self.sounds[name] = sound
                self._voices[name] = []
            except (pygame.error, FileNotFoundError) as e:
                print(f"[audio] missing/invalid SFX '{name}' ({path}): {e}")

    def _load_music(self):
        """Load the looping background track once via pygame.mixer.music."""
        try:
            pygame.mixer.music.load(MUSIC_PATH)
            pygame.mixer.music.set_volume(self.music_volume)
            self.music_loaded = True
        except (pygame.error, FileNotFoundError) as e:
            print(f"[audio] missing/invalid music ({MUSIC_PATH}): {e}")
            self.music_loaded = False

    # ------------------------------------------------------------------
    # Listener (call once per frame from the game loop)
    # ------------------------------------------------------------------
    def set_listener(self, world_x, world_y, zoom, half_view_width=None):
        """Update where the player is listening from. `world_x/world_y` is
        the world-space point at the centre of the camera view and `zoom`
        is Camera.zoom. Everything derived from zoom (audible radius, zoom
        volume, pan scale) is computed here, once, not per sound."""
        self.listener_x = float(world_x)
        self.listener_y = float(world_y)
        if half_view_width:
            self.half_view_w = float(half_view_width)
            self._pan_scale = PAN_STRENGTH / self.half_view_w

        zoom = max(float(zoom), 1e-6)
        if zoom == self.zoom:
            return
        self.zoom = zoom

        # audible radius in world units: shrinks as we zoom in, grows as we
        # zoom out, clamped to sane bounds
        radius = _clamp(AUDIBLE_RADIUS_AT_ZOOM_1 / zoom,
                        AUDIBLE_RADIUS_MIN, AUDIBLE_RADIUS_MAX)
        self.audible_radius = radius
        self._radius_sq = radius * radius
        self._inv_radius = 1.0 / radius

        # overall loudness: full when zoomed in, fading as we zoom out
        z = _clamp(zoom / ZOOM_FULL_VOLUME, 0.0, 1.0)
        self.zoom_volume = max(ZOOM_VOLUME_MIN, z ** ZOOM_VOLUME_CURVE)

    # ------------------------------------------------------------------
    # Spatial maths (pure functions of cached listener state)
    # ------------------------------------------------------------------
    def compute_spatial(self, name, world_x, world_y):
        """Return (volume, left_gain, right_gain) for a sound of type `name`
        at the given world position, or None if it is out of earshot.
        Cheap early-out: a squared-distance test against the cached radius
        before any sqrt / curve maths."""
        dx = world_x - self.listener_x
        dy = world_y - self.listener_y
        d_sq = dx * dx + dy * dy
        if d_sq >= self._radius_sq:
            return None                        # 1. outside radius -> ignore

        # 2. distance attenuation: flat inside the inner fraction, then a
        #    smoothstep down to exactly 0 at the radius edge
        d = math.sqrt(d_sq) * self._inv_radius          # 0..1
        attenuation = 1.0 - _smoothstep(ATTENUATION_INNER_FRACTION, 1.0, d)
        if attenuation <= 0.0:
            return None

        volume = (SFX_BASE_VOLUME.get(name, 1.0)
                  * self.sfx_volume
                  * self.zoom_volume
                  * attenuation)
        if volume < MIN_AUDIBLE_VOLUME:
            return None

        # 3. stereo pan from horizontal SCREEN offset (world dx * zoom),
        #    saturating at the screen edge. Pan only redistributes, it
        #    never raises the volume above `volume`.
        pan = _clamp(dx * self.zoom * self._pan_scale, -1.0, 1.0)
        left = volume * (1.0 - pan) if pan > 0.0 else volume
        right = volume * (1.0 + pan) if pan < 0.0 else volume
        return volume, left, right

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def play_music(self):
        """Start the background soundtrack looping forever. Safe to call
        once at game start; it is a no-op if music is already playing so
        the track is never restarted during normal gameplay. Music is
        global: it ignores listener position and zoom entirely."""
        if not (self.enabled and self.music_loaded):
            return
        if pygame.mixer.music.get_busy():
            return
        pygame.mixer.music.play(loops=-1)

    def play_sfx(self, name, position=None):
        """Play a cached sound effect. With a world-space `position` the
        sound is culled, attenuated and panned relative to the listener;
        with position=None it plays globally at base * sfx volume (for UI
        or non-diegetic cues). Unknown/missing sounds are silently ignored."""
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return

        if position is None:
            volume = SFX_BASE_VOLUME.get(name, 1.0) * self.sfx_volume
            if volume < MIN_AUDIBLE_VOLUME:
                return
            left = right = volume
        else:
            spatial = self.compute_spatial(name, position[0], position[1])
            if spatial is None:
                return
            volume, left, right = spatial

        self._start_voice(name, sound, volume, left, right)

    def _start_voice(self, name, sound, volume, left, right):
        """Rate-limit, enforce the per-sound voice cap, then grab a free
        channel and start the sound at the given stereo gains."""
        now = pygame.time.get_ticks()
        if now - self._last_play_ms.get(name, -10_000) < \
                MIN_RETRIGGER_MS.get(name, DEFAULT_MIN_RETRIGGER_MS):
            return

        # prune voices that have finished (list is tiny: <= max voices)
        voices = self._voices.setdefault(name, [])
        if voices:
            voices[:] = [v for v in voices if v[0].get_busy()]

        channel = None
        if len(voices) >= MAX_VOICES_PER_SOUND.get(name, DEFAULT_MAX_VOICES):
            # at the cap: only replace the quietest copy if we're louder
            quietest = min(voices, key=lambda v: v[1])
            if volume <= quietest[1]:
                return
            channel = quietest[0]
            channel.stop()
            voices.remove(quietest)

        if channel is None:
            channel = pygame.mixer.find_channel()   # None if every channel is busy
            if channel is None:
                return                              # drop rather than steal

        channel.set_volume(left, right)
        channel.play(sound)
        voices.append([channel, volume])
        self._last_play_ms[name] = now

    # convenience wrappers so call sites read clearly at the event.
    # `position` is the world-space (x, y) of the organism/event.
    def play_eat_cell(self, position=None):
        self.play_sfx("eat_cell", position)

    def play_eat_particle(self, position=None):
        self.play_sfx("eat_particle", position)

    def play_split(self, position=None):
        self.play_sfx("split", position)

    def play_collide_sand(self, position=None):
        self.play_sfx("collide_sand", position)

    # ------------------------------------------------------------------
    # Runtime volume control (optional -- edit the CONFIG constants for
    # the persistent defaults)
    # ------------------------------------------------------------------
    def set_music_volume(self, volume):
        self.music_volume = _clamp(volume, 0.0, 1.0)
        if self.enabled:
            pygame.mixer.music.set_volume(self.music_volume)

    def set_sfx_volume(self, volume):
        # master SFX volume is folded into every play request, so nothing
        # on the Sound objects needs to change
        self.sfx_volume = _clamp(volume, 0.0, 1.0)


# The single shared instance. Import this everywhere:
#     from audio import audio
audio = AudioManager()
