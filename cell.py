import copy
import uuid

import pygame
import math
import random

from pymunk import Vec2d

from colors import BLACK, LIME, ORANGE, RED, FUNGI, LIGHT_BLUE, MAGENTA, MED_LIGHT_RED
from env_features import EnvFeatures
from physics_object import *
from world_grid import WaterCell, Particle
from decision_models import create_decision_model
from multicell import (begin_multicellular_split, finish_multicellular_split,
                       growth_direction, is_multicellular_walled, remove_all_joints,
                       animal_growth_direction, adopt_daughters, same_organism)
from audio import audio
from sim_clock import sim_clock
from global_constants import *

# Cell life-cycle states:  normal -> splitting -> normal (+ invulnerability)
# A freshly split daughter is "splitting" until it no longer overlaps its
# sibling (see Cell.update_split); every other cell is "normal".
CELL_STATE_NORMAL = "normal"
CELL_STATE_SPLITTING = "splitting"

# The gap must grow by at least this much (px) per frame to count as progress.
_SPLIT_PROGRESS_EPSILON = 0.01

# ----------------------------------------------------------------------
# Speed colour gradient (see Genome.speed_color)
# ----------------------------------------------------------------------
# A cell's colour is blended between these stops by its genome.max_speed.
# Each entry is (max_speed, (r, g, b)), listed from slowest to fastest.
# Change a colour or a speed here; you can also add or remove stops.
# Speeds below the first stop / above the last use that stop's colour.
SPEED_SLOW_COLOR = LIGHT_BLUE        # (36, 159, 222)
SPEED_MID_COLOR = MAGENTA            # (188, 74, 155)  <- swap this freely
SPEED_FAST_COLOR = MED_LIGHT_RED     # (223, 62, 35)

SPEED_COLOR_STOPS = [
    (20,  SPEED_SLOW_COLOR),
    (40,  SPEED_MID_COLOR),
    (120, SPEED_FAST_COLOR),
    (240, (255,255,255))
]


