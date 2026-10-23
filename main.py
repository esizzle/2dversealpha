from resources import APP_NAME, APP_VERSION, redirect_output_when_frozen

from world_grid import *
from camera import *
from player import *
from colors import *
from profiler import Profiler
from journal import Journal
from settings import SettingsPanel, SettingsTab
from audio import audio
from sim_clock import sim_clock
from multicell import (remove_all_joints, same_organism, steering_head, members_collide,
                       can_rearrange, detach_cell, reattach_cell)
from plant_defense import check_vertex_defense
from global_constants import (SHOW_CELL_JOINTS, AI_DECISION_INTERVAL,
                              SIM_LOD, SIM_LOD_FULL_RADIUS, SIM_LOD_MAX_INTERVAL,
                              FOOD_RECHECK_DISTANCE, PARTICLE_RESPAWN_RATE)
FOOD_RECHECK_DISTANCE_SQ = FOOD_RECHECK_DISTANCE * FOOD_RECHECK_DISTANCE
from collections import deque


SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 720
WORLD_WINDOW_WIDTH = 600
WORLD_WINDOW_HEIGHT = 600
STAT_BOX_W = 200
STAT_BOX_H = 150
MUT_BOX_W = 200
MUT_BOX_H = 200
SPECIES_BOX_W = 200
SPECIES_BOX_H = 600
JOURNAL_BOX_W = 200
JOURNAL_BOX_H = 600
INTEL_BOX_W = 200
INTEL_BOX_H = 220

VEL_BOX_W = 200
VEL_BOX_H = 220
VEL_SAMPLES_PER_SEC = 60      # must match dt = 1/60 in update()
VEL_HISTORY_SECONDS = 10.0    # x-axis span (default)

# Screen-space HUD chrome (fixed to the application window, never the world).
HUD_PAD = 8              # padding from the screen edges for the FPS counter / tab
SETTINGS_TAB_W = 90
SETTINGS_TAB_H = 26

# Cell dragging (rearranging the player's own organism). Pressing a cell
# always selects it (stat panels). Only holding the button for DRAG_HOLD_MS
# turns the press into a drag; releasing sooner is a plain click and never
# changes the organism, even if the mouse wobbled a little.
DRAG_HOLD_MS = 250
DRAG_ATTACH_COLOR = MED_LIGHT_GREEN   # ghost over a valid attach target
DRAG_DETACH_COLOR = GOLD              # ghost over empty space
DRAG_INVALID_COLOR = RED              # ghost over an invalid spot
DRAG_TETHER_COLOR = (150, 150, 150)   # line from the real cell to the ghost

# Seed the journal with a few placeholder rows at startup so the panel is
# visible immediately. These are UI samples only -- they do NOT drive any game
# mechanic. Set to False (or delete _seed_journal_demo) once the real
# mutation-discovery hooks are wired in (see check_mutations below).
JOURNAL_DEMO_SEED = False

# Performance cull: while the measured frame rate is below FPS_CULL_THRESHOLD,
# one random non-player cell is killed, at most once every FPS_CULL_COOLDOWN
# seconds, until the frame rate recovers. Set the cooldown to 0 to cull on
# every slow frame.
FPS_CULL_THRESHOLD = 55
FPS_CULL_COOLDOWN = 0.25

# energy gained per frame, by algae color and light level.
# Green algae thrive near the surface, brown mid-depth, red in the deep.
PHOTOSYNTHESIS_RATES = {
    LIME:   {5: 100, 4: 50, 3: 20, 2: 10},
    ORANGE: {5: 50,  4: 20, 3: 50, 2: 20},
    RED:    {5: 20,  4: 10, 3: 20, 2: 50},
}


