"""MenuDemo -- the battle that plays itself behind the main menu.

It runs the real BattleSimulation in a world of its own, so these check
that it stays busy and keeps going, and that nothing it does reaches the
player: no saves, no sound, no shared state with the real game.
"""

import random

import pygame
import pytest
from pygame.math import Vector2

from gameplay import menu_demo
from gameplay.menu_demo import (
    FADE_S,
    GROUND_TOWER_TYPES,
    MIN_TOWERS_LEFT,
    PLANE_TYPE,
    START_LEVELS,
    TOWER_PATH_DISTANCE,
    WAVE_SIZE_FACTOR,
    MenuDemo,
    _distance_to_path,
)
from gameplay.tilemap import Tilemap
from pygamine import GameAudio, SaveStore
from util.constants import TILE_SIZE, HALF_TILE


@pytest.fixture(scope="module")
def tilemap():
    return Tilemap("assets/tiled_project/tiled_tilemap.tmx")


@pytest.fixture
def make_demo(tilemap, assets, tower_config):
    def build(seed=1, size=(1280, 720)):
        return MenuDemo(tilemap, assets, tower_config, size, random.Random(seed))

    return build


def run(demo, seconds, fps=60):
    for _ in range(round(seconds * fps)):
        demo.update(1000 / fps)


def finish_fade_out(demo):
    run(demo, FADE_S + 0.1)


# ── a run ────────────────────────────────────────────────────────────────────


def test_a_run_opens_on_a_battle_under_way(make_demo):
    demo = make_demo()

    assert START_LEVELS[0] <= demo.game_state.level <= START_LEVELS[1]
    assert demo.game_state.is_started
    assert demo.enemies, "the pre-warm should already have enemies on the path"
    assert (
        sum(t.tower_type in GROUND_TOWER_TYPES for t in demo.towers) >= MIN_TOWERS_LEFT
    )


def test_towers_stand_on_free_build_tiles_within_reach_of_the_path(make_demo, tilemap):
    demo = make_demo()
    near, far = TOWER_PATH_DISTANCE
    ground = [t for t in demo.towers if t.tower_type in GROUND_TOWER_TYPES]

    assert len({(t.row, t.col) for t in ground}) == len(ground)
    for t in ground:
        assert tilemap.buildable_grid[t.row][t.col]
        centre = Vector2(t.col * TILE_SIZE + HALF_TILE, t.row * TILE_SIZE + HALF_TILE)
        assert near <= _distance_to_path(centre, tilemap.waypoints) <= far


def test_planes_fly_bombing_runs(make_demo):
    demo = make_demo()
    demo._next_plane_at = demo.game_state.time_ms  # due now

    run(demo, 0.1)

    assert any(t.tower_type == PLANE_TYPE for t in demo.towers)


def test_its_waves_are_denser_than_the_real_games(make_demo):
    demo = make_demo()
    from gameplay.combat.wave_manager import WaveManager

    real = WaveManager(demo.tilemap.waypoints, demo._assets)
    real._build_queue(demo.game_state.level)
    demo.wave_manager._build_queue(demo.game_state.level)

    assert len(demo.wave_manager._spawn_queue) == WAVE_SIZE_FACTOR * len(
        real._spawn_queue
    )
    assert demo.wave_manager._spawn_interval_ms < real._spawn_interval_ms


def test_the_same_seed_plays_the_same_run(make_demo):
    a, b = make_demo(seed=7), make_demo(seed=7)
    layout = lambda d: [(t.tower_type, t.row, t.col, t.level) for t in d.towers]

    assert layout(a) == layout(b)
    assert a.game_state.level == b.game_state.level


def test_different_seeds_play_different_runs(make_demo):
    layout = lambda d: [(t.tower_type, t.row, t.col) for t in d.towers]
    assert layout(make_demo(seed=1)) != layout(make_demo(seed=2))


# ── it keeps going ───────────────────────────────────────────────────────────


def test_enemies_reaching_the_end_cost_nothing(make_demo):
    demo = make_demo()
    enemy = demo.enemies[0]
    enemy.waypoint_index = len(enemy.waypoints)  # at the end of the path
    lives = demo.game_state.lives

    demo._update_enemies()

    assert enemy not in demo.enemies
    assert demo.game_state.lives == lives


