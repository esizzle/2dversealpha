import random
import math
from dataclasses import dataclass
import pygame
from physics_object import *
from colors import *
from env_features import (
    EnvFeatures,
    MATERIAL_AIR,
    MATERIAL_WATER,
    MATERIAL_SAND, MATERIAL_BASALT,
)
# #World 1:
# WORLD_KEY = [[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,1,1,1,1,1,1,1,1,1,1,2,2],[1,1,1,1,1,1,1,1,1,2,2,2,2,2,2,2],[1,1,1,1,1,1,2,2,2,2,2,2,2,2,2,2],[1,1,1,1,1,2,2,2,2,2,2,2,2,2,2,2],[1,1,1,1,2,2,2,2,2,2,2,2,2,2,2,2],[1,1,1,1,2,2,2,2,2,2,2,2,2,2,2,2],[1,1,1,2,2,2,2,2,2,2,2,2,2,2,2,2],[2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2]]
# WORLD_PARTICLES = [[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1],[0,0,0,0,0,1,1,1,1,1,1,1,1,1,0,0],[0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0],[0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0],[0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0],[0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0],[1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0]]
# WORLD_SHADER = [[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],[4,4,4,4,4,4,4,4,4,4,4,4,4,4,0,0],[4,4,4,4,4,4,4,4,4,0,0,0,0,0,0,0],[3,3,3,3,3,3,0,0,0,0,0,0,0,0,0,0],[3,3,3,3,3,0,0,0,0,0,0,0,0,0,0,0],[2,2,2,2,0,0,0,0,0,0,0,0,0,0,0,0],[2,2,2,2,0,0,0,0,0,0,0,0,0,0,0,0],[2,2,2,0,0,0,0,0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]]

# Water World:
# WORLD_KEY = [[3,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,3,3,3,3,1,1,1,1,1],
#              [1,1,1,1,1,1,1,3,1,1,3,1,1,1,1,1],
#              [1,1,1,1,1,1,1,3,1,1,3,1,1,1,1,1],
#              [1,1,1,1,1,1,1,3,3,3,3,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
#              [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]]
#
# WORLD_PARTICLES = [[1,1,1,1,0,0,1,1,1,1,0,0,1,1,1,1],
#                    [1,1,1,1,0,0,1,1,1,0,1,0,0,1,1,1],
#                    [1,1,1,1,0,1,1,1,0,1,1,1,1,1,0,1],
#                    [1,1,1,1,1,1,0,0,0,1,1,1,0,0,1,1],
#                    [0,0,1,1,1,1,1,0,0,0,1,1,0,1,1,1],
#                    [0,0,0,1,1,1,1,0,0,0,0,0,1,1,1,1],
#                    [0,0,0,0,1,1,1,1,1,0,0,0,1,1,1,1],
#                    [0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0],
#                    [0,0,0,0,0,0,0,1,1,1,1,1,0,0,0,0],
#                    [0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0],
#                    [0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0],
#                    [0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0],
#                    [0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0],
#                    [0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0],
#                    [1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0],
#                    [1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0]]
#
# WORLD_SHADER = [[4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
#                 [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
#                 [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
#                 [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
#                 [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
#                 [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
#                 [3,3,3,3,3,3,3,3,4,4,3,3,3,3,3,3],
#                 [3,3,3,3,3,3,3,3,4,4,3,3,3,3,3,3],
#                 [3,3,3,3,3,3,3,3,4,4,3,3,3,3,3,3],
#                 [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
#                 [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
#                 [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
#                 [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
#                 [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
#                 [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
#                 [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2]]

