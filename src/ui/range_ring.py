"""The range ring drawn around a selected tower and under the placement
cursor: a translucent grey disc out to the tower's range with a coloured
outline. A tower with a blind spot (the heavy cannon's minimum range,
issue #11) gets a hole in the disc out to that radius, edged by a thin
ring in the same colour, so the area it can't shoot at reads as uncovered.
"""

import pygame

FILL = (128, 128, 128, 120)
CLEAR = (0, 0, 0, 0)
BLIND_SPOT_WIDTH = 2  # px; the inner ring stays thinner than the outer one


def draw_range_ring(
    surface: pygame.Surface,
    center,
    radius: int,
    outline: tuple,
    width: int,
    min_radius: int = 0,
) -> None:
    """Blit a ring of `radius` screen px centred on `center`, outlined in
    `outline` `width` px wide, with a blind spot out to `min_radius` (none
    when 0)."""
    if radius <= 0:
        return
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    mid = (radius, radius)
    pygame.draw.circle(surf, FILL, mid, radius, 0)
    if 0 < min_radius < radius:
        # Drawing on an SRCALPHA surface replaces pixels, so this cuts a
        # transparent hole in the disc rather than blending into it.
        pygame.draw.circle(surf, CLEAR, mid, min_radius, 0)
        pygame.draw.circle(surf, outline, mid, min_radius, BLIND_SPOT_WIDTH)
    pygame.draw.circle(surf, outline, mid, radius, width)
    surface.blit(surf, (center[0] - radius, center[1] - radius))
