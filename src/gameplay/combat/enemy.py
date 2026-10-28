from typing import TYPE_CHECKING

from pygame.math import Vector2

from util.config_loader import load_enemy_stats
from gameplay.rotatable_object import RotatableObject

if TYPE_CHECKING:
    from domain.protocols import IGameContext

_BASE_STATS = load_enemy_stats()


class Enemy(RotatableObject):
    """Walks a polyline of world-space waypoints.

    Spawn position is `waypoints[0]`; the enemy advances to each subsequent
    waypoint at `mov_speed * game_speed` pixels per frame, then halts past
    the last vertex (caller checks `reached_end()` to deduct a life).
    """

    def __init__(
        self, id: int, enemy_type: int, level: int, waypoints: list[Vector2], assets
    ) -> None:
        if not waypoints:
            raise ValueError("Enemy requires at least one waypoint")
        spawn = waypoints[0]
        super().__init__(assets.image_path(f"enemy_{enemy_type}"), (spawn.x, spawn.y))
        self.id = id
        self.enemy_type = enemy_type
        self.is_walking = True
        self.waypoints = waypoints
        self.waypoint_index = 1  # index of the *next* waypoint to walk to
        self._calculate_stats(enemy_type, level)
        if len(waypoints) > 1:
            self._face_toward(waypoints[1])

    def _calculate_stats(self, enemy_type: int, level: int) -> None:
        stats = _BASE_STATS[enemy_type]
        scale = 1.0 + (level - 1) * 0.25
        self.maxHP = int(stats.hp * scale)
        self.hp = self.maxHP
        self.killMoney = max(1, int(stats.kill_money * scale))
        self.damage = stats.damage
        self.mov_speed = stats.speed

    def destroy(self, ctx: "IGameContext") -> None:
        if self in ctx.enemies:
            ctx.enemies.remove(self)

    def decrease_hp(self, damage: int, ctx: "IGameContext", source=None) -> None:
        """`source` is the tower whose shot/bomb dealt the damage; it is
        credited with the HP this hit took (overkill not counted) and, if
        this hit kills, with the kill and its money."""
        if self not in ctx.enemies:
            return
        if source is not None:
            source.record_damage(min(damage, max(0, self.hp)))
        self.hp -= damage
        if self.hp <= 0:
            self.destroy(ctx)
            ctx.enemy_killed(self)
            if source is not None:
                source.record_kill(self.killMoney)

    def reached_end(self) -> bool:
        return self.waypoint_index >= len(self.waypoints)

    def move(self, game_speed: int) -> None:
        if self.reached_end():
            return

        target = self.waypoints[self.waypoint_index]
        step = self.mov_speed * game_speed
        delta = target - self.position

        if delta.length() <= step:
            self.position = Vector2(target)
            self.waypoint_index += 1
            if not self.reached_end():
                self._face_toward(self.waypoints[self.waypoint_index])
        else:
            self.position += delta.normalize() * step

        self.rect.center = self.position

    def _face_toward(self, target: Vector2) -> None:
        delta = target - self.position
        self.rotate_to_delta(delta)