def test_after_its_last_wave_it_fades_out_and_starts_a_new_run(make_demo):
    demo = make_demo()
    old_state = demo.game_state
    demo.game_state.level = demo._last_level

    run(demo, 1 / 60)
    assert demo._fading_out
    finish_fade_out(demo)

    assert demo.game_state is not old_state
    assert not demo._fading_out
    assert demo.enemies and demo.towers


def test_a_worn_down_defence_starts_a_new_run(make_demo):
    demo = make_demo()
    old_state = demo.game_state
    ground = [t for t in demo.towers if t.tower_type in GROUND_TOWER_TYPES]
    for tower in ground[: len(ground) - MIN_TOWERS_LEFT + 1]:
        demo.towers.remove(tower)

    run(demo, 1 / 60)
    finish_fade_out(demo)

    assert demo.game_state is not old_state


def test_it_fades_in_from_black(make_demo):
    demo = make_demo()
    assert demo._fade == 1.0

    run(demo, FADE_S / 2)
    assert 0 < demo._fade < 1
    run(demo, FADE_S)
    assert demo._fade == 0


def test_a_long_session_keeps_running(make_demo):
    demo = make_demo(seed=3)
    surface = pygame.Surface((1280, 720))
    for _ in range(60 * 45):  # 45 s
        demo.update(1000 / 60)
    demo.draw(surface)

    assert demo.game_state.is_started


# ── the camera ───────────────────────────────────────────────────────────────


def test_the_camera_follows_the_fighting(make_demo):
    demo = make_demo()
    run(demo, 8)

    # Whatever it's following, the view sits inside the map.
    top_left = demo.camera.world_to_screen((0, 0))
    bottom_right = demo.camera.world_to_screen((demo.map_width, demo.map_height))
    assert top_left.x <= 0 and top_left.y <= 0
    assert bottom_right.x >= demo.view.width and bottom_right.y >= demo.view.height


def test_a_followed_enemy_frames_its_whole_group(make_demo):
    demo = make_demo()
    a, b = demo.enemies[0], demo.enemies[1]
    demo.enemies[:] = [a, b]
    a.position, b.position = Vector2(1000, 1000), Vector2(1200, 1000)
    demo._camera_target = a

    assert demo._target_position() == Vector2(1100, 1000)


def test_resize_keeps_the_view_on_the_same_spot(make_demo):
    demo = make_demo(size=(1280, 720))
    # Mid-map, so the map edges clamp neither view.
    demo._camera_pos = Vector2(demo.map_width / 2, demo.map_height / 2)
    demo.camera.center_on(demo._camera_pos)
    centre = demo.camera.screen_to_world(demo.view.center)

    demo.resize((1920, 1080))

    assert demo.view.size == (1920, 1080)
    assert demo.camera.screen_to_world(demo.view.center).distance_to(centre) < 1


# ── nothing reaches the player ───────────────────────────────────────────────


def test_it_never_saves(make_demo, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the menu demo touched a save")

    monkeypatch.setattr(SaveStore, "save", forbidden)
    monkeypatch.setattr(SaveStore, "delete", forbidden)

    demo = make_demo()
    for enemy in demo.enemies:
        enemy.waypoint_index = len(enemy.waypoints)
    run(demo, 20)


def test_its_towers_make_no_sound(make_demo, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the menu demo played a sound")

    monkeypatch.setattr(GameAudio, "play_sfx", staticmethod(forbidden))

    demo = make_demo()
    run(demo, 5)

    assert all(isinstance(t.audio, menu_demo._SilentAudio) for t in demo.towers)


# ── geometry helper ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "point, expected",
    [
        ((50, 0), 0),  # on the first segment
        ((50, 30), 30),  # beside it
        ((-40, 0), 40),  # before its start
        ((130, 50), 30),  # beside the second segment
    ],
)
def test_distance_to_path(point, expected):
    path = [Vector2(0, 0), Vector2(100, 0), Vector2(100, 100)]
    assert _distance_to_path(Vector2(point), path) == pytest.approx(expected)
