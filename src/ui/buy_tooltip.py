"""The buy button tooltip: hovering a tower's buy button shows its name and
one line each for what it's good and bad at.

The tooltip's objects are declared in config/panels.yaml (`buy_tooltip_*` on
the game panel), so they scale and are styled with the rest of the HUD; the
texts come from config/towers.yaml (`name` + `tooltip`). This module fills
them in, widens the background to the longest line, and moves the tooltip
above the hovered button, clamped to the screen. It's hidden while the HUD
is hidden or sliding (Tab), and takes no clicks or hover itself.
"""

import pygame
from pygamine import PanelManager

from ui.hud_slide import BUY_BUTTONS
from util.config_loader import TowerTooltip

BG = "buy_tooltip_bg"
TEXTS = (
    "buy_tooltip_title_text",
    "buy_tooltip_strength_label",
    "buy_tooltip_weakness_label",
    "buy_tooltip_strength_text",
    "buy_tooltip_weakness_text",
)
BUY_TOOLTIP_OBJECTS = (BG, *TEXTS)
GAP = 8  # px between the tooltip and the top of the tower bar


class BuyTooltip:
    """Shows a tower's tooltip over its buy button while it's hovered."""

    def __init__(
        self,
        panel_manager: PanelManager,
        canvas: tuple[int, int],
        tooltips: dict[int, TowerTooltip],
    ) -> None:
        self.tooltips = tooltips
        self.tower_type: int | None = None
        self.rebind(panel_manager, canvas)

    def rebind(self, panel_manager: PanelManager, canvas: tuple[int, int]) -> None:
        """Pick up the objects of a freshly (re)built game panel."""
        panel = panel_manager["game"]
        self._screen = pygame.Rect((0, 0), canvas)
        self._bg = panel[BG]
        self._texts = [panel[name] for name in TEXTS]
        self._objects = [self._bg, *self._texts]
        self._buttons = [panel[name] for name in BUY_BUTTONS]
        self._bar = panel["tower_panel_bg"]
        # The background colour as panels.yaml set it, for re-sizing it.
        self._bg_color = self._bg.images[None].get_at((0, 0))
        # Left padding (the title's offset) is mirrored on the right.
        self._pad = self._texts[0].rect.left - self._bg.rect.left
        for obj in self._objects:
            obj.visible = False  # decorative: never blocks a click or hover
            obj.active = False  # rebuilt objects start shown; re-open below
        shown, self.tower_type = self.tower_type, None
        self.show(shown)

    @property
    def is_open(self) -> bool:
        return self.tower_type is not None

    def update(self, mouse_pos, hud_shown: bool) -> None:
        """Show the hovered buy button's tooltip, or hide it. Buttons that
        slid away with the HUD take no hover, and the tooltip stays hidden
        until the HUD has settled back in place."""
        hovered = None
        if hud_shown:
            for tower_type, button in enumerate(self._buttons, start=1):
                if button.is_mouse_over(mouse_pos):
                    hovered = tower_type
                    break
        self.show(hovered)

    def show(self, tower_type: int | None) -> None:
        """Open the tooltip for `tower_type` above its button, or close it with
        None. Cheap to call every frame: nothing changes when it's the same."""
        if tower_type is not None and tower_type not in self.tooltips:
            tower_type = None
        if tower_type == self.tower_type:
            return
        self.tower_type = tower_type
        for obj in self._objects:
            obj.active = tower_type is not None
        if tower_type is None:
            return
        tip = self.tooltips[tower_type]
        title, _, _, strength, weakness = self._texts
        title.set_text(tip.name)
        strength.set_text(tip.strength)
        weakness.set_text(tip.weakness)
        self._fit_width()
        self._place(self._buttons[tower_type - 1].rect)

    def _fit_width(self) -> None:
        """Widen (or narrow) the background to the longest line."""
        bg = self._bg
        right = max(obj.rect.right for obj in self._texts)
        size = (right - bg.rect.left + self._pad, bg.rect.height)
        if size == bg.rect.size:
            return
        surface = pygame.Surface(size, pygame.SRCALPHA)
        surface.fill(self._bg_color)
        bg.rect.size = size
        bg.add_surface(None, surface)

    def _place(self, button: pygame.Rect) -> None:
        """Centred above the button, clear of the tower bar (and the 1-4
        badges on it), clamped to the screen."""
        bg = self._bg.rect
        target = bg.copy()
        target.centerx = button.centerx
        target.bottom = min(button.top, self._bar.rect.top) - GAP
        target.clamp_ip(self._screen)
        dx, dy = target.x - bg.x, target.y - bg.y
        for obj in self._objects:
            obj.rect.move_ip(dx, dy)
