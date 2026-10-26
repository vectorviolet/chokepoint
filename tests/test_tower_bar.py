"""TowerBar -- Tab slides the bottom tower bar off-screen and back.

Built on a real Game(), since the slide moves the real panel objects that
panels.yaml lays out for the window size. Saves go to a temporary directory.
"""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore
from ui.tower_bar import BUY_BUTTONS, OBJECT_NAMES, SLIDE_MS

MOUSE = {"pos": (400, 300)}


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    MOUSE["pos"] = (400, 300)  # mid-window, so the camera doesn't edge-scroll
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: MOUSE["pos"])

    def build(window_size=None):
        if window_size is not None:
            SaveStore("settings", directory=tmp_path).save(
                {"window_mode": "windowed", "window_size": list(window_size)}
            )
        game = Game()
        game._start_new_game()
        return game

    return build


def play(game, fake_ticks, ms, fps=60):
    for _ in range(round(ms / (1000 / fps))):
        fake_ticks["t"] += 1000 / fps
        game.update()


def press(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    game.handle_event(pygame.event.Event(pygame.KEYUP, key=key))


def click(game, pos):
    MOUSE["pos"] = pos
    game.mouse.update()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def rects(game):
    panel = game.panel_manager["game"]
    return {name: pygame.Rect(panel[name].rect) for name in OBJECT_NAMES}


def assert_off_screen(game):
    height = game.game_area.height  # the canvas
    for name, rect in rects(game).items():
        assert rect.top >= height, name
    # the 1-4 badges drawn over the buttons' top-left corners go too
    for name in BUY_BUTTONS:
        assert game.panel_manager["game"][name].rect.top - 8 >= height, name


def test_tab_slides_the_bar_off_screen_and_back(make_game, fake_ticks):
    game = make_game()
    resting = rects(game)

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)
    assert not game.tower_bar.shown
    assert_off_screen(game)

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)
    assert game.tower_bar.shown
    assert rects(game) == resting


def test_the_slide_eases_out_over_about_200_ms(make_game, fake_ticks):
    game = make_game()
    top = game.panel_manager["game"]["tower_panel_bg"].rect.top
    distance = game.game_area.height - top

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS / 2)
    halfway = game.panel_manager["game"]["tower_panel_bg"].rect.top - top
    assert game.tower_bar.is_sliding
    assert halfway > distance / 2  # ease-out: most of the way in half the time

    play(game, fake_ticks, SLIDE_MS / 2 + 50)
    assert not game.tower_bar.is_sliding


def test_hidden_buy_buttons_ignore_clicks_and_hover(make_game, fake_ticks):
    game = make_game()
    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)

    button = game.panel_manager["game"]["buy_tower_1"]
    click(game, button.rect.center)

    assert game.tower_controller.buying_tower_type == 0
    assert not button.is_mouse_over(button.rect.center)


def test_buy_buttons_take_clicks_again_once_shown(make_game, fake_ticks):
    game = make_game()
    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)
    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)

    click(game, game.panel_manager["game"]["buy_tower_2"].rect.center)

    assert game.tower_controller.buying_tower_type == 2


def test_hotkeys_still_pick_towers_while_hidden(make_game, fake_ticks):
    game = make_game()
    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)

    press(game, pygame.K_3)

    assert game.tower_controller.buying_tower_type == 3


def test_hiding_keeps_a_placement_in_progress(make_game, fake_ticks):
    game = make_game()
    press(game, pygame.K_1)

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)

    assert game.tower_controller.buying_tower_type == 1


def test_price_labels_stay_hidden_when_their_colour_changes(make_game, fake_ticks):
    """A price label re-lays itself out when the money crosses its price."""
    game = make_game()
    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)

    game.game_state.decrease_money(game.game_state.money)  # every label turns red
    game.game_state.increase_money(5000)  # and back to green

    assert_off_screen(game)


@pytest.mark.parametrize("window_size", [(1280, 720), (800, 600)])
def test_it_slides_relative_to_the_scaled_layout(make_game, fake_ticks, window_size):
    game = make_game(window_size)
    assert game.window.get_size() == window_size
    resting = rects(game)
    assert resting["tower_panel_bg"].bottom <= window_size[1]

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)
    assert_off_screen(game)

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)
    assert rects(game) == resting


def test_a_resize_while_hidden_keeps_it_hidden(make_game, fake_ticks):
    game = make_game()
    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)

    game.on_canvas_resized((800, 600))  # rebuilds the panels at their resting places
    assert game.game_area.size == (800, 600)

    assert_off_screen(game)
    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)
    assert rects(game)["tower_panel_bg"].bottom <= 600


def test_it_slides_while_paused(make_game, fake_ticks):
    game = make_game()
    game.game_state.is_started = False

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS + 50)

    assert_off_screen(game)
    assert game.game_state.time_ms == 0  # the game itself stayed paused


def test_game_speed_does_not_change_the_slide(make_game, fake_ticks):
    positions = []
    for speed in (1, 4):
        game = make_game()
        game.game_state.is_started = True
        game.game_state.speed = speed
        press(game, pygame.K_TAB)
        play(game, fake_ticks, SLIDE_MS / 2)
        positions.append(game.panel_manager["game"]["tower_panel_bg"].rect.top)

    assert positions[0] == positions[1]