class Game:
    def __init__(self):
        self.screen, self.clock = self.init_pygame()
        self.world_surface = pygame.Surface((WORLD_WINDOW_WIDTH, WORLD_WINDOW_HEIGHT))
        self.stat_box_surface = pygame.Surface((STAT_BOX_W, STAT_BOX_H))
        self.mut_box_surface = pygame.Surface((MUT_BOX_W, MUT_BOX_H))
        self.species_box_surface = pygame.Surface((SPECIES_BOX_W, SPECIES_BOX_H))
        self.intel_box_surface = pygame.Surface((INTEL_BOX_W, INTEL_BOX_H))
        self.vel_box_surface = pygame.Surface((VEL_BOX_W, VEL_BOX_H))
        self.vel_history = deque(maxlen=int(VEL_HISTORY_SECONDS * VEL_SAMPLES_PER_SEC))

        # HUD font. This has always rendered with pygame's bundled default
        # font: the old call was SysFont("assets/fonts/Arcade_Classic.ttf")
        # and SysFont takes a *font name*, so the unknown name silently fell
        # back to the default. Font(None, ...) asks for that default font
        # explicitly, so the build looks exactly like the dev version and
        # does not depend on the fonts installed on the player's machine.
        # To switch to Arcade Classic later:
        #   pygame.font.Font(resource_path("assets/fonts/Aasrcade_Classic.ttf"), 18)
        # (glyph metrics change, so the hard-coded HUD offsets need a pass).
        self.font = pygame.font.Font(None, 18)

        # Mutation journal, mounted in the (currently unused) left slot -- the
        # same position/size the species box reserves. It reuses the game font
        # and owns its own surface, data and tab state (see journal.py).
        self.journal = Journal(self.font, JOURNAL_BOX_W, JOURNAL_BOX_H)
        self.journal_pos = ((SCREEN_WIDTH - WORLD_WINDOW_WIDTH) // 2 - 220,
                            (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) // 2)
        if JOURNAL_DEMO_SEED:
            self._seed_journal_demo()

        # Right-hand HUD slot: the Player Stats box lives here, and the
        # Settings panel takes over the exact same slot while it is open
        # (see render()). One position, two panels, never both at once.
        self.stat_box_pos = ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH) // 2 + 20,
                             (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) // 2)
        self.settings = SettingsPanel(self.font, STAT_BOX_W, STAT_BOX_H)
        self._build_settings()
        # the tab sits in the top-right corner of the window, right-aligned
        # with the slot below it, fixed in screen space
        self.settings_tab = SettingsTab(
            self.font,
            (self.stat_box_pos[0] + STAT_BOX_W - SETTINGS_TAB_W, HUD_PAD,
             SETTINGS_TAB_W, SETTINGS_TAB_H))

        # World (chunk-based)
        self.world = World()
        self.world.init_world()
        self.world.load_lvl2chunks()

        # Physics Space
        self.space = pymunk.Space()

        # the basalt boundary walls are always loaded, independent of the
        # player's position, so no cell can ever leave the world
        self.world.load_permanent_walls(self.space)

        # handle collisions between carnivorous cells and cells with cell walls
        self.handler = self.space.add_collision_handler(1, 2)
        self.handler.begin = self.on_cell_begin
        self.handler.pre_solve = self.on_cell_pre_solve
        self.handler.separate = self.on_cell_separate

        # walled <-> walled: only needed so two walled daughters can overlap
        # while they split (see on_walled_pair_begin).
        self.walled_handler = self.space.add_collision_handler(2, 2)
        self.walled_handler.begin = self.on_walled_pair_begin

        # unwalled <-> unwalled: only cells of an animal organism get here
        # (they leave filter group 1 when they join one, see multicell.py),
        # and only cells of the SAME organism collide
        self.animal_handler = self.space.add_collision_handler(1, 1)
        self.animal_handler.begin = self.on_animal_pair_begin

        # play a sound when a cell (walled or not, types 1/2) bumps into sand
        # (type 3). begin fires once per contact, so it isn't spammed per frame.
        for cell_type in (1, 2):
            sand_handler = self.space.add_collision_handler(cell_type, 3)
            sand_handler.begin = self.on_sand_begin
            # unloaded sand chunks are single solid boxes (world_grid)
            solid_handler = self.space.add_collision_handler(cell_type, SOLID_SAND_COLLISION_TYPE)
            solid_handler.begin = self.on_solid_sand_begin

        self.camera = Camera(type=0)

        self.player = Player((11500, 11500), self.space)
        plant_g = Genome(intelligence=-1)
        plant_g.has_cell_wall = True
        plant_g.has_chloroplast = True
        plant_g.color = LIME
        plant = Cell((11500, 11400), plant_g)
        self.space.add(plant.body, plant.shape)
        plant.body.velocity = 20,-20
        fungi_g = Genome(intelligence=-1)
        fungi_g.has_cell_wall = True
        fungi_g.has_chloroplast = False
        fungi_g.is_fungi = True
        fungi_g.color = FUNGI
        fungi = Cell((11500, 11600), fungi_g)
        fungi.body.velocity = -20,20
        self.space.add(fungi.body, fungi.shape)


        # mutations tracking
        self.previous_genome = self.player.cell.genome
        self.increased = []
        self.decreased = []

        self.cells = []
        self.cells.append(self.player.cell)
        self.cells.append(plant)
        self.cells.append(fungi)
        self.previous_cell_length = 3

        # cell picked by clicking in the game world. None = show the player.
        # The stat box, intelligence matrix and velocity graphs all read
        # self.inspected_cell, which falls back to the player.
        self.selected_cell = None

        # in-progress drag of one of the player's own cells, or None:
        # {"cell": Cell, "t0": press time (ms), "active": bool}. Not active
        # until held for DRAG_HOLD_MS (see update_drag_hold).
        self.drag = None

        # initial chunk (and hitbox) load around the player
        pos = self.world.world_to_lvl1_chunk(self.player.cell.body.position)
        self.world.load_chunks(pos, self.space)
        self.world.update_solid_sand(self.space)

        self.to_remove_particles = []
        self.running = True
        self.next_fps_cull = 0.0
        self.frame = 0  # sim_clock time the next performance cull is allowed

        self.profiler = Profiler(window=60)

    def init_pygame(self):
        pygame.init()
        # bring up the mixer and load audio once, right after pygame.init()
        audio.init()
        pygame.display.set_caption(f"{APP_NAME} - {APP_VERSION}")
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        clock = pygame.time.Clock()
        return screen, clock

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _build_settings(self):
        """Populate the Settings panel. Every option is a getter/setter (or
        callback) pair, so the panel never touches audio / game state itself.
        To add an option later (fullscreen, sim speed, UI scale, ...), add a
        control here -- the panel lays them out top-to-bottom."""
        # Volumes: the panel shows the live value from the audio manager and
        # writes back through its existing set_* API, so changes are
        # immediate and every SFX call site inherits the new master volume.
        self.settings.add_slider("MUSIC VOLUME",
                                 get=lambda: audio.music_volume,
                                 set=audio.set_music_volume)
        self.settings.add_slider("SFX VOLUME",
                                 get=lambda: audio.sfx_volume,
                                 set=audio.set_sfx_volume)
        # Quit goes through the normal shutdown: running=False ends the
        # main loop, which calls pygame.quit() exactly as the window's close
        # button does.
        self.settings.add_button("Quit Application", self.quit,
                                 accent=(255, 0, 0), bottom=True)

    def toggle_settings(self):
        self.settings.toggle()

    def quit(self):
        self.running = False

    def handle_inputs(self):
        # inputs
        events = pygame.event.get()
        keys = pygame.key.get_pressed()

        # events the HUD consumed are withheld from the camera / player below,
        # so a click or scroll on the Settings panel never reaches the world
        world_events = []

        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.drag is not None:
                        # ESC first cancels a cell drag in progress
                        self.drag = None
                        continue
                    # ESC toggles Settings; it never quits (Quit lives in the panel)
                    self.toggle_settings()
                    continue
                elif event.key == pygame.K_F3:
                    self.profiler.overlay = not self.profiler.overlay  # toggle overlay
                elif event.key == pygame.K_F4:
                    self.profiler.request_deep_profile()
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                                pygame.MOUSEMOTION):
                # 0. a cell drag in progress owns the left button until it is
                #    released (wherever that is); right-click cancels it
                if self.drag is not None:
                    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self.end_drag(event.pos)
                        continue
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                        self.drag = None
                        continue
                # 1. the Settings tab (always visible, always clickable)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 \
                        and self.settings_tab.hit(event.pos):
                    self.toggle_settings()
                    continue
                # 2. the Settings panel, while open, owns the right-hand slot
                if self.settings.handle_event(event, self.stat_box_pos):
                    continue
                # 3. forward left-clicks to the journal in its local coordinates
                #    (screen click minus the panel's top-left) so its tabs are
                #    clickable. Returns True if a tab was hit; otherwise ignored.
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    jx, jy = self.journal_pos
                    self.journal.handle_click((event.pos[0] - jx, event.pos[1] - jy))
                # 4. left-click inside the game world: pressing on one of the
                #    player's own organism cells starts a (pending) drag;
                #    anything else selects the cell under the cursor (or
                #    clears the selection on empty space)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 \
                        and self.world_rect().collidepoint(event.pos):
                    cell = self.cell_at(event.pos)
                    # a press always selects; holding it on one of your own
                    # cells may turn it into a drag (see update_drag_hold)
                    self.set_selected_cell(cell)
                    if cell is not None and self.can_drag(cell):
                        self.drag = {"cell": cell, "t0": pygame.time.get_ticks(),
                                     "active": False}
                    continue
            world_events.append(event)

        # a press held long enough on one of the player's cells becomes a drag
        self.update_drag_hold()

        # camera inputs
        self.camera.handle_input(world_events, keys)
        # player inputs: the player cell (always its organism's head) and
        # every body cell of the player's organism respond to the same keys,
        # each with its own acceleration -- agar.io-style (see steering_head)
        for cell in self.cells:
            head = steering_head(cell)
            if cell.is_player or (head is not None and head.is_player):
                cell.handle_input(world_events, keys)

    # ------------------------------------------------------------------
    # Cell selection (click a cell to inspect it)
    # ------------------------------------------------------------------
    def world_rect(self):
        """Screen-space rect of the game world viewport."""
        return pygame.Rect((SCREEN_WIDTH - WORLD_WINDOW_WIDTH) // 2,
                           (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) // 2,
                           WORLD_WINDOW_WIDTH, WORLD_WINDOW_HEIGHT)

    @property
    def inspected_cell(self):
        """The cell the stat panels show: the selected cell, or the player."""
        cell = self.selected_cell
        if cell is None or cell.is_dead:
            return self.player.cell
        return cell

    def set_selected_cell(self, cell):
        """Select `cell` (None or the player = back to showing the player).
        The velocity history restarts, since it belonged to another cell."""
        if cell is not None and cell.is_player:
            cell = None
        if cell is not self.selected_cell:
            self.selected_cell = cell
            self.vel_history.clear()

    def screen_to_world(self, screen_pos):
        """Screen-space point -> world-space Vec2d (through the world
        viewport's position, then the camera's offset and zoom)."""
        wr = self.world_rect()
        return pymunk.Vec2d(*self.camera.screen_to_world(screen_pos[0] - wr.x,
                                                         screen_pos[1] - wr.y))

    def cell_at(self, screen_pos):
        """The living cell under a screen-space point, or None. A few px of
        slack so tiny, zoomed-out cells are still clickable."""
        point = self.screen_to_world(screen_pos)
        slack = 4 / max(self.camera.zoom, 0.01)
        best, best_dist = None, float("inf")
        for info in self.space.point_query(point, slack, pymunk.ShapeFilter()):
            cell = getattr(info.shape, "_object", None)
            if cell is None or cell.is_dead:
                continue
            if info.distance < best_dist:
                best, best_dist = cell, info.distance
        return best

    def select_cell_at(self, screen_pos):
        self.set_selected_cell(self.cell_at(screen_pos))

    # ------------------------------------------------------------------
    # Cell dragging: rearrange / detach cells of the player's organism.
    # Input + preview only; the structural change itself is
    # multicell.detach_cell / reattach_cell (joints, then rebuild()).
    # ------------------------------------------------------------------
    def can_drag(self, cell):
        """Only cells of the player's own multicellular organism."""
        organism = self.player.cell.multicell
        return organism is not None and cell.multicell is organism and can_rearrange(cell)

    def update_drag_hold(self):
        """Once the button has been held on a cell for DRAG_HOLD_MS, the
        press becomes a drag (ghost appears). Called once per frame."""
        drag = self.drag
        if drag is not None and not drag["active"] \
                and pygame.time.get_ticks() - drag["t0"] >= DRAG_HOLD_MS:
            drag["active"] = True

    def end_drag(self, screen_pos):
        drag, self.drag = self.drag, None
        if not drag["active"]:
            # released before the hold time: a plain click. The press
            # already selected the cell; the organism is left alone.
            return
        self.apply_drop(drag["cell"], screen_pos)

    def _spot_is_clear(self, cell, pos, ignore=()):
        """True if `cell`'s body could sit at world point `pos` without
        overlapping terrain or any other cell (its own shape and the cells in
        `ignore` don't count). 1 px of tolerance so edge-to-edge is fine."""
        reach = max(cell.size - 1, 0.5)
        for info in self.space.point_query(pos, reach, pymunk.ShapeFilter()):
            shape = info.shape
            if shape is cell.shape or shape.sensor:
                continue
            if getattr(shape, "_object", None) in ignore:
                continue
            return False
        return True

    def _attach_spot(self, cell, target, toward):
        """Where `cell` goes when attached to `target`: edge to edge with it
        (the joint's rest length, so nothing stretches), on the side facing
        `toward` (the cursor). If that spot is blocked, try angles further
        round the target, alternating sides; None if all are blocked."""
        centre = target.body.position
        direction = toward - centre
        if direction.length < 1e-6:
            direction = cell.body.position - centre
        if direction.length < 1e-6:
            direction = pymunk.Vec2d(1, 0)
        direction = direction.normalized()
        distance = cell.size + target.size
        for k in range(12):
            angle = ((k + 1) // 2) * (math.pi / 6) * (1 if k % 2 else -1)
            spot = centre + direction.rotated(angle) * distance
            if self._spot_is_clear(cell, spot, ignore=(target,)):
                return spot
        return None

    def resolve_drop(self, cell, screen_pos):
        """What releasing the dragged `cell` at `screen_pos` would do, without
        doing it -- the preview and the actual drop share this, so what you
        see is what happens. Returns (kind, target, spot):
            ("cancel",  None,   None)   released over itself
            ("attach",  target, spot)   onto a cell of the same organism
            ("detach",  None,   spot)   over clear, empty space
            ("invalid", target, spot)   anything else (another organism's
                                        cell, terrain, outside the view...)"""
        if not self.world_rect().collidepoint(screen_pos) or not self.can_drag(cell):
            return "invalid", None, None
        point = self.screen_to_world(screen_pos)
        under = self.cell_at(screen_pos)
        if under is cell:
            return "cancel", None, None
        if under is not None:
            if not same_organism(under, cell) or under.is_splitting:
                return "invalid", under, point
            spot = self._attach_spot(cell, under, point)
            if spot is None:
                return "invalid", under, point
            return "attach", under, spot
        if self._spot_is_clear(cell, point):
            return "detach", None, point
        return "invalid", None, point

    def _move_body(self, cell, pos, velocity):
        body = cell.body
        body.position = pos
        body.velocity = velocity
        body.angular_velocity = 0
        if body.space is not None:
            body.space.reindex_shapes_for_body(body)

    def apply_drop(self, cell, screen_pos):
        kind, target, spot = self.resolve_drop(cell, screen_pos)
        if kind == "attach":
            # move first, so the new joint is made at its rest length
            self._move_body(cell, spot, target.body.velocity)
            reattach_cell(cell, target)
        elif kind == "detach":
            self._move_body(cell, spot, (0, 0))
            detach_cell(cell)
        # "cancel" / "invalid": nothing changes -- the original links stay

    def draw_drag_preview(self):
        """While dragging: a ring on the real cell, a tether to a ghost that
        follows the cursor (snapped next to the target when attaching), and
        the ghost coloured by what a release would do."""
        drag = self.drag
        if drag is None or not drag["active"]:
            return
        cell = drag["cell"]
        if cell.is_dead:
            return
        kind, target, spot = self.resolve_drop(cell, pygame.mouse.get_pos())

        surf = self.world_surface
        zoom = self.camera.zoom
        ox, oy = self.camera.offset

        def to_screen(p):
            return p[0] * zoom + ox, p[1] * zoom + oy

        def outline(c, centre, color, pad, width):
            r = c.size * zoom + pad
            x, y = centre
            if c.has_cell_wall:
                pygame.draw.rect(surf, color, (x - r, y - r, r * 2, r * 2), width)
            else:
                pygame.draw.circle(surf, color, (x, y), r, width)

        source = to_screen(cell.body.position)
        outline(cell, source, DRAG_TETHER_COLOR, 4, 1)
        if kind == "cancel" or spot is None:
            return

        color = {"attach": DRAG_ATTACH_COLOR,
                 "detach": DRAG_DETACH_COLOR}.get(kind, DRAG_INVALID_COLOR)
        ghost = to_screen(spot)
        pygame.draw.line(surf, DRAG_TETHER_COLOR, source, ghost, 1)
        if target is not None:
            target_pos = to_screen(target.body.position)
            outline(target, target_pos, color, 4, 1)
            if kind == "attach":
                pygame.draw.line(surf, color, ghost, target_pos, 2)   # the new link
        outline(cell, ghost, color, 0, 2)

    def draw_selection_marker(self, visible):
        """A gold ring/box just outside the selected cell."""
        cell = self.selected_cell
        if cell is None or cell.is_dead or cell not in visible:
            return
        zoom = self.camera.zoom
        ox, oy = self.camera.offset
        x = cell.body.position[0] * zoom + ox
        y = cell.body.position[1] * zoom + oy
        r = cell.size * zoom + 5
        if cell.has_cell_wall:
            pygame.draw.rect(self.world_surface, GOLD, (x - r, y - r, r * 2, r * 2), 1)
        else:
            pygame.draw.circle(self.world_surface, GOLD, (x, y), r, 1)

    def on_cell_begin(self, arbiter, space, data):
        a, b = arbiter.shapes
        predator_cell = a._object
        prey_cell = b._object

        # an unwalled + walled daughter pair still pulling apart: ignore the
        # contact (no push, no contact-damage timer). Returning False from
        # begin makes pymunk ignore this pair until the shapes stop touching,
        # which is exactly when the split completes -- nothing to restore.
        if predator_cell.is_split_sibling_of(prey_cell):
            return False

        # cells of one animal organism still collide, but never hurt each
        # other (no contact-damage timer)
        if same_organism(predator_cell, prey_cell):
            return True

        predator_cell.contact_time[prey_cell] = 0.0
        return True

    def on_cell_pre_solve(self, arbiter, space, data):
        # runs every step while an unwalled cell touches a plant (a contact
        # that begin rejected, like a splitting sibling pair, never gets
        # here). Plant defence: a larger cell touching an exposed corner of
        # the plant dies -- see plant_defense.py. Not between cells of one
        # animal organism.
        a, b = arbiter.shapes
        if not same_organism(a._object, b._object):
            check_vertex_defense(a._object, b._object, arbiter)
        return True

    def on_cell_separate(self, arbiter, space, data):
        a, b = arbiter.shapes
        predator_cell = a._object
        prey_cell = b._object

        predator_cell.contact_time.pop(prey_cell, None)

    def on_walled_pair_begin(self, arbiter, space, data):
        # two walled daughters mid-split may overlap each other; every other
        # walled <-> walled contact collides as normal
        a, b = arbiter.shapes
        return not a._object.is_split_sibling_of(b._object)

    def on_animal_pair_begin(self, arbiter, space, data):
        # two unwalled cells, at least one of them in an animal organism:
        # members of the same organism collide with each other (except a
        # splitting pair, which overlaps until it separates); any other pair
        # passes through each other, like all unwalled cells always have
        a, b = arbiter.shapes
        return members_collide(a._object, b._object)

    def on_sand_begin(self, arbiter, space, data):
        # a cell just touched a sand block -- play the collision sound at the
        # cell's world position (shape order matches the handler: cell, sand)
        # and let pymunk resolve the collision normally (return True)
        cell_shape, _ = arbiter.shapes
        cell = getattr(cell_shape, "_object", None)
        position = cell.body.position if cell is not None else cell_shape.body.position
        audio.play_collide_sand(position)
        return True

    def on_solid_sand_begin(self, arbiter, space, data):
        # a cell touching the solid box of an unloaded sand chunk. It is a
        # wall from the outside; but a cell whose centre is already inside
        # (it was swimming in that chunk's water when the chunk went solid)
        # is ignored until it has left, instead of being blasted out.
        cell_shape, solid_shape = arbiter.shapes
        inside = solid_shape.point_query(cell_shape.body.position).distance < 0
        return not inside

    # ------------------------------------------------------------------
    # Audio listener
    # ------------------------------------------------------------------
    def update_audio_listener(self):
        """Tell the audio system where the player is listening from: the
        world-space centre of the camera view plus the current zoom. Called
        once per frame; all per-sound culling/attenuation reads this cache."""
        lx, ly = self.camera.world_center(WORLD_WINDOW_WIDTH, WORLD_WINDOW_HEIGHT)
        audio.set_listener(lx, ly, self.camera.zoom, WORLD_WINDOW_WIDTH / 2)

    # ------------------------------------------------------------------
    # Mutation tracking (game logic — runs in update, not in render)
    # ------------------------------------------------------------------
    def check_mutations(self):
        genome = self.player.cell.genome
        if genome is self.previous_genome:
            return

        env = self.world.get_env_features(self.player.cell.body.position)

        self.increased.clear()
        self.decreased.clear()

        max_mass = genome.max_mass - self.previous_genome.max_mass
        if max_mass > 0:
            self.increased.append("MAX MASS")
            self.journal.add_environmental_mutation("Water", "Increased Size")

        elif max_mass < 0:
            self.decreased.append("MAX MASS")
            self.journal.add_environmental_mutation("Sand", "Decreased Size")

        size = genome.size - self.previous_genome.size
        if size > 0:
            self.increased.append("SIZE")
        elif size < 0:
            self.decreased.append("SIZE")

        speed = genome.max_speed - self.previous_genome.max_speed
        if speed > 0:
            self.increased.append("SPEED")
            self.journal.add_behavioural_mutation("Eats Cells", "Speed")
        elif speed < 0:
            self.decreased.append("SPEED")

        if genome.has_cell_wall != self.previous_genome.has_cell_wall:
            if genome.has_cell_wall:
                self.increased.append("EVOLVED CELL WALL")
                self.decreased.append("CAN NO LONGER MOVE")
                self.journal.add_behavioural_mutation("Doesn't Move", "Cell Wall")

        if genome.has_chloroplast != self.previous_genome.has_chloroplast:
            if genome.has_chloroplast:
                self.increased.append("EVOLVED CHLOROPLAST")
                self.journal.add_environmental_mutation("Sunny + Cell Wall", "Chloroplast")

        # ---- JOURNAL HOOK ------------------------------------------------

        # This is where the player's real discovered mutations are detected.
        # To log them, call self.journal.add_environmental_mutation(env, mut)
        # or self.journal.add_behavioural_mutation(beh, mut). `mut` is the label
        # above (e.g. "EVOLVED CHLOROPLAST"); the pressure string comes from the
        # environment the split happened in -- get it with
        #   env = self.world.get_env_features(self.player.cell.body.position)
        # and map env.chunk_material / env.light_level / env.has_particles (see
        # Genome.mutate_gene in cell.py) to a human-readable pressure. Behaviour
        # rows pair the decision model's .name change (decision_models.py) with
        # the intelligence/behaviour gene that unlocked it. Duplicates are
        # rejected by the journal, so it's safe to call every frame.
        # ------------------------------------------------------------------

        self.previous_genome = genome

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw_stat_bar(self, player_stat, player_max_stat, stat_name, units, height, buffer=1):
        stat_width = min(player_stat, player_max_stat) * 120 / player_max_stat
        pygame.draw.rect(self.stat_box_surface, (255, 0, 0), (70, height, STAT_BOX_W - 80, 10), 1)
        pygame.draw.rect(self.stat_box_surface, (255, 0, 0), (70, height, stat_width, 10))
        stat_bar = self.font.render(stat_name + ":", True, (255, 255, 255))
        stat_fraction = self.font.render(
            f"{player_stat // buffer} {units} / {player_max_stat // buffer} {units}",
            True,
            (255, 255, 255))
        self.stat_box_surface.blit(stat_bar, (10, height))
        self.stat_box_surface.blit(stat_fraction, (100, height + 15))

    def draw_stat_text(self, stat_name, value, height):
        """A plain text stat row: label on the left, value right-aligned to
        the right edge of the stat bars (x = STAT_BOX_W - 10, see
        draw_stat_bar), so its last digit lines up with the bars below."""
        label = self.font.render(stat_name + ":", True, (255, 255, 255))
        value_text = self.font.render(str(value), True, (255, 0, 0))
        self.stat_box_surface.blit(label, (10, height))
        self.stat_box_surface.blit(value_text, value_text.get_rect(topright=(STAT_BOX_W - 10, height)))

    def draw_stat_box(self):
        self.stat_box_surface.fill(BLACK)
        cell = self.inspected_cell

        # Generation
        self.draw_stat_text("GENERATION", cell.generation, 20)

        # Mass
        self.draw_stat_bar(cell.mass, cell.max_mass, "MASS", "pg", 55)

        # Energy
        self.draw_stat_bar(cell.energy, cell.max_energy, "ENERGY", "nJ", 100, 1000)

        # OUTLINE
        pygame.draw.rect(self.stat_box_surface, BORDER, (0, 0, STAT_BOX_W, STAT_BOX_H), 1)

        self.screen.blit(self.stat_box_surface, self.stat_box_pos)

    def draw_settings_panel(self):
        # settings owns its surface + layout; it is blitted into the SAME slot
        # as the stat box, so opening it visually replaces Player Stats
        self.screen.blit(self.settings.render(), self.stat_box_pos)

    def draw_mut_box(self):
        self.mut_box_surface.fill(BLACK)
        pygame.draw.rect(self.mut_box_surface, BORDER, (0, 0, MUT_BOX_W, MUT_BOX_H), 1)

        # increases first, then decreases directly below them
        for i, name in enumerate(self.increased):
            text = self.font.render("+ " + name, True, (0, 255, 0))
            self.mut_box_surface.blit(text, (10, 25 * (i + 1)))

        for j, name in enumerate(self.decreased):
            text = self.font.render("- " + name, True, (255, 0, 0))
            self.mut_box_surface.blit(text, (10, 25 * (len(self.increased) + j + 1)))

        if not (self.increased or self.decreased):
            text = self.font.render("No New Mutations", True, (100, 100, 100))
            self.mut_box_surface.blit(text, (10, 25))

        self.screen.blit(self.mut_box_surface, ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH) // 2 + 20,
                                                (SCREEN_HEIGHT // 2) + 20))

    def set_vel_history(self, seconds):
        """Change the time window. Keeps the most recent samples."""
        self.vel_history = deque(self.vel_history,
                                 maxlen=max(2, int(seconds * VEL_SAMPLES_PER_SEC)))

    def _draw_vel_plot(self, surf, name, axis, top, height, max_speed):
        grey, dark = (100, 100, 100), (50, 50, 50)
        left, right = 10, VEL_BOX_W - 10
        hist = self.vel_history
        current = hist[-1][axis] if hist else 0.0
        secs = hist.maxlen / VEL_SAMPLES_PER_SEC

        title = self.font.render(f"{name}: {current:+.1f}", True, (255, 255, 255))
        surf.blit(title, (left, top))
        scale = self.font.render(f"{secs:.0f}s  ±{max_speed:.0f}", True, grey)
        surf.blit(scale, scale.get_rect(topright=(right, top)))

        plot_top = top + 16
        plot_bot = top + height - 6
        mid = (plot_top + plot_bot) // 2
        half = (plot_bot - plot_top) / 2

        # +max / -max guides and the zero axis
        pygame.draw.line(surf, dark, (left, plot_top), (right, plot_top))
        pygame.draw.line(surf, dark, (left, plot_bot), (right, plot_bot))
        pygame.draw.line(surf, grey, (left, mid), (right, mid))

        n = len(hist)
        if n < 2:
            return
        # newest sample pinned to the right edge; until the buffer fills,
        # the trace grows in from the right
        step = (right - left) / (hist.maxlen - 1)
        x0 = right - (n - 1) * step
        k = half / max_speed
        pts = [(x0 + i * step, mid - max(-max_speed, min(max_speed, s[axis])) * k)
               for i, s in enumerate(hist)]
        pygame.draw.aalines(surf, (0, 255, 0), False, pts)

    def draw_vel_box(self, pos):
        surf = self.vel_box_surface
        surf.fill(BLACK)
        pygame.draw.rect(surf, BORDER, (0, 0, VEL_BOX_W, VEL_BOX_H), 1)

        max_speed = max(1, self.inspected_cell.genome.speed_range[1])
        plot_h = (VEL_BOX_H - 8) // 2
        self._draw_vel_plot(surf, "VX", 0, 6, plot_h, max_speed)
        self._draw_vel_plot(surf, "VY", 1, 6 + plot_h, plot_h, max_speed)

        self.screen.blit(surf, pos)

    def draw_species_box(self):
        self.species_box_surface.fill(BLACK)
        pygame.draw.rect(self.species_box_surface, (255, 255, 255), (0, 0, SPECIES_BOX_W, SPECIES_BOX_H), 1)

        self.screen.blit(self.species_box_surface, ((SCREEN_WIDTH - WORLD_WINDOW_WIDTH) // 2 - 220,
                                                    (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) // 2))

    def draw_intel_box(self):
        surf = self.intel_box_surface
        surf.fill(BLACK)
        pygame.draw.rect(surf, BORDER, (0, 0, INTEL_BOX_W, INTEL_BOX_H), 1)

        matrix = self.inspected_cell.genome.intelligence_matrix
        grey = (100, 100, 100)

        # number line geometry: labels live left of line_left
        line_left = 55
        line_right = INTEL_BOX_W - 15
        line_w = line_right - line_left
        mid = line_left + line_w // 2

        def to_x(v):
            v = max(-1.0, min(1.0, v))
            return int(line_left + (v + 1) / 2 * line_w)

        # scale header: -1   0   +1
        for txt, x in (("-1", line_left), ("0", mid), ("+1", line_right)):
            t = self.font.render(txt, True, grey)
            surf.blit(t, t.get_rect(midtop=(x, 15)))

        top, row_h = 35, 23
        for i, (key, value) in enumerate(matrix.items()):
            y = top + i * row_h

            label = self.font.render(key.upper(), True, (255, 255, 255))
            surf.blit(label, label.get_rect(midleft=(10, y)))

            # axis + ticks at -1, 0, +1
            pygame.draw.line(surf, grey, (line_left, y), (line_right, y), 1)
            for x in (line_left, mid, line_right):
                pygame.draw.line(surf, grey, (x, y - 4), (x, y + 4), 1)

            if value > 0:
                color = (0, 255, 0)  # attraction
            elif value < 0:
                color = (255, 0, 0)  # avoidance
            else:
                color = grey  # ignored

            x = to_x(value)
            if value:
                # bar from 0 out to the value so magnitude reads at a glance
                pygame.draw.line(surf, color, (mid, y), (x, y), 3)
            pygame.draw.circle(surf, color, (x, y), 4)

        self.screen.blit(surf, ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH) // 2 + 20,
                                (SCREEN_HEIGHT // 2) - 135))

    def draw_journal(self):
        # journal owns its surface + layout; we just blit it into the left slot
        self.screen.blit(self.journal.render(), self.journal_pos)

    def _seed_journal_demo(self):
        # Placeholder rows so the panel shows something on first run. UI-only:
        # these are NOT game mechanics. Remove this method (and its call) once
        # real discovered mutations are pushed in via the hooks below.
        self.journal.add_environmental_mutation("Nutrient Poor", "Increased Detection Radius")
        self.journal.add_environmental_mutation("Sand", "Reduced Cell Size")
        self.journal.add_environmental_mutation("Low Light", "Increased Chloroplast Efficiency")
        self.journal.add_behavioural_mutation("Random Movement", "Terrain Detection")
        self.journal.add_behavioural_mutation("Terrain Avoidance", "Cell Detection")

    def visible_cells(self):
        """Cells whose shape overlaps the view, found with pymunk's spatial
        index (in C) instead of testing every cell in Python. The margin
        (world px) covers the invulnerability ring, which reaches past the
        shape's own bounding box."""
        zoom = self.camera.zoom
        ox, oy = self.camera.offset
        m = 25
        bb = pymunk.BB(-ox / zoom - m, -oy / zoom - m,
                       (WORLD_WINDOW_WIDTH - ox) / zoom + m,
                       (WORLD_WINDOW_HEIGHT - oy) / zoom + m)
        visible = set()
        for shape in self.space.bb_query(bb, pymunk.ShapeFilter()):
            cell = getattr(shape, "_object", None)   # only cell shapes have one
            if cell is None:
                continue
            visible.add(cell)
            # a mid-split pair is drawn by its lead daughter, so the lead
            # must draw when only its sibling is in view
            if cell.split_sibling is not None:
                visible.add(cell.split_sibling)
        return visible

    def draw_game_world(self):
        self.world_surface.fill(BLACK)

        with self.profiler.section("render_chunks"):
            self.world.render_chunks(self.world_surface, self.camera)

        with self.profiler.section("render_cells"):
            zoom = self.camera.zoom
            offset = self.camera.offset
            surface = self.world_surface
            visible = self.visible_cells()
            # iterate self.cells (not the query result) so draw order stays
            # stable frame to frame; a set lookup is ~50 ns per cell
            for cell in self.cells:
                if cell in visible:
                    cell.draw(surface, zoom, offset)

            if SHOW_CELL_JOINTS:
                self.draw_joints(visible)

            self.draw_selection_marker(visible)
            self.draw_drag_preview()

        # WORLD BOX
        pygame.draw.rect(self.world_surface, BORDER, (0, 0, WORLD_WINDOW_WIDTH, WORLD_WINDOW_HEIGHT), 1)

        self.screen.blit(self.world_surface,
                         ((SCREEN_WIDTH - WORLD_WINDOW_WIDTH) / 2, (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) / 2))

    def draw_joints(self, visible):
        """A thin centre-to-centre line per multicellular joint, skipped when
        both ends are off-screen. Each joint is stored on both of its cells,
        so it is drawn from one side only."""
        zoom = self.camera.zoom
        ox, oy = self.camera.offset
        for cell in self.cells:
            for neighbour in cell.joints:
                if id(cell) > id(neighbour):
                    continue
                if cell not in visible and neighbour not in visible:
                    continue
                p1 = cell.body.position
                p2 = neighbour.body.position
                pygame.draw.line(self.world_surface, cell.color,
                                 (p1.x * zoom + ox, p1.y * zoom + oy),
                                 (p2.x * zoom + ox, p2.y * zoom + oy), 1)

    def draw_fps(self):
        # screen-space: top-left of the application window, outside the world
        # viewport, so it is unaffected by camera position / zoom
        fps = self.clock.get_fps()
        fps_text = self.font.render(f"FPS: {fps:.0f}", True, (0,255,0))
        fps_rect = fps_text.get_rect(topleft=(HUD_PAD, HUD_PAD))
        # self.screen is never cleared (each panel repaints only its own box),
        # so paint a background first or successive frames stack on top of
        # each other -- same trick create_box_label / the profiler overlay use
        pygame.draw.rect(self.screen, BLACK, fps_rect.inflate(6, 4))
        self.screen.blit(fps_text, fps_rect)

    def draw_hud_chrome(self):
        """Fixed screen-space HUD: FPS counter (top-left) and the Settings tab
        (top-right). Drawn after the panels so they always sit on top."""
        #self.draw_fps()
        self.settings_tab.render(self.screen, pygame.mouse.get_pos(), self.settings.is_open)

    def create_box_label(self, text, top_left, clear_width=None):
        label = self.font.render(text, True, (0, 255, 0))
        label_rect = label.get_rect(topleft=top_left)
        # background: the screen is never cleared, so this is what erases the
        # previous frame's label. `clear_width` lets a label that changes text
        # (Player Stats <-> Settings) wipe the widest version it can show.
        clear_rect = label_rect.inflate(6, 4)
        if clear_width is not None:
            clear_rect.width = max(clear_rect.width, clear_width + 6)
        pygame.draw.rect(self.screen, BLACK, clear_rect)
        self.screen.blit(label, label_rect)

    def render(self):
        with self.profiler.section("render_world"):
            self.draw_game_world()
        with self.profiler.section("render_ui"):
            # right-hand slot: Settings replaces Player Stats while it is open
            slot_label_pos = ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH + STAT_BOX_W) // 2 - 15, 55)
            if self.settings.is_open:
                self.draw_settings_panel()
            else:
                self.draw_stat_box()
            #self.draw_mut_box()
            self.draw_intel_box()
            self.create_box_label("Intelligence Matrix",
                                  ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH + INTEL_BOX_W) // 2 - 35,
                                   SCREEN_HEIGHT // 2 - 140))
            self.draw_vel_box(((SCREEN_WIDTH + WORLD_WINDOW_WIDTH) // 2 + 20, SCREEN_HEIGHT // 2 + 100))
            self.create_box_label("Cell Velocity",
                                  ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH + INTEL_BOX_W) // 2 - 15,
                                   SCREEN_HEIGHT // 2 + 95))
            self.draw_journal()
            self.create_box_label("Game World", (SCREEN_WIDTH / 2 - 16, 55))
            if self.settings.is_open:
                slot_label = "Settings"
            elif self.selected_cell is not None and not self.selected_cell.is_dead:
                slot_label = "Cell Stats"
            else:
                slot_label = "Player Stats"
            self.create_box_label(slot_label, slot_label_pos,
                                  clear_width=self.font.size("Player Stats")[0])
            #self.create_box_label("Mutations", ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH + STAT_BOX_W) // 2 - 10, 375))
            self.create_box_label("Mutation Journal", (self.journal_pos[0] + 50, 55))
            self.draw_hud_chrome()

        # overlay on top, just below the FPS counter so the two don't collide
        self.profiler.draw_overlay(self.screen, self.font,
                                   topleft=(HUD_PAD, HUD_PAD + self.font.get_height() + 4))

        pygame.display.flip()
        self.clock.tick(60)

    def kill_cell(self, cell):
        """Remove `cell` from the game. Returns the animal organism it was a
        member of (or None) so the caller can rebuild it once all of this
        frame's deaths are in.

        A parent that just split is NOT a member of any organism any more
        (Cell.split handed its slot to its daughters), so its removal here
        never fragments or re-heads an organism -- only actual deaths do."""
        organism = cell.multicell

        # the inspected cell died: go back to showing the player
        if cell is self.selected_cell:
            self.set_selected_cell(None)

        # spawn particles for mass
        if cell.is_player:
            # free camera. If the rest of the player's organism survives,
            # process_deaths hands control to its new head right after,
            # which puts the camera back on the player.
            self.camera.type = 1
            cell.is_player = False

        if not cell.has_split:
            cell.cell_death(self.world)
        # unlink from every multicellular neighbour BEFORE the body leaves
        # the space, so no constraint is left pointing at a removed body
        remove_all_joints(cell)
        if organism is not None:
            organism.remove(cell)
        if cell.last_grid_pos is not None:
            grid_cell = self.world.get_lvl1_chunk_local_cell(cell.last_grid_pos)
            if grid_cell is not None and cell in getattr(grid_cell, "entities", ()):
                grid_cell.entities.remove(cell)
        self.cells.remove(cell)
        self.space.remove(cell.body, cell.shape)
        return organism

    def give_player_control(self, cell):
        """Hand player control to `cell` (the replacement head of the
        player's organism). Exactly one cell is ever the player."""
        cell.is_player = True
        self.player.cell = cell
        self.camera.type = 0

    def process_deaths(self, dead_cells):
        """Remove this frame's dead cells, then rebuild every animal organism
        that lost a member -- once each, however many members it lost -- so
        every surviving connected group has its own Multicell, head and
        tails. If the player's head died, control goes to the head of the
        component that kept the original organism (the largest one)."""
        broken = {}                   # organisms that lost members (ordered set)
        player_organism = None
        for cell in dead_cells:
            if cell not in self.cells:
                continue
            was_player = cell.is_player
            organism = self.kill_cell(cell)
            if organism is not None:
                broken[organism] = None
                if was_player:
                    player_organism = organism

        for organism in broken:
            survivors = organism.rebuild()
            if organism is player_organism and survivors:
                self.give_player_control(survivors[0].head)

    def cull_for_fps(self):
        """Population control: if the frame rate has dropped below
        FPS_CULL_THRESHOLD, mark one random non-player cell as dead. It then
        goes through the normal death path later this same update (dropped
        particles, kill_cell), exactly like a starved cell."""
        fps = self.clock.get_fps()
        # get_fps() averages the last 10 frames and reads 0 until it has them,
        # so 0 means "not measured yet", not "slow"
        if fps == 0 or fps >= FPS_CULL_THRESHOLD or sim_clock.now < self.next_fps_cull:
            return
        candidates = [cell for cell in self.cells if not cell.is_player and not cell.is_dead]
        if candidates:
            random.choice(candidates).is_dead = True
            self.next_fps_cull = sim_clock.now + FPS_CULL_COOLDOWN

    def respawn_particles(self, dt):
        """Regrow food in every food chunk of the world, on the same
        distance rings as the cells: chunks near the player every frame,
        further rings every 2nd, 4th, ... frame with dt scaled to match.
        (With SIM_LOD off, only the loaded chunks regrow, every frame.)"""
        center = self.world.center_chunk if SIM_LOD else None
        if center is None:
            chunks = [self.world.lvl1chunks[k] for k in self.world.loaded_lvl1chunks]
        else:
            chunks = self.world.food_chunks()
        for lvl1chunk in chunks:
            if not lvl1chunk.has_particles or not lvl1chunk.water_cells:
                continue
            steps = 1 if center is None else self.chunk_interval(lvl1chunk.wx, lvl1chunk.wy, center)
            if steps > 1 and (self.frame + lvl1chunk.update_phase) % steps:
                continue
            for grid_cell in lvl1chunk.respawn_particles(dt * steps, PARTICLE_RESPAWN_RATE):
                self.world.mark_food_changed((grid_cell.wx, grid_cell.wy))

    def chunk_interval(self, cx, cy, center):
        """Frames between updates for something in lvl1 chunk (cx, cy):
        every frame within SIM_LOD_FULL_RADIUS rings of the player's chunk,
        then 2, 4, 8, ... up to SIM_LOD_MAX_INTERVAL."""
        ring = max(abs(int(cx) - center[0]), abs(int(cy) - center[1]))
        if ring <= SIM_LOD_FULL_RADIUS:
            return 1
        return min(1 << (ring - SIM_LOD_FULL_RADIUS), SIM_LOD_MAX_INTERVAL)

    def update_interval(self, cell, center):
        """How many frames apart this cell's per-cell logic runs, from its
        distance in lvl1 chunks (rings) to the player's chunk: every frame
        inside SIM_LOD_FULL_RADIUS, then 2, 4, 8, ... up to
        SIM_LOD_MAX_INTERVAL. The player and freshly spawned cells always
        run every frame."""
        if center is None or cell.is_player or cell.last_grid_pos is None:
            return 1
        gx, gy = cell.last_grid_pos
        return self.chunk_interval(gx // LVL1_CHUNK_SIZE, gy // LVL1_CHUNK_SIZE, center)

    def update(self):
        dt = 1 / 60
        v = self.inspected_cell.body.velocity
        self.vel_history.append((v.x, -v.y))

        # simulated time, advanced by the same fixed dt as the physics step.
        # Cell.invulnerable_until is stamped against this clock.
        sim_clock.tick(dt)
        self.frame += 1

        # too slow? thin the population by one random non-player cell
        #self.cull_for_fps()

        with self.profiler.section("physics"):
            # refresh the audio listener BEFORE physics so the sand-collision
            # callbacks fired inside space.step() are judged against this
            # frame's camera position/zoom
            self.update_audio_listener()
            self.space.step(dt)
            if self.camera.type == 1:
                self.camera.update(width=WORLD_WINDOW_WIDTH, height=WORLD_WINDOW_HEIGHT)

        with self.profiler.section("respawn"):
            self.respawn_particles(dt)

        with self.profiler.section("sim_loop"):
            new_cells = []
            dead_cells = []
            center = self.world.center_chunk if SIM_LOD else None
            for cell in self.cells:
                # distance-based update rate: far cells only run this loop
                # every `steps` frames (staggered), and everything
                # time-based below is scaled by `steps` so they keep pace
                steps = self.update_interval(cell, center)
                if steps > 1 and (self.frame + cell.update_phase) % steps:
                    if cell.is_dead:            # killed by someone else
                        dead_cells.append(cell)
                    continue
                cdt = dt * steps

                self.world.update_entity(cell, cdt)

                # EnvFeatures is only consumed by split() and photosynthesis, so
                # build it lazily instead of once per cell per frame. (Phase 1 opt)
                # A cell that is still pulling apart from its sibling can't
                # start another split.
                will_split = (cell.mass >= cell.max_mass and cell.energy >= cell.max_energy
                              and not cell.is_splitting and not cell.is_dead)
                env = None
                if will_split:
                    env = self.world.get_env_features(cell.body.position)
                elif cell.has_chloroplast or cell.is_fungi:
                    # plants (photosynthesis) and fungi (decomposition) read
                    # their environment; cached until they change grid cell
                    if cell._env_grid_pos != cell.last_grid_pos:
                        cell._env = self.world.get_env_features(cell.body.position)
                        cell._env_grid_pos = cell.last_grid_pos
                    env = cell._env

                # player funcs
                if cell.is_player:
                    self.player.cell = cell
                    self.world.process(cell.body.position, self.space)

                    if cell.multicellular and cell.multicell is not None:
                        size = 0
                        i = 0
                        for unit in cell.multicell.cells:
                            size += ((unit.size-i)**2)
                            i += 1
                        target_zoom = max(20/(math.sqrt(size)), 0.5)

                    else:
                        target_zoom = 20/cell.size

                    #Smoothly interpolate toward target zoom
                    smoothing = 0.1
                    self.camera.zoom += (target_zoom - self.camera.zoom) * smoothing
                    # Snap to target when sufficiently close
                    if abs(target_zoom - self.camera.zoom) < 0.001:
                        self.camera.zoom = target_zoom

                    self.camera.update(cell.body, WORLD_WINDOW_WIDTH, WORLD_WINDOW_HEIGHT)

                elif not cell.is_splitting and not cell.has_cell_wall:
                    head = steering_head(cell)
                    if head is None:
                        # AI re-decides every AI_DECISION_INTERVAL frames,
                        # staggered across cells; in between it keeps moving
                        # along its last chosen direction
                        if (cell.ai_direction is None or steps >= AI_DECISION_INTERVAL
                                or (self.frame + cell.update_phase) % AI_DECISION_INTERVAL == 0):
                            cell.ai_direction = cell.decide()
                        cell.apply_movement(cell.ai_direction, steps)
                    elif (head is not None and not head.is_player
                          and head.ai_direction is not None):
                        # body cell of an AI organism: only the head decides;
                        # this cell swims the way the head chose (the
                        # player's body cells get the keys in handle_inputs)
                        cell.apply_movement(head.ai_direction, steps)

                # mitosis: a splitting daughter slides away from its sibling
                # until the two no longer overlap (input / AI are paused for
                # it until then -- see Cell.update_split)
                if cell.is_splitting:
                    cell.update_split(cdt)

                # cell reproduction (children spawn into new_cells)
                if will_split:
                    cell.split(self.space, new_cells, env, self.world)
                    # a selected cell that divides: follow daughter 1 (the
                    # same lineage rule the player follows); keep its graph
                    if cell is self.selected_cell and cell.has_split:
                        self.selected_cell = new_cells[-2]

                # gain energy: eat nearby particles. Food nearby changed ->
                # rebuild the list from the grid. Walled cells (plants, fungi)
                # otherwise only re-check once they've drifted a little;
                # moving cells check every update.
                px, py = cell.body.position
                check = True
                if cell.food_changed:
                    cell.refresh_nearby_particles(self.world)
                    cell.food_changed = False
                elif cell.has_cell_wall and cell.food_check_pos is not None:
                    lx, ly = cell.food_check_pos
                    check = (px - lx) * (px - lx) + (py - ly) * (py - ly) > FOOD_RECHECK_DISTANCE_SQ
                if check:
                    cell.food_check_pos = (px, py)
                    if cell.nearby_particles:
                        r2 = cell.size * cell.size
                        hits = [p for p in cell.nearby_particles
                                if not p.eaten and (p.x - px) * (p.x - px) + (p.y - py) * (p.y - py) <= r2]
                        for particle in hits:
                            cell.consume_particle(particle, self.to_remove_particles)

                # gain energy: photosynthesis
                if cell.has_chloroplast and env is not None and env.in_water:
                    rates = PHOTOSYNTHESIS_RATES.get(cell.color, {})
                    cell.add_energy(rates.get(env.light_level, 0) * steps)

                # gain energy: decomposition
                if cell.is_fungi and env is not None and env.chunk_material == MATERIAL_SAND and env.has_particles:
                    cell.add_energy(100*steps)

                # aging: fixed energy drain every second, independent of mass
                cell.age(cdt)

                # death by starvation
                if cell.energy <= 0:
                    cell.is_dead = True

                # death by starvation
                if cell.energy <= 0:
                    cell.is_dead = True

                # death by contact
                for other in cell.contact_time:
                    if other.is_invulnerable():
                        # can't be hurt right now: hold the timer at zero so
                        # it doesn't die the instant its protection ends
                        cell.contact_time[other] = 0.0
                        continue
                    cell.contact_time[other] += cdt
                    cell.total_contact_time += cdt
                    if other.genome.is_fungi:
                        if cell.contact_time[other] >= 0.5:
                            other.kill(cell)
                    else:
                        if cell.contact_time[other] >= 0.3:
                            other.kill(cell)

                # death by consumption
                for entity in cell.nearby_entities:
                    # only a strictly smaller, unwalled cell can be swallowed
                    if entity.size < cell.size and not entity.has_cell_wall:
                        cell.consume_cell(entity)

                if cell.is_dead:
                    dead_cells.append(cell)

            # apply deferred list changes
            self.cells.extend(new_cells)

        with self.profiler.section("deaths"):
            # actual deaths only: remove the cells, then fragment / re-head
            # the animal organisms they belonged to (see process_deaths)
            self.process_deaths(dead_cells)

        with self.profiler.section("post"):
            self.check_mutations()
            for particle in self.to_remove_particles:
                gx, gy = particle.x // CELL_SIZE, particle.y // CELL_SIZE
                cell = self.world.get_lvl1_chunk_local_cell((gx, gy))

                if cell is not None and hasattr(cell, "particles") and particle in cell.particles:
                    cell.particles.remove(particle)
                    self.world.mark_food_changed((gx, gy))

            self.to_remove_particles.clear()

    def main_game_loop(self):
        # start the looping background soundtrack once, as the game begins
        audio.play_music()
        while self.running:
            self.handle_inputs()
            self.profiler.maybe_deep_profile(self.update)  # was: self.update()
            self.render()
            self.profiler.frame()  # <-- once per frame

            if len(self.cells) != self.previous_cell_length:
                print("Amount of cells:", len(self.cells))
                self.previous_cell_length = len(self.cells)
        pygame.quit()

if __name__ == "__main__":
    # in a windowed PyInstaller build there is no console: send prints and
    # tracebacks to 2dverse.log next to the exe (no-op when run from source)
    redirect_output_when_frozen()
    game = Game()
    game.main_game_loop()
