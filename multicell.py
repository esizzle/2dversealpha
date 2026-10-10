"""Multicellularity: the physical links between cells, and (for animals) the
organism they form.

For now multicellularity is purely physical -- a PinJoint between two cell
bodies. Each cell still owns its own mass, energy, feeding, movement and
splitting; nothing is shared through a joint. The one organism-level thing
is animal movement: only an animal organism's head decides the direction,
and every other member swims that way too (see steering_head).

Bookkeeping
-----------
Every cell has `joints`, a dict {neighbour_cell: pymunk.PinJoint}. A link is
stored on BOTH cells and both entries point at the SAME joint object, so

    a.joints[b] is b.joints[a]

That symmetry is the invariant every helper here maintains:
  * one joint per pair (join_cells refuses duplicates),
  * a joint is only ever removed through remove_joint, which drops both dict
    entries and removes the constraint from the space exactly once,
  * no cell keeps a key for a cell it is no longer linked to.

Joint shape
-----------
Joints run centre to centre and their length is the two cells' sizes added
together (size is the half-width of a walled square / the radius of a round
cell), so linked cells sit edge against edge with no gap.
"""

import math
import random

import pymunk

from global_constants import (
    SPLIT_SPEED,
    SPLIT_DRIFT_SPEED,
    FUNGAL_SENSE_RADIUS,
    FUNGAL_MIN_GRADIENT,
    FUNGAL_DISTANCE_FALLOFF,
)


def join_distance(a, b):
    """Centre-to-centre length that puts two cells edge against edge."""
    return a.size + b.size


def join_cells(a, b):
    """Link cells a and b with a centre-to-centre PinJoint of length
    a.size + b.size. Returns the joint, or the existing one if they are
    already linked."""
    if a is b:
        return None
    existing = a.joints.get(b)
    if existing is not None:
        return existing                      # never two joints on one pair

    joint = pymunk.PinJoint(a.body, b.body, (0, 0), (0, 0))
    joint.distance = join_distance(a, b)
    joint.collide_bodies = True              # linked cells still collide
    space = a.body.space or b.body.space
    if space is not None:
        space.add(joint)

    a.joints[b] = joint
    b.joints[a] = joint
    return joint


def remove_joint(a, b):
    """Unlink a and b. Safe to call when they are not linked, or when the
    constraint has already left the space."""
    joint = a.joints.pop(b, None)
    other = b.joints.pop(a, None)
    joint = joint or other
    if joint is None:
        return
    space = a.body.space or b.body.space
    if space is not None and joint in space.constraints:
        space.remove(joint)


def remove_all_joints(cell):
    """Unlink `cell` from every neighbour. Call BEFORE its body leaves the
    space, so no constraint is left pointing at a removed body."""
    for neighbour in list(cell.joints):
        remove_joint(cell, neighbour)


def inherit_joints(parent, heir):
    """Move every link of `parent` onto `heir` (the daughter that takes the
    parent's place). Each old joint is removed -- it references the parent's
    body, which is about to be destroyed -- and a new one is made between the
    heir and the same neighbour, sized for the heir (heir.size + neighbour.size)
    in case the size gene mutated. Works for any number of joints."""
    for neighbour in list(parent.joints):
        remove_joint(parent, neighbour)
        if neighbour.is_dead:
            # dying this frame (eaten / starved): kill_cell would only
            # unlink it again, so don't re-link
            continue
        join_cells(heir, neighbour)


def division_axis(body, min_speed):
    """World-space unit vector along which a multicellular cell divides:
    whichever of the body's OWN x / y axes its velocity is mostly along,
    pointing the way it is travelling (so a rotated square still divides
    edge-to-edge). Below `min_speed` there is no meaningful direction, so a
    random side is picked."""
    velocity = body.velocity
    if velocity.length < min_speed:
        local = random.choice([pymunk.Vec2d(1, 0), pymunk.Vec2d(-1, 0),
                               pymunk.Vec2d(0, 1), pymunk.Vec2d(0, -1)])
    else:
        v = velocity.rotated(-body.angle)
        if abs(v.x) >= abs(v.y):
            local = pymunk.Vec2d(1 if v.x > 0 else -1, 0)
        else:
            local = pymunk.Vec2d(0, 1 if v.y > 0 else -1)
    return local.rotated(body.angle)


# ----------------------------------------------------------------------
# Growth direction: the ONLY thing plants, fungi and animals do differently
# ----------------------------------------------------------------------
# Kinds of multicell, from existing traits only (no new genes):
#   plant  = multicellular AND cell wall AND chloroplast
#   fungus = multicellular AND cell wall AND NOT chloroplast
#   animal = multicellular AND NO cell wall AND NO chloroplast
def is_multicellular_walled(cell):
    return cell.multicellular and cell.has_cell_wall


