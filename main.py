import pygame
import pymunk
from world_grid import *
from camera import *
from player import *
from colors import *
from profiler import Profiler

SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 720
WORLD_WINDOW_WIDTH = 600
WORLD_WINDOW_HEIGHT = 600
STAT_BOX_W = 200
STAT_BOX_H = 300
MUT_BOX_W = 200
MUT_BOX_H = 200
SPECIES_BOX_W = 200
SPECIES_BOX_H = 600

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

        self.font = pygame.font.SysFont("Arcade_Classic", 18)

        # World (chunk-based)
        self.world = World()
        self.world.init_world()
        self.world.load_lvl2chunks()

        # Physics Space
        self.space = pymunk.Space()

        # handle collisions between carnivorous cells and cells with cell walls
        self.handler = self.space.add_collision_handler(1, 2)
        self.handler.begin = self.on_cell_begin
        self.handler.separate = self.on_cell_separate

        self.camera = Camera(type=0)

        self.player = Player((11500, 11500), self.space)
        # plant_g = Genome(intelligence=-1)
        # plant_g.has_cell_wall = True
        # plant = Cell((11500, 11400), plant_g)
        # self.space.add(plant.body, plant.shape)


        # mutations tracking
        self.previous_genome = self.player.cell.genome
        self.increased = []
        self.decreased = []

        self.cells = []
        self.cells.append(self.player.cell)
        # self.cells.append(plant)
        self.previous_cell_length = 1

        # initial chunk (and hitbox) load around the player
        pos = self.world.world_to_lvl1_chunk(self.player.cell.body.position)
        self.world.load_chunks(pos, self.space)

        self.to_remove_particles = []
        self.running = True

        self.profiler = Profiler(window=60)

    def init_pygame(self):
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        clock = pygame.time.Clock()
        return screen, clock

    def handle_inputs(self):
        # inputs
        events = pygame.event.get()
        keys = pygame.key.get_pressed()

        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F3:
                    self.profiler.overlay = not self.profiler.overlay  # toggle overlay
                elif event.key == pygame.K_F4:
                    self.profiler.request_deep_profile()

        # camera inputs
        self.camera.handle_input(events, keys)
        # player inputs
        for cell in self.cells:
            if cell.is_player:
                cell.handle_input(events, keys)

    def on_cell_begin(self, arbiter, space, data):
        a, b = arbiter.shapes
        predator_cell = a._object
        prey_cell = b._object

        predator_cell.contact_time[prey_cell] = 0.0
        return True

    def on_cell_separate(self, arbiter, space, data):
        a, b = arbiter.shapes
        predator_cell = a._object
        prey_cell = b._object

        predator_cell.contact_time.pop(prey_cell, None)

    # ------------------------------------------------------------------
    # Mutation tracking (game logic — runs in update, not in render)
    # ------------------------------------------------------------------
    def check_mutations(self):
        genome = self.player.cell.genome
        if genome is self.previous_genome:
            return

        self.increased.clear()
        self.decreased.clear()

        max_mass = genome.max_mass - self.previous_genome.max_mass
        if max_mass > 0:
            self.increased.append("MAX MASS")
        elif max_mass < 0:
            self.decreased.append("MAX MASS")

        size = genome.size - self.previous_genome.size
        if size > 0:
            self.increased.append("SIZE")
        elif size < 0:
            self.decreased.append("SIZE")

        speed = genome.max_speed - self.previous_genome.max_speed
        if speed > 0:
            self.increased.append("SPEED")
        elif speed < 0:
            self.decreased.append("SPEED")

        if genome.has_cell_wall != self.previous_genome.has_cell_wall:
            if genome.has_cell_wall:
                self.increased.append("EVOLVED CELL WALL")
                self.decreased.append("CAN NO LONGER MOVE")

        if genome.has_chloroplast != self.previous_genome.has_chloroplast:
            if genome.has_chloroplast:
                self.increased.append("EVOLVED CHLOROPLAST")

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

    def draw_stat_box(self):
        self.stat_box_surface.fill(BLACK)

        # Mass
        self.draw_stat_bar(self.player.cell.mass, self.player.cell.max_mass, "MASS", "pg", 25)

        # Energy
        self.draw_stat_bar(self.player.cell.energy, self.player.cell.max_energy, "ENERGY", "nJ", 62, 1000)

        # OUTLINE
        pygame.draw.rect(self.stat_box_surface, (255, 255, 255), (0, 0, STAT_BOX_W, STAT_BOX_H), 1)

        self.screen.blit(self.stat_box_surface, ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH) // 2 + 20,
                                                 (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) // 2))

    def draw_mut_box(self):
        self.mut_box_surface.fill(BLACK)
        pygame.draw.rect(self.mut_box_surface, (255, 255, 255), (0, 0, MUT_BOX_W, MUT_BOX_H), 1)

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

    def draw_species_box(self):
        self.species_box_surface.fill(BLACK)
        pygame.draw.rect(self.species_box_surface, (255, 255, 255), (0, 0, SPECIES_BOX_W, SPECIES_BOX_H), 1)

        self.screen.blit(self.species_box_surface, ((SCREEN_WIDTH - WORLD_WINDOW_WIDTH) // 2 - 220,
                                                    (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) // 2))

    def draw_game_world(self):
        self.world_surface.fill(BLACK)

        # draw grid
        self.world.render_chunks(self.world_surface, self.camera)

        # draw cells
        for cell in self.cells:
            cell.draw(self.world_surface, self.camera.zoom, self.camera.offset)

        # WORLD BOX
        pygame.draw.rect(self.world_surface, (255, 255, 255), (0, 0, WORLD_WINDOW_WIDTH, WORLD_WINDOW_HEIGHT), 1)

        fps = self.clock.get_fps()
        fps_text = self.font.render(f"FPS: {fps:.0f}", True, (255, 255, 255))
        self.world_surface.blit(fps_text, (10, 10))

        self.screen.blit(self.world_surface,
                         ((SCREEN_WIDTH - WORLD_WINDOW_WIDTH) / 2, (SCREEN_HEIGHT - WORLD_WINDOW_HEIGHT) / 2))

    def create_box_label(self, text, top_left):
        label = self.font.render(text, True, (0, 255, 0))
        label_rect = label.get_rect(topleft=top_left)
        pygame.draw.rect(
            self.screen,
            BLACK,
            label_rect.inflate(6, 4)
        )
        self.screen.blit(label, label_rect)

    def render(self):
        with self.profiler.section("render_world"):
            self.draw_game_world()
        with self.profiler.section("render_ui"):
            self.draw_stat_box()
            self.draw_mut_box()
            self.create_box_label("Game World", (SCREEN_WIDTH / 2 - 16, 55))
            self.create_box_label("Player Stats", ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH + STAT_BOX_W) // 2 - 15, 55))
            self.create_box_label("Mutations", ((SCREEN_WIDTH + WORLD_WINDOW_WIDTH + STAT_BOX_W) // 2 - 10, 375))

        self.profiler.draw_overlay(self.screen, self.font, topleft=(8, 8))  # overlay on top

        pygame.display.flip()
        self.clock.tick(60)

    def kill_cell(self, cell):
        # spawn particles for mass
        if cell.is_player:
            self.camera.type = 1
            cell.is_player = False

        if not cell.has_split:
            cell.cell_death(self.world)
        self.cells.remove(cell)
        self.space.remove(cell.body, cell.shape)

    def respawn_particles(self, dt):
        for chunk in self.world.loaded_lvl1chunks:
            lvl1chunk = self.world.lvl1chunks[chunk]
            if not lvl1chunk.has_particles:
                continue
            for grid_cell in lvl1chunk.materials.values():
                if isinstance(grid_cell, WaterCell):
                    if len(grid_cell.particles) < grid_cell.particle_count:
                        if random.random() < 0.05 * dt:
                            grid_cell.spawn_particle()

    def update(self):
        dt = 1 / 60

        with self.profiler.section("physics"):
            self.space.step(dt)
            if self.camera.type == 1:
                self.camera.update(width=WORLD_WINDOW_WIDTH, height=WORLD_WINDOW_HEIGHT)

        with self.profiler.section("respawn"):
            self.respawn_particles(dt)

        with self.profiler.section("sim_loop"):
            new_cells = []
            dead_cells = []
            for cell in self.cells:
                self.world.update_entity(cell)

                # EnvFeatures is only consumed by split() and photosynthesis, so
                # build it lazily instead of once per cell per frame. (Phase 1 opt)
                will_split = cell.mass >= cell.max_mass and cell.energy >= cell.max_energy
                env = None
                if will_split or cell.has_chloroplast:
                    env = self.world.get_env_features(cell.body.position)

                # player cell functions
                if cell.is_player:
                    self.player.cell = cell
                    self.world.process(cell.body.position, self.space)
                    self.camera.update(cell.body, WORLD_WINDOW_WIDTH, WORLD_WINDOW_HEIGHT)
                else:
                    if cell.genome.intelligence >= 0:
                        direction = cell.decision_model.decide(cell, self.world)
                        cell.apply_movement(direction)

                # cell reproduction (children spawn into new_cells)
                if will_split:
                    cell.split(self.space, new_cells, env)

                # gain energy: eat nearby particles
                for particle in list(cell.nearby_particles):
                    cell.consume_particle(particle, self.to_remove_particles)

                # gain energy: photosynthesis
                if cell.has_chloroplast and env is not None and env.in_water:
                    rates = PHOTOSYNTHESIS_RATES.get(cell.color, {})
                    cell.add_energy(rates.get(env.light_level, 0))

                # death by starvation
                if cell.energy <= 0:
                    cell.is_dead = True

                # death by contact
                for other in cell.contact_time:
                    cell.contact_time[other] += dt
                    cell.total_contact_time += dt
                    if cell.contact_time[other] >= 1:
                        other.is_dead = True

                # death by consumption
                for entity in cell.nearby_entities:
                    cell.consume_cell(entity)

                if cell.is_dead:
                    dead_cells.append(cell)

            # apply deferred list changes
            self.cells.extend(new_cells)

        with self.profiler.section("deaths"):
            for cell in dead_cells:
                if cell in self.cells:
                    self.kill_cell(cell)

        with self.profiler.section("post"):
            self.check_mutations()
            for particle in self.to_remove_particles:
                gx, gy = particle.x // CELL_SIZE, particle.y // CELL_SIZE
                cell = self.world.get_lvl1_chunk_local_cell((gx, gy))

                if cell is not None and hasattr(cell, "particles") and particle in cell.particles:
                    cell.particles.remove(particle)

            self.to_remove_particles.clear()

    def main_game_loop(self):
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
    game = Game()
    game.main_game_loop()
