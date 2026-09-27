import pymunk

# create a class to initialize pymunk parameters
def init_cell_physics(mass, size, position, has_cell_wall = False):
    if not has_cell_wall:
        moment = pymunk.moment_for_circle(mass, 0, size)
        body = pymunk.Body(mass, moment, pymunk.Body.DYNAMIC)
        body.position = position
        shape = pymunk.Circle(body, size)
        shape.filter = pymunk.ShapeFilter(group=1)
        shape.elasticity = 0.0
        shape.collision_type = 1

    else:
        moment = pymunk.moment_for_box(mass, (size*2, size*2))
        body = pymunk.Body(mass, moment, pymunk.Body.DYNAMIC)
        body.position = position
        shape = pymunk.Poly.create_box(body, (size*2,size*2))
        shape.elasticity = 0.0
        shape.collision_type = 2


    return body, shape

# create body's for sand cells
# TODO: Abstract to all materials
# collision_type defaults to 0 (unclassified terrain, e.g. basalt). Sand is
# tagged with type 3 by its caller so the game can hook cell<->sand contacts
# (see the collision handlers in main.py). Cells themselves are 1/2 above.
def sand_body(position, collision_type=0):
    moment = pymunk.moment_for_box(4, (40, 40))
    body = pymunk.Body(4, moment, pymunk.Body.STATIC)
    body.position = position
    shape = pymunk.Poly.create_box(body, (40, 40))
    shape.collision_type = collision_type

    return body, shape

# one solid static square of side `size` centred on `position` -- used for the
# world's boundary walls, which cover a whole chunk with a single shape
def static_box(position, size, collision_type=0):
    body = pymunk.Body(body_type=pymunk.Body.STATIC)
    body.position = position
    shape = pymunk.Poly.create_box(body, (size, size))
    shape.collision_type = collision_type

    return body, shape
