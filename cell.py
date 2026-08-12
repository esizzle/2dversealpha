import copy
import uuid

import pygame
import math
import random

from colors import  BLACK, LIME, ORANGE, RED
from env_features import EnvFeatures
from physics_object import *
from world_grid import WaterCell, Particle
from decision_models import create_decision_model


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

        # hard coded bounds
        # max_mass 10 -> 80
        self.mass_range = [10, 80]
        # max_speed 20 -> 240
        self.speed_range = [20, 240]
        # max_size 5 -> 40
        self.size_range = [5,40]

        # intelligence: which decision model this organism uses (0 = random
        # walk). Emerges under scarcity in mutate_gene, not handed out for free.
        self.intelligence = intelligence
        # level 1 intelligence features
        self.terrain_avoidance = terrain_avoidance
        self.intelligence_range = [-1, 4]  # 3 == Level 3A, 4 == Level 3B

        # social genes (only consulted once the matching model is unlocked)
        self.cell_attraction = 0.0  # 3A: single toward/away, [-1, 1]
        self.smaller_cell_attraction = 0.0  # 3B: response to smaller cells
        self.larger_cell_attraction = 0.0  # 3B: response to larger cells
        self.wall_cell_attraction = 10.0

    def mutate_gene(self, env: EnvFeatures, cell):
        """Mutate this genome based on the environment (env) and the parent
        cell's lifetime state (movement history, diet)."""

        # mutate size: size increases in less material dense areas, and decreases in more material dense areas
        if env.chunk_material == 1:
            if random.random() < self.mutation_rate:
                # self.size += random.choice([1, 2, 3, 4])
                # self.size = max(self.size_range[0], min(self.size, self.size_range[1]))
                self.max_mass += random.choice([2, 4, 6, 8])
                self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))
                self.size = self.max_mass//2

        if env.chunk_material == 2:
            if random.random() < self.mutation_rate:
                # self.size -= random.choice([1, 2, 3, 4])
                # self.size = max(self.size_range[0], min(self.size, self.size_range[1]))
                self.max_mass -= random.choice([2, 4, 6, 8])
                self.max_mass = max(self.mass_range[0], min(self.max_mass, self.mass_range[1]))
                self.size = self.max_mass//2

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

        self.acceleration = self.max_speed

        # mutate cell wall: only cells that never moved can evolve one
        if not cell.has_moved:
            if random.random() < self.mutation_rate:
                self.has_cell_wall = True

        # mutate chloroplast: needs a wall, water, and bright light
        # (light_level >= 4 replaces the old hardcoded c2y == 8 check)
        if self.has_cell_wall and not self.has_chloroplast:
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

        # mutate intelligence: perception is costly, so it only pays off -- and
        # only evolves -- where food is scarce. Rich water keeps cells at Level 0.
        # level 0 intelligence: if in water and high nutrients --> level 0 intelligence (random movement)
        if env.chunk_material == 1 and env.has_particles:
            # decrease chance of first form of intelligence evolving
            if random.random() < self.mutation_rate/2:
                self.intelligence = max(0, self.intelligence)
        if env.chunk_material == 2 and env.has_particles:
            if random.random() < self.mutation_rate:
                self.intelligence = max(1, self.intelligence)

        if self.intelligence >= 1:
            if random.random() < self.mutation_rate:
                self.terrain_avoidance += random.uniform(-0.5,0.5)

        # level 2 intelligence: nutrient awareness
        if not env.has_particles:
            if random.random() < self.mutation_rate:
                self.intelligence = max(2, self.intelligence)

        # level 3 intelligence: cell awareness
        if cell.amt_type1_particles > 0:
            if random.random() < self.mutation_rate:
                self.intelligence = max(3, self.intelligence)

        if self.intelligence == 3:
            choice = random.uniform(0.1, 0.2)
            if cell.amt_type1_particles > 0:
                for i in range(cell.amt_type1_particles):
                    if random.random() < self.mutation_rate:
                        self.cell_attraction = max(self.cell_attraction + choice, 1)
            else:
                if random.random() < self.mutation_rate:
                    self.cell_attraction = max(-1, self.cell_attraction - choice)


        # if not env.has_particles:
        #     if random.random() < self.mutation_rate:
        #         self.intelligence = min(self.intelligence + 1, self.intelligence_range[1])
        # elif random.random() < self.mutation_rate * 0.5:
        #     self.intelligence = max(self.intelligence - 1, self.intelligence_range[0])
        #
        # # drift the social genes so 3A/3B behaviours can emerge once unlocked
        # if random.random() < self.mutation_rate:
        #     self.cell_attraction = max(-1.0, min(self.cell_attraction + random.uniform(-0.3, 0.3), 1.0))
        # if random.random() < self.mutation_rate:
        #     self.smaller_cell_attraction = max(-1.0,
        #                                        min(self.smaller_cell_attraction + random.uniform(-0.3, 0.3),
        #                                            1.0))
        # if random.random() < self.mutation_rate:
        #     self.larger_cell_attraction = max(-1.0,
        #                                       min(self.larger_cell_attraction + random.uniform(-0.3, 0.3), 1.0))

        # Behavioral Mutation: Sticky Cell: Lock onto cell if you try to eat it.


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
        self.neighboring_grid_cells = []

        # food
        self.nearby_particles = []
        self.nearby_entities = []
        self.amt_type1_particles = 0

        # booleans
        self.is_dead = False
        self.has_split = False
        self.is_player = is_player
        self.has_moved = False

        # mutation booleans
        self.has_cell_wall = genome.has_cell_wall
        self.has_chloroplast = genome.has_chloroplast

        # physics
        self.body, self.shape = init_cell_physics(
            self.mass, self.size, position, self.has_cell_wall
        )
        self.shape._object = self

        # object tracking
        self.id = uuid.uuid4()
        self.contact_time = {}
        self.total_contact_time = 0

    # ------------------------------------------------------------------
    # Energy
    # ------------------------------------------------------------------
    def add_energy(self, amount):
        """Single place where energy changes, so max_energy is always
        respected. Negative amounts spend energy (starvation is checked
        against <= 0 in the game loop)."""
        self.energy = min(self.energy + amount, self.max_energy)

    def _movement_cost(self):
        return (self.mass * self.acceleration * self.efficiency_factor + self.genome.intelligence*100) * 1/60

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle_input(self, events, keys):

        # disable movement if the cell has a cell wall
        if not self.has_cell_wall:
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

        if keys[pygame.K_k]:
            self.is_dead = True

    def apply_movement(self, direction):
        """Act on a desired direction from this cell's decision model. AI cells
        call this; the player never does (player uses handle_input). Same rules
        as manual movement: a cell wall forbids it, and moving costs energy and
        sets has_moved, so mutation rules stay identical for AI and player."""
        if self.has_cell_wall:
            return
        dx, dy = direction
        if dx == 0 and dy == 0:
            return
        vx = self.body.velocity.x + dx * self.acceleration
        vy = self.body.velocity.y + dy * self.acceleration
        speed = math.hypot(vx, vy)
        if speed > self.max_speed:
            scale = self.max_speed / speed
            vx *= scale
            vy *= scale
        self.body.velocity = (vx, vy)
        self.add_energy(-self._movement_cost())
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
    def consume_particle(self, particle, removal_list):
        dx = particle.x - self.body.position.x
        dy = particle.y - self.body.position.y

        if dx * dx + dy * dy <= self.size * self.size:
            self.add_energy(1000 * particle.multiplier)
            self.mass += 1 * particle.multiplier
            if self.mass >= self.max_mass:
                self.mass = self.max_mass
                self.add_energy(4000 * particle.multiplier)

            removal_list.append(particle)
            if particle in self.nearby_particles:
                self.nearby_particles.remove(particle)
            if particle.type == 1:
                self.amt_type1_particles += 1

    def consume_cell(self, cell):
        if cell is self:
            return
        if not cell.has_cell_wall:
            dx = cell.body.position.x - self.body.position.x
            dy = cell.body.position.y - self.body.position.y

            d_squared = dx ** 2 + dy ** 2
            # within cell radius
            if d_squared + cell.size ** 2 <= self.size ** 2:
                cell.is_dead = True

    # TODO: Turn INTO MUTATION
    def convert_mass_to_energy(self):
        self.mass -= 1
        self.add_energy(5000)
        if self.mass <= 0:
            self.is_dead = True

    # ------------------------------------------------------------------
    # Reproduction / death
    # ------------------------------------------------------------------
    def split(self, space, cell_list, env: EnvFeatures):
        # clone genome, mutating each child based on the local environment
        new_genome1 = copy.deepcopy(self.genome)
        new_genome2 = copy.deepcopy(self.genome)
        new_genome1.mutate_gene(env, self)
        new_genome2.mutate_gene(env, self)

        # dynamic spawn positions
        a = -1 if self.body.velocity.x < 0 else 1

        # spawn cells: child 1 inherits player control
        new_cell1 = Cell(
            (self.body.position.x + a * new_genome1.size, self.body.position.y),
            new_genome1,
            self.is_player,
        )
        new_cell2 = Cell(
            (self.body.position.x - a * new_genome2.size, self.body.position.y),
            new_genome2,
            False,
        )

        # configure cell pymunk settings
        space.add(new_cell1.body, new_cell1.shape)
        space.add(new_cell2.body, new_cell2.shape)

        new_cell1.body.velocity = self.body.velocity.x, self.body.velocity.y
        new_cell2.body.velocity = -self.body.velocity.x, self.body.velocity.y

        # add new cells to game cell list
        cell_list.extend([new_cell1, new_cell2])

        # prepare current cell for deletion
        self.is_player = False
        self.has_split = True
        self.is_dead = True

    def cell_death(self, world):
        # from cell mass get amount of large (5x) particles and small particles
        num_large_particles = int(self.mass // 5)
        num_small_particles = int(self.mass % 5)
        total = num_small_particles + num_large_particles

        if total == 0:
            return

        choices = [0] * num_small_particles + [1] * num_large_particles

        # spawn particles around radius of dead cell
        for i in range(total):
            rx = self.size * math.cos(2 * i * math.pi / total)
            ry = self.size * math.sin(2 * i * math.pi / total)

            wx = self.body.position.x + rx
            wy = self.body.position.y + ry
            choice = random.choice(choices)
            choices.remove(choice)

            particle = Particle((wx, wy), choice)

            # get water cell at world position
            gx, gy = world.world_to_grid_cell((wx, wy))

            # get local cell inside chunk
            cell = world.get_lvl1_chunk_local_cell((gx, gy))

            if isinstance(cell, WaterCell):
                cell.add_particle(particle)
            else:
                print("Error, could not find Water Cell!")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self, surface, zoom_factor=1.0, offset=(0, 0)):
        x = self.body.position[0] * zoom_factor + offset[0]
        y = self.body.position[1] * zoom_factor + offset[1]

        if self.has_cell_wall:
            # tl, w, h
            rect = (
                (x - self.size * zoom_factor, y - self.size * zoom_factor),
                (self.size * 2 * zoom_factor, self.size * 2 * zoom_factor),
            )
            pygame.draw.rect(surface, BLACK, rect)
            pygame.draw.rect(surface, self.color, rect, 1)

        else:
            pygame.draw.circle(surface, BLACK, (x, y), self.size * zoom_factor)
            pygame.draw.circle(surface, self.color, (x, y), self.size * zoom_factor, 1)
