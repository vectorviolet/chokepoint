"""The selected enemy's HP as numbers ("320 / 420"), drawn just right of
its in-world HP bar.

The text is a fixed screen size (it doesn't scale with the camera zoom) so
it stays readable when zoomed out, in the tower info panel's Anton font with
a dark outline over the map, like the kill reward's "+$N".
"""

import pygame

from ui import hp_bar

FONT_SIZE = 16
TEXT_COLOR = (255, 255, 255)
OUTLINE_COLOR = (20, 20, 20)
GAP = 4  # screen px between the bar's right end and the text


def hp_text(enemy) -> str:
    """ "current / max", both whole numbers, current never below 0."""
    return f"{max(0, int(enemy.hp))} / {int(enemy.maxHP)}"


class EnemyHpLabel:
    def __init__(self, font_path) -> None:
        self._font = pygame.font.Font(font_path, FONT_SIZE)
        self._text: str | None = None
        self._label: pygame.Surface | None = None

    def draw(self, surface: pygame.Surface, camera, enemy) -> None:
        """Draws `enemy`'s HP numbers next to its bar (nothing for None).
        Cheap every frame: the label is only re-rendered when it changes."""
        if enemy is None:
            return
        label = self._render(hp_text(enemy))
        bar = hp_bar.bar_rect(camera, enemy.position)
        surface.blit(label, label.get_rect(midleft=(bar.right + GAP, bar.centery)))

    def _render(self, text: str) -> pygame.Surface:
        if text != self._text:
            self._text = text
            self._label = _outlined(self._font, text)
        return self._label


def _outlined(font: pygame.font.Font, text: str) -> pygame.Surface:
    fill = font.render(text, True, TEXT_COLOR)
    outline = font.render(text, True, OUTLINE_COLOR)
    label = pygame.Surface(
        (fill.get_width() + 2, fill.get_height() + 2), pygame.SRCALPHA
    )
    for dx in (0, 1, 2):
        for dy in (0, 1, 2):
            if (dx, dy) != (1, 1):
                label.blit(outline, (dx, dy))
    label.blit(fill, (1, 1))
    return label
