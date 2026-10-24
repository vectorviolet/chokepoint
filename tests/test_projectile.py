import pytest
from pygame.math import Vector2

from gameplay.combat.enemy import Enemy
from gameplay.combat.projectile import Bomb, Explosion
from towers import TowerFactory

PLANE_TYPE = 4
MAP_WIDTH = 3008
WAYPOINTS = [Vector2(0, 0), Vector2(500, 0)]


def make_plane(tower_config, assets):
    return TowerFactory.create(PLANE_TYPE, 0, 0, tower_config, assets, audio=None, map_width=MAP_WIDTH)


def test_bomb_inherits_damage_and_radius_from_the_dropping_tower(tower_config, assets):
    plane = make_plane(tower_config, assets)
    bomb = Bomb(plane, Vector2(5, 0))

    assert bomb.damage == plane.damage
    assert bomb.radius == plane.range


def test_bomb_moves_by_velocity_and_decelerates_via_drag(tower_config, assets, ctx):
    plane = make_plane(tower_config, assets)
    start_pos = Vector2(plane.position)
    velocity = Vector2(10, 0)
    bomb = Bomb(plane, velocity)

    ctx.time_ms = 1
    bomb.update(ctx)

    assert bomb.position == start_pos + velocity
    assert bomb._velocity == velocity * Bomb.DRAG


def test_bomb_detonates_into_an_explosion_after_fall_duration(tower_config, assets, ctx):
    plane = make_plane(tower_config, assets)
    plane.bullets = []
    bomb = Bomb(plane, Vector2(5, 0))
    plane.bullets.append(bomb)

    ctx.time_ms = Bomb.FALL_DURATION_MS - 1
    bomb.update(ctx)
    assert bomb in plane.bullets  # not yet

    ctx.time_ms = Bomb.FALL_DURATION_MS
    bomb.update(ctx)

    assert bomb not in plane.bullets
    assert len(plane.bullets) == 1
    assert isinstance(plane.bullets[0], Explosion)


def test_bomb_tick_at_x2_covers_two_x1_ticks_of_motion_and_drag(tower_config, assets, ctx):
    """At x2 a tick moves the bomb twice as far and applies two ticks' worth
    of drag, so its flight path is the same at every game speed (its fall
    time is game time, which GameState already runs faster at x2)."""
    plane = make_plane(tower_config, assets)
    start_pos = Vector2(plane.position)
    velocity = Vector2(10, 0)
    bomb = Bomb(plane, velocity)
    ctx.speed = 2

    bomb.update(ctx)

    assert bomb.position == start_pos + velocity * 2
    assert bomb._velocity == velocity * Bomb.DRAG ** 2


