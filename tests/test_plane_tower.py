from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from domain.game_state import GameState
from gameplay.combat.projectile import Bomb
from towers import TowerFactory
from towers.plane_tower import BOMB_DROP_INTERVAL_MS

PLANE_TYPE = 4
MAP_WIDTH = 3008


def make_plane(tower_config, assets, row=5, col=3):
    return TowerFactory.create(PLANE_TYPE, row, col, tower_config, assets, audio=None, map_width=MAP_WIDTH)


def running_state(speed=1, time_ms=0.0) -> GameState:
    gs = GameState(start_money=0, start_lives=10)
    gs.is_started = True
    gs.speed = speed
    gs.time_ms = time_ms
    return gs


def test_flies_right_by_its_speed_times_game_speed_each_tick(tower_config, assets):
    plane = make_plane(tower_config, assets)
    x0 = plane.position.x
    gs = running_state(speed=2)

    plane.update(gs, [])

    assert plane.position.x == x0 + plane.speed * 2
    assert plane.rect.centerx == round(plane.position.x)


def test_stays_put_while_the_game_is_paused(tower_config, assets):
    plane = make_plane(tower_config, assets)
    x0 = plane.position.x
    gs = running_state()
    gs.is_started = False

    plane.update(gs, [])

    assert plane.position.x == x0


def test_drops_bombs_every_interval_of_game_time(tower_config, assets):
    plane = make_plane(tower_config, assets)
    gs = running_state(time_ms=1000)

    plane.update(gs, [])  # first update starts the bomb timer
    assert plane.bullets == []

    gs.time_ms += BOMB_DROP_INTERVAL_MS - 1
    plane.update(gs, [])
    assert plane.bullets == []

    gs.time_ms += 1
    plane.update(gs, [])
    assert len(plane.bullets) == 1 and isinstance(plane.bullets[0], Bomb)


def test_takes_the_global_plane_level(tower_config, assets):
    plane = make_plane(tower_config, assets)
    gs = running_state()
    gs.plane_level = 2

    plane.update(gs, [])

    assert plane.level == 2
    assert plane.damage == tower_config.damages[PLANE_TYPE - 1][1]


def test_is_removed_once_fully_past_the_right_edge_of_the_map(tower_config, assets):
    plane = make_plane(tower_config, assets)
    assert not plane.should_remove()

    plane.position.x = MAP_WIDTH + plane.rect.width / 2 + 1

    assert plane.should_remove()


def test_never_blocks_a_build_tile_and_is_untargetable(tower_config, assets):
    plane = make_plane(tower_config, assets)

    assert plane.get_blocking_position() is None
    assert plane.maxHP is None and plane.hp is None


def test_draw_renders_shadow_plane_and_range_when_selected(tower_config, assets):
    from pygamine import Camera
    plane = make_plane(tower_config, assets)
    gs = running_state()
    gs.selected_tower = plane
    camera = Camera(pygame.Rect(0, 0, 800, 600), MAP_WIDTH, 2176)
    surface = pygame.Surface((800, 600))

    plane.draw(gs, camera, surface)  # must not raise

    plane.work([], True)  # planes attack only through their bombs
