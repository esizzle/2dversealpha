import pygame


class Camera:
    def __init__(self, type = 1, position = (0,0), zoom = 1.0, rotation = 0):
        self.x, self.y = position
        self.offset = -self.x, -self.y
        self.speed = 1
        self.zoom = zoom
        self.zoom_speed = 0.025
        self.rotation = rotation
        self.type = type

    def update(self, obj = None, width = None, height = None):
        if self.type == 1:
            self.offset = -self.x, -self.y
        else:
            self.x = (obj.position[0] * self.zoom) - width / 2
            self.y = (obj.position[1] * self.zoom) - height / 2
            self.offset = -self.x, -self.y

    def screen_to_world(self, screen_x, screen_y):
        """Inverse of the draw transform (screen = world * zoom + offset,
        offset = (-x, -y)) for a point in world-window pixel coordinates."""
        return (screen_x + self.x) / self.zoom, (screen_y + self.y) / self.zoom

    def world_center(self, width, height):
        """World-space point at the centre of a `width` x `height` view.
        This is the audio listener position: in follow mode (type 0) it is
        exactly the followed body's position; in free mode (type 1) it is
        wherever the player has panned the view to."""
        return self.screen_to_world(width / 2, height / 2)


    def handle_input(self, events, keys):
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_x, mouse_y = pygame.mouse.get_pos()
                world_x = (mouse_x + self.x) / self.zoom
                world_y = (mouse_y + self.y) / self.zoom

                if event.button == 4:  # Scroll up to zoom in
                    self.zoom += self.zoom_speed
                elif event.button == 5:  # Scroll down to zoom out
                    self.zoom = max(self.zoom - self.zoom_speed, 0.01)
                else:
                    pass

                # Recalculate camera offset to keep world_x/y under the cursor fixed
                self.x = -mouse_x + world_x * self.zoom
                self.y = -mouse_y + world_y * self.zoom

        speed = self.speed * (2 if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] else 1)

        if keys[pygame.K_a]:
            self.x -= speed
        if keys[pygame.K_d]:
            self.x += speed
        if keys[pygame.K_w]:
            self.y -= speed
        if keys[pygame.K_s]:
            self.y += speed

