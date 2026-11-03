"""Hit feedback (#84): a hit enemy or tower flashes white for FLASH_MS with
a spark at the impact point, rate-capped per target, capped overall, on
real time, and cosmetic only. Unit tests drive HitFeedback directly; the
rest go through a real Game() (saves in a temporary directory) or the menu
demo."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.combat.enemy import Enemy
from gameplay.combat.projectile import Bomb, MuzzleFlash, Projectile
from gameplay.combat.tank import Tank, TankBullet
from gameplay.menu_demo import MenuDemo
from gameplay.tilemap import Tilemap
from gameplay.towers import PLANE_TYPE, TowerFactory
from pygamine import SaveStore
from ui.hit_feedback import (
    FLASH_ALPHA,
    FLASH_MS,
    HIT_MIN_INTERVAL_MS,
    IMPACT_REACH,
    MAX_EFFECTS,
    SPARK_LIFE_MS,
    HitFeedback,
    impact_point,
    silhouette,
)


class Target:
    """Stands in for an enemy or tower: a position and one flash part."""

    def __init__(self, pos=(0, 0), image=None):
        self.position = Vector2(pos)
        if image is None:
            image = pygame.Surface((10, 10), pygame.SRCALPHA)
            image.fill((200, 30, 30, 255))
        self.image = image
        self.parts_asked = 0

    def flash_parts(self):
        self.parts_asked += 1
        return [(self.image, Vector2(self.position))]


class Camera:
    """No offset, a zoom of `scale`; scales images like pygamine's camera."""

    def __init__(self, scale=1.0):
        self.scale = scale

    def world_to_screen(self, pos):
        return Vector2(pos) * self.scale

    def scale_image(self, image):
        if self.scale == 1.0:
            return image
        return pygame.transform.scale_by(image, self.scale)


HIT_FROM = (50, 0)  # where the shot was, for tests that don't care


@pytest.fixture
def feedback():
    return HitFeedback(rng=random.Random(1))


# ── flash timing and the rate cap ─────────────────────────────────────────────


def test_a_hit_flashes_for_flash_ms_of_real_time(feedback):
    target = Target()
    assert feedback.target_hit(target, (50, 0))

    assert feedback.is_flashing(target)
    feedback.update(FLASH_MS - 1)
    assert feedback.is_flashing(target)
    feedback.update(1)
    assert not feedback.is_flashing(target)


def test_hits_on_one_target_are_shown_at_most_once_per_interval(feedback):
    target = Target()
    feedback.target_hit(target, HIT_FROM)

    feedback.update(HIT_MIN_INTERVAL_MS - 1)
    assert not feedback.target_hit(target, HIT_FROM)  # gun spam: no strobe
    assert not feedback.is_flashing(target)

    feedback.update(1)
    assert feedback.target_hit(target, HIT_FROM)
    assert feedback.is_flashing(target)


