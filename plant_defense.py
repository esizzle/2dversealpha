"""Plant defence: exposed corners of a plant (walled, square) cell kill a
LARGER cell that runs into them.

Event-driven: Game.on_cell_pre_solve (main.py) calls check_vertex_defense
only while an unwalled cell is actually touching a plant, so nothing here
runs per cell or per frame on its own. Per contact the work is:
  1. a size comparison            (almost always stops here)
  2. 4 vertex distance checks
  3. for a hit vertex: one point query per directly joined neighbour
All geometry uses the bodies' CURRENT world position and rotation, so it
stays correct for flexible, rotated multicellular plants -- no grid, no
whole-organism outline.
"""

from global_constants import (
    PLANT_VERTEX_DEFENSE,
    PLANT_VERTEX_HIT_RADIUS,
    PLANT_VERTEX_COVER_TOLERANCE,
)


def plant_vertices_world(plant):
    """The plant square's four corners in world coordinates, using the
    body's current position AND rotation (Poly vertices are stored in the
    body's local frame)."""
    body = plant.body
    return [body.local_to_world(v) for v in plant.shape.get_vertices()]


def vertex_is_exposed(plant, vertex):
    """A corner is covered when it lies inside -- or within
    PLANT_VERTEX_COVER_TOLERANCE px of -- the shape of a plant cell this one
    is directly joined to. Only direct neighbours are checked (plant.joints),
    never the whole organism."""
    for neighbour in plant.joints:
        if neighbour.is_dead or not neighbour.has_cell_wall:
            continue
        info = neighbour.shape.point_query(vertex)   # distance < 0 == inside
        if info.distance <= PLANT_VERTEX_COVER_TOLERANCE:
            return False
    return True


def hit_exposed_vertex(plant, contact_points):
    """True if any contact point on the plant's surface is within
    PLANT_VERTEX_HIT_RADIUS of an exposed corner."""
    r_sq = PLANT_VERTEX_HIT_RADIUS * PLANT_VERTEX_HIT_RADIUS
    vertices = None
    for point in contact_points:
        if vertices is None:
            vertices = plant_vertices_world(plant)
        for v in vertices:
            dx = point.x - v.x
            dy = point.y - v.y
            if dx * dx + dy * dy <= r_sq and vertex_is_exposed(plant, v):
                return True
    return False


def check_vertex_defense(attacker, plant, arbiter):
    """Called from the unwalled<->walled pre_solve. Kills `attacker` through
    the normal Cell.kill() path (which respects invulnerability and only
    flags is_dead; Game.kill_cell removes it and its joints later in the
    frame) if it is larger than the plant and touching an exposed corner.
    Returns True if it killed the attacker."""
    if not PLANT_VERTEX_DEFENSE:
        return False
    if attacker.is_dead or plant.is_dead:
        return False                      # already dying: no duplicate kill
    if attacker.size <= plant.size:
        return False                      # equal / smaller cells are safe
    if not plant.has_cell_wall:
        return False

    # point_b is the contact point on shape b -- the plant, because the
    # (1, 2) handler always orders shapes unwalled first, walled second
    points = [cp.point_b for cp in arbiter.contact_point_set.points]
    if not points or not hit_exposed_vertex(plant, points):
        return False
    return attacker.kill(plant)
