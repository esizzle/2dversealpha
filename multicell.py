"""Multicellularity: the physical links between cells.

For now multicellularity is purely physical -- a PinJoint between two cell
bodies. Each cell still owns its own mass, energy, feeding, movement and
splitting; nothing is shared through a joint.

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
    in case the size gene mutated."""
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
# Growth direction: the ONLY thing plants and fungi do differently
# ----------------------------------------------------------------------
# Kinds of walled multicell, from existing traits only (no fungus gene):
#   plant  = multicellular AND cell wall AND chloroplast
#   fungus = multicellular AND cell wall AND NOT chloroplast
def is_multicellular_walled(cell):
    return cell.multicellular and cell.has_cell_wall


def is_fungal(cell):
    return is_multicellular_walled(cell) and not cell.has_chloroplast


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


def begin_multicellular_split(parent, d1, d2, axis):
    """Start a multicellular division using the normal mitosis animation.

    Both daughters start on the parent's spot in the "splitting" state, so
    they render as one pinching silhouette and ignore each other's
    collisions, exactly like an ordinary split. The differences:
      * d1 takes the parent's place: it inherits all of the parent's links
        right away and is NOT pushed by the split -- physics keeps owning it,
        so those links stay where they were;
      * d2 slides out alone along the velocity axis, and the pair finishes
        when their edges meet (d1.size + d2.size apart) instead of when the
        squares' corners clear;
      * at that moment Cell.update_split joins d1 and d2 (see join_cells)
        and gives them equal and opposite drift (see finish_multicellular_split).

    The parent's own velocity is NOT carried into the daughters: velocities
    are directional (d1 one way, d2 the other), never stacked on top of the
    parent's drift, so a drifting plant that divides doesn't speed up.

    `axis` is the world-space unit growth direction (growth_direction).
    Plants' axes run along the parent's own x/y axes, so the daughters keep
    the parent's rotation. A fungal axis can point anywhere, so the
    daughters are turned to face it -- that keeps the facing edges flush at
    the normal joint length (joints are centre to centre, so turning d1
    doesn't disturb the links it inherits)."""
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