def test_explosion_damages_enemies_inside_radius_but_not_outside(tower_config, assets, ctx):
    plane = make_plane(tower_config, assets)
    plane.bullets = []
    center = Vector2(1000, 1000)

    inside  = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    outside = Enemy(2, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    inside.position  = center + Vector2(plane.range - 1, 0)
    outside.position = center + Vector2(plane.range + 50, 0)
    ctx.enemies.extend([inside, outside])

    explosion = Explosion(center, plane, damage=plane.damage, radius=plane.range, created_at=0)
    plane.bullets.append(explosion)

    explosion.update(ctx)

    assert inside.hp == inside.maxHP - plane.damage
    assert outside.hp == outside.maxHP


def test_explosion_only_deals_damage_once_across_multiple_updates(tower_config, assets, ctx):
    plane = make_plane(tower_config, assets)
    plane.bullets = []
    center = Vector2(1000, 1000)

    victim = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    victim.position = Vector2(center)
    ctx.enemies.append(victim)

    explosion = Explosion(center, plane, damage=plane.damage, radius=plane.range, created_at=0)
    plane.bullets.append(explosion)

    ctx.time_ms = 0
    explosion.update(ctx)
    ctx.time_ms = Explosion.FRAME_DURATION_MS
    explosion.update(ctx)

    assert victim.hp == victim.maxHP - plane.damage  # not hit twice


def test_explosion_removes_itself_once_all_frames_have_played(tower_config, assets, ctx):
    plane = make_plane(tower_config, assets)
    plane.bullets = []
    explosion = Explosion(Vector2(0, 0), plane, damage=plane.damage, radius=plane.range, created_at=0)
    plane.bullets.append(explosion)

    ctx.time_ms = Explosion.FRAME_DURATION_MS * (Explosion.TOTAL_FRAMES - 1)
    explosion.update(ctx)
    assert explosion in plane.bullets  # last frame still playing

    ctx.time_ms = Explosion.FRAME_DURATION_MS * Explosion.TOTAL_FRAMES
    explosion.update(ctx)
    assert explosion not in plane.bullets



# ── homing missile ───────────────────────────────────────────────────────────

def make_missile_tower(tower_config, assets, position=(1000, 1000)):
    tower = TowerFactory.create(2, 0, 0, tower_config, assets, audio=None, map_width=3008)
    tower.position = Vector2(position)
    tower.bullets = []
    return tower


def make_enemy(assets, position, enemy_id=1):
    enemy = Enemy(enemy_id, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    enemy.position = Vector2(position)
    return enemy


def test_missile_homes_in_on_its_target_by_its_speed_times_game_speed(tower_config, assets, ctx):
    from gameplay.combat.projectile import Projectile
    tower = make_missile_tower(tower_config, assets)
    target = make_enemy(assets, (1300, 1000))
    ctx.enemies.append(target)
    missile = Projectile(target, tower)
    tower.bullets.append(missile)
    ctx.speed = 2

    missile.update(ctx)

    assert missile.position == Vector2(1000 + Projectile.BULLET_SPEED * 2, 1000)
    assert target.hp == target.maxHP  # still in flight


def test_missile_explodes_on_reaching_its_target(tower_config, assets, ctx):
    from gameplay.combat.projectile import Projectile
    tower = make_missile_tower(tower_config, assets)
    target = make_enemy(assets, (1000 + Projectile.EXPLODE_DISTANCE - 1, 1000))
    ctx.enemies.append(target)
    missile = Projectile(target, tower)
    tower.bullets.append(missile)

    missile.update(ctx)

    assert missile not in tower.bullets
    assert target.hp == target.maxHP - tower.damage


def test_missile_follows_its_target_when_the_enemy_list_is_rebuilt(tower_config, assets, ctx):
    """Saving/restoring rebuilds Enemy objects; the missile re-finds its
    target by id rather than chasing a stale object."""
    from gameplay.combat.projectile import Projectile
    tower = make_missile_tower(tower_config, assets)
    stale = make_enemy(assets, (1300, 1000), enemy_id=7)
    missile = Projectile(stale, tower)
    fresh = make_enemy(assets, (1000, 1300), enemy_id=7)
    ctx.enemies.append(fresh)

    missile.update(ctx)

    assert missile.target is fresh
    assert missile.position.y > 1000 and missile.position.x == 1000


def test_missile_is_removed_once_out_of_the_map(tower_config, assets, ctx):
    from gameplay.combat.projectile import Projectile
    tower = make_missile_tower(tower_config, assets, position=(-5, 100))
    target = make_enemy(assets, (500, 100))
    ctx.enemies.append(target)
    missile = Projectile(target, tower)
    tower.bullets.append(missile)

    missile.update(ctx)

    assert missile not in tower.bullets
    assert target.hp == target.maxHP


# ── muzzle flash (instant hit) ───────────────────────────────────────────────

def test_muzzle_flash_hits_once_then_disappears_after_its_duration(tower_config, assets, ctx):
    from gameplay.combat.projectile import MuzzleFlash
    tower = TowerFactory.create(1, 0, 0, tower_config, assets, audio=None, map_width=3008)
    tower.bullets = []
    tower.now = 500.0
    target = make_enemy(assets, tower.position + Vector2(50, 0))
    ctx.enemies.append(target)
    flash = MuzzleFlash(target, tower, tower.position + Vector2(20, 0))
    tower.bullets.append(flash)

    ctx.time_ms = 500.0
    flash.update(ctx)
    flash.update(ctx)
    assert target.hp == target.maxHP - tower.damage  # hit exactly once
    assert flash in tower.bullets

    ctx.time_ms = 500.0 + MuzzleFlash.FLASH_DURATION_MS + 1
    flash.update(ctx)
    assert flash not in tower.bullets


def test_second_barrel_flash_is_visual_only(tower_config, assets, ctx):
    from gameplay.combat.projectile import MuzzleFlash
    tower = TowerFactory.create(1, 0, 0, tower_config, assets, audio=None, map_width=3008)
    target = make_enemy(assets, tower.position + Vector2(50, 0))
    ctx.enemies.append(target)

    MuzzleFlash(target, tower, tower.position, deals_damage=False).update(ctx)

    assert target.hp == target.maxHP
