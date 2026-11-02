import math
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

# rotate_to_angle_cached() draws angles rounded to this many degrees: at the
# turrets' 26 px barrel length a step moves the tip under a pixel.
ANGLE_STEP = 2

# (source surface, quantised angle) -> the source rotated by that angle onto
# a fixed-size square canvas. The sources are load_image()'s cached
# surfaces, so this stays small: one entry per image and angle step.
_rotation_cache: dict[tuple[pygame.Surface, int], pygame.Surface] = {}


def wrap_angle(angle: float) -> float:
    """`angle` in degrees, brought into [-180, 180)."""
    return (angle + 180) % 360 - 180


def turn_toward(current: float, target: float, max_step: float) -> float:
    """`current` turned toward `target` by at most `max_step` degrees, the
    shortest way round (across the +-180 seam when that's shorter). The
    result is wrapped to [-180, 180); it is `target` itself once within
    reach."""
    diff = wrap_angle(target - current)
    if abs(diff) <= max_step:
        return wrap_angle(target)
    return wrap_angle(current + math.copysign(max_step, diff))


def quantise_angle(angle: float) -> int:
    """`angle` rounded to the nearest ANGLE_STEP, wrapped to [-180, 180)."""
    return int(wrap_angle(round(angle / ANGLE_STEP) * ANGLE_STEP))


def rotated_on_canvas(source: pygame.Surface, rotation: int) -> pygame.Surface:
    """`source` rotated by `rotation` degrees (counter-clockwise, as
    pygame.transform.rotate) and centred on a square canvas big enough for
    any rotation of it, so every angle gives the same size and the sprite's
    centre never shifts between frames. Cached."""
    key = (source, rotation)
    cached = _rotation_cache.get(key)
    if cached is None:
        w, h = source.get_size()
        side = math.ceil(math.hypot(w, h))
        side += side % 2  # even, like the 64 px sources: centres stay whole
        rotated = pygame.transform.rotate(source, rotation)
        cached = pygame.Surface((side, side), pygame.SRCALPHA)
        cached.blit(rotated, rotated.get_rect(center=(side // 2, side // 2)))
        _rotation_cache[key] = cached
    return cached


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

    def rotate_to_angle_cached(self, angle: float) -> None:
        """Like rotate_to_angle(), for a sprite that turns smoothly every
        tick: the angle is rounded to ANGLE_STEP and the rotated image comes
        from a shared cache on a fixed-size canvas, so the sprite neither
        wobbles nor re-rotates every tick."""
        rotation = quantise_angle(self.sprite_orientation - angle)
        self.rotated_image = rotated_on_canvas(
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
