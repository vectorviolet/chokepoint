import math
from collections import OrderedDict
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

# Rotated images shared by every object, least recently used dropped first:
# (source surface, rotation step) -> the source rotated by that much. The
# bound keeps it small whatever the sources are (shared load_image()
# surfaces, or a scaled copy per object): a 64 px sprite rotates to at most
# 91x91 px (33 KB), so 512 entries hold at most about 17 MB. The turrets'
# sprites need 8 x 180 steps in all; a step dropped is re-rotated (tens of
# microseconds) the next time it is drawn.
MAX_CACHED_ROTATIONS = 512
_rotation_cache: OrderedDict[tuple[pygame.Surface, int], pygame.Surface] = OrderedDict()


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
    """`angle` rounded to the nearest ANGLE_STEP (halves round up), wrapped
    to [-180, 180)."""
    return int(wrap_angle(math.floor(angle / ANGLE_STEP + 0.5) * ANGLE_STEP))


def cached_rotation(source: pygame.Surface, rotation: int) -> pygame.Surface:
    """`source` rotated by `rotation` degrees (counter-clockwise, as
    pygame.transform.rotate), from the shared LRU cache."""
    key = (source, rotation)
    rotated = _rotation_cache.get(key)
    if rotated is None:
        rotated = pygame.transform.rotate(source, rotation)
        _rotation_cache[key] = rotated
        if len(_rotation_cache) > MAX_CACHED_ROTATIONS:
            _rotation_cache.popitem(last=False)
    else:
        _rotation_cache.move_to_end(key)
    return rotated


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
        # The renderer StateObject added, looked up once through the public API.
        self._sprite: SpriteRenderer2D = self.require_component(SpriteRenderer2D)
        self.rect.center = pos
        self.rotated_image: pygame.Surface | None = None
        self.is_rotated = False
        self.sprite_orientation = sprite_orientation
        # The (source image, rotation step) rotate_to_angle_cached() drew.
        self._rotation_key: tuple[pygame.Surface, int] | None = None

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
        source = self._sprite_image()
        rotation = self.sprite_orientation - angle
        self.rotated_image = pygame.transform.rotate(source, rotation)
        self.rect.size = self.rotated_image.get_size()
        self.rect.center = self.position
        self.is_rotated = True

    def rotate_to_angle_cached(self, angle: float) -> None:
        """Like rotate_to_angle(), for a sprite that turns smoothly and is
        called every tick: the angle is rounded to ANGLE_STEP, nothing is
        done while the (image, step) pair is unchanged, and rotated images
        come from a shared bounded cache. The rect is re-centered on the
        position, so the sprite keeps its center at every angle."""
        source = self._sprite_image()
        rotation = quantise_angle(self.sprite_orientation - angle)
        if (
            self.is_rotated
            and self.rotated_image is not None
            and self._rotation_key == (source, rotation)
        ):
            return
        self._rotation_key = (source, rotation)
        self.rotated_image = cached_rotation(source, rotation)
        self.rect.size = self.rotated_image.get_size()
        self.rect.center = self.position
        self.is_rotated = True

    def _sprite_image(self) -> pygame.Surface:
        """The unrotated sprite: every RotatableObject is built with one."""
        return self._sprite.require_image()

    @override
    def draw(self, surface: pygame.Surface) -> None:
        if self.is_rotated and self.rotated_image is not None:
            surface.blit(self.rotated_image, self.rect)
        else:
            super().draw(surface)

    # Read-only on purpose: the sprite changes through load() and the
    # renderer, never by assigning `image` (which pygamine's setter allows).
    @property  # type: ignore[misc]
    @override
    def image(self) -> pygame.Surface | None:
        # Drawable.image (see pygamine's camera.py): camera.draw() reads
        # this directly now instead of checking is_rotated/rotated_image
        # itself, so the rotation switch lives here instead.
        if self.is_rotated and self.rotated_image is not None:
            return self.rotated_image
        return super().image
