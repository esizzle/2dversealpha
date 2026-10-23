"""Decision models: interchangeable movement strategies for organisms.

An organism (your Cell) owns exactly one DecisionModel, chosen from its genome
by create_decision_model(). Each frame the sim asks the model for a *desired
direction*; the organism itself decides how to act on it (Cell.apply_movement).

Design contract
---------------
* decide() returns a desired direction as a Vec2d of length 0..1 -- never a
  velocity, force, or energy change. Its direction is where the organism wants
  to go; its length is how strongly (1 = full thrust). Cell.apply_movement
  already scales the push by it. A model never reads or writes body.velocity,
  energy, mass, etc. This keeps "what do I want to do" fully separate from
  "how does my body do it", which is the whole point of the split.
* Vec2d.zero() means "no preference this frame" (coast / stay put).
* Drives that pull in opposite directions must be allowed to cancel into a
  SHORT vector. Never re-normalise a near-zero sum: that turns leftover noise
  into full thrust in a random direction, and the cell jitters in place
  ("decision paralysis" -- see claude/decision-paralysis-diagnosis.md).
* Any per-organism perception a model wants to remember (memory, smell trails,
  last-seen prey, ...) lives on the *model instance*, not on the Cell, so each
  capability stays self-contained.

On future capabilities
-----------------------
Today the models form a linear ladder (Level 0..3B) and the factory branches on
a single integer, because that's all the first four levels need. The ladder is a
convenience, not a load-bearing assumption: nothing requires level N to be a
strict superset of N-1. When capabilities stop being linear -- memory, food /
light sensing, smell, kin & species recognition, planning -- add sibling models
or compose them, and change only create_decision_model(). No caller changes.
"""

import math
import random

from pymunk import Vec2d

from world_grid import SandCell


# ----------------------------------------------------------------------
# Shared perception helpers (so models don't each re-implement grid math)
# ----------------------------------------------------------------------
def _random_unit():
    a = random.uniform(0, 2 * math.pi)
    return Vec2d(math.cos(a), math.sin(a))


def   _safe_normalize(vec):
    return vec.normalized() if vec.length > 1e-9 else Vec2d.zero()


def _clamp_length(vec, max_length=1.0):
    """Cap a vector's length at max_length WITHOUT stretching short ones. Use
    this, not _safe_normalize, wherever drives are combined, so drives that
    cancel out give a weak push instead of a random full-strength one."""
    length = vec.length
    if length > max_length:
        return vec * (max_length / length)
    return vec


def _neighbor_terrain(organism, world):
    """Yield (offset, grid_cell) for the 8 grid cells around the organism.

    `offset` points from the organism's cell toward the neighbour, so a model can
    weight it directly. Neighbours outside loaded chunks come back None and are
    skipped -- terrain sensing reads the logical grid, so it works even where no
    physics colliders are loaded.
    """
    gx, gy = world.world_to_grid_cell(organism.body.position)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            cell = world.get_lvl1_chunk_local_cell((gx + dx, gy + dy))
            if cell is not None:
                yield Vec2d(dx, dy), cell

def _terrain_steer(organism, world):
    """A push away from solid terrain (sand). May be zero. Shared by every model
    from Level 1 up, so terrain awareness is never re-derived per level."""
    steer = Vec2d.zero()
    for offset, cell in _neighbor_terrain(organism, world):
        if isinstance(cell, SandCell):
            steer -= offset  # move opposite the sand
    return steer

def _particle_steer(organism, world):
    """Returns a steering vector toward the closest nearby particle."""

    if not organism.nearby_particles:
        return Vec2d.zero()

    pos = organism.body.position

    closest_particle = None
    closest_dist_sq = float("inf")

    for particle in organism.nearby_particles:
        dx = particle.x - pos.x
        dy = particle.y - pos.y
        dist_sq = dx * dx + dy * dy

        if dist_sq < closest_dist_sq:
            closest_dist_sq = dist_sq
            closest_particle = particle

    return Vec2d(
        closest_particle.x - pos.x,
        closest_particle.y - pos.y
    )

