from typing import TYPE_CHECKING

import pygame
from pygame.math import Vector2

from gameplay.rotatable_object import RotatableObject
from pygamine import SpriteRenderer2D
from pygamine import GameObject
from pygamine import angle_between_points

if TYPE_CHECKING:
    from domain.protocols import IGameContext


class Projectile(RotatableObject):
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
        renderer = self.get_component(SpriteRenderer2D)
        missile = renderer.image
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

        renderer.set_image(composite)
        self.rect.size = composite.get_size()
        self.rect.center = self.position

    def update(self, ctx: "IGameContext") -> None:
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
    Removes itself after FLASH_DURATION_MS.
    """

    FLASH_DURATION_MS = 120

    def __init__(self, target, tower, pos: Vector2, deals_damage: bool = True) -> None:
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
        self.rotate_to_angle(angle_between_points(pos, target.position))

    def update(self, ctx: "IGameContext") -> None:
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
    FALL_DURATION_MS of game time, replaces itself in tower.bullets with
    an Explosion. Damage and radius come from the dropping tower's level.
    """

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

    def _scale_sprite(self) -> None:
        renderer = self.get_component(SpriteRenderer2D)
        src = renderer.image
        scaled_size = (
            max(1, int(src.get_width() * self.SPRITE_SCALE)),
            max(1, int(src.get_height() * self.SPRITE_SCALE)),
        )
        renderer.set_image(pygame.transform.smoothscale(src, scaled_size))
        self.rect.size = scaled_size
        self.rect.center = self.position

    def update(self, ctx: "IGameContext") -> None:
        elapsed = ctx.time_ms - self._created_at
        if elapsed >= self.FALL_DURATION_MS:
            self._detonate(ctx)
            return
        self.position += self._velocity * ctx.speed
        self._velocity *= self.DRAG**ctx.speed  # x2 covers two x1 ticks' worth of drag
        self.rect.center = self.position

    def _detonate(self, ctx: "IGameContext") -> None:
        if self in self.tower.bullets:
            self.tower.bullets.remove(self)
        self.tower.bullets.append(
            Explosion(self.position, self.tower, self.damage, self.radius, ctx.time_ms)
        )


class Explosion(GameObject):
    """One-shot radius explosion: applies damage once, plays a composite
    smoke + explosion animation, then removes itself from tower.bullets.

    Composite frames are built lazily and cached on the class — every
    explosion in the game reuses the same surface list.
    """

    TOTAL_FRAMES = 13
    EXPLOSION_FRAMES = 9
    FRAME_DURATION_MS = 55  # ~18 fps total
    VISUAL_SCALE = 1.1  # composite size = ceil(radius * VISUAL_SCALE); smoke spills past the damage ring

    _frames_cache: dict[int, list[pygame.Surface]] = {}

    def __init__(
        self, position: Vector2, tower, damage: int, radius: int, created_at: float
    ) -> None:
        super().__init__(name="explosion")
        self.tower = tower
        self.position = Vector2(position)
        self.damage = damage
        self.radius = radius
        self._frames = Explosion._get_frames(tower.assets, radius)
        self._created_at = created_at
        self._damage_dealt = False

        renderer = self.add_component(SpriteRenderer2D)
        renderer.set_image(self._frames[0])
        self.rect.size = self._frames[0].get_size()
        self.rect.center = (int(self.position.x), int(self.position.y))

    @classmethod
    def _get_frames(cls, assets, radius: int) -> list[pygame.Surface]:
        size = max(1, int(radius * cls.VISUAL_SCALE))
        if size not in cls._frames_cache:
            cls._frames_cache[size] = cls._build_frames(assets, (size, size))
        return cls._frames_cache[size]

    @classmethod
    def _build_frames(cls, assets, target: tuple[int, int]) -> list[pygame.Surface]:
        explosions = [
            pygame.transform.smoothscale(assets.get_image(f"explosion_{i}"), target)
            for i in range(cls.EXPLOSION_FRAMES)
        ]
        smokes = [
            pygame.transform.smoothscale(assets.get_image(f"black_smoke_{i}"), target)
            for i in range(cls.TOTAL_FRAMES)
        ]
        composite = []
        for i in range(cls.TOTAL_FRAMES):
            surf = pygame.Surface(target, pygame.SRCALPHA)
            surf.blit(smokes[i], (0, 0))
            if i < cls.EXPLOSION_FRAMES:
                surf.blit(explosions[i], (0, 0))
            composite.append(surf)
        return composite

    def update(self, ctx: "IGameContext") -> None:
        if not self._damage_dealt:
            for enemy in list(ctx.enemies):
                if (enemy.position - self.position).length() <= self.radius:
                    enemy.decrease_hp(self.damage, ctx, self.tower)
            self._damage_dealt = True

        elapsed = ctx.time_ms - self._created_at
        idx = int(elapsed // self.FRAME_DURATION_MS)
        if idx >= self.TOTAL_FRAMES:
            if self in self.tower.bullets:
                self.tower.bullets.remove(self)
            return
        self.get_component(SpriteRenderer2D).set_image(self._frames[idx])
