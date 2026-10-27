"""Bombs a plane dropped keep falling after the plane leaves the map: they
land with their explosion, sound and splash damage, credited to the plane,
and are forgotten once landed (issue #50). Runs a real Game() with saves
in a temporary directory, and the menu demo."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.combat.enemy import Enemy
from gameplay.combat.projectile import Bomb
from gameplay.menu_demo import MenuDemo
from gameplay.towers import TowerFactory
from gameplay.towers.plane_tower import BOMB_DROP_INTERVAL_MS
from pygamine import SaveStore
from util.constants import TICK_MS

PLANE_TYPE = 4
TICKS_TO_LAND = int(Bomb.FALL_DURATION_MS / TICK_MS) + 5


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    g.wave_manager = None  # no spawns: only the enemies a test places
    g.game_state.is_started = True
    return g


@pytest.fixture
def played(game, monkeypatch):
    calls = []

    def spy(path):
        calls.append(path)
        return object()

    monkeypatch.setattr(game.bomb_impacts, "_play_sfx", spy)
    return calls


def plane_at_the_edge(battle, tower_config, assets, audio=None):
    """A plane whose next tick drops a bomb right at the map's right edge,
    the last moment it is still on the map; the tick after takes it off."""
    width = battle.tilemap.map_width
    plane = TowerFactory.create(
        PLANE_TYPE, 10, 40, tower_config, assets, audio, map_width=width
    )
    plane.position = Vector2(width + plane.rect.width / 2 - plane.speed, 700)
    plane.rect.center = plane.position
    plane._last_bomb_drop_at = battle.game_state.time_ms - BOMB_DROP_INTERVAL_MS
    battle.towers.append(plane)
    return plane


def standing_enemy(battle, position, hp):
    """An enemy that stays where it's put, with `hp` hit points."""
    enemy = Enemy(1, 1, 1, battle.tilemap.waypoints, battle.assets)
    enemy.position = Vector2(position)
    enemy.rect.center = enemy.position
    enemy.move = lambda game_speed: None
    enemy.hp = enemy.maxHP = hp
    battle.enemies.append(enemy)
    return enemy


def drop_and_leave(battle):
    """Tick until the plane at the edge has dropped its bomb and been
    removed; returns the bomb, still falling."""
    plane = battle.towers[-1]
    battle._tick()  # drops the bomb at the edge
    (bomb,) = plane.bullets
    battle._tick()  # flies off the map
    battle._tick()  # removed
    assert plane not in battle.towers
    return bomb


def test_a_bomb_dropped_just_before_the_plane_leaves_still_lands(
    game, played, tower_config
):
    plane = plane_at_the_edge(game, tower_config, game.assets)
    target = standing_enemy(game, (game.tilemap.map_width - 20, 700), hp=1000)

    bomb = drop_and_leave(game)
    assert list(game.orphan_bombs) == [bomb]
    game.draw()  # a falling orphan bomb is drawn
    for _ in range(TICKS_TO_LAND):
        game._tick()

    assert target.hp == 1000 - plane.damage
    assert len(game.bomb_impacts.explosions) == 1
    assert game.bomb_impacts.explosions[0].position == bomb.position
    assert played == [str(game.assets.sound_path("bomb_impact"))]
    assert plane not in game.towers
    assert not game.orphan_bombs  # forgotten once landed
    assert plane.bullets == []


def test_its_kill_and_money_are_credited_to_the_departed_plane(game, tower_config):
    plane = plane_at_the_edge(game, tower_config, game.assets)
    target = standing_enemy(game, (game.tilemap.map_width - 20, 700), hp=1)
    money = game.game_state.money

    drop_and_leave(game)
    for _ in range(TICKS_TO_LAND):
        game._tick()

    assert target not in game.enemies
    assert game.game_state.money == money + target.killMoney
    assert plane.kills == 1
    assert plane.money_earned == target.killMoney


def test_an_orphan_bomb_lands_on_the_same_tick_as_with_its_plane(game, tower_config):
    plane_at_the_edge(game, tower_config, game.assets)
    bomb = drop_and_leave(game)
    landing_at = bomb._created_at + Bomb.FALL_DURATION_MS

    while game.orphan_bombs:
        game._tick()

    assert landing_at <= game.game_state.time_ms < landing_at + TICK_MS


def test_an_orphan_bomb_waits_while_the_game_is_paused(game, tower_config):
    plane_at_the_edge(game, tower_config, game.assets)
    bomb = drop_and_leave(game)
    position = Vector2(bomb.position)

    game.game_state.is_started = False
    for _ in range(TICKS_TO_LAND):
        game._tick()

    assert list(game.orphan_bombs) == [bomb]
    assert bomb.position == position
    assert not game.bomb_impacts.explosions


def test_starting_a_new_game_or_loading_drops_orphan_bombs(game, tower_config):
    plane_at_the_edge(game, tower_config, game.assets)
    drop_and_leave(game)
    game._init_wave_manager()  # the save needs one
    game._save_game()  # in-flight bombs aren't saved

    game._load_game()
    assert not game.orphan_bombs

    plane_at_the_edge(game, tower_config, game.assets)
    game.game_state.is_started = True
    drop_and_leave(game)
    game._start_new_game()
    assert not game.orphan_bombs


def test_the_menu_demos_orphan_bombs_land_too(assets, tower_config):
    from gameplay.tilemap import Tilemap

    tilemap = Tilemap("assets/maps/tiled_tilemap.tmx")
    demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))
    demo.bomb_impacts.clear()
    demo.wave_manager = None
    demo.enemies.clear()
    demo.assets = assets
    plane_at_the_edge(demo, tower_config, assets, demo._audio)

    bomb = drop_and_leave(demo)
    demo.draw(pygame.Surface((1280, 720)))
    for _ in range(TICKS_TO_LAND):
        demo._tick()

    assert any(e.position == bomb.position for e in demo.bomb_impacts.explosions)
    assert not demo.orphan_bombs