class Genome:
    def __init__(self, max_mass=20, acceleration=40, max_speed=40, efficiency_factor=1, intelligence = -1, terrain_avoidance = 0.1):
        self.acceleration = acceleration
        self.max_speed = max_speed
        self.max_mass = max_mass
        self.size = max_mass // 2

        self.efficiency_factor = efficiency_factor

        self.mutation_rate = 0.25

        # visual traits
        self.color = (255, 255, 255)

        # boolean mutations
        self.has_cell_wall = False
        self.has_chloroplast = False
        self.is_fungi = False

        # hard coded bounds
        # max_mass 10 -> 80
        self.mass_range = [20, 80]
        # max_speed 20 -> 240
        self.speed_range = [20, 240]
        # max_size 5 -> 40
        self.size_range = [10,40]

        # intelligence: which decision model this organism uses (0 = random
        # walk). Emerges under scarcity in mutate_gene, not handed out for free.
        self.intelligence = intelligence
        # level 1 intelligence features
        self.terrain_avoidance = terrain_avoidance
        self.intelligence_range = [-1, 4]  # 3 == Level 3A, 4 == Level 3B

        # social genes (only consulted once the matching model is unlocked)
        self.intelligence_matrix = {"p0": 0.0, "p1": 0.0, "p2": 0.0, "p3" : 0.0, "sc": 0.0, "bc": 0.0, "spc": 0.0, "bepc": 0.0 }
        self.cell_attraction = 0.0  # 3A: single toward/away, [-1, 1]
        self.smaller_cell_attraction = 0.0  # 3B: response to smaller cells
        self.larger_cell_attraction = 0.0  # 3B: response to larger cells
        self.wall_cell_attraction = 0.0

        #multicularity
        self.multicellular = False

        self.update_speed_color()

    # --- speed colour ------------------------------------------------------
    def speed_color(self):
        """The colour for this genome's max_speed, blended linearly between
        the two SPEED_COLOR_STOPS (top of this file) on either side of it."""
        speed = self.max_speed
        stops = SPEED_COLOR_STOPS
        if speed <= stops[0][0]:
            return tuple(stops[0][1])
        for (s0, c0), (s1, c1) in zip(stops, stops[1:]):
            if speed <= s1:
                f = (speed - s0) / (s1 - s0) if s1 > s0 else 1.0
                return tuple(round(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))
        return tuple(stops[-1][1])

    def update_speed_color(self):
        """Set self.color from max_speed. Plants and fungi keep their own
        colours: photosynthesis rates are looked up by colour (see
        PHOTOSYNTHESIS_RATES in main.py)."""
        if not (self.has_chloroplast or self.is_fungi):
            self.color = self.speed_color()

    def mutate_gene(self, env: EnvFeatures, cell):
        """Mutate this genome based on the environment (env) and the parent
        cell's lifetime state (movement history, diet)."""

        # mutate size: size increases in less material dense areas, and decreases in more material dense areas
        if env.chunk_material == 1:
            if random.random() < self.mutation_rate or ((cell.is_player or (cell.multicell is not None and cell.multicell.is_player)) and cell.generation % 4 == 0):
                # self.size += random.choice([1, 2, 3, 4])
                # self.size = max(self.size_range[0], min(self.size, self.size_range[1]))
                self.max_mass += random.choice([2, 4, 6, 8])
                self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))
                self.size = self.max_mass//2

        if env.chunk_material == 2:
            if not self.has_cell_wall:
                if random.random() < self.mutation_rate or ((cell.is_player or (cell.multicell is not None and cell.multicell.is_player)) and cell.generation % 3 == 0):
                    # self.size -= random.choice([1, 2, 3, 4])
                    # self.size = max(self.size_range[0], min(self.size, self.size_range[1]))
                    self.max_mass -= random.choice([2, 4, 6, 8])
                    self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))
                    self.size = self.max_mass//2
            if self.has_cell_wall and not self.has_chloroplast:
                if random.random() < 2*self.mutation_rate:
                    self.is_fungi = True
                    self.color = FUNGI

        # TODO: Add less particles to less nutrient dense areas, so cells can still eat and mutate within them
        #  For now lets just leave mass and size coupled
        # mutate mass: mass decreases in less nutrient dense areas, and increases in more nutrient dense areas.
        # if env.has_particles:
        #     if random.random() < self.mutation_rate:
        #         self.max_mass += random.choice([2, 4, 6, 8])
        #         self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))
        #
        #
        # if not env.has_particles:
        #     if random.random() < self.mutation_rate:
        #         self.max_mass -= random.choice([2, 4, 6, 8])
        #         self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))

        # mutate speed: each type-1 particle eaten is a chance at more speed
        for _ in range(cell.amt_type1_particles):
            if random.random() < self.mutation_rate:
                self.max_speed = min(self.max_speed + 5, self.speed_range[1])
            # if random.random() < self.mutation_rate and env.chunk_material != 2:
            #     self.max_mass += random.choice([2, 4, 6, 8])
            #     self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))
            #     self.size = self.max_mass // 2

        for _ in range(cell.amt_type2_particles):
            if random.random() < self.mutation_rate:
                self.max_speed = max(self.max_speed - 5, self.speed_range[0])
            if random.random() < self.mutation_rate:
                self.max_mass -= random.choice([2, 4, 6, 8])
                self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))
                self.size = self.max_mass // 2

        self.acceleration = self.max_speed

        # mutate cell wall: only cells that never moved can evolve one
        if not cell.has_moved and not cell.multicellular:
            if random.random() < self.mutation_rate:
                self.has_cell_wall = True

        # mutate chloroplast: needs a wall, water, and bright light
        # (light_level >= 4 replaces the old hardcoded c2y == 8 check)
        if self.has_cell_wall and not (self.has_chloroplast or self.is_fungi):
            if env.in_water and env.light_level >= 4:
                if random.random() < self.mutation_rate:
                    self.has_chloroplast = True
                    self.color = LIME

        # algae color adapts to depth, mirroring real light absorption:
        # green near the surface, brown mid-depth, red in the deep
        if self.has_chloroplast:
            if env.depth in (8, 9):
                if random.random() < self.mutation_rate:
                    self.color = LIME

            elif env.depth in (10, 11):
                if random.random() < self.mutation_rate:
                    self.color = ORANGE

            elif 12 <= env.depth <= 15:
                if random.random() < self.mutation_rate:
                    self.color = RED

        # mutate intelligence attractions
        if cell.amt_type0_particles > 0:
            for _ in range(cell.amt_type0_particles):
                if random.random() < self.mutation_rate:
                    pass
                    #self.intelligence_matrix["p0"] += 0.01
        if cell.amt_type1_particles  > 0:
            for _ in range(cell.amt_type1_particles):
                # if random.random() < self.mutation_rate:
                #     self.intelligence_matrix["p0"] -= 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["p1"] += 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["p2"] -= 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["sc"] += 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["bepc"] -= 0.1
        if cell.amt_type2_particles > 0:
            for _ in range(cell.amt_type2_particles):
                # if random.random() < self.mutation_rate:
                #     self.intelligence_matrix["p0"] -= 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["p1"] -= 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["p2"] += 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["sc"] -= 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["bepc"] += 0.1
        if cell.amt_type3_particles > 0:
            for _ in range(cell.amt_type3_particles):
                # if random.random() < self.mutation_rate:
                #     self.intelligence_matrix["p0"] -= 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["p3"] += 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["bc"] -= 0.1
                if random.random() < self.mutation_rate:
                    self.intelligence_matrix["spc"] -= 0.1

        for key, value in self.intelligence_matrix.items():
            self.intelligence_matrix[key] = max(-1.0, min(1.0, value))

        # multicellularity
        if len(cell.nearby_entities) > 3:
            for i in range(len(cell.nearby_entities)):
                if random.random() < self.mutation_rate:
                    self.multicellular = True

        for _ in range(cell.amt_type3_particles):
            if random.random() < 2*self.mutation_rate:
                self.multicellular = True

        # colour follows the (possibly mutated) speed
        self.update_speed_color()

