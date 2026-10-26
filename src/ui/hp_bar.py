"""Tiny HP bar drawn above an entity in world space.

Only renders when hp is below max — entities at full health show nothing.
The bar scales with camera zoom and uses a 3-stop colour ramp
(green -> yellow -> red) to make low health read at a glance.
"""

import pygame

BAR_WIDTH = 36
BAR_HEIGHT = 4
DEFAULT_OFFSET = 30  # world-px from entity center to bar bottom
BG_COLOR = (40, 40, 40)
BORDER_COLOR = (0, 0, 0)


def health_color(ratio: float) -> tuple[int, int, int]:
    if ratio > 0.6:
        return (80, 220, 80)
    if ratio > 0.3:
        return (220, 200, 60)
    return (220, 60, 60)


def draw(
    surface: pygame.Surface,
    camera,
    world_pos,
    hp,
    max_hp,
    offset: int = DEFAULT_OFFSET,
    force: bool = False,
) -> None:
    if max_hp is None or hp is None:
        return
    if not force and hp >= max_hp:
        return
    ratio = max(0.0, min(1.0, hp / max_hp))
    center = camera.world_to_screen(world_pos)

    w = max(2, int(BAR_WIDTH * camera.scale))
    h = max(2, int(BAR_HEIGHT * camera.scale))
    off = int(offset * camera.scale)
    x = int(center.x - w / 2)
    y = int(center.y - off - h)

    pygame.draw.rect(surface, BG_COLOR, (x, y, w, h))
    pygame.draw.rect(surface, health_color(ratio), (x, y, max(0, int(w * ratio)), h))
    pygame.draw.rect(surface, BORDER_COLOR, (x, y, w, h), 1)