def is_fungal(cell):
    return is_multicellular_walled(cell) and not cell.has_chloroplast


def is_multicellular_animal(cell):
    return cell.multicellular and not cell.has_cell_wall and not cell.has_chloroplast


def food_gradient(cell, world):
    """Cheap, local pseudo food gradient around ONE cell (the one splitting).

    Reads the food particles in a fixed (2R+1)^2 window of grid cells around
    the cell (R = FUNGAL_SENSE_RADIUS) straight from the world grid, where
    particles live on their WaterCell -- no global search, no joints, nothing
    from the rest of the organism -- and sums

        unit direction to particle * particle.multiplier / distance**k

    with k = FUNGAL_DISTANCE_FALLOFF. A gentle falloff (0.5) lets closer food
    count a bit more while a cluster still outweighs one nearby particle.

    Returns a unit Vec2d, or None if there is no food in the window or the
    food around the cell doesn't agree on a direction: the length of the sum
    divided by the total weight (0 = pulls cancel out, 1 = all food on one
    side) must be at least FUNGAL_MIN_GRADIENT."""
    if world is None:
        return None
    here = cell.body.position
    gx, gy = world.world_to_grid_cell(here)
    r = FUNGAL_SENSE_RADIUS
    k = FUNGAL_DISTANCE_FALLOFF
    sx = sy = total = 0.0
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            grid_cell = world.get_lvl1_chunk_local_cell((gx + dx, gy + dy))
            particles = getattr(grid_cell, "particles", None)
            if not particles:
                continue
            for p in particles:
                vx = p.x - here.x
                vy = p.y - here.y
                d = math.hypot(vx, vy)
                if d < 1.0:
                    continue          # sitting on it: no direction
                w = p.multiplier / d ** k
                sx += vx / d * w
                sy += vy / d * w
                total += w
    if total <= 0.0 or math.hypot(sx, sy) < FUNGAL_MIN_GRADIENT * total:
        return None
    return pymunk.Vec2d(sx, sy).normalized()


def growth_direction(parent, world, min_speed):
    """World-space unit vector the outward daughter grows along.
    plant  -> the parent's velocity axis (division_axis)
    fungus -> its own local food gradient, falling back to the velocity
              axis when there is no useful gradient."""
    if is_fungal(parent):
        towards_food = food_gradient(parent, world)
        if towards_food is not None:
            return towards_food
    return division_axis(parent.body, min_speed)


def animal_growth_direction(parent, split_direction):
    """World-space unit vector an animal's budding daughter slides out along.

    `split_direction` is the axis an ordinary split would send daughter 2
    along (Cell.split passes the opposite of the direction of travel, or a
    random direction when nearly at rest). A cell with no links -- a lone
    cell founding an organism -- uses it unchanged, so the bud trails behind
    the moving head.

    A linked cell buds AWAY from its neighbours instead: unwalled cells never
    collide with each other (shared ShapeFilter group), so a bud sent along
    the direction of travel would slide straight through the next cell in
    the body. Away-from-neighbours makes a tail extend outward and a body
    cell bud sideways, which is where branches come from. When the pulls
    cancel (a body cell in a straight line), the bud goes out at a right
    angle to the line, on a random side."""
    here = parent.body.position
    away = pymunk.Vec2d(0.0, 0.0)
    first = None
    for neighbour in parent.joints:
        offset = neighbour.body.position - here
        if offset.length < 1e-6:
            continue
        unit = offset.normalized()
        first = first or unit
        away -= unit
    if first is None:
        return pymunk.Vec2d(*split_direction).normalized()
    if away.length < 1e-3:
        side = random.choice((1, -1))
        return pymunk.Vec2d(-first.y * side, first.x * side)
    return away.normalized()


