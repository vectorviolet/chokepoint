import pygame
from pygame.math import Vector2

from util.constants import TILE_SIZE, HALF_TILE
from gameplay.rotatable_object import RotatableObject
from pygamine import StateObject
from domain.game_state import GameState, TowerConfig

UPGRADE_BTN_OFFSET = Vector2(-55, -105)
SELL_BTN_OFFSET = Vector2(20, -110)
BTN_SIZE = (50, 50)

# Share of everything spent on a tower (purchase plus upgrades) refunded on sale.
SELL_REFUND = 0.7


class BaseTower(RotatableObject):
    def __init__(
        self, tower_type: int, row: int, col: int, config: TowerConfig, assets, audio
    ) -> None:
        super().__init__(
            assets.image_path(f"tower_{tower_type}_lvl1"),
            (col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE),
        )
        self.assets = assets
        self.audio = audio
        self._price_font = pygame.font.Font(assets.font_path("comic_neue"), 17)
        self.tower_type = tower_type
        self.row = row
        self.col = col
        self.level = 1
        self._config = config
        self.last_reload_time = 0
        self.bullets: list = []
        self.now: int = 0
        self.hp: int | None = self.maxHP

    # ── config-derived stats ──────────────────────────────────────────────────

    @property
    def range(self) -> int:
        return self._config.ranges[self.tower_type - 1][self.level - 1]

    @property
    def damage(self) -> int:
        return self._config.damages[self.tower_type - 1][self.level - 1]

    @property
    def speed(self) -> int:
        return self._config.speeds[self.tower_type - 1][self.level - 1]

    @property
    def max_level(self) -> int:
        return self._config.max_levels[self.tower_type - 1]

    @property
    def sell_price(self) -> int:
        spent = sum(self._config.prices[self.tower_type - 1][: self.level])
        return int(spent * SELL_REFUND)

    @property
    def upgrade_price(self) -> int:
        return self._config.prices[self.tower_type - 1][self.level]

    @property
    def buy_price(self) -> int:
        return self._config.prices[self.tower_type - 1][0]

    @property
    def shoot_sound(self) -> str | None:
        return self._config.shoot_sounds[self.tower_type - 1]

    @property
    def maxHP(self) -> int | None:
        hps = self._config.hps[self.tower_type - 1]
        if hps is None:
            return None
        return hps[self.level - 1]

    def is_max_level(self) -> bool:
        return self.level >= self.max_level

    def decrease_hp(self, damage: int) -> None:
        if self.hp is None:
            return
        self.hp -= damage

    # ── action hit-rects (screen space, zoom-aware) ───────────────────────────

    def _upgrade_hit_rect(self, camera) -> pygame.Rect:
        screen = camera.world_to_screen(self.position)
        return pygame.Rect(
            screen.x + UPGRADE_BTN_OFFSET.x,
            screen.y + UPGRADE_BTN_OFFSET.y,
            *BTN_SIZE,
        )

    def _sell_hit_rect(self, camera) -> pygame.Rect:
        screen = camera.world_to_screen(self.position)
        return pygame.Rect(
            screen.x + SELL_BTN_OFFSET.x,
            screen.y + SELL_BTN_OFFSET.y,
            *BTN_SIZE,
        )

    # ── shared actions ────────────────────────────────────────────────────────

    def upgrade(self, mouse_pos: tuple, game_state: GameState, camera) -> None:
        if self.is_max_level() or game_state.money < self.upgrade_price:
            return
        if not self._upgrade_hit_rect(camera).collidepoint(mouse_pos):
            return
        price = self.upgrade_price
        self.level += 1
        self.load(self.assets.image_path(f"tower_{self.tower_type}_lvl{self.level}"))
        self.hp = self.maxHP  # refill on upgrade
        game_state.decrease_money(price)
        game_state.selected_tower = self

    def sell(
        self, mouse_pos: tuple, game_state: GameState, towers: list, camera
    ) -> None:
        if game_state.selected_tower != self:
            return
        if self._sell_hit_rect(camera).collidepoint(mouse_pos):
            game_state.increase_money(self.sell_price)
            towers.remove(self)

    # ── shared rendering helpers ──────────────────────────────────────────────

    def draw_range(self, surface: pygame.Surface, camera) -> None:
        radius = int(self.range * camera.scale)
        if radius <= 0:
            return
        center = camera.world_to_screen(self.position)
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (128, 128, 128, 120), (radius, radius), radius, 0)
        pygame.draw.circle(surf, (0, 200, 0, 120), (radius, radius), radius, 2)
        surface.blit(surf, (center.x - radius, center.y - radius))

    def draw_selected_ui(
        self, surface: pygame.Surface, game_state: GameState, camera
    ) -> None:
        screen = camera.world_to_screen(self.position)

        sell_btn = StateObject(
            None, screen + SELL_BTN_OFFSET, BTN_SIZE, self.assets.image_path("btn_sell")
        )
        sell_text = self._price_font.render(f"{self.sell_price} $", 2, "white")

        if self.is_max_level():
            StateObject(
                None,
                screen + Vector2(-60, -85),
                (50, 25),
                self.assets.image_path("btn_max"),
            ).draw(surface)
        else:
            upgrade_btn = StateObject(
                None,
                screen + UPGRADE_BTN_OFFSET,
                BTN_SIZE,
                self.assets.image_path("btn_upgrade"),
            )
            upgrade_color = "green" if game_state.money >= self.upgrade_price else "red"
            upgrade_text = self._price_font.render(
                f"{self.upgrade_price} $", True, upgrade_color
            )
            surface.blit(upgrade_text, screen + Vector2(-50, -60))
            upgrade_btn.draw(surface)

        surface.blit(sell_text, screen + Vector2(30, -60))
        sell_btn.draw(surface)

    # ── polymorphic interface ─────────────────────────────────────────────────

    def should_remove(self) -> bool:
        return self.hp is not None and self.hp <= 0

    def get_blocking_position(self) -> tuple | None:
        return self.row, self.col

    def update(self, game_state: GameState, enemies: list) -> None:
        raise NotImplementedError

    def draw(self, game_state: GameState, camera, surface: pygame.Surface) -> None:
        raise NotImplementedError

    def work(self, enemies: list, is_started: bool) -> None:
        raise NotImplementedError