def test_steady_gunfire_flashes_at_the_capped_rate(feedback):
    """A hit every frame for a second shows 1000 / HIT_MIN_INTERVAL_MS
    flashes, each FLASH_MS long."""
    target = Target()
    shown = 0
    flashing_ms = 0
    frame_ms = 5
    for _ in range(1000 // frame_ms):
        shown += feedback.target_hit(target, HIT_FROM)
        flashing_ms += frame_ms if feedback.is_flashing(target) else 0
        feedback.update(frame_ms)

    assert shown == 1000 // HIT_MIN_INTERVAL_MS
    assert flashing_ms == shown * FLASH_MS


def test_the_cap_is_per_target(feedback):
    a, b = Target(), Target()
    feedback.target_hit(a, HIT_FROM)

    assert feedback.target_hit(b, HIT_FROM)
    assert feedback.is_flashing(a) and feedback.is_flashing(b)


def test_at_most_max_effects_hits_play_at_once(feedback):
    targets = [Target() for _ in range(MAX_EFFECTS + 3)]
    shown = [feedback.target_hit(t, HIT_FROM) for t in targets]

    assert shown == [True] * MAX_EFFECTS + [False] * 3
    assert feedback.live_effects == MAX_EFFECTS

    feedback.update(HIT_MIN_INTERVAL_MS)  # they play out
    assert feedback.live_effects == 0
    assert feedback.target_hit(targets[-1], HIT_FROM)


def test_clear_drops_every_hit(feedback):
    target = Target()
    feedback.target_hit(target, HIT_FROM)
    feedback.clear()

    assert feedback.live_effects == 0
    assert not feedback.is_flashing(target)


# ── where and how it's drawn ──────────────────────────────────────────────────


def test_the_spark_sits_on_the_side_facing_the_shot():
    assert impact_point((100, 100), (200, 100)) == Vector2(100 + IMPACT_REACH, 100)
    assert impact_point((100, 100), (100, 105)) == Vector2(100, 105)  # closer
    assert impact_point((100, 100), (100, 100)) == Vector2(100, 100)  # right on it


def test_the_silhouette_is_white_in_the_sprites_shape():
    image = pygame.Surface((4, 1), pygame.SRCALPHA)
    image.fill((0, 0, 0, 0))
    image.set_at((1, 0), (200, 30, 30, 255))
    image.set_at((2, 0), (10, 90, 10, 128))

    white = silhouette(image)

    assert white.get_at((0, 0)).a == 0
    assert white.get_at((1, 0)) == (255, 255, 255, FLASH_ALPHA)
    assert white.get_at((2, 0))[:3] == (255, 255, 255)
    assert white.get_at((2, 0)).a == round(128 * FLASH_ALPHA / 255)


def test_the_flash_draws_white_over_the_target_while_it_flashes(feedback):
    target = Target((20, 20))
    surface = pygame.Surface((40, 40))
    surface.fill((0, 0, 0))

    feedback.draw_flash(surface, Camera(), target)
    assert surface.get_at((20, 20))[:3] == (0, 0, 0)  # not hit: nothing

    feedback.target_hit(target, HIT_FROM)
    feedback.draw_flash(surface, Camera(), target)
    r, g, b, _ = surface.get_at((20, 20))
    assert min(r, g, b) > 200  # white over it
    assert surface.get_at((5, 5))[:3] == (0, 0, 0)  # only its shape


def test_the_flash_follows_the_zoom(feedback):
    target = Target((20, 20))
    surface = pygame.Surface((80, 80))
    surface.fill((0, 0, 0))
    feedback.target_hit(target, HIT_FROM)

    feedback.draw_flash(surface, Camera(scale=2.0), target)

    lit = pygame.mask.from_threshold(surface, (255, 255, 255), (60, 60, 60, 255))
    assert lit.get_bounding_rects() == [pygame.Rect(30, 30, 20, 20)]


def test_silhouettes_are_built_once_per_source_image(feedback, monkeypatch):
    import ui.hit_feedback as module

    built = []
    real = module.silhouette
    monkeypatch.setattr(
        module, "silhouette", lambda img: built.append(img) or real(img)
    )
    target = Target()
    surface = pygame.Surface((40, 40))
    feedback.target_hit(target, HIT_FROM)

    for _ in range(5):
        feedback.draw_flash(surface, Camera(), target)
        feedback.update(1)

    assert built == [target.image]


def test_a_spark_bursts_at_the_impact_point_and_fades_out(feedback):
    target = Target((20, 20))
    feedback.target_hit(target, (60, 20))  # shot from the right
    feedback.update(SPARK_LIFE_MS / 3)
    surface = pygame.Surface((60, 60))
    surface.fill((0, 0, 0))

    feedback.draw_sparks(surface, Camera())

    drawn = pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255))
    drawn.invert()
    rects = drawn.get_bounding_rects()
    assert rects
    burst = rects[0].unionall(rects[1:])
    assert burst.collidepoint(20 + IMPACT_REACH, 20)  # around the impact
    assert not burst.collidepoint(20, 20)  # not the target's center

    feedback.update(SPARK_LIFE_MS)  # over
    surface.fill((0, 0, 0))
    feedback.draw_sparks(surface, Camera())
    dark = pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255))
    assert dark.count() == 60 * 60


# ── real targets ──────────────────────────────────────────────────────────────


def test_a_ground_tower_flashes_its_platform_and_turret(tower_config, assets):
    tower = TowerFactory.create(1, 5, 5, tower_config, assets, None, map_width=3008)
    parts = tower.flash_parts()

    assert len(parts) == 2
    assert [image for image, _ in parts] == [tower.platform.image, tower.image]
    assert all(center == tower.position for _, center in parts)


