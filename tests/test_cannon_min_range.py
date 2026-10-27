"""The heavy cannon's blind spot (issue #11): its minimum range in
config/towers.yaml, the cannon ignoring enemies inside it (and dropping a
target that walks in), the range ring's inner ring, and the info panel's
"Min range" row. The grid side is in tests/test_targeting.py."""

from functools import partial

import pygame
import pytest
from pygame.math import Vector2
from pygamine import Camera, SaveStore

import app.game
from app.game import Game

from gameplay.towers import TowerFactory
from ui.range_ring import draw_range_ring
from ui.tower_info import ARROW, stat_texts
from util.config_loader import load_tower_config, load_tower_tooltips, parse_min_ranges

MAP_WIDTH = 3008
CANNON = 3
MIN_RANGE = 96  # 1.5 tiles


class FakeEnemy:
    def __init__(self, position):
        self.position = Vector2(position)


class FakeAudio:
    def play_sfx(self, path) -> None:
        pass


def make_tower(tower_config, assets, tower_type=CANNON, level=1, row=5, col=5):
    tower = TowerFactory.create(
        tower_type, row, col, tower_config, assets, FakeAudio(), MAP_WIDTH
    )
    tower.level = level
    tower.now = tower.speed + 1  # reloaded
    return tower


# ── config ───────────────────────────────────────────────────────────────────


def test_only_the_heavy_cannon_has_a_blind_spot():
    cfg = load_tower_config()
    assert cfg.min_ranges[CANNON - 1] == [MIN_RANGE, MIN_RANGE]
    for i, min_ranges in enumerate(cfg.min_ranges):
        if i != CANNON - 1:
            assert min_ranges == [0] * cfg.max_levels[i]


def test_every_blind_spot_is_smaller_than_its_range():
    cfg = load_tower_config()
    for min_ranges, ranges in zip(cfg.min_ranges, cfg.ranges):
        assert all(0 <= m < r for m, r in zip(min_ranges, ranges))


def test_a_tower_without_min_ranges_has_none():
    assert parse_min_ranges({"type": 1, "ranges": [160, 192]}) == [0, 0]


@pytest.mark.parametrize(
    "min_ranges",
    [[96], [96, 96, 96], [256, 96], [300, 96], [-1, 96], [1.5, 96], [True, 96], "96"],
)
def test_a_bad_min_ranges_is_rejected(min_ranges):
    tower = {"type": 3, "ranges": [256, 288], "min_ranges": min_ranges}
    with pytest.raises(ValueError, match="tower type 3"):
        parse_min_ranges(tower)


def test_the_tower_exposes_its_min_range_per_level(tower_config, assets):
    assert make_tower(tower_config, assets).min_range == MIN_RANGE
    assert make_tower(tower_config, assets, level=2).min_range == MIN_RANGE
    assert make_tower(tower_config, assets, tower_type=1).min_range == 0


# ── targeting ────────────────────────────────────────────────────────────────


def test_the_cannon_ignores_an_enemy_just_inside_its_min_range(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(MIN_RANGE - 1, 0))

    tower.work([enemy], is_started=True)

    assert tower.is_rotated is False
    assert tower.bullets == []


def test_the_cannon_ignores_an_enemy_right_on_its_min_range(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(0, MIN_RANGE))

    tower.work([enemy], is_started=True)

    assert tower.bullets == []


def test_the_cannon_shoots_an_enemy_just_outside_its_min_range(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(MIN_RANGE + 1, 0))

    tower.work([enemy], is_started=True)

    assert tower.bullets and tower.bullets[0].target is enemy


def test_other_towers_still_shoot_up_close(tower_config, assets):
    for tower_type in (1, 2):
        tower = make_tower(tower_config, assets, tower_type=tower_type)
        enemy = FakeEnemy(tower.position + Vector2(10, 0))

        tower.work([enemy], is_started=True)

        assert tower.bullets and tower.bullets[0].target is enemy


def test_the_cannon_skips_a_nearer_enemy_in_its_blind_spot(tower_config, assets):
    tower = make_tower(tower_config, assets)
    close = FakeEnemy(tower.position + Vector2(40, 0))
    far = FakeEnemy(tower.position + Vector2(0, 200))

    tower.work([close, far], is_started=True)

    assert tower.bullets and tower.bullets[0].target is far