def _perceived_cells(organism):
    """Other organisms this organism can currently perceive. Populated by
    World.update_entity into organism.nearby_entities (refreshed on grid-cell
    change), so this is cheap and slightly stale -- fine for v1.

    Cells of the organism's OWN animal body (same Multicell, see multicell.py)
    are left out: they are part of "me", not neighbours. Without this a head
    spends most of its attention on its own body -- pulled back into its tail
    (positive attraction) or shoved forward into terrain (negative)."""
    own = getattr(organism, "multicell", None)
    return [c for c in organism.nearby_entities
            if c is not organism and not c.is_dead
            and (own is None or getattr(c, "multicell", None) is not own)]


def _weighted_social(organism, others, weight_fn):
    """Sum of (unit direction to each other) * weight_fn(other), capped at
    length 1.

    Each contribution is a *unit* direction, so distance doesn't distort the
    sign; the weight (the gene) sets how strongly it pulls. A negative weight
    flips a contribution from attraction into avoidance. The sum is capped,
    not normalised, so a weak gene (e.g. +0.1) gives a weak social drive
    instead of a full-strength one. Empty / all-zero -> Vec2d.zero().
    """
    here = organism.body.position
    accum = Vec2d.zero()
    for other in others:
        accum += _safe_normalize(other.body.position - here) * weight_fn(other)
    return _clamp_length(accum)


# ----------------------------------------------------------------------
# Cell-wall-aware feeding / spacing steering (unlocked at the cell-aware tier)
# ----------------------------------------------------------------------
# The whole "cooperation" effect is just two simple, unscripted forces:
#   * plant cells  (has_cell_wall == True)  -> attract  (they are food)
#   * animal cells (has_cell_wall == False) -> repel    (personal space)
# Two animals drawn to the same plant push each other apart and settle on
# different sides -- no flanking, roles, teams or pack logic is coded anywhere.
#
# These are plain module constants (not genes) so they stay trivially tunable.
# Promote them to Genome fields later if you want the weights to evolve.
PLANT_ATTRACTION = 1.0         # strength of pull toward a walled (plant) cell
ANIMAL_REPULSION = 0.0         # magnitude of push away from another animal
PLANT_SOFT_RADIUS = 0.0       # px: inside this the plant pull eases off, so a
                               #     plant you're sitting on can't slingshot you
ANIMAL_PERSONAL_SPACE = 20.0  # px: repulsion acts only within this radius
FEEDING_STEER_CLAMP = 1.5      # cap on the combined feeding vector before it is
                               #     blended with terrain/wander (keeps it from
                               #     swamping obstacle avoidance)

_PLANT_SOFT_SQ = PLANT_SOFT_RADIUS ** 2
_PERSONAL_SPACE_SQ = ANIMAL_PERSONAL_SPACE ** 2
_MIN_DIST_SQ = 1.0             # closer than ~1px counts as "overlapping"

# Flip on to record per-model steering debug data (drawn by main.py when on).
# Off by default: when False, decide() does zero extra work.
DEBUG_SOCIAL_STEERING = False

# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
class DecisionModel:
    """Abstract movement strategy. Subclasses implement decide()."""

    name = "base"  # handy label for a mutation / debug overlay

    def decide(self, organism, world):
        """Return a desired direction (Vec2d, length 0..1); Vec2d.zero() == no
        preference. Must not mutate the organism's physical state."""
        raise NotImplementedError

    def seed_heading(self, direction):
        """Optional hint: the organism is already travelling along `direction`
        (a unit (x, y)), e.g. a daughter cell leaving a split. Models that keep
        a wander heading adopt it, so they carry on the way they were going
        instead of turning on the spot. Still direction-only -- a model never
        touches physics. Default: ignore the hint."""
        pass


class RandomDecisionModel(DecisionModel):
    """Level 0 -- no perception. A slow random walk, the baseline for organisms
    in nutrient-rich water where perception has no payoff."""
    name = "random"

    def __init__(self):
        self._heading = _random_unit()

    def decide(self, organism, world):
        self._heading = _random_unit()
        return self._heading

    def seed_heading(self, direction):
        self._heading = Vec2d(direction[0], direction[1])


class TerrainDecisionModel(DecisionModel):
    """Level 1 -- senses adjacent sand/water and steers around solid terrain,
    wandering when nothing is nearby."""
    name = "terrain"

    def __init__(self):
        self._wander = _random_unit()

    def decide(self, organism, world):
        if random.random() < 0.01:
            self._wander = _random_unit()
        steer = _terrain_steer(organism, world)
        # avoidance dominates when terrain is close, otherwise the wander shows
        return _safe_normalize(steer * organism.genome.terrain_avoidance + self._wander)

    def seed_heading(self, direction):
        self._wander = Vec2d(direction[0], direction[1])