def test_a_tank_flashes_its_hull_and_turret(assets):
    tank = Tank(1, 5, 1, [Vector2(100, 100), Vector2(500, 100)], assets)
    parts = tank.flash_parts()

    assert len(parts) == 2
    assert parts[0][0] is tank.image
    assert parts[1][0] is tank._muzzle_image  # the turret as drawn


# ── through the battle ────────────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    g.game_state.is_started = True
    g.towers.clear()
    g.enemies.clear()
    return g


def add_enemy(game, pos, hp=None, enemy_type=1):
    enemy = Enemy(len(game.enemies) + 1, enemy_type, 1, [Vector2(pos)], game.assets)
    if hp is not None:
        enemy.hp = hp
    game.enemies.append(enemy)
    return enemy


def ground_tower(game, tower_type=2, row=10, col=10):
    tower = TowerFactory.create(
        tower_type, row, col, game.tower_config, game.assets, None, map_width=3008
    )
    tower.now = game.game_state.time_ms
    game.towers.append(tower)
    return tower


def test_a_missile_hit_flashes_the_enemy_with_a_spark_toward_the_missile(game):
    tower = ground_tower(game)
    enemy = add_enemy(game, tower.position + Vector2(100, 0))
    missile = Projectile(enemy, tower)
    missile.position = enemy.position - Vector2(20, 0)

    missile.update(game)

    assert enemy.hp == enemy.max_hp - tower.damage
    assert game.hit_feedback.is_flashing(enemy)
    hit = game.hit_feedback._hits[id(enemy)]
    assert hit.impact == enemy.position - Vector2(min(20, IMPACT_REACH), 0)


def test_an_instant_hit_sparks_on_the_side_facing_the_tower(game):
    tower = ground_tower(game, tower_type=1)
    enemy = add_enemy(game, tower.position + Vector2(100, 0))
    flash = MuzzleFlash(enemy, tower, tower.position)

    flash.update(game)

    hit = game.hit_feedback._hits[id(enemy)]
    assert hit.impact == enemy.position - Vector2(IMPACT_REACH, 0)


def test_a_bomb_flashes_every_enemy_in_its_splash(game):
    plane = TowerFactory.create(
        PLANE_TYPE, 0, 0, game.tower_config, game.assets, None, map_width=3008
    )
    plane.position = Vector2(700, 700)
    plane.now = game.game_state.time_ms
    near = add_enemy(game, (700, 700))
    side = add_enemy(game, (730, 700))
    far = add_enemy(game, (700 + plane.range + 50, 700))
    bomb = Bomb(plane, Vector2(0, 0))
    plane.bullets.append(bomb)

    bomb._detonate(game)

    assert game.hit_feedback.is_flashing(near)
    assert game.hit_feedback.is_flashing(side)
    assert not game.hit_feedback.is_flashing(far)
    # Each spark on the side facing the blast; right under it, the center.
    hits = game.hit_feedback._hits
    assert hits[id(near)].impact == near.position
    assert hits[id(side)].impact == side.position - Vector2(IMPACT_REACH, 0)


def test_a_tank_shell_flashes_the_tower_it_hits(game):
    tower = ground_tower(game)
    tank = Tank(1, 5, 1, [tower.position + Vector2(200, 0)], game.assets)
    shell = TankBullet(tank, tower, tower.position + Vector2(10, 0))
    tank.bullets.append(shell)

    shell.update(game)

    assert tower.hp == tower.max_hp - tank.bullet_damage
    assert game.hit_feedback.is_flashing(tower)
    hit = game.hit_feedback._hits[id(tower)]
    assert hit.impact == tower.position + Vector2(10, 0)  # facing the shell


def test_a_tower_without_hp_shows_no_hit(game):
    plane = TowerFactory.create(
        PLANE_TYPE, 0, 0, game.tower_config, game.assets, None, map_width=3008
    )

    plane.decrease_hp(50, game, Vector2(0, 0))

    assert plane.hp is None
    assert game.hit_feedback.live_effects == 0


def test_the_flash_matches_the_sprite_as_drawn(game):
    """Silhouettes come from the drawn (rotated) surface: the flash covers
    exactly the pixels of the turned enemy, at its exact angle."""
    enemy = add_enemy(game, (700, 700))
    enemy.rotate_to_angle(37.3)
    game.target_hit(enemy, (650, 700))

    ((drawn, _),) = enemy.flash_parts()
    white = game.hit_feedback._silhouette(drawn)

    assert drawn is enemy.rotated_image
    assert white.get_size() == drawn.get_size()
    opaque = pygame.mask.from_surface(drawn, 1)
    assert pygame.mask.from_surface(white, 1).overlap_area(opaque, (0, 0)) == (
        opaque.count()
    )
    assert game.hit_feedback._silhouette(drawn) is white  # built once


