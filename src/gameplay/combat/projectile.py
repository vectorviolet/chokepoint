from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from gameplay.rotatable_object import RotatableObject
from pygamine import angle_between_points

if TYPE_CHECKING:
    from domain.protocols import IGameContext


class Projectile(RotatableObject):
    outlives_source = True  # flies on if its tower is sold or destroyed
    EXPLODE_DISTANCE = 30
    BULLET_SPEED = 2
    FLAME_SCALE = 0.7  # tower-2 trail flame size relative to the missile sprite

    def __init__(self, target, tower) -> None:
        super().__init__(
            tower.assets.image_path(f"bullet_{tower.tower_type}_lvl{tower.level}"),
            tower.position,
        )
        self.tower_type = tower.tower_type
        self.target = target
        self.tower = tower
        self.damage = tower.damage
        self._velocity = Vector2(0, 0)
        if tower.tower_type == 2:
            self._attach_trail_flame(tower)

    def _attach_trail_flame(self, tower) -> None:
        missile = self._sprite_image()
        flame_key = f"muzzle_flash_3_lvl{min(tower.level, 2)}"
        flame_src = tower.assets.get_image(flame_key)
        flame_w = max(1, int(missile.get_width() * self.FLAME_SCALE))
        flame_h = max(1, int(missile.get_height() * self.FLAME_SCALE))
        flame = pygame.transform.smoothscale(flame_src, (flame_w, flame_h))
        flame = pygame.transform.rotate(
            flame, 180
        )  # flare points backward, away from the missile nose

        # Canvas keeps the missile centered so rotation pivots on the missile, not the flame.
        # Symmetric padding (= flame_w on each side) leaves wasted right-side space, but that's
        # fully transparent and only costs a few bytes per projectile.
        pad = flame_w
        canvas_w = missile.get_width() + 2 * pad
        canvas_h = max(missile.get_height(), flame_h)
        composite = pygame.Surface((canvas_w, canvas_h), pygame.SRCALPHA)

        missile_rect = missile.get_rect(center=(canvas_w // 2, canvas_h // 2))
        # Flame nudged slightly into the missile from its tail edge so a small slice sits under it.
        flame_rect = flame.get_rect(
            center=(missile_rect.left + int(flame_w * 0.2), canvas_h // 2)
        )
        composite.blit(flame, flame_rect)
        composite.blit(missile, missile_rect)

        # Registered under the current state (not only shown by the renderer),
        # so a later set_state() can't bring back the bare missile.
        self.add_surface(self.state, composite)
        self.rect.size = composite.get_size()
        self.rect.center = self.position

    # Takes the battle's state, unlike GameObject.update() (mypy: override).
    def update(self, ctx: "IGameContext") -> None:  # type: ignore[override]
        if self._is_out_of_bounds(ctx):
            self._remove()
            return

        if not ctx.enemies:
            self._explode(ctx)
            return

        # Re-find target by id in case the list was rebuilt
        for enemy in ctx.enemies:
            if enemy.id == self.target.id:
                self.target = enemy
                break

        self.rotate_to_angle(angle_between_points(self.position, self.target.position))

        distance = self.target.position - self.position
        if distance.length() <= self.EXPLODE_DISTANCE:
            self._explode(ctx)
            return

        self._move(distance, ctx.speed)

    def _is_out_of_bounds(self, ctx: "IGameContext") -> bool:
        return (
            self.position.x < 0
            or self.position.x > ctx.map_width
            or self.position.y < 0
            or self.position.y > ctx.map_height
        )

    def _remove(self) -> None:
        if self in self.tower.bullets:
            self.tower.bullets.remove(self)

    def _explode(self, ctx: "IGameContext") -> None:
        self._remove()
        self.target.decrease_hp(self.damage, ctx, self.tower)

    def _move(self, distance: Vector2, speed: int) -> None:
        self._velocity = distance.normalize() * self.BULLET_SPEED * speed
        self.position += self._velocity
        self.rect.center = self.position


class MuzzleFlash(RotatableObject):
    """Instant-hit effect for tower types 1 and 3.

    Positioned at the barrel tip (pos). Deals damage on the first update tick
    if deals_damage=True (set False for the second barrel of a twin-gun tower).
    Removes itself after FLASH_DURATION_MS. `angle` is the barrel's drawn
    angle to point the flash along; None points it at the target.
    """

    FLASH_DURATION_MS = 120

    def __init__(
        self,
        target,
        tower,
        pos: Vector2,
        deals_damage: bool = True,
        angle: float | None = None,
    ) -> None:
        super().__init__(
            tower.assets.image_path(
                f"muzzle_flash_{tower.tower_type}_lvl{tower.level}"
            ),
            pos,
        )
        self.tower = tower
        self.target = target
        self.damage = tower.damage
        self._created_at = tower.now
        self._damage_dealt = not deals_damage
        if angle is None:
            angle = angle_between_points(pos, target.position)
        self.rotate_to_angle(angle)

    # Takes the battle's state, unlike GameObject.update() (mypy: override).
    def update(self, ctx: "IGameContext") -> None:  # type: ignore[override]
        if not self._damage_dealt:
            for enemy in ctx.enemies:
                if enemy.id == self.target.id:
                    self.target = enemy
                    break
            if self.target in ctx.enemies:
                self.target.decrease_hp(self.damage, ctx, self.tower)
            self._damage_dealt = True

        if ctx.time_ms - self._created_at > self.FLASH_DURATION_MS:
            if self in self.tower.bullets:
                self.tower.bullets.remove(self)


class Bomb(RotatableObject):
    """Bomb dropped by a plane.

    Released with the plane's forward velocity, then decelerates via drag
    each tick. The plane keeps powering forward at full speed, so the bomb
    visually lags behind it and lands where its momentum runs out. After
    FALL_DURATION_MS of game time it lands: splash damage at once, and the
    context shows the explosion. Damage and radius come from the dropping
    tower's level.
    """

    outlives_source = True  # falls on after its plane leaves the map
    FALL_DURATION_MS = 600
    DRAG = 0.94  # per-tick velocity multiplier at x1 (air resistance)
    SPRITE_SCALE = 0.6  # bullet_2_lvl1 is sized for missiles; scale down for bombs

    def __init__(self, tower, drop_velocity: Vector2) -> None:
        super().__init__(
            tower.assets.image_path("bullet_2_lvl1"),
            tower.position,
        )
        self.tower = tower
        self.damage = tower.damage
        self.radius = tower.range
        self._velocity = Vector2(drop_velocity)
        self._created_at = tower.now
        self._scale_sprite()
        if self._velocity.length_squared() > 0:
            self.rotate_to_delta(self._velocity)

    @classmethod
    def landing_offset(cls, drop_velocity: Vector2, game_speed: float) -> Vector2:
        """The farthest a bomb dropped with `drop_velocity` drifts before it
        lands, while the game speed doesn't exceed `game_speed` (update():
        each tick it moves by velocity * speed, then drag scales the
        velocity by DRAG**speed).

        The geometric series' limit, velocity * speed / (1 - DRAG**speed).
        A fall at exactly `game_speed` comes within 0.1 px of it (the ticks
        after FALL_DURATION_MS would add the rest). Any slower tick, or a
        speed change mid-fall, covers less: speed / (1 - DRAG**speed) grows
        with the speed. So it is an upper bound however game time rounds
        into ticks."""
        assert game_speed > 0  # bombs only fall while the game runs
        return drop_velocity * game_speed / (1 - cls.DRAG**game_speed)

    def _scale_sprite(self) -> None:
        src = self._sprite_image()
        scaled_size = (
            max(1, int(src.get_width() * self.SPRITE_SCALE)),
            max(1, int(src.get_height() * self.SPRITE_SCALE)),
        )
        # Registered under the current state, like the missile's trail flame.
        self.add_surface(self.state, pygame.transform.smoothscale(src, scaled_size))
        self.rect.size = scaled_size
        self.rect.center = self.position

    # Takes the battle's state, unlike GameObject.update() (mypy: override).
    def update(self, ctx: "IGameContext") -> None:  # type: ignore[override]
        elapsed = ctx.time_ms - self._created_at
        if elapsed >= self.FALL_DURATION_MS:
            self._detonate(ctx)
            return
        self.position += self._velocity * ctx.speed
        self._velocity *= self.DRAG**ctx.speed  # x2 covers two x1 ticks' worth of drag
        self.rect.center = self.position

    def _detonate(self, ctx: "IGameContext") -> None:
        """Lands: damages every enemy within the splash radius once, right
        now (on game time), then tells the context where, for the explosion
        and its sound (cosmetic, on real time: ui.bomb_impact_feedback)."""
        if self in self.tower.bullets:
            self.tower.bullets.remove(self)
        for enemy in list(ctx.enemies):
            if (enemy.position - self.position).length() <= self.radius:
                enemy.decrease_hp(self.damage, ctx, self.tower)
        ctx.bomb_landed(Vector2(self.position), self.radius)
