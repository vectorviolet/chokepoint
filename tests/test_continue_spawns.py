"""Continuing a saved run keeps the waves coming (#25).

Each test saves a run in one Game and continues it in a brand-new Game,
as relaunching the game does: game time starts again from 0, and a wave
end the save left pending is restored at time 0. That used to read as "no
wave end pending", so the next wave never came. Saves go to a temporary
directory, never the repo's saves/.
"""

from functools import partial

import pygame
import pytest

import app.game
from app.game import WIN_WAVE, Game
from gameplay.combat.wave_manager import WaveManager
from pygamine import SaveStore

FRAME = 1000 / 60
NEXT_WAVE_MS = WaveManager.LEVEL_END_DELAY_MS + 2 * WaveManager.SPAWN_INTERVAL_MS


@pytest.fixture
def new_game(monkeypatch, tmp_path, fake_ticks):
    """A fresh Game, as after launching: its game clock starts at 0."""
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    return Game


def play(game, fake_ticks, ms):
    for _ in range(round(ms / FRAME)):
        fake_ticks["t"] += FRAME
        game.update()


def play_until(game, fake_ticks, done, limit_ms=120_000):
    for _ in range(round(limit_ms / FRAME)):
        if done():
            return
        fake_ticks["t"] += FRAME
        game.update()
    raise AssertionError("never got there")


def wave_fully_spawned(game):
    wm = game.wave_manager
    return wm._spawn_queue and wm._queue_index == len(wm._spawn_queue)


def continue_in_a_new_game(new_game, fake_ticks, save):
    """Saves `save`'s run, then loads it in a fresh Game and starts it."""
    save.game_state.is_started = False
    save._save_game()
    game = new_game()
    game._load_game()
    assert game.game_state.time_ms == 0  # a fresh process
    game.game_state.is_started = True
    return game


def run_to_end_of_wave(new_game, fake_ticks, level=1):
    game = new_game()
    game._start_new_game()
    game.game_state.level = level
    game.game_state.is_started = True
    play_until(game, fake_ticks, lambda: wave_fully_spawned(game))
    return game


# ── the reported save: between waves ──────────────────────────────────────────


def test_continuing_between_waves_starts_the_next_wave(new_game, fake_ticks):
    """The reported save: wave 2 fully spawned, every enemy gone."""
    before = run_to_end_of_wave(new_game, fake_ticks, level=2)
    before.enemies.clear()
    assert before.wave_manager._level_finish_time is not None

    game = continue_in_a_new_game(new_game, fake_ticks, before)
    play(game, fake_ticks, NEXT_WAVE_MS)

    assert game.game_state.level == 3
    assert game.enemies, "the next wave should be spawning"


# ── other save states ─────────────────────────────────────────────────────────


def test_continuing_after_the_last_spawn_ends_the_wave_once_it_is_cleared(
    new_game, fake_ticks
):
    before = run_to_end_of_wave(new_game, fake_ticks)
    assert before.enemies  # the wave's enemies are still on the path

    game = continue_in_a_new_game(new_game, fake_ticks, before)
    game.enemies.clear()  # the defence finishes them off
    play(game, fake_ticks, NEXT_WAVE_MS)

    assert game.game_state.level == 2
    assert game.enemies


def test_continuing_mid_wave_spawns_the_rest_of_it(new_game, fake_ticks):
    before = new_game()
    before._start_new_game()
    before.game_state.is_started = True
    play_until(before, fake_ticks, lambda: before.wave_manager._queue_index >= 2)
    spawned = before.wave_manager._queue_index

    game = continue_in_a_new_game(new_game, fake_ticks, before)
    play(game, fake_ticks, 3 * WaveManager.SPAWN_INTERVAL_MS)

    assert game.wave_manager._queue_index > spawned


def test_continuing_after_victory_goes_on_into_endless_mode(new_game, fake_ticks):
    before = run_to_end_of_wave(new_game, fake_ticks, level=WIN_WAVE)
    before.enemies.clear()
    play_until(before, fake_ticks, lambda: before.game_state.has_won)
    assert before.game_state.level == WIN_WAVE + 1

    game = continue_in_a_new_game(new_game, fake_ticks, before)
    game._close_victory_popup()
    play(game, fake_ticks, 3 * WaveManager.SPAWN_INTERVAL_MS)

    assert game.game_state.level == WIN_WAVE + 1
    assert game.enemies


def test_continuing_between_endless_waves_starts_the_next_one(new_game, fake_ticks):
    level = WIN_WAVE + 4
    before = run_to_end_of_wave(new_game, fake_ticks, level=level)
    before.game_state.has_won = True
    before.enemies.clear()

    game = continue_in_a_new_game(new_game, fake_ticks, before)
    play(game, fake_ticks, NEXT_WAVE_MS)

    assert game.game_state.level == level + 1
    assert game.enemies
