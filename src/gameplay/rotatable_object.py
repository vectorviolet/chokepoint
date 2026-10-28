from typing import override
import pygame
from pygame.math import Vector2

from pygamine import angle_of_delta
from pygamine import ImagePath, PathLike
from pygamine import SpriteRenderer2D
from pygamine import StateObject


# Angle (atan2 / screen-coord convention) the sprite's "forward" points in its source PNG.
FACE_RIGHT = 0
FACE_DOWN = 90
FACE_LEFT = 180
FACE_UP = -90


class RotatableObject(StateObject):
    def __init__(
        self,
        image_path: ImagePath,
        pos: Vector2,
        sprite_orientation: float = FACE_RIGHT,
    ):
        self.position = Vector2(
            pos
        )  # must precede super() — ImageObject.__init__ triggers self.load(), which reads self.position
        super().__init__(pos=pos, image_path=image_path)
        self.rect.center = pos
        self.rotated_image: pygame.Surface | None = None
        self.is_rotated = False
        self.sprite_orientation = sprite_orientation

    def load(
        self, path: PathLike, size: tuple[int, int] = (0, 0), nine_slice: int = 0
    ) -> None:
        self._size = size
        self._nine_slice = nine_slice
        self.add_state(self._state, path)
        self.rect.center = self.position
        self.is_rotated = False

    def rotate_to_delta(self, delta: Vector2) -> None:
        if delta.length_squared() == 0:
            return

        self.rotate_to_angle(angle_of_delta(delta))

    def rotate_to_angle(self, angle: float) -> None:
        rotation = self.sprite_orientation - angle
        self.rotated_image = pygame.transform.rotate(
            self.get_component(SpriteRenderer2D).image, rotation
        )
        self.rect.size = self.rotated_image.get_size()
        self.rect.center = self.position
        self.is_rotated = True

    @override
    def draw(self, surface: pygame.Surface) -> None:
        if self.is_rotated and self.rotated_image is not None:
            surface.blit(self.rotated_image, self.rect)
        else:
            super().draw(surface)

    @property
    @override
    def image(self) -> pygame.Surface | None:
        # Drawable.image (see pygamine's camera.py): camera.draw() reads
        # this directly now instead of checking is_rotated/rotated_image
        # itself, so the rotation switch lives here instead.
        if self.is_rotated and self.rotated_image is not None:
            return self.rotated_image
        return super().image
