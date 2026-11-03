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
    assert game.toggles[name] is (other == "ON")

    click(game, f"{name}_back_button")
    assert value(game, name) == default
    assert game.toggles[name] is (default == "ON")


def test_the_toggles_are_saved_and_loaded(make_game):
    first = make_game()
    first.set_toggle("skip_intro", True)
    first.set_toggle("pause_on_focus_loss", False)
    first.set_toggle("reduce_flashing", True)
    first._save_settings()

    second = make_game()

    assert second.toggles["skip_intro"] is True
    assert second.toggles["pause_on_focus_loss"] is False
    assert second.toggles["reduce_flashing"] is True
    assert second.menu_demo.hit_feedback.reduce_flashing is True


def test_reset_restores_the_shipped_defaults(game):
    game.set_toggle("skip_intro", True)
    game.set_toggle("pause_on_focus_loss", False)
    game.set_toggle("reduce_flashing", True)

    game._reset_settings()

    assert (
        game.toggles["skip_intro"],
        game.toggles["pause_on_focus_loss"],
        game.toggles["reduce_flashing"],
    ) == (
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
    first.set_toggle("skip_intro", True)
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
    game.set_toggle("skip_intro", True)  # takes effect on the next launch

    assert isinstance(game.splash, SplashScreen)


# ── pause on focus loss ───────────────────────────────────────────────────────


@pytest.fixture
def window_focus(monkeypatch):
    """Sets what pygame.key.get_focused() reports (the window's real focus)."""
    state = {"focused": True}
    monkeypatch.setattr(pygame.key, "get_focused", lambda: state["focused"])
    return state


def send(game, *events):
    """Posts the events and lets the game take them, as its loop does."""
    pygame.event.clear()
    for event in events:
        pygame.event.post(event)
    game._handle_events()


def lose_focus(game, window_focus):
    window_focus["focused"] = False
    send(game, focus(pygame.WINDOWFOCUSLOST))
    game.update()


def regain_focus(game, window_focus):
    window_focus["focused"] = True
    send(game, focus(pygame.WINDOWFOCUSGAINED))
    game.update()


def test_focus_loss_pauses_a_battle_like_esc(game, window_focus):
    start_battle(game)

    lose_focus(game, window_focus)

    assert game.pause_panel.is_open
    assert not game.game_state.is_started
    assert game._resume_on_unpause  # the same bookkeeping as Esc


def test_focus_gain_does_not_resume(game, window_focus):
    start_battle(game)
    lose_focus(game, window_focus)

    regain_focus(game, window_focus)

    assert game.pause_panel.is_open
    assert not game.game_state.is_started


def test_focus_loss_does_not_pause_when_off(game, window_focus):
    game.set_toggle("pause_on_focus_loss", False)
    start_battle(game)

    lose_focus(game, window_focus)

    assert not game.pause_panel.is_open
    assert game.game_state.is_started


def test_focus_loss_does_nothing_in_the_menus(game, window_focus):
    lose_focus(game, window_focus)

    assert game.panel_manager.current_panel == "main_menu"
    assert not game.pause_panel.is_open


@pytest.mark.parametrize("popup", ["victory", "gameover"])
def test_focus_loss_does_nothing_with_a_popup_open(game, window_focus, popup):
    start_battle(game)
    if popup == "victory":
        game._trigger_victory()
    else:
        game._trigger_game_over()

    lose_focus(game, window_focus)

    assert not game.pause_panel.is_open


def test_focus_loss_with_the_pause_menu_open_keeps_it_as_it_was(game, window_focus):
    start_battle(game)
    game._open_pause_menu()

    lose_focus(game, window_focus)

    assert game.pause_panel.is_open
    assert game._resume_on_unpause  # not overwritten by a second open


def test_a_focus_blip_from_a_window_mode_change_does_not_pause(game, window_focus):
    """F11 makes SDL send focus-lost and focus-gained in a row; the window
    has its focus again by the next update, so the run goes on."""
    start_battle(game)

    send(game, focus(pygame.WINDOWFOCUSLOST), focus(pygame.WINDOWFOCUSGAINED))
    game.update()

    assert not game.pause_panel.is_open
    assert game.game_state.is_started


def test_a_focus_loss_the_window_has_already_recovered_from_does_not_pause(
    game, window_focus
):
    start_battle(game)

    send(game, focus(pygame.WINDOWFOCUSLOST))  # the gain event isn't in yet...
    game.update()  # ...but the window is focused when the frame updates

    assert not game.pause_panel.is_open


# ── the click that brings the window back ─────────────────────────────────────


def press_and_release(game, pos):
    game.mouse.position = pos
    send(
        game,
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos),
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos),
    )


