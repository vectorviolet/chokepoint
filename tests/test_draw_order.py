"""The battle's layers (#55, #60, #84, #85): a destroyed tower's rubble
under everything, then ground towers, then enemies (a hit one's flash right
over it), then bomb and death explosions and hit sparks, then
planes (they fly), then HP bars on top; a plane's falling bombs under the
plane, and a departed plane's bombs still in the planes' layer. Checked in
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
from gameplay.towers import PLANE_TYPE

GROUND_TYPE = 1
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
    battle.hit_feedback.clear()
    battle.death_feedback.clear()

    tower = TowerFactory.create(
        GROUND_TYPE, 10, 10, tower_config, assets, None, map_width=3008
    )
    tower.hp = tower.max_hp - 1  # so its HP bar shows
    plane = TowerFactory.create(
        PLANE_TYPE, 0, 0, tower_config, assets, None, map_width=3008
    )
    plane.position = Vector2(700, 700)
    plane.rect.center = plane.position
    plane.now = battle.game_state.time_ms
    bomb = Bomb(plane, Vector2(0, 0))
    plane.bullets.append(bomb)
    enemy = Enemy(1, 1, level=1, waypoints=[Vector2(700, 700)], assets=assets)
    enemy.hp = enemy.max_hp - 1
    battle.towers.extend([tower, plane])
    battle.enemies.append(enemy)
    battle.bomb_impacts.bomb_landed((700, 700), 96)
    battle.death_feedback.enemy_died((700, 700), is_tank=False)
    battle.death_feedback.tower_destroyed((700, 700))
    return tower, plane, bomb, enemy


def record_layers(battle, camera, monkeypatch):
    """Draw the battle once; return what was drawn, in order: entities
    drawn through the camera, "decals", "explosions", "blasts",
    ("flash", target) per hit flash, "sparks", and ("hp", position) per
    bar."""
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

    hits = type(battle.hit_feedback)
    flash_draw, sparks_draw = hits.draw_flash, hits.draw_sparks

    def spy_flash_draw(self, surface, cam, target):
        drawn.append(("flash", target))
        return flash_draw(self, surface, cam, target)

    def spy_sparks_draw(self, surface, cam):
        drawn.append("sparks")
        return sparks_draw(self, surface, cam)

    deaths = type(battle.death_feedback)
    decals_draw, blasts_draw = deaths.draw_decals, deaths.draw_blasts

    def spy_decals_draw(self, surface, cam):
        drawn.append("decals")
        return decals_draw(self, surface, cam)

    def spy_blasts_draw(self, surface, cam):
        drawn.append("blasts")
        return blasts_draw(self, surface, cam)

    monkeypatch.setattr(deaths, "draw_decals", spy_decals_draw)
    monkeypatch.setattr(deaths, "draw_blasts", spy_blasts_draw)
    monkeypatch.setattr(hits, "draw_flash", spy_flash_draw)
    monkeypatch.setattr(hits, "draw_sparks", spy_sparks_draw)
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


def test_a_hit_flash_goes_right_over_its_target(
    battle, tower_config, assets, monkeypatch
):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)
    tank = Tank(2, TANK_TYPE, 1, [Vector2(700, 700)], assets)
    shot = TankBullet(tank, tower)
    tank.bullets.append(shot)
    battle.enemies.append(tank)
    for target in (tower, enemy, tank):
        battle.target_hit(target, target.position)

    drawn = record_layers(battle, battle.camera, monkeypatch)

    for target in (tower, enemy, tank):
        flash = drawn.index(("flash", target))
        assert drawn[flash - 1] is target  # its own sprite, nothing else
    # A tower's flash comes before its shots, a tank's before its shells.
    assert drawn.index(("flash", tank)) < index_of(drawn, shot)


def test_hit_sparks_go_with_the_explosions_under_planes(
    battle, tower_config, assets, monkeypatch
):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)
    battle.target_hit(enemy, (650, 700))

    drawn = record_layers(battle, battle.camera, monkeypatch)

    sparks = drawn.index("sparks")
    assert index_of(drawn, enemy) < sparks
    assert index_of(drawn, "explosions") < sparks < index_of(drawn, plane)
    assert sparks < index_of(drawn, ("hp", tuple(enemy.position)))


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


def test_rubble_goes_under_towers_and_enemies(
    battle, tower_config, assets, monkeypatch
):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)

    drawn = record_layers(battle, battle.camera, monkeypatch)

    decals = drawn.index("decals")
    assert decals < index_of(drawn, tower)
    assert decals < index_of(drawn, enemy)


def test_death_blasts_go_with_the_bomb_explosions(
    battle, tower_config, assets, monkeypatch
):
    tower, plane, bomb, enemy = stage(battle, tower_config, assets)
    battle.target_hit(enemy, (650, 700))

    drawn = record_layers(battle, battle.camera, monkeypatch)

    blasts = drawn.index("blasts")
    assert index_of(drawn, tower) < blasts
    assert index_of(drawn, enemy) < blasts
    assert drawn.index("explosions") + 1 == blasts  # right with them
    assert blasts < drawn.index("sparks") < index_of(drawn, plane)
    assert blasts < index_of(drawn, ("hp", tuple(enemy.position)))


# ── popups go over everything from the run (#93) ──────────────────────────


@pytest.mark.parametrize(
    ("open_popup", "panel_bg"),
    [
        (lambda g: g._open_pause_menu(), "pause_panel_bg"),
        (lambda g: g._trigger_victory(), "victory_panel_bg"),
        (lambda g: g._trigger_game_over(), "gameover_panel_bg"),
    ],
    ids=["pause", "victory", "game_over"],
)
def test_popups_are_drawn_after_the_kill_coins(game, monkeypatch, open_popup, panel_bg):
    game.kill_feedback.add_kill((700, 700), 5, (700, 700), game.game_state.time_ms)
    assert game.kill_feedback.coins  # in flight
    open_popup(game)
    panel = game.panel_manager["game"]
    drawn: list[str] = []
    real_coins = game.kill_feedback.draw_coins
    real_pop = game.kill_feedback.draw_pop
    real_bg = panel[panel_bg].draw
    monkeypatch.setattr(
        game.kill_feedback,
        "draw_coins",
        lambda *a: (drawn.append("coins"), real_coins(*a))[1],
    )
    monkeypatch.setattr(
        game.kill_feedback,
        "draw_pop",
        lambda *a: (drawn.append("pop"), real_pop(*a))[1],
    )
    monkeypatch.setattr(
        panel[panel_bg], "draw", lambda s: (drawn.append("popup"), real_bg(s))[1]
    )

    game.draw()

    assert drawn == ["coins", "pop", "popup"]