def test_a_killing_hit_is_safe_and_does_not_block_the_death(game):
    tower = ground_tower(game)
    enemy = add_enemy(game, tower.position + Vector2(100, 0), hp=1)
    money = game.game_state.money
    missile = Projectile(enemy, tower)
    missile.position = Vector2(enemy.position)

    missile.update(game)

    assert enemy not in game.enemies  # it died on this hit
    assert game.game_state.money == money + enemy.kill_money
    assert game.hit_feedback.live_effects == 1  # its spark plays out
    surface = pygame.Surface((1280, 720))
    game._draw_battle(surface, game.camera)  # no crash with the target gone
    game.hit_feedback.draw_flash(surface, game.camera, enemy)
    game.hit_feedback.update(HIT_MIN_INTERVAL_MS)
    assert game.hit_feedback.live_effects == 0  # and lets go of it


def test_a_destroyed_tower_is_removed_as_usual(game):
    tower = ground_tower(game)
    tower.hp = 1
    tank = Tank(1, 5, 1, [tower.position + Vector2(200, 0)], game.assets)
    shell = TankBullet(tank, tower, tower.position + Vector2(10, 0))
    tank.bullets.append(shell)

    shell.update(game)
    game._tick()

    assert tower not in game.towers
    game._draw_battle(pygame.Surface((1280, 720)), game.camera)


def test_hits_play_out_on_real_time_while_paused(game):
    enemy = add_enemy(game, (500, 500))
    game.target_hit(enemy, enemy.position)
    game.game_state.is_started = False

    game._update_game(FLASH_MS)

    assert not game.hit_feedback.is_flashing(enemy)


@pytest.mark.parametrize("reset", ["_start_new_game", "load"])
def test_new_game_and_load_drop_the_hits(game, reset):
    enemy = add_enemy(game, (500, 500))
    game.target_hit(enemy, enemy.position)
    if reset == "load":
        game._save_game()
        game._load_game()
    else:
        game._start_new_game()

    assert game.hit_feedback.live_effects == 0


# ── no gameplay change ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tilemap():
    return Tilemap("assets/maps/tiled_tilemap.tmx")


def battle_outcome(demo):
    gs = demo.game_state
    return (
        gs.money,
        gs.lives,
        gs.level,
        [(e.id, e.hp, tuple(e.position)) for e in demo.enemies],
        [
            (t.tower_type, t.row, t.col, t.hp, t.kills, t.damage_dealt)
            for t in demo.towers
        ],
    )


def test_the_battle_plays_out_the_same_without_it(tilemap, assets, tower_config):
    """The menu demo's battle, seeded, ticked with and without hit
    feedback: money, lives, every enemy's and tower's HP, kills and damage
    end up identical."""
    with_it = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(3))
    without = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(3))
    without.hit_feedback = None
    for _ in range(1500):
        with_it._tick()
        without._tick()

    assert with_it.hit_feedback is not None
    assert with_it.hit_feedback.live_effects > 0  # it was fighting
    assert battle_outcome(with_it) == battle_outcome(without)


def test_a_seeded_menu_demo_shows_the_same_sparks(tilemap, assets, tower_config):
    def sparks(seed):
        demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(seed))
        for _ in range(600):
            demo._tick()
        return [(tuple(h.impact), h.angle) for h in demo.hit_feedback._hits.values()]

    assert sparks(5) and sparks(5) == sparks(5)


def test_update_drops_only_expired_hits(feedback):
    old, new = Target(), Target()
    feedback.target_hit(old, HIT_FROM)
    feedback.update(HIT_MIN_INTERVAL_MS - 10)
    feedback.target_hit(new, HIT_FROM)

    feedback.update(10)

    assert not feedback.target_hit(new, HIT_FROM)  # still in its window
    assert feedback.live_effects == 1
    assert feedback.target_hit(old, HIT_FROM)  # its window is over


def test_the_menu_demo_shows_hits(tilemap, assets, tower_config):
    demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))
    for _ in range(600):
        demo._tick()
    assert demo.hit_feedback.live_effects > 0
    demo.draw(pygame.Surface((1280, 720)))