class Cell:
    def __init__(self, position: tuple, genome: Genome, is_player=False):
        self.mass = genome.max_mass / 2
        self.max_mass = genome.max_mass
        self.energy = 5000 * self.mass
        self.max_energy = 5000 * self.max_mass
        self.size = genome.size
        self.acceleration = genome.acceleration
        self.max_speed = genome.max_speed
        self.efficiency_factor = genome.efficiency_factor
        self.generation = 1

        # visual traits
        self.color = genome.color

        self.genome = genome
        self.decision_model = create_decision_model(genome)
        if self.genome.intelligence == 0:
            self.max_energy += 5000
        elif self.genome.intelligence == 1:
            self.max_energy += 50000
        elif self.genome.intelligence == 2:
            self.max_energy += 500000
        elif self.genome.intelligence == 3:
            self.max_energy += 50000

        # world tracking
        self.last_chunk_pos = None
        self.last_grid_pos = None
        self.grid_physics = None      # 'air' / 'surface' / None, set by World.update_entity
        self.neighboring_grid_cells = []

        # food
        self.nearby_particles = []
        self.nearby_entities = []
        self.food_changed = False     # set by World.mark_food_changed
        self.food_check_pos = None    # where food was last checked (None = check now)
        self.amt_type0_particles = 0
        self.amt_type1_particles = 0
        self.amt_type2_particles = 0
        self.amt_type3_particles = 0

        # booleans
        self.is_dead = False
        self.has_split = False
        self.is_player = is_player
        self.has_moved = False

        # mutation booleans
        self.has_cell_wall = genome.has_cell_wall
        self.has_chloroplast = genome.has_chloroplast
        self.is_fungi = genome.is_fungi
        self.multicellular = genome.multicellular

        # physics
        self.body, self.shape = init_cell_physics(
            self.mass, self.size, position, self.has_cell_wall
        )
        self.shape._object = self

        self._env = None
        self._env_grid_pos = None
        self.ai_direction = None          # last decision-model output (see main.py)
        self.ai_target = None
        # random offset that staggers AI re-decisions and distance-based
        # (level of detail) updates across cells, so they don't all land on
        # the same frame
        self.update_phase = random.randrange(1 << 16)

        # multicellular links: {neighbour Cell: pymunk.PinJoint}. The same
        # joint object is stored on both cells (see multicell.py).
        self.joints = {}

        # animal organism this cell belongs to (multicell.Multicell), or None
        # for a cell that has never been part of one (and for plants / fungi).
        # Set and cleared only by Multicell -- see multicell.py.
        self.multicell = None

        # object tracking
        self.id = uuid.uuid4()
        self.contact_time = {}
        self.total_contact_time = 0

        # split state machine (see "Splitting" section below)
        self.state = CELL_STATE_NORMAL
        self.split_sibling = None             # the other daughter, while splitting
        self.split_is_lead = False            # render only: the lead draws the fused pair
        self.split_direction = (0.0, 0.0)     # unit vector this daughter slides along
        self.split_exit_speed = SPLIT_SPEED   # speed it eases toward as the gap opens
        self.split_elapsed = 0.0
        self.split_best_distance = 0.0        # widest gap so far (stall detection)
        self.split_stall_time = 0.0
        self.split_joins = False              # multicellular: join the pair when done

        # sim_clock time until which other organisms can't hurt this cell
        self.invulnerable_until = 0.0
        # aging timer: seconds since the last aging drain (see age)
        self.aging_timer = 0.0

    # ------------------------------------------------------------------
    # Energy
    # ------------------------------------------------------------------
    def add_energy(self, amount):
        """Single place where energy changes, so max_energy is always
        respected. Negative amounts spend energy (starvation is checked
        against <= 0 in the game loop)."""
        self.energy = min(self.energy + amount, self.max_energy)

    def age(self, dt):
        """Aging: subtract a fixed AGING_DRAIN once every AGING_TICK seconds.
        dt is this cell's update step (larger for far-away cells), so the
        timer keeps real pace at any update rate. Fixed amount: mass, size
        and genome don't change it."""
        self.aging_timer += dt
        while self.aging_timer >= AGING_TICK:
            self.aging_timer -= AGING_TICK
            self.add_energy(-AGING_DRAIN)

    def _movement_cost(self):
        return (self.mass * self.acceleration * self.efficiency_factor) * 1/60

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle_input(self, events, keys):

        # disable movement if the cell has a cell wall, or while it is still
        # pulling apart from its sibling (update_split owns velocity then)
        if not self.has_cell_wall and not self.is_splitting:
            # this should create a glitch in some cases where when you add the velocity the cell
            # reaches a greater speed than its max_speed
            # for now we call this a feature, not a bug
            if keys[pygame.K_a]:
                if self.body.velocity.x > -self.max_speed:
                    self.body.velocity = self.body.velocity.x - self.acceleration, self.body.velocity.y
                else:
                    self.body.velocity = -self.max_speed, self.body.velocity.y

                self.add_energy(-self._movement_cost())
                self.has_moved = True

            if keys[pygame.K_d]:
                if self.body.velocity.x < self.max_speed:
                    self.body.velocity = self.body.velocity.x + self.acceleration, self.body.velocity.y
                else:
                    self.body.velocity = self.max_speed, self.body.velocity.y

                self.add_energy(-self._movement_cost())
                self.has_moved = True

            if keys[pygame.K_w]:
                if self.body.velocity.y > -self.max_speed:
                    self.body.velocity = self.body.velocity.x, self.body.velocity.y - self.acceleration
                else:
                    self.body.velocity = self.body.velocity.x, -self.max_speed

                self.add_energy(-self._movement_cost())
                self.has_moved = True

            if keys[pygame.K_s]:
                if self.body.velocity.y < self.max_speed:
                    self.body.velocity = self.body.velocity.x, self.body.velocity.y + self.acceleration
                else:
                    self.body.velocity = self.body.velocity.x, self.max_speed

                self.add_energy(-self._movement_cost())
                self.has_moved = True


        # (the K "kill my cell" debug key was removed for the alpha release)
        if keys[pygame.K_k]:
            self.is_dead = True
    def dist_sq(self, obj):
        pos = self.body.position
        if isinstance(obj, Particle):
            dx = obj.x - pos.x
            dy = obj.y - pos.y
        elif isinstance(obj , Cell):
            dx = obj.body.position.x - pos.x
            dy = obj.body.position.y - pos.y
        else:
            dx = float("inf")
            dy = float("inf")
        return dx * dx + dy * dy

    # --- intelligence-matrix decision model -------------------------------
    _SWITCH_MARGIN = 1.25  # a new target must score 25% better to steal focus
    _ARRIVE_RADIUS = 2.0  # x own size: start easing off inside this

    def _gene_for(self, obj):
        """Which intelligence_matrix gene applies to this object, or None."""
        m = self.genome.intelligence_matrix
        if isinstance(obj, Particle):
            return m.get(f"p{obj.type}")
        if obj is self or obj.is_dead or same_organism(self, obj):
            return None
        if obj.has_cell_wall:
            return m["spc"] if obj.size < self.size else m["bepc"]
        if obj.size < self.size:
            return m["sc"]
        if obj.size > self.size:
            return m["bc"]
        return None  # same-size unwalled cells: no gene yet

    def _score(self, obj):
        gene = self._gene_for(obj)
        if not gene:  # None or 0.0 -> ignored
            return 0.0, 0
        d2 = self.dist_sq(obj) + 1.0  # +1 avoids div-by-zero on contact
        return abs(gene) / d2, (1 if gene > 0 else -1)

    def decide(self):
        best, best_score, best_sign = None, 0.0, 0
        for obj in (*self.nearby_entities, *self.nearby_particles):
            if isinstance(obj, Particle) and obj.eaten:
                continue
            score, sign = self._score(obj)
            if score > best_score:
                best, best_score, best_sign = obj, score, sign

        # hysteresis: keep the current target unless the new one is clearly better
        current = getattr(self, "ai_target", None)
        if current is not None and current is not best:
            cur_score, cur_sign = self._score(current)
            still_there = cur_score > 0 and not getattr(current, "eaten", False)
            if still_there and cur_score * self._SWITCH_MARGIN >= best_score:
                best, best_sign = current, cur_sign
        self.ai_target = best

        if best is None:
            # nothing worth reacting to: keep drifting the way we were going
            v = self.body.velocity
            if v.length > 1:
                return v.normalized()
            a = random.uniform(0, 2 * math.pi)
            return Vec2d(math.cos(a), math.sin(a))

        tx, ty = (best.x, best.y) if isinstance(best, Particle) else best.body.position
        offset = Vec2d(tx - self.body.position.x, ty - self.body.position.y)
        dist = offset.length
        if dist < 1e-6:
            return Vec2d(0, 0)
        direction = offset / dist * best_sign  # unit, toward (+) or away (-)

        # arrival: ease thrust when closing on something we're attracted to
        if best_sign > 0:
            arrive = self.size * self._ARRIVE_RADIUS
            if dist < arrive:
                direction *= dist / arrive
        return direction

    def apply_movement(self, direction, steps=1):
        """
        Apply movement along one axis at a time,
        preserving existing velocity on the other axis.
        """
        if self.has_cell_wall or self.is_splitting:
            return

        dx, dy = direction
        if dx == 0 and dy == 0:
            return

        vx, vy = self.body.velocity
        acceleration = self.acceleration * steps
        # Determine which axis to accelerate along
        if abs(dx) >= abs(dy):
            vx += math.copysign(acceleration, dx)
        else:
            vy += math.copysign(acceleration, dy)

        # Enforce maximum speed
        vx = max(-self.max_speed, min(self.max_speed, vx))
        vy = max(-self.max_speed, min(self.max_speed, vy))

        self.body.velocity = (vx, vy)
        self.add_energy(-self._movement_cost() * steps)
        self.has_moved = True

    # ------------------------------------------------------------------
    # World queries
    # ------------------------------------------------------------------
    def get_neighbor_grid_cells(self):
        gx, gy = self.last_grid_pos

        return [
            (gx + dx, gy + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        ]

    def get_nearby_objects(self, world):
        for gx, gy in self.neighboring_grid_cells:
            cell = world.get_lvl1_chunk_local_cell((gx, gy))
            if cell and isinstance(cell, WaterCell):
                self.nearby_particles.extend(cell.particles)
                self.nearby_entities.extend(cell.entities)

    # ------------------------------------------------------------------
    # Eating
    # ------------------------------------------------------------------
    def refresh_nearby_particles(self, world):
        """Rebuild the food list from the grid (after food nearby changed),
        so eaten particles drop out and new ones show up."""
        self.nearby_particles.clear()
        for gx, gy in self.neighboring_grid_cells:
            cell = world.get_lvl1_chunk_local_cell((gx, gy))
            if cell and isinstance(cell, WaterCell):
                self.nearby_particles.extend(cell.particles)

    def consume_particle(self, particle, removal_list):
        dx = particle.x - self.body.position.x
        dy = particle.y - self.body.position.y

        if dx * dx + dy * dy <= self.size * self.size:
            self.add_energy(1000 * particle.multiplier)
            if self.has_cell_wall:
                self.mass += 1 * particle.multiplier
            else:
                self.mass += 1 * particle.multiplier
            if self.mass >= self.max_mass:
                self.mass = self.max_mass
                self.add_energy(4000 * particle.multiplier)

            particle.eaten = True
            removal_list.append(particle)
            # spatial: heard only if this cell is within the listener's radius
            audio.play_eat_particle(self.body.position)
            if particle in self.nearby_particles:
                self.nearby_particles.remove(particle)
            if particle.type == 0:
                self.amt_type0_particles += 1
            if particle.type == 1:
                self.amt_type1_particles += 1
            if particle.type == 2:
                self.amt_type2_particles += 1
            if particle.type == 3:
                self.amt_type3_particles += 1

    def consume_cell(self, cell):
        if cell is self:
            return
        # an organism never eats its own cells
        if same_organism(self, cell):
            return
        # splitting / freshly split cells can't be eaten (this is also what
        # stops overlapping daughters from swallowing each other)
        if not cell.has_cell_wall and not cell.is_invulnerable():
            dx = cell.body.position.x - self.body.position.x
            dy = cell.body.position.y - self.body.position.y

            d_squared = dx ** 2 + dy ** 2
            # within cell radius
            if d_squared + cell.size ** 2 <= self.size ** 2:
                # guard so the sound fires once, on the frame of the kill,
                # not again while the prey waits to be removed
                if not cell.is_dead:
                    audio.play_eat_cell(cell.body.position)
                cell.kill(self)

    # TODO: Turn INTO MUTATION
    def convert_mass_to_energy(self):
        self.mass -= 1
        self.add_energy(5000)
        if self.mass <= 0:
            self.is_dead = True

    # ------------------------------------------------------------------
    # Damage
    # ------------------------------------------------------------------
    def is_invulnerable(self):
        """True while other organisms can't hurt this cell: for the whole
        splitting state, then until invulnerable_until (stamped when the
        separation finishes). Starvation and the player's own K key are not
        attacks, so they ignore this."""
        return self.is_splitting or sim_clock.now < self.invulnerable_until

    def kill(self, attacker=None):
        """The ONE place another organism kills this cell. Every predation /
        contact-damage path must go through here (never set is_dead directly)
        so invulnerability is respected everywhere. Returns True if it died."""
        if self.is_invulnerable():
            return False
        self.is_dead = True
        return True

    # ------------------------------------------------------------------
    # Reproduction / death
    # ------------------------------------------------------------------
    def split(self, space, cell_list, env: EnvFeatures, world=None):
        # clone genome, mutating each child based on the local environment
        new_genome1 = copy.deepcopy(self.genome)
        new_genome2 = copy.deepcopy(self.genome)
        new_genome1.mutate_gene(env, self)
        new_genome2.mutate_gene(env, self)

        # split axis: the parent's direction of travel, captured before the
        # parent is replaced. A parent that is (nearly) at rest has no
        # direction, so pick a random one and the pair can still separate.
        parent_vx, parent_vy = self.body.velocity.x, self.body.velocity.y
        parent_speed = math.hypot(parent_vx, parent_vy)
        if parent_speed >= SPLIT_MIN_PARENT_SPEED:
            direction = (parent_vx / parent_speed, parent_vy / parent_speed)
        else:
            parent_speed = 0.0
            angle = random.uniform(0, 2 * math.pi)
            direction = (math.cos(angle), math.sin(angle))

        # spawn cells: child 1 inherits player control. Both daughters start
        # exactly where the parent was, so on screen they still read as one
        # cell; update_split then slides them apart.
        position = (self.body.position.x, self.body.position.y)
        new_cell1 = Cell(position, new_genome1, self.is_player)
        new_cell2 = Cell(position, new_genome2, False)

        # configure cell pymunk settings
        space.add(new_cell1.body, new_cell1.shape)
        space.add(new_cell2.body, new_cell2.shape)

        if self.multicellular or self.multicell is not None:
            # multicellular division: same mitosis animation, but daughter 1
            # stays in the parent's place (and takes over its links) while
            # daughter 2 slides out along the velocity axis; the two are
            # joined when their edges meet (see multicell.py / update_split)
            # plants grow along their velocity, fungi toward their own local
            # food gradient (see multicell.growth_direction); the rest of
            # the division is shared
            if is_multicellular_walled(self):
                axis = growth_direction(self, world, SPLIT_MIN_PARENT_SPEED)
            else:
                # animals: daughter 2 buds out where an ordinary split would
                # send it (opposite the direction of travel) when the parent
                # has no links, and away from its neighbours when it has (see
                # multicell.animal_growth_direction) -- that is where
                # branches come from
                axis = animal_growth_direction(self, (-direction[0], -direction[1]))
            begin_multicellular_split(self, new_cell1, new_cell2, axis)

            if self.multicell is not None or not is_multicellular_walled(self):
                # reproductive replacement, NOT a death: daughter 1 takes the
                # parent's slot in its animal organism (and the head role, if
                # the parent was the head -- player control already went to
                # daughter 1 above), daughter 2 joins it. The parent leaves
                # the organism here, so removing it in Game.kill_cell
                # triggers no connectivity check. (Plants / fungi never
                # belong to one; a member that mutated a wall still does.)
                # (the organism's is_player follows new_cell1 automatically --
                # see Multicell.is_player)
                adopt_daughters(self, new_cell1, new_cell2)

        else:
            # daughter 1 leaves along the parent's heading and picks the parent's
            # forward momentum back up; daughter 2 leaves the opposite way
            new_cell1.begin_split(new_cell2, direction, parent_speed, True)
            new_cell2.begin_split(new_cell1, (-direction[0], -direction[1]), parent_speed, False)

        # track new cell generation
        new_cell1.generation = self.generation + 1
        new_cell2.generation = self.generation + 1
        # add new cells to game cell list
        cell_list.extend([new_cell1, new_cell2])

        # prepare current cell for deletion (any links it still has were
        # handed to daughter 1 above; this just guarantees none are left)
        remove_all_joints(self)
        self.is_player = False
        self.has_split = True
        self.is_dead = True

        audio.play_split(self.body.position)

    def cell_death(self, world):
        # from cell mass get amount of large (5x) particles and small particles
        # lower consumption efficiency
        edible_mass = self.mass * 0.4
        if self.has_cell_wall and (self.is_fungi or self.has_chloroplast):
            num_large_particles = int(edible_mass // 6)
            num_small_particles = int(edible_mass % 6)
            total = num_small_particles + num_large_particles
            if total == 0:
                return
            if self.has_chloroplast:
                choices = [0] * num_small_particles + [2] * num_large_particles
            elif self.is_fungi:
                choices = [0] * num_small_particles + [3] * num_large_particles

        else:
            num_large_particles = int(edible_mass // 5)
            num_small_particles = int(edible_mass % 5)
            total = num_small_particles + num_large_particles
            if total == 0:
                return
            choices = [0] * num_small_particles + [1] * num_large_particles

        # Spawn particles around the perimeter of the dead cell
        random.shuffle(choices)

        for i, choice in enumerate(choices):
            if self.has_cell_wall:
                # Distribute particles evenly along a square perimeter
                t = (i / total) * 4
                side = int(t)
                offset = (t % 1) * 2 * self.size - self.size

                if side == 0:
                    rx, ry = offset, -self.size
                elif side == 1:
                    rx, ry = self.size, offset
                elif side == 2:
                    rx, ry = -offset, self.size
                else:
                    rx, ry = -self.size, -offset

            else:
                # Distribute particles evenly around a circle
                angle = 2 * math.pi * i / total
                rx = self.size * math.cos(angle)
                ry = self.size * math.sin(angle)

            wx = self.body.position.x + rx
            wy = self.body.position.y + ry

            # Get grid position and corresponding cell
            gx, gy = world.world_to_grid_cell((wx, wy))
            cell = world.get_lvl1_chunk_local_cell((gx, gy))

            # Fallback: search nearby grid cells if initial position is invalid
            if not isinstance(cell, WaterCell):
                found = False
                max_radius = 5

                for radius in range(1, max_radius + 1):
                    candidates = []

                    # Search only the perimeter of each expanding square
                    for dx in range(-radius, radius + 1):
                        for dy in range(-radius, radius + 1):
                            if max(abs(dx), abs(dy)) != radius:
                                continue

                            nx, ny = gx + dx, gy + dy
                            nearby = world.get_lvl1_chunk_local_cell((nx, ny))

                            if isinstance(nearby, WaterCell):
                                candidates.append((nx, ny, nearby))

                    if candidates:
                        # Choose nearest valid water cell in this ring
                        gx, gy, cell = min(
                            candidates,
                            key=lambda c: (c[0] - gx) ** 2 + (c[1] - gy) ** 2
                        )

                        # Move particle to the center of the valid grid cell
                        # Assumes a world.grid_cell_to_world() method exists
                        wx, wy = world.grid_cell_to_world((gx, gy))
                        found = True
                        break

                if not found:
                    print(f"FAILED TO SPAWN: No WaterCell within {max_radius} grid cells")
                    continue

            particle = Particle((wx, wy), choice)
            cell.add_particle(particle)
            world.mark_food_changed((gx, gy))

    # ------------------------------------------------------------------
    # Splitting (mitosis):  normal -> splitting -> normal + invulnerability
    # ------------------------------------------------------------------
    # split() spawns both daughters on top of each other in the "splitting"
    # state. While splitting, update_split() (called once per frame from the
    # game loop) owns the daughter's velocity along the split axis, so the two
    # slide apart through the real physics world -- what is drawn is where the
    # bodies actually are. Player input and the decision model are ignored,
    # the pair can't collide with or eat each other, and the state ends on a
    # purely geometric test: the two no longer overlap.
    @property
    def is_splitting(self):
        return self.state == CELL_STATE_SPLITTING

    @property
    def split_radius(self):
        """Radius used for the "no longer overlapping" test. Walled cells are
        boxes, so use the half-diagonal: clear of each other on any axis."""
        if self.has_cell_wall:
            return self.size * math.sqrt(2)
        return self.size

    def is_split_sibling_of(self, other):
        """True only while BOTH cells are mid-split and paired with each other.
        The collision handlers in main.py use this to ignore the sibling pair
        (and nothing else) while they overlap."""
        return (
            self.is_splitting
            and self.split_sibling is other
            and other.is_splitting
            and other.split_sibling is self
        )

    def begin_split(self, sibling, direction, parent_speed, inherits_momentum, joins=False):
        """Enter the splitting state. A zero `direction` means this daughter
        is not pushed at all (the multicellular daughter that stays in the
        parent's place). `joins` = link the pair with a joint when they finish
        separating, and finish when their edges meet."""
        self.state = CELL_STATE_SPLITTING
        self.split_joins = joins
        self.split_sibling = sibling
        self.split_is_lead = inherits_momentum
        self.split_direction = direction
        self.split_exit_speed = self._split_exit_speed(parent_speed, inherits_momentum)
        self.split_elapsed = 0.0
        self.split_best_distance = 0.0
        self.split_stall_time = 0.0
        if direction[0] or direction[1]:
            self.body.velocity = (direction[0] * SPLIT_SPEED, direction[1] * SPLIT_SPEED)

    def _split_exit_speed(self, parent_speed, inherits_momentum):
        """Speed this daughter eases toward as the gap opens, chosen so the
        hand-back to normal behaviour has no jump in speed or direction."""
        if self.has_cell_wall:
            return SPLIT_DRIFT_SPEED      # plants can't swim: they drift off
        if not self.is_player and self.genome.intelligence >= 0:
            return max(self.max_speed, SPLIT_DRIFT_SPEED)   # AI cruises at max_speed
        if inherits_momentum:
            return max(parent_speed, SPLIT_DRIFT_SPEED)     # parent's forward momentum
        return SPLIT_DRIFT_SPEED          # keeps its separation momentum

    def update_split(self, dt):
        """Advance the separation by one frame. No-op unless splitting."""
        if not self.is_splitting:
            return

        # sibling was eaten / starved / removed mid-split: nothing left to
        # separate from, so carry on alone as a normal cell
        sibling = self.split_sibling
        if sibling is None or sibling.is_dead or sibling.split_sibling is not self:
            self.end_split()
            return

        dx = self.body.position.x - sibling.body.position.x
        dy = self.body.position.y - sibling.body.position.y
        distance = math.hypot(dx, dy)
        if self.split_joins:
            # multicellular: done when the facing edges meet (no gap)
            target = self.size + sibling.size
        else:
            target = self.split_radius + sibling.split_radius + SPLIT_SEPARATION_MARGIN

        # geometric completion: the daughters no longer overlap
        if distance >= target:
            if self.split_joins:
                self._join_split_pair(sibling)
            sibling.end_split()
            self.end_split()
            return

        # safety nets for a wedged pair (terrain / crowding on both sides)
        self.split_elapsed += dt
        if distance > self.split_best_distance + _SPLIT_PROGRESS_EPSILON:
            self.split_best_distance = distance
            self.split_stall_time = 0.0
        else:
            self.split_stall_time += dt

        if self.split_elapsed >= SPLIT_MAX_DURATION:
            self._force_end_split(sibling)
            return
        if self.split_stall_time >= SPLIT_STALL_TIME and not self.split_joins:
            # blocked along this axis: turn the split axis 90 degrees
            # (not for multicellular pairs: they must stay edge-aligned, so
            # they wait for SPLIT_MAX_DURATION instead)
            ax, ay = self.split_direction
            self._retarget_split((-ay, ax))
            sibling._retarget_split((ay, -ax))

        # drive the body along the split axis. Easing on progress^2 keeps the
        # start slow and readable, and lands exactly on split_exit_speed as
        # the state ends. The lateral component is left to the physics world
        # (gravity, bumps from other organisms), so only the separation itself
        # is scripted.
        ax, ay = self.split_direction
        if ax == 0 and ay == 0:
            return      # the daughter that stays put: physics owns it
        progress = min(distance / target, 1.0)
        speed = SPLIT_SPEED + (self.split_exit_speed - SPLIT_SPEED) * progress * progress
        if self.split_joins:
            # multicellular: slide out RELATIVE to the daughter that stays
            # put, which keeps the parent's velocity -- otherwise a moving
            # parent's stay-put daughter could overtake this one
            base = sibling.body.velocity
            self.body.velocity = (base.x + ax * speed, base.y + ay * speed)
            return
        velocity = self.body.velocity
        lateral = velocity.y * ax - velocity.x * ay
        self.body.velocity = (ax * speed - ay * lateral, ay * speed + ax * lateral)

    def _retarget_split(self, direction):
        self.split_direction = direction
        self.split_stall_time = 0.0
        self.body.velocity = (direction[0] * SPLIT_SPEED, direction[1] * SPLIT_SPEED)

    def end_split(self):
        """splitting -> normal. Starts the post-split invulnerability window
        and hands control back to input / the decision model. The body keeps
        the velocity it has right now, so nothing snaps."""
        if not self.is_splitting:
            return
        self.state = CELL_STATE_NORMAL
        self.split_sibling = None
        self.invulnerable_until = sim_clock.now + POST_SPLIT_INVULNERABILITY

        if not self.is_player and (self.split_direction[0] or self.split_direction[1]):
            # let the wander heading continue the way the split was already
            # carrying this cell, instead of wheeling round on the first frame
            self.decision_model.seed_heading(self.split_direction)

    def _force_end_split(self, sibling):
        """Last resort (SPLIT_MAX_DURATION): give up separating. The sibling
        pair's collision was rejected in the begin callback, and pymunk keeps
        a rejected collision ignored until the shapes stop touching -- which a
        wedged pair never would. Re-adding the shape drops that cached
        contact, so begin fires again next step, the pair is no longer
        splitting, and normal collision resolution pushes them apart."""
        if self.split_joins:
            self._join_split_pair(sibling)
        sibling.end_split()
        self.end_split()
        self._reset_contacts()

    def _reset_contacts(self):
        """Remove and re-add this cell's shape so pymunk forgets a sibling
        contact it was told to ignore; the pair then collides normally."""
        space = self.shape.space
        if space is not None:
            space.remove(self.shape)
            space.add(self.shape)

    def _join_split_pair(self, sibling):
        """Multicellular split finished: link the two daughters edge to
        edge. The sibling contact was ignored during the split and pymunk
        keeps ignoring it while the shapes touch -- which edge-to-edge cells
        always do -- so reset it, or linked cells would never collide."""
        finish_multicellular_split(self, sibling)
        self._reset_contacts()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self, surface, zoom_factor=1.0, offset=(0, 0)):
        # two daughters that still overlap are drawn together, as one
        # silhouette, on the lead daughter's turn; the other one's turn is a
        # no-op. (If the sibling just died, fall through and draw normally.)
        sibling = self.split_sibling
        if (SPLIT_MERGE_OUTLINES and sibling is not None and not sibling.is_dead
                and self.is_split_sibling_of(sibling)):
            if self.split_is_lead:
                self._draw_split_pair(sibling, surface, zoom_factor, offset)
            return

        self._draw_body(surface, zoom_factor, offset)

        # post-split invulnerability: a faint outer ring that fades out as the
        # window runs down (nothing extra is drawn during the split itself)
        if SHOW_INVULNERABILITY_RING and not self.is_splitting:
            remaining = self.invulnerable_until - sim_clock.now
            if remaining > 0:
                x = self.body.position[0] * zoom_factor + offset[0]
                y = self.body.position[1] * zoom_factor + offset[1]
                shade = int(40 + 100 * min(remaining / POST_SPLIT_INVULNERABILITY, 1.0))
                ring = (self.size + 3) * zoom_factor
                if self.has_cell_wall:
                    pygame.draw.rect(surface, (shade, shade, shade),
                                     ((x - ring, y - ring), (ring * 2, ring * 2)), 1)
                else:
                    pygame.draw.circle(surface, (shade, shade, shade), (x, y), ring, 1)

    def _draw_body(self, surface, zoom_factor, offset, inset=0):
        """The cell's own shape at its real world position: black fill plus a
        coloured outline. With inset > 0, draw ONLY the black fill, shrunk by
        `inset` screen px -- i.e. everything inside the outline (the mitosis
        mask, see _draw_split_pair)."""
        x = self.body.position[0] * zoom_factor + offset[0]
        y = self.body.position[1] * zoom_factor + offset[1]
        half = self.size * zoom_factor - inset
        if inset and half < 1:
            return      # zoomed out so far there is no interior left to mask

        if self.has_cell_wall:
            # tl, w, h
            rect = (
                (x - half, y - half),
                (half * 2, half * 2),
            )
            pygame.draw.rect(surface, BLACK, rect)
            if not inset:
                pygame.draw.rect(surface, self.color, rect, CELL_OUTLINE_WIDTH)

        else:
            pygame.draw.circle(surface, BLACK, (x, y), half)
            if not inset:
                pygame.draw.circle(surface, self.color, (x, y), half, CELL_OUTLINE_WIDTH)

    def _draw_split_pair(self, sibling, surface, zoom_factor, offset):
        """Mitosis silhouette: draw this cell and its overlapping sibling so
        that only the OUTER border of the combined shape is visible.

        Purely a rendering effect -- no body, no shape, nothing in the
        simulation. Three passes, all built from the two daughters' actual
        world positions and sizes pushed through the normal zoom / offset:

          1. this cell        (fill + outline)
          2. the sibling      (fill + outline) -- its black fill covers the
             part of MY outline that lies inside the sibling
          3. my interior again (black, inset by the outline width) -- covers
             the part of the SIBLING'S outline that lies inside me, without
             touching my own border

        What survives is exactly each outline's arc outside the other cell:
        one circle at distance 0, then a peanut whose waist (the chord through
        the two intersection points) narrows as the real bodies move apart,
        and two whole cells once distance >= r1 + r2 -- at which point pass 3
        covers nothing, so the mask vanishes on its own with the overlap. It
        works unchanged for unequal sizes, any split direction, any zoom, and
        for walled (square) daughters."""
        self._draw_body(surface, zoom_factor, offset)
        sibling._draw_body(surface, zoom_factor, offset)
        self._draw_body(surface, zoom_factor, offset, inset=CELL_OUTLINE_WIDTH)
