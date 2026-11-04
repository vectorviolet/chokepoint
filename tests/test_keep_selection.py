"""Keep selection while buying (#132) in a real Game() (saves in a temporary
directory): with the GAME tab setting off, picking a tower to buy (button
click or 1-4) deselects the selected tower and closes its info panel; with it
on, the selection and its range ring stay."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from gameplay.towers import TowerFactory
from pygamine import SaveStore

KEY = "keep_selection_while_buying"


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))

    def make() -> Game:
        g = Game()
        g._start_new_game()
        return g

    return make


@pytest.fixture
def game(make_game):
    return make_game()


def select_a_tower(game):
    tower = TowerFactory.create(
        1, 5, 5, game.tower_config, game.assets, game.audio, game.tilemap.map_width
    )
    game.towers.append(tower)
    game.game_state.selected_tower = tower
    game.tower_info.show(tower)
    return tower


def click_buy_button(game, tower_type):
    button = game.panel_manager["game"][f"buy_tower_{tower_type}"]
    game.mouse.position = button.rect.center
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=button.rect.center))


def press(game, k):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k))


def test_it_is_off_by_default(game):
    assert game.toggles[KEY] is False
    assert game.tower_controller.keep_selection_while_buying is False


@pytest.mark.parametrize("how", ["click", "key"])
def test_off_picking_a_tower_deselects_and_closes_the_info_panel(game, how):
    select_a_tower(game)

    if how == "click":
        click_buy_button(game, 2)
    else:
        press(game, pygame.K_2)

    assert game.tower_controller.buying_tower_type == 2
    assert game.game_state.selected_tower is None
    assert game._selected_tower() is None  # no range ring is drawn
    game.update()
    assert not game.tower_info.is_open


@pytest.mark.parametrize("how", ["click", "key"])
def test_on_picking_a_tower_keeps_the_selection_and_its_range_ring(game, how):
    tower = select_a_tower(game)
    game.set_toggle(KEY, True)

    if how == "click":
        click_buy_button(game, 2)
    else:
        press(game, pygame.K_2)

    assert game.tower_controller.buying_tower_type == 2
    assert game.game_state.selected_tower is tower
    assert game._selected_tower() is tower  # the range ring is drawn for it
    game.update()
    assert game.tower_info.tower is tower


def test_off_a_refused_pick_keeps_the_selection(game):
    tower = select_a_tower(game)
    game.game_state.decrease_money(game.game_state.money)  # can't afford anything

    press(game, pygame.K_1)

    assert game.tower_controller.buying_tower_type == 0
    assert game.game_state.selected_tower is tower


def test_the_setting_is_saved_and_loaded(make_game):
    first = make_game()
    first.set_toggle(KEY, True)
    first._save_settings()

    second = make_game()

    assert second.toggles[KEY] is True
    assert second.tower_controller.keep_selection_while_buying is True


def test_reset_to_default_turns_it_off(game):
    game.set_toggle(KEY, True)

    game._reset_settings()

    assert game.toggles[KEY] is False
    assert game.tower_controller.keep_selection_while_buying is False
    assert game.settings_store.load()[KEY] is False


def test_the_game_tab_row_flips_it(game):
    game._open_settings("main_menu")
    game._show_settings_tab("game")
    settings = game.panel_manager["settings"]
    assert settings[f"{KEY}_value_text"].text == "OFF"

    button = settings[f"{KEY}_next_button"]
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.mouse.position = button.rect.center
        game.handle_event(pygame.event.Event(kind, button=1, pos=button.rect.center))

    assert settings[f"{KEY}_value_text"].text == "ON"
    assert game.tower_controller.keep_selection_while_buying is True
