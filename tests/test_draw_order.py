"""The battle's layers (#55, #60): ground towers, then enemies, then bomb
explosions, then planes (they fly), then HP bars on top; a plane's falling
bombs under the plane, and a departed plane's bombs still in the planes'
layer. Checked in
the real game (saves in a temporary directory) and in the menu demo, by
recording what is drawn in which order."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.battle import OrphanShot
from gameplay.combat.enemy import Enemy
from gameplay.combat.projectile import Bomb
from gameplay.combat.tank import Tank, TankBullet
from gameplay.menu_demo import MenuDemo
from gameplay.tilemap import Tilemap
from gameplay.towers import TowerFactory
from pygamine import SaveStore
from ui import hp_bar

GROUND_TYPE = 1
PLANE_TYPE = 4
TANK_TYPE = 5


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    return g


@pytest.fixture
def demo(assets, tower_config):
    tilemap = Tilemap("assets/maps/tiled_tilemap.tmx")
    return MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))


def stage(battle, tower_config, assets):
    """A ground tower, a plane with a falling bomb and a hurt enemy, all
    near (700, 700), and an explosion on top of them. Returns them."""
    battle.towers.clear()
    battle.enemies.clear()
    battle.bomb_impacts.clear()

    tower = TowerFactory.create(
        GROUND_TYPE, 10, 10, tower_config, assets, None, map_width=3008
    )
    tower.hp = tower.maxHP - 1  # so its HP bar shows
    plane = TowerFactory.create(
        PLANE_TYPE, 0, 0, tower_config, assets, None, map_width=3008
    )
    plane.position = Vector2(700, 700)
    plane.rect.center = plane.position
    plane.now = battle.game_state.time_ms
    bomb = Bomb(plane, Vector2(0, 0))
    plane.bullets.append(bomb)
    enemy = Enemy(1, 1, level=1, waypoints=[Vector2(700, 700)], assets=assets)
    enemy.hp = enemy.maxHP - 1
    battle.towers.extend([tower, plane])
    battle.enemies.append(enemy)
    battle.bomb_impacts.bomb_landed((700, 700), 96)
    return tower, plane, bomb, enemy


def record_layers(battle, camera, monkeypatch):
    """Draw the battle once; return what was drawn, in order: entities
    drawn through the camera, "explosions", and ("hp", position) per bar."""
    drawn = []
    camera_draw = camera.draw

    def spy_camera_draw(surface, obj, *args, **kwargs):
        drawn.append(obj)
        return camera_draw(surface, obj, *args, **kwargs)

    impacts_draw = type(battle.bomb_impacts).draw

    def spy_impacts_draw(self, surface, cam):
        drawn.append("explosions")
        return impacts_draw(self, surface, cam)

    bar_draw = hp_bar.draw

    def spy_bar_draw(surface, cam, world_pos, hp, max_hp, **kwargs):
        if max_hp is not None and hp is not None and hp < max_hp:
            drawn.append(("hp", tuple(world_pos)))
        return bar_draw(surface, cam, world_pos, hp, max_hp, **kwargs)

    monkeypatch.setattr(camera, "draw", spy_camera_draw)
    monkeypatch.setattr(type(battle.bomb_impacts), "draw", spy_impacts_draw)
    monkeypatch.setattr(hp_bar, "draw", spy_bar_draw)
    battle._draw_battle(pygame.Surface((1280, 720)), camera)
    return drawn


def index_of(drawn, obj):
    return next(i for i, x in enumerate(drawn) if x is obj or x == obj)


@pytest.fixture(params=["game", "demo"])
def battle(request):
    return request.getfixturevalue(request.param)


def test_explosions_go_over_towers_and_enemies(
    battle, tower_config, assets, monkeypatch
):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)

    drawn = record_layers(battle, battle.camera, monkeypatch)

    explosions = index_of(drawn, "explosions")
    assert index_of(drawn, tower) < explosions
    assert index_of(drawn, enemy) < explosions


def test_planes_fly_over_enemies_and_explosions(
    battle, tower_config, assets, monkeypatch
):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)
    tank = Tank(2, TANK_TYPE, 1, [Vector2(700, 700)], assets)
    shot = TankBullet(tank, tower)
    tank.bullets.append(shot)
    battle.enemies.append(tank)

    drawn = record_layers(battle, battle.camera, monkeypatch)

    plane_at = index_of(drawn, plane)
    assert index_of(drawn, "explosions") < plane_at
    assert index_of(drawn, enemy) < plane_at
    assert index_of(drawn, tower) < plane_at
    assert index_of(drawn, tank) < plane_at
    assert index_of(drawn, shot) < plane_at


def test_hp_bars_stay_above_planes(battle, tower_config, assets, monkeypatch):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)

    drawn = record_layers(battle, battle.camera, monkeypatch)

    plane_at = index_of(drawn, plane)
    assert index_of(drawn, ("hp", tuple(tower.position))) > plane_at
    assert index_of(drawn, ("hp", tuple(enemy.position))) > plane_at


def test_a_gone_ground_towers_shots_stay_under_enemies(
    battle, tower_config, assets, monkeypatch
):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)
    sold = TowerFactory.create(
        GROUND_TYPE, 11, 11, tower_config, assets, None, map_width=3008
    )
    orphan = Bomb(sold, Vector2(0, 0))  # any shot in flight will do
    battle._orphan_tower_shots = [OrphanShot(sold, orphan)]

    drawn = record_layers(battle, battle.camera, monkeypatch)

    assert index_of(drawn, orphan) < index_of(drawn, enemy)


def test_a_departed_planes_bombs_keep_the_planes_layer(
    battle, tower_config, assets, monkeypatch
):
    # #59 review: a plane lingers until its sprite is off the map, so its
    # bombs are orphaned mid-fall; they must not drop under the enemies.
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)
    departed = TowerFactory.create(
        PLANE_TYPE, 0, 0, tower_config, assets, None, map_width=3008
    )
    orphan = Bomb(departed, Vector2(0, 0))
    battle._orphan_tower_shots = [OrphanShot(departed, orphan)]

    drawn = record_layers(battle, battle.camera, monkeypatch)

    assert index_of(drawn, orphan) > index_of(drawn, enemy)
    assert index_of(drawn, orphan) > index_of(drawn, "explosions")
    assert index_of(drawn, orphan) < index_of(drawn, plane)  # under live planes
    assert sum(x is orphan for x in drawn) == 1


def test_hp_bars_stay_above_explosions(battle, tower_config, assets, monkeypatch):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)

    drawn = record_layers(battle, battle.camera, monkeypatch)

    explosions = index_of(drawn, "explosions")
    assert index_of(drawn, ("hp", tuple(tower.position))) > explosions
    assert index_of(drawn, ("hp", tuple(enemy.position))) > explosions


def test_a_planes_bombs_fall_under_it(battle, tower_config, assets, monkeypatch):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)

    drawn = record_layers(battle, battle.camera, monkeypatch)

    assert index_of(drawn, bomb) < index_of(drawn, plane)
    assert sum(x is bomb for x in drawn) == 1  # drawn once, not again on top
