"""Skipping the splash with Space, Enter or a click only skips it (pygamine
v0.27.0, pygamine#7): the release of that press must not also activate the
focused PLAY button and start a run. A real Game() with its real splash,
saves in a temporary directory, driven by posted events."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return Game()


def press(kind: str) -> tuple[pygame.event.Event, pygame.event.Event]:
    if kind == "click":
        return (
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)),
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0)),
        )
    key = pygame.K_SPACE if kind == "space" else pygame.K_RETURN
    return (
        pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0),
        pygame.event.Event(pygame.KEYUP, key=key, mod=0, unicode="", scancode=0),
    )


def skip_splash(game: Game, kind: str) -> None:
    """Runs the real splash with the press posted: it skips the whole splash
    (skip_completely), and its release is left for the game's own loop."""
    down, up = press(kind)
    pygame.event.clear()
    pygame.event.post(down)
    game.show_splash()
    assert game.splash.is_done
    pygame.event.post(up)
    game._handle_events()


@pytest.mark.parametrize("kind", ["space", "enter", "click"])
def test_the_press_that_skips_the_splash_does_not_start_the_game(game, kind):
    assert game.panel_manager["main_menu"]["play"].focused  # PLAY has focus

    skip_splash(game, kind)

    assert game.panel_manager.current_panel == "main_menu"
    assert not game.game_state.is_started


@pytest.mark.parametrize("kind", ["space", "enter"])
def test_a_fresh_press_after_the_splash_activates_play(game, kind):
    skip_splash(game, kind)

    down, up = press(kind)
    pygame.event.post(down)
    pygame.event.post(up)
    game._handle_events()

    assert game.panel_manager.current_panel == "game"