class NutrientDecisionModel(RandomDecisionModel):
    name = "nutrient"

    def __init__(self):
        super().__init__()

    def decide(self, organism, world):
        base = super().decide(organism, world)  # wander (no terrain sensing yet)
        p_steer = _particle_steer(organism, world)
        return _safe_normalize(base + p_steer * 0.5)

class CellAwareDecisionModel(NutrientDecisionModel):
    """Cell-aware tier (reached via 3A/3B) -- everything Nutrient does, PLUS it
    perceives nearby organisms (excluding its own animal body). Higher levels
    add their genome-driven social layer on top of this.
    """
    name = "cell_aware"

    def __init__(self):
        super().__init__()
        self.perceived = []
        self.debug_info = None  # populated only when DEBUG_SOCIAL_STEERING

    def decide(self, organism, world):
        self.perceived = _perceived_cells(organism)
        base = super().decide(organism, world)           # wander + food
        final = _safe_normalize(base)

        if DEBUG_SOCIAL_STEERING:
            self.debug_info = {
                "base": base,
                "final": final,
                "n_plants": sum(1 for c in self.perceived if c.has_cell_wall),
                "n_animals": sum(1 for c in self.perceived if not c.has_cell_wall),
            }

        return final


class AttractionDecisionModel(CellAwareDecisionModel):
    """Level 3A -- a single genome.cell_attraction in [-1, 1] blends steering
    toward (+) or away from (-) the perceived organisms, on top of the food /
    wander drive. The gene's size is its strength: food and social pulls that
    disagree cancel into a weak push rather than a random full-strength one."""
    name = "attraction"

    def decide(self, organism, world):
        base = super().decide(organism, world)  # wander + food, unit length
        a = organism.genome.cell_attraction
        social = _weighted_social(organism, self.perceived, lambda other: a)
        return _clamp_length(base + social)

class TypeAwareDecisionModel(AttractionDecisionModel):
    name = "type_aware"

    def __init__(self):
        super().__init__()

    def decide(self, organism, world):
        base = super().decide(organism, world)
        weight = organism.genome.wall_cell_attraction
        # only walled (plant) cells pull on this organism; unwalled cells
        # are handled by the cell_attraction gene in the parent model
        social = _weighted_social(organism, self.perceived,
                                  lambda other: weight if other.has_cell_wall else 0.0)

        return _clamp_length(base + social)



class SizeAwareDecisionModel(CellAwareDecisionModel):
    """Level 3B -- two genes, smaller_cell_attraction and larger_cell_attraction,
    each in [-1, 1]. Per-cell size comparison picks which gene applies, so
    predator / social / fearful / etc. emerge from the values alone, e.g.
        smaller=+1, larger=-1 -> predator (chase small, flee big)
        smaller=-1, larger=-1 -> solitary / fearful (avoid everyone)
        smaller=+1, larger=+1 -> highly social (approach everyone)
    """
    name = "size_aware"

    def decide(self, organism, world):
        base = super().decide(organism, world)  # wander + food
        g = organism.genome

        def weight(other):
            if other.size < organism.size:
                return g.smaller_cell_attraction
            return g.larger_cell_attraction

        social = _weighted_social(organism, self.perceived, weight)
        return _clamp_length(base + social)


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------
# Intelligence is a single int today (3 == Level 3A, 4 == Level 3B). When
# capabilities decouple from one ladder, branch on individual genome flags here
# -- this is the only place that needs to change.
_MODELS_BY_LEVEL = {
    0: RandomDecisionModel,
    1: TerrainDecisionModel,
    2: NutrientDecisionModel,
    #2: CellAwareDecisionModel,
    3: AttractionDecisionModel,   # 3A
    4: TypeAwareDecisionModel,
    #4: SizeAwareDecisionModel,    # 3B
}


def create_decision_model(genome):
    """Return the decision model a genome calls for, defaulting to random."""
    level = getattr(genome, "intelligence", 0)
    return _MODELS_BY_LEVEL.get(level, RandomDecisionModel)()
