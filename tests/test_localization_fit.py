"""Every text fits its place in both languages (#120): Turkish runs longer
than English and Fira Sans is wider than the font it replaced, so buttons,
rows, the HUD, the tower panel and the tooltips are measured in each language
at the authored size and at a small window."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from gameplay.towers import TowerFactory
from pygamine import SaveStore
from pygamine.ui_widgets.text_object import TextObject
from pygamine.util.localization import localization
from ui.tower_info import ROWS
from util.text import money

PANELS = ("main_menu", "play_menu", "thanks", "credits", "settings", "game")
SIZES = [(1920, 1080), (1280, 720)]


class _Audio:
    def play_sfx(self, *args, **kwargs):
        pass


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    g = Game()
    g._start_new_game()
    return g


def resize(game, size):
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)


def texts(game, panel_name):
    return [
        o for o in game.panel_manager[panel_name].values() if isinstance(o, TextObject)
    ]


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("language", ["en", "tr"])
def test_every_text_stays_inside_its_parent_or_the_window(game, language, size):
    resize(game, size)
    game.set_language(language)
    window = pygame.Rect((0, 0), size)
    for panel_name in PANELS:
        for obj in texts(game, panel_name):
            parent = obj.rect.parent
            limit = window if parent is None else parent  # a Transform: left, right
            assert limit.left <= obj.rect.left and obj.rect.right <= limit.right, (
                panel_name,
                obj.text,
            )


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("language", ["en", "tr"])
def test_the_tower_panel_rows_fit_for_every_tower_and_level(
    game, assets, tower_config, language, size
):
    resize(game, size)
    game.set_language(language)
    panel = game.panel_manager["game"]
    for tower_type in (1, 2, 3, 4):
        for level in range(1, tower_config.max_levels[tower_type - 1] + 1):
            tower = TowerFactory.create(
                tower_type, 5, 5, tower_config, assets, _Audio(), 3008
            )
            tower.level = level
            tower.kills = 1234
            tower.money_earned = 123456
            game.game_state.plane_level = level if tower_type == 4 else 1
            game.tower_info.show(tower)
            bg = panel["tower_info_bg"].rect
            title = panel["tower_info_title_text"].rect
            assert title.right <= bg.right, (tower_type, level)
            for key in ROWS:
                label = panel[f"tower_info_{key}_label"]
                value = panel[f"tower_info_{key}_value"]
                where = (tower_type, level, key, label.text, value.text)
                assert label.rect.right < value.rect.left, where
                assert value.rect.right <= bg.right, where
    game.tower_info.show(None)


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("language", ["en", "tr"])
def test_the_buy_tooltip_fits_the_window_for_every_tower(game, language, size):
    resize(game, size)
    game.set_language(language)
    window = pygame.Rect((0, 0), size)
    panel = game.panel_manager["game"]
    for tower_type in (1, 2, 3, 4):
        game.buy_tooltip.show(None)
        game.buy_tooltip.show(tower_type)
        bg = panel["buy_tooltip_bg"].rect
        assert window.contains(bg), tower_type
        for name in ("title_text", "strength_text", "weakness_text"):
            assert bg.contains(panel[f"buy_tooltip_{name}"].rect), (tower_type, name)
        for name in ("strength", "weakness"):
            label = panel[f"buy_tooltip_{name}_label"].rect
            text = panel[f"buy_tooltip_{name}_text"].rect
            assert label.right < text.left, (tower_type, name)


@pytest.mark.parametrize("language", ["en", "tr"])
def test_the_counters_grow_with_their_text(game, language):
    game.set_language(language)
    game.game_state.level = 100
    game.game_state.money = 1_000_000
    game.hud.refresh()
    panel = game.panel_manager["game"]
    assert money(1) and localization.language == language
    assert panel["level_text"].rect.right < panel["control_panel_bg"].rect.left
    assert panel["coin_text"].rect.right < panel["control_panel_bg"].rect.left
