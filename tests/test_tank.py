from dataclasses import dataclass

import pytest
from pygame.math import Vector2

from gameplay.combat.tank import Tank, TankBullet, TankMuzzleFlash

WAYPOINTS = [Vector2(0, 0), Vector2(500, 0)]


@dataclass
class FakeTower:
    """Only what Tank._nearest_tower/_fire touch (see domain/protocols.py's
    stub-friendly design): position and maxHP (None marks an untargetable
    tower, e.g. a plane -- see BaseTower.maxHP)."""

    position: Vector2
    maxHP: int | None = 100


def make_tank(assets, enemy_type=5, level=1) -> Tank:
    return Tank(1, enemy_type, level, WAYPOINTS, assets)


def test_nearest_tower_is_none_with_no_towers(assets, ctx):
    tank = make_tank(assets)
    nearest, dist_sq = tank._nearest_tower(ctx)
    assert nearest is None


def test_nearest_tower_skips_untargetable_towers(assets, ctx):
    # maxHP=None marks a plane -- Tank._nearest_tower explicitly excludes
    # those (planes have no HP system, so they can't be shot at).
    tank = make_tank(assets)
    ctx.towers.append(FakeTower(Vector2(10, 0), maxHP=None))

    nearest, _ = tank._nearest_tower(ctx)

    assert nearest is None


def test_nearest_tower_picks_the_closest_one(assets, ctx):
    tank = make_tank(assets)  # spawns at (0, 0)
    far = FakeTower(Vector2(300, 0))
    close = FakeTower(Vector2(50, 0))
    ctx.towers.extend([far, close])

    nearest, dist_sq = tank._nearest_tower(ctx)

    assert nearest is close
    assert dist_sq == pytest.approx(50 * 50)


def test_update_combat_does_not_fire_when_target_out_of_range(assets, ctx):
    tank = make_tank(assets)
    ctx.towers.append(FakeTower(Vector2(tank.range * 2, 0)))

    tank.update_combat(ctx)

    assert tank.bullets == []


def test_update_combat_fires_a_bullet_and_muzzle_flash_when_in_range(assets, ctx):
    tank = make_tank(assets)
    ctx.time_ms = tank.fire_interval_ms  # past the initial cooldown (_last_fire_time=0)
    ctx.towers.append(FakeTower(Vector2(tank.range / 2, 0)))

    tank.update_combat(ctx)

    assert len(tank.bullets) == 2
    kinds = {type(b) for b in tank.bullets}
    assert kinds == {TankBullet, TankMuzzleFlash}


def test_update_combat_respects_the_fire_cooldown(assets, ctx):
    tank = make_tank(assets)
    target = FakeTower(Vector2(tank.range / 2, 0))
    ctx.towers.append(target)

    ctx.time_ms = tank.fire_interval_ms
    tank.update_combat(ctx)
    assert len(tank.bullets) == 2

    ctx.time_ms = (
        tank.fire_interval_ms + 1
    )  # nowhere near a full cooldown since last shot
    tank.update_combat(ctx)
    assert len(tank.bullets) == 2  # unchanged -- still on cooldown

    ctx.time_ms = tank.fire_interval_ms * 2
    tank.update_combat(ctx)
    assert len(tank.bullets) == 4  # cooldown elapsed -- fired again


# ── tank bullets ─────────────────────────────────────────────────────────────


class HpTower:
    def __init__(self, position, hp=100):
        self.position = Vector2(position)
        self.maxHP = hp
        self.hp = hp

    def decrease_hp(self, damage):
        self.hp -= damage


def test_tank_bullet_flies_at_its_target_and_chips_its_hp_on_contact(assets, ctx):
    tank = make_tank(assets)
    tower = HpTower((200, 0))
    ctx.towers.append(tower)
    bullet = TankBullet(tank, tower)
    tank.bullets.append(bullet)

    bullet.update(ctx)
    assert bullet.position.x == pytest.approx(TankBullet.SPEED)
    assert tower.hp == 100

    bullet.position = Vector2(200 - TankBullet.EXPLODE_DISTANCE + 1, 0)
    bullet.update(ctx)
    assert tower.hp == 100 - tank.bullet_damage
    assert bullet not in tank.bullets


def test_tank_bullet_vanishes_when_its_target_tower_is_gone(assets, ctx):
    tank = make_tank(assets)
    tower = HpTower((200, 0))
    bullet = TankBullet(tank, tower)
    tank.bullets.append(bullet)

    bullet.update(ctx)  # tower was never (or is no longer) in ctx.towers

    assert bullet not in tank.bullets


def test_tank_muzzle_flash_expires_after_its_duration_of_game_time(assets, ctx):
    tank = make_tank(assets)
    tank.now = 1000.0
    flash = TankMuzzleFlash(tank, Vector2(10, 0), 0.0)
    tank.bullets.append(flash)

    ctx.time_ms = 1000.0 + TankMuzzleFlash.FLASH_DURATION_MS
    flash.update(ctx)
    assert flash in tank.bullets

    ctx.time_ms += 1
    flash.update(ctx)
    assert flash not in tank.bullets


def test_draw_muzzle_renders_the_turret(assets):
    import pygame
    from pygamine import Camera

    tank = make_tank(assets)
    tank._aim_at(Vector2(100, 100))

    tank.draw_muzzle(
        pygame.Surface((400, 300)), Camera(pygame.Rect(0, 0, 400, 300), 3008, 2176)
    )