def begin_multicellular_split(parent, d1, d2, axis):
    """Start a multicellular division using the normal mitosis animation.

    Both daughters start on the parent's spot in the "splitting" state, so
    they render as one pinching silhouette and ignore each other's
    collisions, exactly like an ordinary split. The differences:
      * d1 takes the parent's place: it inherits all of the parent's links
        right away and is NOT pushed by the split -- physics keeps owning it,
        so those links stay where they were;
      * d2 slides out alone along the growth axis, and the pair finishes
        when their edges meet (d1.size + d2.size apart) instead of when the
        squares' corners clear;
      * at that moment Cell.update_split joins d1 and d2 (see join_cells)
        and gives them equal and opposite drift (see finish_multicellular_split).

    The parent's own velocity is NOT carried into the daughters: velocities
    are directional (d1 one way, d2 the other), never stacked on top of the
    parent's drift, so a drifting plant that divides doesn't speed up.

    `axis` is the world-space unit growth direction (growth_direction for
    plants / fungi, animal_growth_direction for animals). Plants' axes run
    along the parent's own x/y axes, so the daughters keep the parent's
    rotation. Any other axis can point anywhere, so the daughters are turned
    to face it -- that keeps walled facing edges flush at the normal joint
    length (joints are centre to centre, so turning d1 doesn't disturb the
    links it inherits; for round animal cells the angle is cosmetic)."""
    speed = parent.body.velocity.length

    local = axis.rotated(-parent.body.angle)
    on_own_axis = abs(abs(local.x) - 1.0) < 1e-6 or abs(abs(local.y) - 1.0) < 1e-6
    angle = parent.body.angle if on_own_axis else math.atan2(axis.y, axis.x)

    for daughter in (d1, d2):
        daughter.body.angle = angle
        daughter.body.angular_velocity = parent.body.angular_velocity
    d1.body.velocity = (0.0, 0.0)             # parent's drift is not inherited

    inherit_joints(parent, d1)

    d1.begin_split(d2, (0.0, 0.0), speed, True, joins=True)
    d2.begin_split(d1, (axis.x, axis.y), speed, False, joins=True)
    d2.body.velocity = d1.body.velocity + axis * SPLIT_SPEED    # relative to d1


def finish_multicellular_split(a, b):
    """The pair's edges have met: join them and send them off in opposite
    directions along the division axis at SPLIT_DRIFT_SPEED -- d2 outward,
    d1 back the other way. Equal and opposite, so across the joint they
    cancel out and the pair doesn't fly off (the velocities are SET, not
    added to whatever the cells already had)."""
    mover, stayer = (a, b) if (a.split_direction[0] or a.split_direction[1]) else (b, a)
    ax, ay = mover.split_direction
    mover.body.velocity = (ax * SPLIT_DRIFT_SPEED, ay * SPLIT_DRIFT_SPEED)
    stayer.body.velocity = (-ax * SPLIT_DRIFT_SPEED, -ay * SPLIT_DRIFT_SPEED)
    join_cells(a, b)


# ----------------------------------------------------------------------
# Animal organisms
# ----------------------------------------------------------------------
def structural_links(cell):
    """Cells `cell` is physically connected to: its joints, plus -- while a
    multicellular division is still sliding apart -- its split sibling, whose
    joint only appears when the edges meet. Counting that pending link keeps
    a half-finished bud part of its organism if a death elsewhere forces a
    connectivity check mid-split."""
    links = list(cell.joints)
    sibling = cell.split_sibling
    if (sibling is not None and cell.split_joins and sibling not in cell.joints
            and cell.is_split_sibling_of(sibling)):
        links.append(sibling)
    return links


# Collisions inside an organism
# -----------------------------
# Unwalled cells share ShapeFilter group 1, so they never collide with each
# other. A cell that joins an animal organism leaves that group (group 0),
# so its contacts with other unwalled cells reach Game.on_animal_pair_begin,
# which lets only cells of the SAME organism collide. Cells outside any
# organism keep group 1 and are filtered as before, so nothing changes for
# them and the broadphase stays cheap.
_MEMBER_FILTER = pymunk.ShapeFilter()


def _join_organism(cell, organism):
    """Make `cell` a member of `organism` (the only place membership is
    set) and let it collide with its fellow members."""
    cell.multicell = organism
    if not cell.has_cell_wall:
        cell.shape.filter = _MEMBER_FILTER


def members_collide(a, b):
    """Collision rule for two unwalled cells whose contact got past the
    shape filter: they collide only if they belong to the same animal
    organism -- except a pair still pulling apart from a split, which must
    overlap until they separate (the usual mitosis rule)."""
    return same_organism(a, b) and not a.is_split_sibling_of(b)


