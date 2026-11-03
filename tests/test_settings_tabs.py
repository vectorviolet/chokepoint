"""The Settings tabs, on a real Game: only the open tab's rows show, hidden
rows can't be clicked or focused, reset covers every tab, saving still works."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from app.settings_tabs import SETTINGS_TABS
from app.volume_settings import VOLUME_SETTINGS
from pygamine import SaveStore

AUDIO_ROWS = [
    name
    for v in VOLUME_SETTINGS
    for name in (v.slider, v.label, v.slider.replace("slider", "label_text"))
]
DISPLAY_ROWS = [
    "window_size_back_button",
    "window_size_next_button",
    "window_mode_back_button",
    "window_mode_next_button",
    "window_size_value_text",
    "window_mode_value_text",
]


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._open_settings("main_menu")
    return g


def panel(game):
    return game.panel_manager["settings"]


def click(game, obj):
    game.mouse.position = obj.rect.center
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=obj.rect.center))


def key_up(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYUP, key=key))


def test_opens_on_display_with_only_its_rows(game):
    p = panel(game)
    assert game.panel_manager.current_panel == "settings"
    assert game.settings_tabs.active == "display"
    assert all(p[n].active for n in DISPLAY_ROWS)
    assert not any(p[n].active for n in AUDIO_ROWS)


def test_clicking_a_tab_shows_only_its_rows(game):
    p = panel(game)
    click(game, p["tab_audio_button"])
    assert game.settings_tabs.active == "audio"
    assert all(p[n].active for n in AUDIO_ROWS)
    assert not any(p[n].active for n in DISPLAY_ROWS)


def test_hidden_tabs_have_no_visible_button(game):
    p = panel(game)
    for tab in SETTINGS_TABS:
        assert p[tab.button].active == tab.shown
    assert not p["tab_game_button"].active
    assert not p["tab_controls_button"].active
    click(game, p["tab_game_button"])  # nothing there to click
    assert game.settings_tabs.active == "display"


def test_active_tab_button_is_highlighted(game):
    p = panel(game)
    assert p["tab_display_button"]._state == "selected"
    assert p["tab_audio_button"]._state is None
    click(game, p["tab_audio_button"])
    assert p["tab_audio_button"]._state == "selected"
    assert p["tab_display_button"]._state is None


def test_hidden_rows_are_not_clickable(game):
    p = panel(game)
    click(game, p["tab_audio_button"])
    steps = []
    game.cycle_resolution = steps.append
    click(game, p["window_size_next_button"])  # on DISPLAY, which is hidden now
    assert steps == []


def test_visible_rows_still_work(game):
    p = panel(game)
    steps = []
    game.cycle_resolution = steps.append
    click(game, p["window_size_next_button"])
    assert steps == [1]


def test_focus_order_covers_tabs_and_open_tab_rows_only(game):
    p = panel(game)
    buttons = game.menu_controllers["settings"].buttons
    assert buttons[:2] == [p["tab_display_button"], p["tab_audio_button"]]
    assert p["window_size_next_button"] in buttons
    assert p["tab_game_button"] not in buttons
    assert p["back"] in buttons and p["reset"] in buttons
    click(game, p["tab_audio_button"])
    buttons = game.menu_controllers["settings"].buttons
    assert p["window_size_next_button"] not in buttons
    assert buttons[:2] == [p["tab_display_button"], p["tab_audio_button"]]


def test_keyboard_moves_focus_and_selects_a_tab(game):
    p = panel(game)
    assert p["tab_display_button"].focused
    key_up(game, pygame.K_DOWN)
    assert p["tab_audio_button"].focused
    key_up(game, pygame.K_RETURN)
    assert game.settings_tabs.active == "audio"
    assert p["tab_audio_button"].focused
    assert sum(b.focused for b in game.menu_controllers["settings"].buttons) == 1


def test_reopening_settings_starts_on_display(game):
    click(game, panel(game)["tab_audio_button"])
    game._open_settings("game")
    assert game.settings_tabs.active == "display"
    assert game._settings_return_panel == "game"


def test_reset_to_default_resets_every_tab(game):
    p = panel(game)
    game.audio.set_master_volume(0.2)
    click(game, p["reset"])
    defaults = game._default_audio_settings
    assert game.audio.master_volume() == defaults["master_volume"]
    assert game.audio.sfx_volume() == defaults["sfx_volume"]
    assert game.audio.music_volume() == defaults["music_volume"]
    assert p["master_volume_slider"].value == defaults["master_volume"]


def test_volumes_save_and_load(game):
    game.audio.set_sfx_volume(0.3)
    game._leave_settings()
    again = Game()
    assert again.audio.sfx_volume() == pytest.approx(0.3)
