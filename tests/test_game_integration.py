"""A real Game(), driven through its public update()/draw() loop.

The other Game tests build a bare instance and stub what each method
touches. These build the whole thing (panels, tilemap, assets, camera)
and play it, to catch what only shows up when the pieces run together:
the viewport at startup, the fixed simulation tick, game speed, pausing,
saving. Saves go to a temporary directory, never the repo's saves/.
"""

from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from pygamine import SaveStore
from util.constants import TILE_SIZE, HALF_TILE, TICK_MS


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    """Builds a real Game whose saves live in tmp_path. Optionally seeds
    the saved settings first (e.g. a window size), as a returning player
    would have."""
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    # Mouse parked mid-window: at the dummy driver's (0, 0) the camera would
    # edge-scroll every frame.
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))

    def build(settings=None):
        if settings is not None:
            SaveStore("settings", directory=tmp_path).save(settings)
        return Game()

    return build


def play(game, fake_ticks, seconds, fps=60, draw_every=0):
    """Runs the real update() loop for `seconds` of wall-clock time at `fps`."""
    frame_ms = 1000 / fps
    for i in range(round(seconds * fps)):
        fake_ticks["t"] += frame_ms
        game.update()
        if draw_every and i % draw_every == 0:
            game.draw()


def place_defence(game, types=(1, 1, 2)):
    """Buys towers on the first buildable tiles beside the path's opening
    stretch -- a fixed, reproducible layout (paid for with a top-up: these
    tests are about the loop, not the economy)."""
    game.game_state.money = 2000
    a, b = game.tilemap.waypoints[0], game.tilemap.waypoints[1]
    path = [a + (b - a) * (i / 20) for i in range(21)]
    grid = game.tilemap.buildable_grid
    tiles = [
        (r, c)
        for r, row in enumerate(grid)
        for c, ok in enumerate(row)
        if ok
        and min(
            (Vector2(c * TILE_SIZE + HALF_TILE, r * TILE_SIZE + HALF_TILE) - p).length()
            for p in path
        )
        < 120
    ]
    controller = game.tower_controller
    game.camera.center_on(a)  # purchases only land on tiles in view
    for tower_type, (r, c) in zip(types, tiles):
        controller.buying_tower_type = tower_type
        controller.cursor_row, controller.cursor_col = r, c
        controller._handle_tower_purchase(
            game.camera.world_to_screen((c * TILE_SIZE, r * TILE_SIZE))
        )
    assert len(game.towers) == len(types)


def snapshot(game):
    gs = game.game_state
    return (
        gs.money,
        gs.lives,
        gs.level,
        len(game.enemies),
        sorted((round(e.position.x), round(e.position.y)) for e in game.enemies),
    )


# ── startup ─────────────────────────────────────────────────────────────────


def test_a_saved_window_size_reaches_the_viewport_at_startup(make_game):
    """Startup used to keep config's 1920x1080 viewport whatever size the
    window was restored at, until the first resize: at 1280x720 the right
    of the map, where enemies spawn, couldn't be scrolled to."""
    game = make_game({"window_mode": "windowed", "window_size": [1280, 720]})

    assert game.window.get_size() == (1280, 720)
    assert game.game_area.size == (1280, 720)

    game.camera.center_on((game.map_width, game.map_height))
    corner = game.camera.world_to_screen((game.map_width, game.map_height))
    assert (round(corner.x), round(corner.y)) == (1280, 720)


def test_a_new_game_opens_with_the_path_entrance_in_view(make_game):
    game = make_game()
    game._start_new_game()

    spawn = game.camera.world_to_screen(game.tilemap.waypoints[0])
    assert game.game_area.collidepoint(spawn)


# ── playing ─────────────────────────────────────────────────────────────────


def test_a_defended_opening_wave_is_fought_through_the_real_loop(make_game, fake_ticks):
    game = make_game()
    game._start_new_game()
    place_defence(game)
    money_after_buying = game.game_state.money
    game.game_state.is_started = True

    play(game, fake_ticks, seconds=30, draw_every=15)

    assert game.game_state.money > money_after_buying  # kills paid out
    assert game.game_state.level >= 2  # wave 1 cleared
    assert game.game_state.lives > 0