class Multicell:
    """One animal organism: a connected group of linked animal cells.

        cells -- every member, in a stable order (founder first, buds after)
        head  -- the member that steers the organism (player input or AI)
        tails -- every non-head member with exactly one link

    Tails are DERIVED from the joints by refresh_tails() after each structural
    change (a split, a death), never maintained by hand. Valid shapes:
    a lone cell (head, no tails), a pair (head + one tail), a branching body
    (several tails), and a closed loop (several cells, no tails).

    Structure only changes in two ways, kept strictly apart:
      * reproductive replacement -- replace_parent(), called from Cell.split:
        the parent's slot goes to its daughters in one step, so the organism
        never sees the parent "die";
      * actual death -- remove() from Game.kill_cell, then rebuild() once per
        frame after every death has been processed, which finds the connected
        components and gives each its own Multicell with a valid head."""

    def __init__(self, cells, head):
        self.cells = []
        self.head = head
        self.tails = []
        for cell in cells:
            _join_organism(cell, self)
            self.cells.append(cell)
        self.refresh_tails()

    # -- queries -------------------------------------------------------
    def degree(self, cell):
        """Number of links `cell` has to other members of this organism."""
        return sum(1 for n in structural_links(cell) if n.multicell is self)

    def refresh_tails(self):
        self.tails = [c for c in self.cells
                      if c is not self.head and self.degree(c) == 1]

    # -- reproductive replacement --------------------------------------
    def replace_parent(self, parent, d1, d2):
        """`parent` has just split into d1 (which took its place and its
        joints) and d2 (budding off d1). Swap them in as one operation: d1
        takes the parent's slot and, if the parent was the head, the head
        role; d2 joins the organism. Call AFTER begin_multicellular_split so
        the links are already in place when the tails are recomputed."""
        index = self.cells.index(parent)
        self.cells[index] = d1
        self.cells.append(d2)
        _join_organism(d1, self)
        _join_organism(d2, self)
        parent.multicell = None
        if self.head is parent:
            self.head = d1
        self.refresh_tails()

    # -- actual death --------------------------------------------------
    def remove(self, cell):
        """A member has died for real (its joints are already gone). Only
        the membership changes here; call rebuild() once all of this frame's
        deaths are in, so the structure is checked once, not per death."""
        if cell in self.cells:
            self.cells.remove(cell)
        cell.multicell = None
        if self.head is cell:
            self.head = None

    def rebuild(self):
        """Split this organism into its connected components (iterative DFS
        over structural_links, limited to members) and give each one a valid
        head and tails. This object is kept for the component that holds the
        surviving head -- or, if the head died, for the largest component --
        and every other component gets a new Multicell.

        Returns the surviving organisms, this one first; [] if no members
        are left."""
        members = set(self.cells)
        seen = set()
        components = []
        for start in self.cells:                 # stable order -> deterministic
            if start in seen:
                continue
            found = {start}
            seen.add(start)
            stack = [start]
            while stack:
                cell = stack.pop()
                for neighbour in structural_links(cell):
                    if neighbour in members and neighbour not in seen:
                        seen.add(neighbour)
                        found.add(neighbour)
                        stack.append(neighbour)
            components.append([c for c in self.cells if c in found])

        if not components:
            self.cells = []
            self.tails = []
            self.head = None
            return []

        if self.head is not None:
            kept = next(comp for comp in components if self.head in comp)
        else:
            kept = max(components, key=len)      # first of the largest on ties

        self.cells = kept
        if self.head is None:
            self.head = choose_head(kept)
        self.refresh_tails()

        organisms = [self]
        for comp in components:
            if comp is not kept:
                organisms.append(Multicell(comp, choose_head(comp)))
        return organisms


def choose_head(cells):
    """Deterministic replacement head for a group of connected cells: the
    first terminal cell (exactly one link inside the group), else the first
    cell. Cells already marked dead (removed next frame) come last."""
    group = set(cells)

    def degree(cell):
        return sum(1 for n in structural_links(cell) if n in group)

    living = [c for c in cells if not c.is_dead] or list(cells)
    for cell in living:
        if degree(cell) == 1:
            return cell
    return living[0]


# ----------------------------------------------------------------------
# Hooks used by Cell.split and Game (cell.py / main.py)
# ----------------------------------------------------------------------
def adopt_daughters(parent, d1, d2):
    """Reproductive replacement: `parent` has just split into d1 (which took
    its place and its joints) and d2. A lone animal cell founds a new
    organism with itself as head first, so every split of an animal goes
    through the same Multicell.replace_parent. After this the parent belongs
    to no organism, so its removal in Game.kill_cell is NOT a death as far
    as the organism is concerned -- no connectivity check, no new head."""
    organism = parent.multicell
    if organism is None:
        organism = Multicell([parent], parent)
    organism.replace_parent(parent, d1, d2)
    return organism


def is_steering(cell):
    """Only an organism's head makes movement decisions (player input or
    AI). Cells outside any organism steer themselves as before."""
    organism = cell.multicell
    return organism is None or organism.head is cell


def steering_head(cell):
    """The head whose steering `cell` follows, or None if `cell` steers
    itself (a head, or a cell outside any organism).

    Agar.io-style animal movement: the head decides the direction (player
    input or its decision model) and every body cell swims that same way
    under its own power -- same input, own acceleration and speed cap -- so
    the whole body flows together instead of the head dragging the rest on
    its joints. See Game.handle_inputs (player) and the AI branch of
    Game.update."""
    organism = cell.multicell
    if organism is None or organism.head is cell:
        return None
    return organism.head


def same_organism(a, b):
    """True if a and b are members of the same animal organism."""
    return a.multicell is not None and a.multicell is b.multicell