# Sand World:
WORLD_KEY = [[2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
             [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2]]

WORLD_PARTICLES = [[1,1,1,1,0,0,1,1,1,1,0,0,1,1,1,1],
                   [1,1,1,1,0,0,1,1,1,0,1,0,0,1,1,1],
                   [1,1,1,1,0,1,1,1,0,1,1,1,1,1,0,1],
                   [1,1,1,1,1,1,0,0,0,1,1,1,0,0,1,1],
                   [0,0,1,1,1,1,1,0,0,0,1,1,0,1,1,1],
                   [0,0,0,1,1,1,1,0,0,0,0,0,1,1,1,1],
                   [0,0,0,0,1,1,1,1,1,0,0,0,1,1,1,1],
                   [0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0],
                   [0,0,0,0,0,0,0,1,1,1,1,1,0,0,0,0],
                   [0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0],
                   [0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0],
                   [0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0],
                   [0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0],
                   [0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0],
                   [1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0],
                   [1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0]]

WORLD_SHADER = [[4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
                [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
                [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
                [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
                [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
                [4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],
                [3,3,3,3,3,3,3,3,4,4,3,3,3,3,3,3],
                [3,3,3,3,3,3,3,3,4,4,3,3,3,3,3,3],
                [3,3,3,3,3,3,3,3,4,4,3,3,3,3,3,3],
                [3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
                [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
                [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
                [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
                [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
                [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
                [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2]]

MATERIALS = {
    MATERIAL_AIR: ('AIR', AIR),
    MATERIAL_WATER: ('WATER', BLUE),
    MATERIAL_SAND: ('SAND', SAND),
    MATERIAL_BASALT: ('BASALT', BASALT)
}

WORLD_SIZE = 16
LVL4_CHUNK_SIZE = 2
LVL3_CHUNK_SIZE = 2
LVL2_CHUNK_SIZE = 2
LVL1_CHUNK_SIZE = 16
CELL_SIZE = 40

LVL1_GRID_MAX = WORLD_SIZE * LVL2_CHUNK_SIZE - 1  # 31

# Physics constants, expressed per-second so they are frame-rate independent.
# Old code added 98.1 px/frame at 60fps -> 98.1 * 60 = 5886 px/s^2.
AIR_GRAVITY = 98.1 * 60          # px/s^2
WATER_SURFACE_DAMPING = 0.5 * 60  # px/s^2 applied at the water/air boundary


class World:
    def __init__(self):
        self.loaded_lvl1chunks = set()
        self.loaded_shapes = {}
        self.loaded_bodies = {}

        # (0,0) -> (15, 15)
        self.lvl2chunks = {}

        # (0,0) -> (31, 31)
        self.lvl1chunks = {}

    def init_world(self):
        for x in range(WORLD_SIZE):
            for y in range(WORLD_SIZE):
                material = WORLD_KEY[y][x]
                # simple case for test, all compositions are the same as the cell type
                composition = [[material, material], [material, material]]
                self.lvl2chunks[(x, y)] = Level2Chunk((x, y), material, composition)
                self.lvl2chunks[(x, y)].light_level = WORLD_SHADER[y][x]
                if WORLD_PARTICLES[y][x] == 1:
                    self.lvl2chunks[(x, y)].has_particles = True

    def load_lvl2chunks(self):
        for x in range(WORLD_SIZE):
            for y in range(WORLD_SIZE):
                self.lvl2chunks[(x, y)].load_lvl2_chunk()
                for key in self.lvl2chunks[(x, y)].lvl1chunks:
                    cx = self.lvl2chunks[(x, y)].lvl1chunks[key].wx
                    cy = self.lvl2chunks[(x, y)].lvl1chunks[key].wy
                    self.lvl1chunks[(cx, cy)] = self.lvl2chunks[(x, y)].lvl1chunks[key]

    # ------------------------------------------------------------------
    # Chunk loading / unloading
    # Hitbox bodies are owned by these two paths and nowhere else:
    # load_chunks adds them, unload_distant_chunks removes them.
    # ------------------------------------------------------------------
    def load_chunks(self, entity_tile_pos, space):
        px, py = entity_tile_pos

        for dx in (px - 1, px, px + 1):
            for dy in (py - 1, py, py + 1):
                if dx < 0 or dy < 0 or dx > LVL1_GRID_MAX or dy > LVL1_GRID_MAX:
                    continue
                if (dx, dy) not in self.loaded_lvl1chunks:
                    self.loaded_lvl1chunks.add((dx, dy))
                    self.load_hit_boxes(space, (dx, dy))

    def load_hit_boxes(self, space, chunk):
        if chunk in self.loaded_bodies:
            return  # already loaded, never double-add

        bodies = []
        shapes = []
        for material in self.lvl1chunks[chunk].materials:
            if isinstance(self.lvl1chunks[chunk].materials[material], SandCell):
                sand_cell = self.lvl1chunks[chunk].materials[material]
                sx = sand_cell.wx * CELL_SIZE + CELL_SIZE / 2
                sy = sand_cell.wy * CELL_SIZE + CELL_SIZE / 2
                body, shape = sand_body((sx, sy))
                space.add(body, shape)
                bodies.append(body)
                shapes.append(shape)

            if isinstance(self.lvl1chunks[chunk].materials[material], BasaltCell):
                basalt_cell = self.lvl1chunks[chunk].materials[material]
                bx = basalt_cell.wx * CELL_SIZE + CELL_SIZE / 2
                by = basalt_cell.wy * CELL_SIZE + CELL_SIZE / 2
                body, shape = sand_body((bx, by))
                space.add(body, shape)
                bodies.append(body)
                shapes.append(shape)
        self.loaded_bodies[chunk] = bodies
        self.loaded_shapes[chunk] = shapes

    def unload_distant_chunks(self, player_tile_pos, space):
        unload_dist = 2  # compared against squared chunk distance
        to_remove = set()

        for chunk in self.loaded_lvl1chunks:
            if self.dist(chunk, player_tile_pos) > unload_dist:
                to_remove.add(chunk)

        for chunk in to_remove:
            self.clear_chunk(space, chunk)
            self.loaded_lvl1chunks.remove(chunk)

    def clear_chunk(self, space, chunk):
        bodies = self.loaded_bodies.pop(chunk, [])
        shapes = self.loaded_shapes.pop(chunk, [])
        for body in bodies:
            space.remove(body)
        for shape in shapes:
            space.remove(shape)

    def dist(self, chunk, player):
        cx, cy = chunk
        px, py = player
        rx = cx - px
        ry = cy - py
        return rx ** 2 + ry ** 2

    # ------------------------------------------------------------------
    # Coordinate conversions
    # ------------------------------------------------------------------
    def world_to_lvl2_chunk(self, position):
        x, y = position
        c2x = int(x // (CELL_SIZE * LVL1_CHUNK_SIZE * LVL2_CHUNK_SIZE))
        c2y = int(y // (CELL_SIZE * LVL1_CHUNK_SIZE * LVL2_CHUNK_SIZE))
        return c2x, c2y

    def world_to_lvl1_chunk(self, position):
        x, y = position
        c1x = int(x // (CELL_SIZE * LVL1_CHUNK_SIZE))
        c1y = int(y // (CELL_SIZE * LVL1_CHUNK_SIZE))
        return c1x, c1y

    def world_to_grid_cell(self, position):
        x, y = position
        # // floors (also for negatives), unlike int(x / CELL_SIZE) which
        # truncated toward zero and mapped small negative positions to cell 0
        gcx = int(x // CELL_SIZE)
        gcy = int(y // CELL_SIZE)
        return gcx, gcy

    def get_lvl1_chunk_local_cell(self, cell_position):
        gx, gy = cell_position
        if gx < 0 or gy < 0:
            return None

        c1x, c1y = gx // LVL1_CHUNK_SIZE, gy // LVL1_CHUNK_SIZE
        chunk = self.lvl1chunks.get((c1x, c1y))
        if chunk is None:
            return None  # chunk not loaded / out of bounds

        local_x = gx % LVL1_CHUNK_SIZE
        local_y = gy % LVL1_CHUNK_SIZE
        return chunk.materials.get((local_x, local_y))

    # ------------------------------------------------------------------
    # Environment features
    # ------------------------------------------------------------------
    def get_env_features(self, position):
        """Build an EnvFeatures snapshot for a world position.

        Compute this once per entity per frame (or on grid-cell change)
        and pass it around, rather than re-querying the grid everywhere.
        """
        c2 = self.world_to_lvl2_chunk(position)
        lvl2 = self.lvl2chunks.get(c2)

        c1 = self.world_to_lvl1_chunk(position)
        lvl1 = self.lvl1chunks.get(c1)

        gx, gy = self.world_to_grid_cell(position)
        cell = self.get_lvl1_chunk_local_cell((gx, gy))
        below = self.get_lvl1_chunk_local_cell((gx, gy + 1))
        above = self.get_lvl1_chunk_local_cell((gx, gy - 1))

        return EnvFeatures(
            depth=c2[1],
            light_level=lvl2.light_level if lvl2 else 0,
            # chunk vs cell material is intentional: a SAND chunk is mostly
            # water cells with embedded sand blocks, so chunk_material can be
            # SAND while cell_material is WATER
            chunk_material=lvl1.material if lvl1 else MATERIAL_AIR,
            cell_material=getattr(cell, 'material_id', MATERIAL_AIR),
            in_water=isinstance(cell, WaterCell),
            on_sand=isinstance(below, SandCell),
            surface_above=isinstance(above, AirCell),
            has_particles=lvl2.has_particles if lvl2 else False,
        )

    # ------------------------------------------------------------------
    # Per-frame processing
    # ------------------------------------------------------------------
    def process(self, entity_pos, space):
        entity_tile_pos = self.world_to_lvl1_chunk(entity_pos)
        self.load_chunks(entity_tile_pos, space)
        self.unload_distant_chunks(entity_tile_pos, space)

    def update_entity(self, entity, dt=1 / 60):
        entity_grid_pos = self.world_to_grid_cell(entity.body.position)
        self.handle_grid_physics(entity, entity_grid_pos, dt)
        entity_chunk_pos = self.world_to_lvl1_chunk(entity.body.position)
        if entity.last_chunk_pos != entity_chunk_pos:
            entity.last_chunk_pos = entity_chunk_pos

        if entity.last_grid_pos != entity_grid_pos:

            # remove entity from previous grid cell
            if entity.last_grid_pos is not None:
                old_cell = self.get_lvl1_chunk_local_cell(entity.last_grid_pos)
                if isinstance(old_cell, WaterCell) and entity in old_cell.entities:
                    old_cell.entities.remove(entity)

            # reset entity nearby objects
            entity.nearby_particles.clear()
            entity.nearby_entities.clear()

            # update entity position
            entity.last_grid_pos = entity_grid_pos
            entity.neighboring_grid_cells = entity.get_neighbor_grid_cells()

            # update current grid cell data
            cell = self.get_lvl1_chunk_local_cell(entity_grid_pos)
            if isinstance(cell, WaterCell):
                cell.entities.append(entity)

            # get objects in entity neighbors
            entity.get_nearby_objects(self)

    def handle_grid_physics(self, entity, grid_pos, dt):
        self.air_ontop_water_phys(entity, grid_pos, dt)

    def air_ontop_water_phys(self, entity, grid_pos, dt):
        cell = self.get_lvl1_chunk_local_cell(grid_pos)
        if isinstance(cell, WaterCell):
            above_cell = self.get_lvl1_chunk_local_cell((grid_pos[0], grid_pos[1] - 1))
            if isinstance(above_cell, AirCell):
                # dampen cell velocity to prevent it from crossing water air boundary
                if entity.body.velocity.y < 1:
                    entity.body.velocity = (
                        entity.body.velocity.x,
                        min(0, entity.body.velocity.y + WATER_SURFACE_DAMPING * dt),
                    )

        if isinstance(cell, AirCell):
            entity.body.velocity = (
                entity.body.velocity.x,
                entity.body.velocity.y + AIR_GRAVITY * dt,
            )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render_chunks(self, surface, camera):
        zoom = camera.zoom
        ox, oy = camera.offset

        screen_w, screen_h = surface.get_size()

        cell_px = CELL_SIZE * zoom
        chunk_px = LVL1_CHUNK_SIZE * cell_px

        # visible chunk bounds
        min_cx = int((-ox) // chunk_px) - 1
        max_cx = int((screen_w - ox) // chunk_px) + 1
        min_cy = int((-oy // chunk_px) - 1)
        max_cy = int((screen_h - oy) // chunk_px) + 1

        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                if cx < 0 or cy < 0:
                    continue
                if cx > LVL1_GRID_MAX or cy > LVL1_GRID_MAX:
                    continue

                if zoom < 0.1:
                    self.lvl2chunks[(cx // 2, cy // 2)].draw(surface, camera)
                else:
                    self.lvl1chunks[(cx, cy)].draw(surface, camera)

    def draw_loaded_chunks(self, surface, camera):
        for chunk in self.loaded_lvl1chunks:
            lvl1chunk = self.lvl1chunks[chunk]
            lvl1chunk.draw(surface, camera)

    def draw_chunk_bounds(self, surface, camera):
        zoom = camera.zoom
        ox, oy = camera.offset

        chunk_px = LVL2_CHUNK_SIZE * LVL1_CHUNK_SIZE * CELL_SIZE * zoom

        for (cx, cy) in self.lvl2chunks.keys():
            x = cx * chunk_px + ox
            y = cy * chunk_px + oy

            pygame.draw.rect(
                surface,
                (255, 0, 0),
                (x, y, chunk_px, chunk_px),
                1
            )


class Level2Chunk:
    def __init__(self, world_pos, material, composition):  # 0 - 16
        self.world_pos = world_pos
        self.wx, self.wy = world_pos
        self.material = material
        self.composition = composition

        self.material_name, self.material_color = MATERIALS[material]
        self.lvl1chunks = {}

        self.light_level = 0
        self.has_particles = False

    def load_lvl2_chunk(self):
        for x in range(LVL2_CHUNK_SIZE):
            for y in range(LVL2_CHUNK_SIZE):
                material = self.composition[y][x]
                cx = (self.wx + x / LVL2_CHUNK_SIZE) * LVL2_CHUNK_SIZE
                cy = (self.wy + y / LVL2_CHUNK_SIZE) * LVL2_CHUNK_SIZE
                self.lvl1chunks[(x, y)] = Level1Chunk((cx, cy), material, self.has_particles)

    def draw(self, surface, camera):
        zoom = camera.zoom
        ox, oy = camera.offset

        chunk_world_x = self.wx * LVL2_CHUNK_SIZE * LVL1_CHUNK_SIZE * CELL_SIZE
        chunk_world_y = self.wy * LVL2_CHUNK_SIZE * LVL1_CHUNK_SIZE * CELL_SIZE

        chunk_pixel_size = LVL2_CHUNK_SIZE * LVL1_CHUNK_SIZE * CELL_SIZE * zoom

        pygame.draw.rect(
            surface,
            self.material_color,
            (
                chunk_world_x * zoom + ox,
                chunk_world_y * zoom + oy,
                chunk_pixel_size,
                chunk_pixel_size
            ),
            1
        )


class Level1Chunk:
    def __init__(self, world_pos, material, has_particles):  # 0 - 32
        self.world_pos = world_pos
        self.wx, self.wy = world_pos

        self.material = material

        self.material_name, self.material_color = MATERIALS[material]
        self.materials = {}
        self.has_particles = has_particles

        self.init_grid()

    def init_grid(self):
        # Base fill per chunk material. Sand chunks are intentionally filled
        # with water cells first; generate_sand_cell then embeds sand blocks.
        base_cell_class = {
            MATERIAL_AIR: AirCell,
            MATERIAL_WATER: WaterCell,
            MATERIAL_SAND: WaterCell,
            MATERIAL_BASALT: BasaltCell,
        }.get(self.material)

        if base_cell_class is None:
            return

        for x in range(LVL1_CHUNK_SIZE):
            for y in range(LVL1_CHUNK_SIZE):
                # x, y: values from 0 -> 15
                cx = (self.wx + x / LVL1_CHUNK_SIZE) * LVL1_CHUNK_SIZE
                cy = (self.wy + y / LVL1_CHUNK_SIZE) * LVL1_CHUNK_SIZE
                cell = base_cell_class((cx, cy))

                if isinstance(cell, WaterCell):
                    cell.particle_count = 3
                    if self.has_particles:
                        cell.create_particles()

                self.materials[(x, y)] = cell

        if self.material == MATERIAL_SAND:
            self.generate_sand_cell()

    def generate_sand_cell(self):
        REGION_SIZE = 4
        BLOCK_SIZE = 2

        for rx in range(0, LVL1_CHUNK_SIZE, REGION_SIZE):
            for ry in range(0, LVL1_CHUNK_SIZE, REGION_SIZE):

                local_positions = [
                    (x, y)
                    for x in range(rx, rx + REGION_SIZE - BLOCK_SIZE + 1)
                    for y in range(ry, ry + REGION_SIZE - BLOCK_SIZE + 1)
                ]

                x, y = random.choice(local_positions)

                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]

                for dx, dy in offsets:
                    lx, ly = x + dx, y + dy
                    # 0 - 15
                    cx = (self.wx + lx / LVL1_CHUNK_SIZE) * LVL1_CHUNK_SIZE
                    cy = (self.wy + ly / LVL1_CHUNK_SIZE) * LVL1_CHUNK_SIZE
                    self.materials[(lx, ly)] = SandCell((cx, cy))

    def draw(self, surface, camera):
        zoom = camera.zoom
        ox, oy = camera.offset

        chunk_world_x = self.wx * LVL1_CHUNK_SIZE * CELL_SIZE
        chunk_world_y = self.wy * LVL1_CHUNK_SIZE * CELL_SIZE

        chunk_pixel_size = LVL1_CHUNK_SIZE * CELL_SIZE * zoom

        if 0.10 < zoom < 0.5:
            pygame.draw.rect(
                surface,
                self.material_color,
                (
                    chunk_world_x * zoom + ox,
                    chunk_world_y * zoom + oy,
                    chunk_pixel_size,
                    chunk_pixel_size
                ),
                1
            )

        if zoom > 0.50:
            for bx in range(LVL1_CHUNK_SIZE):
                for by in range(LVL1_CHUNK_SIZE):
                    material = self.materials.get((bx, by))
                    if material is not None:
                        material.draw(surface, camera)


class GridCell:
    """Shared base for grid cells: position, drawing, entity tracking."""
    material_id = MATERIAL_AIR
    color = AIR
    density = 1

    def __init__(self, world_pos):
        self.wx, self.wy = world_pos
        self.entities = []

    def draw(self, surface, camera):
        zoom = camera.zoom
        ox, oy = camera.offset

        cell_world_x = self.wx * CELL_SIZE
        cell_world_y = self.wy * CELL_SIZE

        cell_pixel_size = CELL_SIZE * zoom

        pygame.draw.rect(
            surface,
            self.color,
            (
                cell_world_x * zoom + ox,
                cell_world_y * zoom + oy,
                cell_pixel_size,
                cell_pixel_size
            ),
            1
        )


class AirCell(GridCell):
    material_id = MATERIAL_AIR
    color = AIR
    density = 1


class SandCell(GridCell):
    material_id = MATERIAL_SAND
    color = SAND
    density = 1500

class BasaltCell(GridCell):
    material_id =  MATERIAL_BASALT
    color = BASALT
    density = 3000

class WaterCell(GridCell):
    material_id = MATERIAL_WATER
    color = BLUE
    density = 1000

    def __init__(self, world_pos, particle_count: int = 0):  # 0 - 15
        super().__init__(world_pos)
        self.particle_count = particle_count
        self.particles = []

    def _random_particle_pos(self):
        PADDING = 10
        px = int(
            self.wx * CELL_SIZE +
            PADDING +
            random.random() * (CELL_SIZE - 2 * PADDING)
        )
        py = int(
            self.wy * CELL_SIZE +
            PADDING +
            random.random() * (CELL_SIZE - 2 * PADDING)
        )
        return px, py

    def create_particles(self):
        for _ in range(self.particle_count):
            self.particles.append(Particle(self._random_particle_pos(), 0))

    def spawn_particle(self):
        self.particles.append(Particle(self._random_particle_pos(), 0))

    def add_particle(self, particle):
        self.particles.append(particle)

    def draw(self, surface, camera):
        super().draw(surface, camera)

        zoom = camera.zoom
        ox, oy = camera.offset
        for p in self.particles:
            p.draw_at(surface, ox, oy, zoom)


class Particle:
    def __init__(self, world_pos, type=0):
        self.x, self.y = world_pos
        self.type = type

        if type == 0:
            self.multiplier = 1
            self.radius = 2
            self.color = TEAL

        elif type == 1:
            self.multiplier = 5
            self.radius = 5
            self.color = MAGENTA

        else:
            self.multiplier = 0
            self.radius = 0
            self.color = (0, 0, 0)

    def draw_at(self, surface, ox, oy, zoom):
        sx = self.x * zoom + ox
        sy = self.y * zoom + oy

        pygame.draw.circle(
            surface,
            self.color,
            (int(sx), int(sy)),
            self.radius * zoom, 1
        )
