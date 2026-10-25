import pygame
from pygame.math import Vector2

from gameplay.rotatable_object import RotatableObject
from domain.game_state import GameState, TowerConfig
from gameplay.combat.projectile import MuzzleFlash, Projectile
from towers.base_tower import BaseTower

BARREL_FORWARD = 26  # px from tower center to barrel tip along aim direction
BARREL_SPREAD = 8  # px lateral offset from center for twin-barrel towers


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

    def update(self, game_state: GameState, enemies: list) -> None:
        self.now = game_state.time_ms
        self.work(enemies, game_state.is_started)

    def draw(self, game_state: GameState, camera, surface: pygame.Surface) -> None:
        camera.draw(surface, self.platform)

        if game_state.selected_tower is self:
            self.draw_range(surface, camera)

        camera.draw(surface, self)

    def work(self, enemies: list, is_started: bool) -> None:
        if not is_started or not enemies:
            return

        distances = [enemy.position - self.position for enemy in enemies]
        lengths = [d.length() for d in distances]
        nearest_dist = min(lengths)
        nearest_idx = lengths.index(nearest_dist)

        if nearest_dist > self.range:
            return

        self.rotate_to_delta(distances[nearest_idx])

        if self._is_attack_ready():
            self._shoot(enemies[nearest_idx])

    # ── private ───────────────────────────────────────────────────────────────

    def _is_attack_ready(self) -> bool:
        return self.now - self.last_reload_time > self.speed

    def _shoot(self, target) -> None:
        if self.tower_type in (1, 3):
            for pos, deals_damage in self._muzzle_positions(target):
                self.bullets.append(MuzzleFlash(target, self, pos, deals_damage))
        else:
            self.bullets.append(Projectile(target, self))
        if self.shoot_sound is not None:
            self.audio.play_sfx(str(self.assets.sound_path(self.shoot_sound)))
        self.last_reload_time = self.now

    def _muzzle_positions(self, target) -> list[tuple[Vector2, bool]]:
        fwd = (target.position - self.position).normalize()
        perp = Vector2(-fwd.y, fwd.x)
        tip = self.position + fwd * BARREL_FORWARD

        twin = self.tower_type == 1 or (self.tower_type == 3 and self.level == 2)
        if twin:
            return [
                (tip + perp * BARREL_SPREAD, True),
                (tip - perp * BARREL_SPREAD, False),
            ]
        return [(tip, True)]
