from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from util.constants import TILE_SIZE, HALF_TILE
from util.text import money
from gameplay.rotatable_object import RotatableObject
from pygamine import StateObject
from domain.game_state import GameState, TowerConfig
from ui.range_ring import draw_range_ring

if TYPE_CHECKING:
    from domain.protocols import IGameContext

UPGRADE_BTN_OFFSET = Vector2(-55, -105)
SELL_BTN_OFFSET = Vector2(20, -110)
BTN_SIZE = (50, 50)

# Share of everything spent on a tower (purchase plus upgrades) refunded on sale.
SELL_REFUND = 0.7


class BaseTower(RotatableObject):
    # False: the battle draws this tower's bullets over it. A tower that
    # layers its own (the plane, with bombs under it) sets True.
    draws_own_bullets = False
    # True for a tower that flies (the plane): it's clicked by its sprite,
    # not its tile, and has no sell/upgrade buttons.
    is_flying = False

    def __init__(
        self, tower_type: int, row: int, col: int, config: TowerConfig, assets, audio
    ) -> None:
        super().__init__(
            assets.image_path(f"tower_{tower_type}_lvl1"),
            Vector2(col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE),
        )
        self.assets = assets
        self.audio = audio
        self._price_font = pygame.font.Font(assets.font_path("fira_sans"), 17)
        self.tower_type = tower_type
        self.row = row
        self.col = col
        self.level = 1
        self._config = config
        self.last_reload_time: float = 0
        self.bullets: list = []
        self.now: float = 0
        self.hp: int | None = self.max_hp
        # Lifetime record shown in the tower info panel (and saved): enemies
        # this tower dealt the killing blow to, and the kill money they paid.
        self.kills: int = 0
        # Whether its destruction was shown (ctx.tower_destroyed) already.
        self.destruction_reported = False
        self.money_earned: int = 0
        # Enemy HP this tower's shots/bombs took (overkill not counted).
        # Statistics only (the balance simulator reads it); not saved.
        self.damage_dealt: int = 0

    # ── config-derived stats ──────────────────────────────────────────────────

    @property
    def range(self) -> int:
        return self._config.ranges[self.tower_type - 1][self.level - 1]

    @property
    def min_range(self) -> int:
        """The blind spot's radius: enemies this close or closer can't be
        targeted. 0 for towers without one."""
        return _min_range(self._config, self.tower_type - 1, self.level - 1)

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
    def max_hp(self) -> int | None:
        hps = self._config.hps[self.tower_type - 1]
        if hps is None:
            return None
        return hps[self.level - 1]

    def is_max_level(self) -> bool:
        return self.level >= self.max_level

    def stats_at(self, level: int) -> dict[str, int | None]:
        """Config stats at any level of this tower's type -- the info panel
        previews the next level with it. reload_ms is the `speeds` entry
        (ms between shots for ground towers, movement for planes)."""
        i, j = self.tower_type - 1, level - 1
        hps = self._config.hps[i]
        return {
            "range": self._config.ranges[i][j],
            "min_range": _min_range(self._config, i, j),
            "damage": self._config.damages[i][j],
            "reload_ms": self._config.speeds[i][j],
            "max_hp": None if hps is None else hps[j],
        }

    def record_kill(self, money: int) -> None:
        """This tower's shot/bomb killed an enemy that paid `money`."""
        self.kills += 1
        self.money_earned += money

    def record_damage(self, amount: int) -> None:
        """This tower's shot/bomb took `amount` HP off an enemy."""
        self.damage_dealt += amount

    def decrease_hp(self, damage: int, ctx: "IGameContext", hit_from=None) -> None:
        """Takes `damage` off the HP, and shows the hit (`ctx.target_hit`,
        cosmetic) only when the damage was applied. `hit_from` is where the
        shot was (world), for the hit's spark; without one the spark shows
        on its center. A tower without HP (a plane) takes no damage and
        shows no hit. The hit that takes its HP to 0 or below reports it
        destroyed (`ctx.tower_destroyed`, cosmetic) right then, before the
        battle removes it on its next tick."""
        if self.hp is None:
            return
        was_standing = self.hp > 0
        self.hp -= damage
        # Cosmetic: the flash and spark, and its death effect.
        ctx.target_hit(self, self.position if hit_from is None else hit_from)
        if was_standing and self.hp <= 0:
            self.destruction_reported = True
            ctx.tower_destroyed(self)

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

    def hits_action_button(self, mouse_pos: tuple, camera) -> bool:
        """Whether mouse_pos is on this tower's upgrade (below max level) or
        sell button -- the buttons shown while it's selected. A destroyed
        tower shows and takes neither."""
        if self.is_destroyed():
            return False
        if self._sell_hit_rect(camera).collidepoint(mouse_pos):
            return True
        return not self.is_max_level() and self._upgrade_hit_rect(camera).collidepoint(
            mouse_pos
        )

    def is_destroyed(self) -> bool:
        """Its HP has run out (a tank's hit took it to 0 or below) but the
        battle hasn't removed it yet, which it does on its next tick. Such a
        tower can't be sold or upgraded, and shows no sell/upgrade buttons.
        Unlike should_remove(), which a plane also answers when it leaves
        the map, this is only about HP."""
        return self.hp is not None and self.hp <= 0

    def upgrade(self, mouse_pos: tuple, game_state: GameState, camera) -> None:
        if (
            self.is_destroyed()
            or self.is_max_level()
            or game_state.money < self.upgrade_price
        ):
            return
        if not self._upgrade_hit_rect(camera).collidepoint(mouse_pos):
            return
        price = self.upgrade_price
        self.level += 1
        self.load(self.assets.image_path(f"tower_{self.tower_type}_lvl{self.level}"))
        self.hp = self.max_hp  # refill on upgrade
        game_state.decrease_money(price)
        game_state.selected_tower = self

    def sell(
        self, mouse_pos: tuple, game_state: GameState, towers: list, camera
    ) -> None:
        """Sells the selected tower on a click on its sell button. A destroyed
        tower (`is_destroyed()`) can't be sold and pays no refund; its
        destruction effect plays as the battle removes it."""
        if game_state.selected_tower != self or self.is_destroyed():
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
        min_radius = int(self.min_range * camera.scale)
        draw_range_ring(surface, center, radius, (0, 200, 0, 120), 2, min_radius)

    def draw_selected_ui(
        self, surface: pygame.Surface, game_state: GameState, camera
    ) -> None:
        if self.is_destroyed():
            return  # no refund or upgrade price on a dead tower
        screen = camera.world_to_screen(self.position)

        sell_btn = StateObject(
            None, screen + SELL_BTN_OFFSET, BTN_SIZE, self.assets.image_path("btn_sell")
        )
        sell_text = self._price_font.render(money(self.sell_price), True, "white")

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
                money(self.upgrade_price), True, upgrade_color
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

    # Takes the battle's state, unlike GameObject.update() (mypy: override).
    def update(self, game_state: GameState, enemies: list, enemy_grid=None) -> None:  # type: ignore[override]
        """One tick. `enemy_grid` is the tick's gameplay.combat.targeting
        .EnemyGrid of `enemies` (or None), for towers that look for targets."""
        raise NotImplementedError

    # Draws through the camera, unlike GameObject.draw() (mypy: override).
    def draw(self, game_state: GameState, camera, surface: pygame.Surface) -> None:  # type: ignore[override]
        raise NotImplementedError

    def work(self, enemies: list, is_started: bool, enemy_grid=None) -> None:
        raise NotImplementedError


def _min_range(config: TowerConfig, i: int, j: int) -> int:
    """config.min_ranges[i][j], or 0 if the config has none for that tower
    (a TowerConfig built without min_ranges)."""
    if i < len(config.min_ranges):
        return config.min_ranges[i][j]
    return 0
