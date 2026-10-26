"""The buy button tooltip: its texts from config/towers.yaml, and in a real
Game() (saves in a temporary directory) showing on hover, hiding with the
HUD, staying out of the way of clicks and fitting on screen."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore
from pygamine.app.application import COMMON_RESOLUTIONS
from ui.buy_tooltip import BUY_TOOLTIP_OBJECTS
from util.config_loader import (
    TowerTooltip,
    load_tower_tooltips,
    parse_tower_tooltips,
)

TOWER_TYPES = (1, 2, 3, 4)


# ── config ───────────────────────────────────────────────────────────────────


def test_every_tower_type_has_a_name_strength_and_weakness():
    tooltips = load_tower_tooltips()
    assert sorted(tooltips) == list(TOWER_TYPES)
    for tip in tooltips.values():
        assert tip.name and tip.strength and tip.weakness
        assert "\n" not in tip.strength + tip.weakness  # one line each


def _towers(**tower):
    return {"towers": [{"type": 1, **tower}]}


@pytest.mark.parametrize(
    "tower, missing",
    [
        ({"tooltip": {"strength": "a", "weakness": "b"}}, "name"),
        ({"name": "Gun"}, "tooltip.strength"),
        ({"name": "Gun", "tooltip": {"strength": "a"}}, "tooltip.weakness"),
        ({"name": "Gun", "tooltip": {"strength": " ", "weakness": "b"}}, "strength"),
    ],
)
def test_a_missing_or_blank_text_is_rejected(tower, missing):
    with pytest.raises(ValueError, match=f"type 1 .*{missing}"):
        parse_tower_tooltips(_towers(**tower))


def test_texts_are_trimmed():
    tip = parse_tower_tooltips(
        _towers(name=" Gun ", tooltip={"strength": "a ", "weakness": " b"})
    )
    assert tip == {1: TowerTooltip("Gun", "a", "b")}


# ── in a real Game ───────────────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    mouse = {"pos": (0, 0)}
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: mouse["pos"])
    g = Game()
    g._start_new_game()
    g.test_mouse = mouse
    return g


def panel(game):
    return game.panel_manager["game"]


def tooltip_objects(game):
    return [panel(game)[name] for name in BUY_TOOLTIP_OBJECTS]


def button(game, tower_type):
    return panel(game)[f"buy_tower_{tower_type}"]


def hover(game, pos):
    game.test_mouse["pos"] = pos
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0)))
    game._update_game(0)


def resize(game, size):
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)


def test_the_tooltip_starts_hidden(game):
    game._update_game(0)
    assert not game.buy_tooltip.is_open
    assert not any(obj.active for obj in tooltip_objects(game))


@pytest.mark.parametrize("tower_type", TOWER_TYPES)
def test_hovering_a_buy_button_shows_its_tooltip(game, tower_type):
    hover(game, button(game, tower_type).rect.center)

    tip = load_tower_tooltips()[tower_type]
    p = panel(game)
    assert game.buy_tooltip.tower_type == tower_type
    assert all(obj.active for obj in tooltip_objects(game))
    assert p["buy_tooltip_title_text"].text == tip.name
    assert p["buy_tooltip_strength_text"].text == tip.strength
    assert p["buy_tooltip_weakness_text"].text == tip.weakness


def test_the_tooltip_sits_above_its_button(game):
    btn = button(game, 2).rect
    hover(game, btn.center)

    bg = panel(game)["buy_tooltip_bg"].rect
    assert bg.bottom <= panel(game)["tower_panel_bg"].rect.top
    assert bg.left <= btn.centerx <= bg.right


def test_moving_off_the_button_hides_the_tooltip(game):
    btn = button(game, 1).rect
    hover(game, btn.center)

    hover(game, (btn.centerx, btn.top - 200))

    assert not game.buy_tooltip.is_open
    assert not any(obj.active for obj in tooltip_objects(game))


def test_moving_to_another_button_switches_the_tooltip(game):
    hover(game, button(game, 1).rect.center)
    hover(game, button(game, 3).rect.center)

    assert game.buy_tooltip.tower_type == 3
    name = load_tower_tooltips()[3].name
    assert panel(game)["buy_tooltip_title_text"].text == name


def test_the_tooltip_hides_with_the_hud(game):
    pos = button(game, 1).rect.center
    hover(game, pos)

    game.hud_slide.toggle()
    hover(game, pos)
    assert not game.buy_tooltip.is_open  # hidden at once, while sliding

    game.hud_slide.update(1000)
    hover(game, pos)  # the button's resting place, now empty
    assert not game.buy_tooltip.is_open


def test_the_tooltip_comes_back_once_the_hud_has(game):
    pos = button(game, 1).rect.center
    game.hud_slide.toggle()
    game.hud_slide.update(1000)
    game.hud_slide.toggle()

    hover(game, pos)
    assert not game.buy_tooltip.is_open  # still sliding back in

    game.hud_slide.update(1000)
    hover(game, pos)
    assert game.buy_tooltip.tower_type == 1


def test_the_tooltip_never_blocks_a_click(game):
    hover(game, button(game, 2).rect.center)
    bg = panel(game)["buy_tooltip_bg"].rect

    assert not game.tower_controller._is_over_ui(bg.center)


def test_clicking_a_hovered_button_still_buys(game):
    pos = button(game, 2).rect.center
    hover(game, pos)

    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))

    assert game.tower_controller.buying_tower_type == 2
    assert game.buy_tooltip.tower_type == 2


def test_drawing_the_tooltip_does_not_raise(game):
    hover(game, button(game, 4).rect.center)
    game.draw()


@pytest.mark.parametrize("size", [*COMMON_RESOLUTIONS, (800, 600), (3840, 2160)])
def test_the_tooltip_fits_on_screen_at_every_window_size(game, size):
    resize(game, size)
    screen = pygame.Rect(0, 0, *size)
    bar = panel(game)["tower_panel_bg"].rect
    for tower_type in TOWER_TYPES:
        hover(game, button(game, tower_type).rect.center)

        assert game.buy_tooltip.tower_type == tower_type
        bg = panel(game)["buy_tooltip_bg"].rect
        assert screen.contains(bg), tower_type
        for obj in tooltip_objects(game):
            assert bg.contains(obj.rect), (tower_type, obj)
        assert not bg.colliderect(bar), tower_type


def test_a_resize_while_open_moves_the_tooltip_with_its_button(game):
    hover(game, button(game, 4).rect.center)

    resize(game, (1280, 720))  # no frame yet: the mouse hasn't moved

    btn = button(game, 4).rect
    bg = panel(game)["buy_tooltip_bg"].rect
    assert game.buy_tooltip.tower_type == 4
    assert all(obj.active for obj in tooltip_objects(game))
    assert bg.bottom <= panel(game)["tower_panel_bg"].rect.top
    assert pygame.Rect(0, 0, 1280, 720).contains(bg)
    assert bg.left <= btn.centerx <= bg.right
