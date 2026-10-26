"""Tank enemy — a heavy walker with an independently rotating muzzle that
fires at the nearest turret. On hit, the turret is destroyed outright (no
HP system on towers for now).

E5 / E6 share this class; they differ only in the asset key suffix and the
stats loaded from config/enemies.yaml.
"""

from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from gameplay.combat.enemy import Enemy, _BASE_STATS
from gameplay.rotatable_object import RotatableObject
from pygamine import load_image
from pygamine import angle_between_delta, angle_between_points

if TYPE_CHECKING:
    from domain.protocols import IGameContext


def _given(value: int | None, default: int) -> int:
    return default if value is None else value


class Tank(Enemy):
    MUZZLE_TIP_FORWARD = 55  # px from tank center to muzzle tip along aim direction

    def __init__(
        self, id: int, enemy_type: int, level: int, waypoints: list[Vector2], assets
    ) -> None:
        super().__init__(id, enemy_type, level, waypoints, assets)
        self.assets = assets

        stats = _BASE_STATS[enemy_type]
        # None means "not in enemies.yaml"; an explicit 0 is kept.
        self.range: int = _given(stats.range, 280)
        self.fire_interval_ms: int = _given(stats.fire_interval_ms, 2500)
        self.bullet_damage: int = _given(stats.bullet_damage, 20)

        muzzle_path = assets.image_path(f"enemy_{enemy_type}_muzzle")
        self._muzzle_base: pygame.Surface = load_image(muzzle_path)
        self._muzzle_image: pygame.Surface = self._muzzle_base
        self._muzzle_angle: float = 0.0

        self.bullets: list = []
        self._last_fire_time: float = 0
        self.now: float = 0  # game time of the latest update_combat()

    # ── combat ───────────────────────────────────────────────────────────────

    def update_combat(self, ctx: "IGameContext") -> None:
        """Aim muzzle at nearest tower; fire on cooldown when in range."""
        self.now = ctx.time_ms
        nearest, dist_sq = self._nearest_tower(ctx)
        if nearest is None:
            return

        self._aim_at(nearest.position)

        if dist_sq > self.range * self.range:
            return
        if self.now - self._last_fire_time < self.fire_interval_ms:
            return
        self._last_fire_time = self.now
        self._fire(nearest)

    def _fire(self, target_tower) -> None:
        fwd = target_tower.position - self.position
        if fwd.length_squared() == 0:
            return
        tip = self.position + fwd.normalize() * self.MUZZLE_TIP_FORWARD
        self.bullets.append(TankBullet(self, target_tower, tip))
        self.bullets.append(TankMuzzleFlash(self, tip, self._muzzle_angle))

    def _nearest_tower(self, ctx: "IGameContext") -> tuple:
        # Skip towers that aren't targetable (planes — no HP system).
        candidates = [t for t in ctx.towers if t.maxHP is not None]
        if not candidates:
            return (None, 0)
        best = None
        best_dist = float("inf")
        for t in candidates:
            d = (t.position - self.position).length_squared()
            if d < best_dist:
                best, best_dist = t, d
        return (best, best_dist)

    def _aim_at(self, target_pos: Vector2) -> None:
        delta = target_pos - self.position
        if delta.length_squared() == 0:
            return
        self._muzzle_angle = angle_between_delta(delta)
        self._muzzle_image = pygame.transform.rotate(
            self._muzzle_base, -self._muzzle_angle
        )

    # ── rendering hook ───────────────────────────────────────────────────────

    def draw_muzzle(self, surface: pygame.Surface, camera) -> None:
        scaled = camera.scale_image(self._muzzle_image)
        center = camera.world_to_screen(self.position)
        rect = scaled.get_rect(center=(int(center.x), int(center.y)))
        surface.blit(scaled, rect)


class TankBullet(RotatableObject):
    """Travels toward a tower and chips at its HP on contact."""

    SPEED = 4
    EXPLODE_DISTANCE = 30

    def __init__(
        self, tank: Tank, target_tower, spawn_pos: Vector2 | None = None
    ) -> None:
        spawn = spawn_pos if spawn_pos is not None else tank.position
        super().__init__(tank.assets.image_path("tank_bullet"), spawn)
        self.tank = tank
        self.target_tower = target_tower
        self.damage = tank.bullet_damage
        self.rotate_to_angle(angle_between_points(self.position, target_tower.position))

    def update(self, ctx: "IGameContext") -> None:
        if self.target_tower not in ctx.towers:
            self._remove()
            return
        if self._is_out_of_bounds(ctx):
            self._remove()
            return

        delta = self.target_tower.position - self.position
        if delta.length() <= self.EXPLODE_DISTANCE:
            self.target_tower.decrease_hp(self.damage)
            self._remove()
            return

        self.rotate_to_angle(
            angle_between_points(self.position, self.target_tower.position)
        )
        self.position += delta.normalize() * self.SPEED * ctx.speed
        self.rect.center = self.position

    def _is_out_of_bounds(self, ctx: "IGameContext") -> bool:
        return (
            self.position.x < 0
            or self.position.x > ctx.map_width
            or self.position.y < 0
            or self.position.y > ctx.map_height
        )

    def _remove(self) -> None:
        if self in self.tank.bullets:
            self.tank.bullets.remove(self)


class TankMuzzleFlash(RotatableObject):
    """Brief visual flash at the tank's muzzle tip when firing — no damage."""

    FLASH_DURATION_MS = 120

    def __init__(self, tank: Tank, pos: Vector2, angle: float) -> None:
        super().__init__(tank.assets.image_path("tank_muzzle_flash"), pos)
        self.tank = tank
        self.rotate_to_angle(angle)
        self._created_at = tank.now

    def update(self, ctx: "IGameContext") -> None:
        if ctx.time_ms - self._created_at > self.FLASH_DURATION_MS:
            if self in self.tank.bullets:
                self.tank.bullets.remove(self)
