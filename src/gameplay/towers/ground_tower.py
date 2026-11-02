import math

import pygame
from pygame.math import Vector2

from pygamine import angle_of_delta
from gameplay.rotatable_object import RotatableObject, quantise_angle, turn_toward
from domain.game_state import GameState, TowerConfig
from gameplay.combat.projectile import MuzzleFlash, Projectile
from gameplay.combat.targeting import EnemyGrid
from gameplay.towers.base_tower import BaseTower

BARREL_FORWARD = 26  # px from tower center to barrel tip along aim direction
BARREL_SPREAD = 8  # px lateral offset from center for twin-barrel towers
# How fast the drawn barrel turns toward its target, in degrees per second of
# game time (so pause freezes it and x2/x4 speed it up). Cosmetic only: aim,
# firing and damage don't wait for it, and a shot fired mid-turn flashes at
# the barrel as drawn. The fastest enemy (speed 1.6 px/tick, 264 px/s)
# passing a tower a tile away sweeps about 240 deg/s, so this keeps up with
# it with room to spare; a retarget still shows as a turn (90 degrees in
# about 0.17 s, half a circle in a third of a second) while the barrel lags
# its shots only briefly.
TURN_RATE_DEG_PER_S = 540


class GroundTower(BaseTower):
    """Stationary tower that aims at the nearest enemy and fires projectiles.

    Covers tower types 1, 2, and 3 — all share the same behavioural contract so
    Liskov substitution holds: a GroundTower can replace any other GroundTower
    without callers noticing.
    """

    def __init__(
        self, tower_type: int, row: int, col: int, config: TowerConfig, assets, audio
    ) -> None:
        super().__init__(tower_type, row, col, config, assets, audio)
        self.platform = RotatableObject(
            assets.image_path(f"tower_{tower_type}_platform"),
            self.position,
        )
        # The angle the barrel is drawn at (atan2 convention, degrees) and
        # the one it is turning toward: the last target's direction, None
        # until the tower first aims. Neither is saved; a loaded tower
        # faces its sprite's default way until it aims again.
        self.barrel_angle: float = float(self.sprite_orientation)
        self.aim_angle: float | None = None
        self._drawn_step: int | None = None

    def update(
        self, game_state: GameState, enemies: list, enemy_grid: EnemyGrid | None = None
    ) -> None:
        elapsed_ms = max(0.0, game_state.time_ms - self.now)
        self.now = game_state.time_ms
        self.work(enemies, game_state.is_started, enemy_grid, elapsed_ms)

    def draw(self, game_state: GameState, camera, surface: pygame.Surface) -> None:
        camera.draw(surface, self.platform)

        if game_state.selected_tower is self:
            self.draw_range(surface, camera)

        camera.draw(surface, self)

    def work(
        self,
        enemies: list,
        is_started: bool,
        enemy_grid: EnemyGrid | None = None,
        elapsed_ms: float = 0.0,
    ) -> None:
        """Aim at the nearest enemy within range and outside the blind spot
        (min_range < distance <= range; the first one in `enemies` on a
        tie) and fire when reloaded. The choice is made afresh every tick,
        so an enemy that walks into the blind spot is dropped for the next
        nearest one outside it. `enemy_grid` is this tick's grid
        of `enemies`, shared by all towers; without one, a grid is built
        just for this call.

        The drawn barrel then turns toward the aim by at most
        TURN_RATE_DEG_PER_S over `elapsed_ms` of game time (it keeps turning
        toward the last aim when no enemy is in range). It is cosmetic:
        a shot fires on reload whichever way the barrel is drawn."""
        target = None
        if is_started and enemies:
            if enemy_grid is None or enemy_grid.enemies is not enemies:
                enemy_grid = EnemyGrid(enemies)
            target, delta = enemy_grid.nearest_in_range(
                self.position, self.range, self.min_range
            )
            if target is not None and delta.length_squared() != 0:
                self.aim_angle = angle_of_delta(delta)

        self._turn_barrel(elapsed_ms)

        if target is not None and self._is_attack_ready():
            self._shoot(target)

    # ── private ───────────────────────────────────────────────────────────────

    def _turn_barrel(self, elapsed_ms: float) -> None:
        if self.aim_angle is None:
            return
        max_step = TURN_RATE_DEG_PER_S * elapsed_ms / 1000
        self.barrel_angle = turn_toward(self.barrel_angle, self.aim_angle, max_step)
        # Re-render only when the drawn step changes, or after load() (an
        # upgrade) put back the unrotated image.
        step = quantise_angle(self.barrel_angle)
        if step != self._drawn_step or not self.is_rotated:
            self.rotate_to_angle_cached(self.barrel_angle)
            self._drawn_step = step

    def _is_attack_ready(self) -> bool:
        return self.now - self.last_reload_time > self.speed

    def _shoot(self, target) -> None:
        if self.tower_type in (1, 3):
            for pos, deals_damage in self._muzzle_positions():
                self.bullets.append(
                    MuzzleFlash(target, self, pos, deals_damage, self.barrel_angle)
                )
        else:
            self.bullets.append(Projectile(target, self))
        if self.shoot_sound is not None:
            self.audio.play_sfx(str(self.assets.sound_path(self.shoot_sound)))
        self.last_reload_time = self.now

    def _muzzle_positions(self) -> list[tuple[Vector2, bool]]:
        """The barrel tips as drawn (along barrel_angle, not straight at the
        target): where the muzzle flashes appear. The first deals the
        damage; the flashes' positions don't affect it."""
        rad = math.radians(self.barrel_angle)
        fwd = Vector2(math.cos(rad), math.sin(rad))
        perp = Vector2(-fwd.y, fwd.x)
        tip = self.position + fwd * BARREL_FORWARD

        twin = self.tower_type == 1 or (self.tower_type == 3 and self.level == 2)
        if twin:
            return [
                (tip + perp * BARREL_SPREAD, True),
                (tip - perp * BARREL_SPREAD, False),
            ]
        return [(tip, True)]