def test_the_click_that_refocuses_does_not_hit_the_pause_menu(game, window_focus):
    start_battle(game)
    lose_focus(game, window_focus)
    regain_focus(game, window_focus)
    main_menu = game.panel_manager["game"]["pause_main_menu"]

    press_and_release(game, main_menu.rect.center)  # the refocusing click

    assert game.panel_manager.current_panel == "game"
    assert game.pause_panel.is_open

    press_and_release(game, main_menu.rect.center)  # a real click

    assert game.panel_manager.current_panel == "main_menu"


def test_a_press_long_after_refocusing_without_a_click_is_not_swallowed(
    game, window_focus, fake_ticks
):
    """Alt-tab or the taskbar brings the window back with no click; the
    player's first deliberate click, on Resume, must work."""
    start_battle(game)
    lose_focus(game, window_focus)
    regain_focus(game, window_focus)
    fake_ticks["t"] += 1000
    resume = game.panel_manager["game"]["pause_back"]

    press_and_release(game, resume.rect.center)

    assert not game.pause_panel.is_open


def test_clicks_are_not_swallowed_after_an_ordinary_focus_change(game, window_focus):
    """Only a focus-loss pause arms it: here the pause menu was opened by the
    player and focus came and went."""
    start_battle(game)
    game._open_pause_menu()
    window_focus["focused"] = False
    send(game, focus(pygame.WINDOWFOCUSLOST))
    game.update()
    regain_focus(game, window_focus)
    back = game.panel_manager["game"]["pause_back"]

    press_and_release(game, back.rect.center)

    assert not game.pause_panel.is_open


# ── focus the window never reported ───────────────────────────────────────────


def test_the_window_focus_is_read_not_assumed(make_game, window_focus):
    """Opened in the background, or the focus lost during the splash (whose
    own loop takes the events): no event ever told the game."""
    window_focus["focused"] = False
    game = make_game()

    assert game._window_focused is False

    window_focus["focused"] = True
    game.update()

    assert game._window_focused is True


def test_focus_taken_during_the_splash_is_picked_up_by_the_next_update(
    game, window_focus
):
    assert game._window_focused is True

    window_focus["focused"] = False  # no event reached handle_event
    game.update()

    assert game._window_focused is False


# ── edge scrolling while unfocused ────────────────────────────────────────────


def camera_spot(game):
    return tuple(game.camera.world_to_screen((0, 0)))


@pytest.mark.parametrize("pause_on_focus_loss", [True, False])
def test_no_edge_scroll_while_unfocused(game, window_focus, pause_on_focus_loss):
    game.set_toggle("pause_on_focus_loss", pause_on_focus_loss)
    start_battle(game)
    game.camera.center_on((1500, 1000))
    game.mouse.position = (0, 0)  # in the top-left edge zone
    lose_focus(game, window_focus)
    game._close_pause_menu()  # with the toggle on, the pause menu is open too
    before = camera_spot(game)

    for _ in range(5):
        game._update_game(16)

    assert camera_spot(game) == before


def test_edge_scroll_runs_again_once_focus_returns(game, window_focus):
    start_battle(game)
    game.camera.center_on((1500, 1000))
    game.mouse.position = (0, 0)
    lose_focus(game, window_focus)
    regain_focus(game, window_focus)
    game._close_pause_menu()
    before = camera_spot(game)

    game._update_game(16)

    assert camera_spot(game) != before