def test_the_cannon_retargets_when_its_target_walks_into_the_blind_spot(
    tower_config, assets
):
    tower = make_tower(tower_config, assets)
    walker = FakeEnemy(tower.position + Vector2(150, 0))
    other = FakeEnemy(tower.position + Vector2(0, -220))

    tower.work([walker, other], is_started=True)
    assert tower.bullets[-1].target is walker

    walker.position = tower.position + Vector2(MIN_RANGE - 10, 0)
    tower.bullets.clear()
    tower.now += tower.speed + 1  # reloaded again
    tower.work([walker, other], is_started=True)

    assert tower.bullets and tower.bullets[-1].target is other


# ── range ring ───────────────────────────────────────────────────────────────


def _alpha(surface, point):
    return surface.get_at((int(point[0]), int(point[1]))).a


def test_the_ring_cuts_out_the_blind_spot():
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)
    draw_range_ring(surface, (200, 200), 150, (0, 200, 0, 120), 2, 60)

    assert _alpha(surface, (200, 200)) == 0  # inside the blind spot: clear
    assert _alpha(surface, (200 + 30, 200)) == 0
    assert _alpha(surface, (200 + 59, 200)) > 0  # its inner ring
    assert _alpha(surface, (200 + 100, 200)) > 0  # covered: shaded
    assert _alpha(surface, (200 + 170, 200)) == 0  # past the range


def test_a_ring_without_a_blind_spot_is_shaded_to_the_centre():
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)
    draw_range_ring(surface, (200, 200), 150, (0, 200, 0, 120), 2)

    assert _alpha(surface, (200, 200)) > 0


def _drawn_range(tower, camera):
    surface = pygame.Surface((800, 600), pygame.SRCALPHA)
    tower.draw_range(surface, camera)
    return surface


def test_the_selected_cannon_shows_its_blind_spot(tower_config, assets):
    camera = Camera(pygame.Rect(0, 0, 800, 600), 3008, 2176)
    cannon = make_tower(tower_config, assets)
    gun = make_tower(tower_config, assets, tower_type=1)
    centre = camera.world_to_screen(cannon.position)
    near = centre + Vector2(MIN_RANGE * camera.scale / 2, 0)
    covered = centre + Vector2(MIN_RANGE * camera.scale + 20, 0)

    assert _alpha(_drawn_range(cannon, camera), near) == 0
    assert _alpha(_drawn_range(cannon, camera), covered) > 0
    assert _alpha(_drawn_range(gun, camera), near) > 0


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    g = Game()
    g._start_new_game()
    return g


def test_the_placement_preview_shows_the_blind_spot(game):
    game.camera.center_on(Vector2(5 * 64 + 32, 5 * 64 + 32))
    ctrl = game.tower_controller
    game.game_state.money = 10_000
    ctrl.buying_tower_type = CANNON
    ctrl.cursor_row, ctrl.cursor_col = 5, 5
    surface = pygame.Surface(game.window.get_size(), pygame.SRCALPHA)
    centre = game.camera.world_to_screen((5 * 64 + 32, 5 * 64 + 32))

    ctrl._draw_cursor_preview(surface, (int(centre.x), int(centre.y)))

    ring = int(MIN_RANGE * game.camera.scale)
    assert _alpha(surface, centre + Vector2(0, ring + 20)) > 0  # shaded
    assert _alpha(surface, centre + Vector2(0, ring - 8)) == 0  # blind spot


# ── tower info panel and tooltip ─────────────────────────────────────────────


def test_the_info_panel_shows_the_cannons_min_range(tower_config, assets):
    for level in (1, 2):
        texts = stat_texts(make_tower(tower_config, assets, level=level))
        assert texts["min_range"] == "1.5 tiles"  # unchanged by the upgrade
        assert ARROW not in texts["min_range"]


def test_the_info_panel_shows_no_min_range_for_other_towers(tower_config, assets):
    for tower_type in (1, 2):  # (a plane shows its flight speed in that row)
        texts = stat_texts(make_tower(tower_config, assets, tower_type))
        assert texts["min_range"] == "-"


def test_the_cannon_tooltip_mentions_the_blind_spot():
    assert "up close" in load_tower_tooltips()[CANNON].weakness


@pytest.mark.parametrize("size", [(1024, 768), (1920, 1080)])
def test_no_info_panel_label_runs_into_its_value(game, size):
    """The blind spot row's label is the longest; every label must end
    before its value starts, small window included."""
    from ui.tower_info import ROWS

    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)
    panel = game.panel_manager["game"]
    for key in ROWS:
        label = panel[f"tower_info_{key}_label"].rect
        value = panel[f"tower_info_{key}_value"].rect
        assert label.right < value.left, key
