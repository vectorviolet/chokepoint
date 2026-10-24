import pygame

SCROLL_SPEED = 0.7   # px per tick (util.constants.TICK_MS)


class MenuBackground:
    """Slowly pans a pre-rendered map surface behind menu panels."""

    _SCALE = 2

    def __init__(self, map_surface: pygame.Surface, viewport: tuple[int, int]) -> None:
        mw, mh = map_surface.get_size()
        vw, vh = viewport

        bg_w = mw * self._SCALE
        bg_h = mh * self._SCALE
        self._bg    = pygame.transform.smoothscale(map_surface, (bg_w, bg_h))
        self._max_x = float(max(0, bg_w - vw))
        self._max_y = float(max(0, bg_h - vh))
        self._vw = vw
        self._vh = vh
        self._x  = 0.0
        self._y  = 0.0
        self._dx = SCROLL_SPEED
        self._dy = SCROLL_SPEED

    def update(self, ticks: float = 1.0) -> None:
        """Pan by `ticks` ticks' worth of SCROLL_SPEED (fractional is fine)."""
        self._x += self._dx * ticks
        self._y += self._dy * ticks
        if self._x >= self._max_x or self._x <= 0:
            self._dx = -self._dx
            self._x  = max(0.0, min(self._max_x, self._x))
        if self._y >= self._max_y or self._y <= 0:
            self._dy = -self._dy
            self._y  = max(0.0, min(self._max_y, self._y))

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self._bg, (0, 0),
                     (int(self._x), int(self._y), self._vw, self._vh))