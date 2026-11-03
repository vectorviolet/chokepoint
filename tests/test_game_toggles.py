"""The GAME and DISPLAY tab toggles (#115, #116, #117): rows, saving, reset,
skip intro and pause on focus loss, on a real Game() (saves in a temporary
directory)."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore, SplashScreen


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return Game


@pytest.fixture
def game(make_game):
    return make_game()


def click(game, name):
    obj = game.panel_manager["settings"][name]
    game.mouse.position = obj.rect.center
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=obj.rect.center))


def value(game, name) -> str:
    return game.panel_manager["settings"][f"{name}_value_text"].text


def open_tab(game, key):
    game._open_settings("main_menu")
    game._show_settings_tab(key)


def start_battle(game):
    game.panel_manager.current_panel = "game"
    game._set_started(True)


def focus(kind):
    return pygame.event.Event(kind)


# ── the rows ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tab, name, default",
    [
        ("game", "skip_intro", "OFF"),
        ("game", "pause_on_focus_loss", "ON"),
        ("display", "reduce_flashing", "OFF"),
    ],
)
def test_a_row_shows_its_default_and_both_arrows_toggle_it(game, tab, name, default):
    open_tab(game, tab)
    assert value(game, name) == default
    other = "OFF" if default == "ON" else "ON"

    click(game, f"{name}_next_button")
    assert value(game, name) == other
    assert getattr(game, name) is (other == "ON")

    click(game, f"{name}_back_button")
    assert value(game, name) == default
    assert getattr(game, name) is (default == "ON")


def test_the_toggles_are_saved_and_loaded(make_game):
    first = make_game()
    first.skip_intro = True
    first.pause_on_focus_loss = False
    first.reduce_flashing = True
    first._save_settings()

    second = make_game()

    assert second.skip_intro is True
    assert second.pause_on_focus_loss is False
    assert second.reduce_flashing is True
    assert second.menu_demo.hit_feedback.reduce_flashing is True


def test_reset_restores_the_shipped_defaults(game):
    game.skip_intro = True
    game.pause_on_focus_loss = False
    game.reduce_flashing = True

    game._reset_settings()

    assert (game.skip_intro, game.pause_on_focus_loss, game.reduce_flashing) == (
        False,
        True,
        False,
    )
    assert game.hit_feedback.reduce_flashing is False
    assert game.menu_demo.hit_feedback.reduce_flashing is False


# ── skip intro ────────────────────────────────────────────────────────────────


def test_with_skip_intro_off_the_splash_is_set_up(game):
    assert isinstance(game.splash, SplashScreen)


def test_with_skip_intro_on_no_splash_runs_at_startup(make_game, monkeypatch):
    first = make_game()
    first.skip_intro = True
    first._save_settings()
    runs = []
    monkeypatch.setattr(SplashScreen, "run", lambda *a, **k: runs.append(a))

    second = make_game()
    second.show_splash()

    assert second.splash is None
    assert runs == []


def test_with_skip_intro_off_the_splash_runs_at_startup(game, monkeypatch):
    runs = []
    monkeypatch.setattr(SplashScreen, "run", lambda *a, **k: runs.append(a))

    game.show_splash()

    assert len(runs) == 1


def test_toggling_skip_intro_does_not_touch_the_running_splash(game):
    game.skip_intro = True  # takes effect on the next launch

    assert isinstance(game.splash, SplashScreen)


# ── pause on focus loss ───────────────────────────────────────────────────────


def test_focus_loss_pauses_a_battle_like_esc(game):
    start_battle(game)

    game.handle_event(focus(pygame.WINDOWFOCUSLOST))

    assert game.pause_panel.is_open
    assert not game.game_state.is_started
    assert game._resume_on_unpause  # the same bookkeeping as Esc


def test_focus_gain_does_not_resume(game):
    start_battle(game)
    game.handle_event(focus(pygame.WINDOWFOCUSLOST))

    game.handle_event(focus(pygame.WINDOWFOCUSGAINED))

    assert game.pause_panel.is_open
    assert not game.game_state.is_started


def test_focus_loss_does_not_pause_when_off(game):
    game.pause_on_focus_loss = False
    start_battle(game)

    game.handle_event(focus(pygame.WINDOWFOCUSLOST))

    assert not game.pause_panel.is_open
    assert game.game_state.is_started


def test_focus_loss_does_nothing_in_the_menus(game):
    game.handle_event(focus(pygame.WINDOWFOCUSLOST))

    assert game.panel_manager.current_panel == "main_menu"
    assert not game.pause_panel.is_open


@pytest.mark.parametrize("popup", ["victory", "gameover"])
def test_focus_loss_does_nothing_with_a_popup_open(game, popup):
    start_battle(game)
    if popup == "victory":
        game._trigger_victory()
    else:
        game._trigger_game_over()

    game.handle_event(focus(pygame.WINDOWFOCUSLOST))

    assert not game.pause_panel.is_open


def test_focus_loss_with_the_pause_menu_open_keeps_it_as_it_was(game):
    start_battle(game)
    game._open_pause_menu()

    game.handle_event(focus(pygame.WINDOWFOCUSLOST))

    assert game.pause_panel.is_open
    assert game._resume_on_unpause  # not overwritten by a second open


# ── edge scrolling while unfocused ────────────────────────────────────────────


def camera_spot(game):
    return tuple(game.camera.world_to_screen((0, 0)))


@pytest.mark.parametrize("pause_on_focus_loss", [True, False])
def test_no_edge_scroll_while_unfocused(game, pause_on_focus_loss):
    game.pause_on_focus_loss = pause_on_focus_loss
    start_battle(game)
    game.camera.center_on((1500, 1000))
    game.mouse.position = (0, 0)  # in the top-left edge zone
    game.handle_event(focus(pygame.WINDOWFOCUSLOST))
    game._close_pause_menu()  # with the toggle on, the pause menu is open too
    before = camera_spot(game)

    for _ in range(5):
        game._update_game(16)

    assert camera_spot(game) == before


def test_edge_scroll_runs_again_once_focus_returns(game):
    start_battle(game)
    game.camera.center_on((1500, 1000))
    game.mouse.position = (0, 0)
    game.handle_event(focus(pygame.WINDOWFOCUSLOST))
    game.handle_event(focus(pygame.WINDOWFOCUSGAINED))
    game._close_pause_menu()
    before = camera_spot(game)

    game._update_game(16)

    assert camera_spot(game) != before