def test_the_same_session_plays_out_identically_at_any_frame_rate(
    make_game, fake_ticks
):
    """The bug this guards: movement was per rendered frame while timers
    were in ms, so a 60 fps machine played a slower, different game."""
    results = []
    for fps in (30, 144):
        fake_ticks["t"] = 0
        game = make_game()
        game._start_new_game()
        game.game_state.is_started = True
        game.update()  # prime the frame clock so both runs simulate exactly 8 s
        play(game, fake_ticks, seconds=8, fps=fps)  # wave 1 still walking the path
        results.append(snapshot(game))

    assert results[0][3] > 0, "snapshot taken with no enemies to compare"
    assert results[0] == results[1]


def test_x4_speed_runs_the_game_clock_four_times_as_fast(make_game, fake_ticks):
    """Speed has to scale timers (spawns, reloads) along with movement --
    it used to scale movement only."""
    game = make_game()
    game._start_new_game()
    game.game_state.is_started = True
    game.game_state.speed = 4

    play(game, fake_ticks, seconds=2)

    real_ms = (
        2000 - 1000 / 60
    )  # the first update() has no previous frame to measure from
    assert game.game_state.time_ms == pytest.approx(4 * real_ms, abs=4 * TICK_MS)


def test_pausing_freezes_the_game_clock_and_the_enemies(make_game, fake_ticks):
    game = make_game()
    game._start_new_game()
    game.game_state.is_started = True
    play(game, fake_ticks, seconds=3)
    assert game.enemies

    game.game_state.is_started = False
    before = (game.game_state.time_ms, snapshot(game))
    play(game, fake_ticks, seconds=5)

    assert (game.game_state.time_ms, snapshot(game)) == before


# ── screens ─────────────────────────────────────────────────────────────────


def test_every_screen_and_game_overlay_draws(make_game, fake_ticks):
    game = make_game()
    for panel in ("main_menu", "play_menu", "credits", "settings"):
        game.panel_manager.current_panel = panel
        play(game, fake_ticks, seconds=0.1)
        game.draw()

    game._start_new_game()
    place_defence(game, types=(2, 4))
    game.game_state.is_started = True
    play(game, fake_ticks, seconds=4, draw_every=20)

    game.game_state.selected_tower = game.towers[0]
    game.draw()
    game.tower_controller.buying_tower_type = 3
    game.draw()
    game._trigger_victory()
    game.draw()
    game._close_victory_popup()
    game._trigger_game_over()
    game.draw()


# ── the main menu's live background ─────────────────────────────────────────


def test_the_menu_demo_plays_in_a_world_of_its_own(make_game, fake_ticks, tmp_path):
    game = make_game()
    game.panel_manager.current_panel = "main_menu"
    before = snapshot(game)
    demo_state, demo_time = game.menu_demo.game_state, game.menu_demo.game_state.time_ms

    play(game, fake_ticks, seconds=10, draw_every=10)

    # The demo played on (or already began a new run)...
    assert game.menu_demo.game_state is not demo_state or demo_state.time_ms > demo_time
    assert game.menu_demo.towers is not game.towers
    assert game.menu_demo.enemies is not game.enemies
    # ...while the player's game didn't move.
    assert snapshot(game) == before
    assert not (tmp_path / "save.json").exists()


def test_play_after_watching_the_menu_demo_starts_a_fresh_game(make_game, fake_ticks):
    game = make_game()
    game.panel_manager.current_panel = "main_menu"
    play(game, fake_ticks, seconds=5)

    game._start_new_game()

    assert game.panel_manager.current_panel == "game"
    assert game.towers == [] and game.enemies == []
    assert (game.game_state.level, game.game_state.time_ms) == (1, 0.0)
    assert game.game_state.money == game._starting_money


# ── leaving and coming back ─────────────────────────────────────────────────


def test_leaving_a_game_saves_it_and_continue_restores_it(make_game, fake_ticks):
    game = make_game()
    game._start_new_game()
    place_defence(game)
    game.game_state.is_started = True
    play(game, fake_ticks, seconds=5)
    towers, money = len(game.towers), game.game_state.money

    game.on_exit_request()  # Esc on the game panel opens the pause menu
    game._leave_game_for_main_menu()  # and its Main menu leaves
    assert game.panel_manager.current_panel == "main_menu"
    assert game._has_saved_game()

    game._start_new_game()
    assert game.towers == []
    game._load_game()

    assert (len(game.towers), game.game_state.money) == (towers, money)
    assert game.panel_manager.current_panel == "game"
