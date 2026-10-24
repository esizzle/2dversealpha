
from cell import *


class Player:
    def __init__(self, position, space = None):
        default_genome = Genome()
        self.cell = Cell(position, default_genome, True)
        self.cell.shape.filter = pymunk.ShapeFilter(group=1)
        space.add(self.cell.body, self.cell.shape)