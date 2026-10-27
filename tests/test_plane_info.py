"""The plane info panel (issue #29): clicking a flying plane opens the tower
info panel on it, with its kills, money earned, splash, flight speed, bomb
rate and the global plane upgrade's previews. In a real Game() with saves
in a temporary directory."""

from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.combat.enemy import Enemy
from gameplay.combat.tower_placement import ENEMY_CLICK_PADDING
from gameplay.towers import TowerFactory
from gameplay.towers.base_tower import BTN_SIZE, SELL_BTN_OFFSET
from gameplay.towers.plane_tower import BOMB_DROP_INTERVAL_MS
from pygamine import SaveStore
from ui.tower_info import (
    ARROW,
    GROUND_LABELS,
    PLANE_LABELS,
    TOWER_INFO_OBJECTS,
    bomb_rate,
    flight_speed,
    stat_texts,
)

MAP_WIDTH = 3008


def make_plane(tower_config, assets, *, level=1, row=8, col=10):
    plane = TowerFactory.create(4, row, col, tower_config, assets, None, MAP_WIDTH)
    plane.level = level
    return plane


# ── the texts ────────────────────────────────────────────────────────────────


def test_bomb_rate_is_bombs_per_second_from_the_drop_interval():
    assert bomb_rate(500) == 2.0


def test_flight_speed_is_tiles_per_second_at_x1():
    # 2 px per tick, 165 ticks per second, 64 px per tile.
    assert flight_speed(2) == pytest.approx(2 * 165 / 64)


def test_a_level_1_plane_previews_the_plane_upgrade(tower_config, assets):
    texts = stat_texts(make_plane(tower_config, assets))

    assert texts["title"] == "Level 1 / 2"
    assert texts["range"] == f"1.5 {ARROW} 2 tiles"  # splash radius 96 -> 128 px
    assert texts["damage"] == f"100 {ARROW} 200"
    assert texts["min_range"] == f"5.2 {ARROW} 2.6 tiles/s"  # flight speed
    assert texts["fire_rate"] == f"{1000 / BOMB_DROP_INTERVAL_MS:.2f}/s"
    assert texts["hp"] == "-"  # planes have no HP


def test_a_max_level_plane_shows_no_previews(tower_config, assets):
    texts = stat_texts(make_plane(tower_config, assets, level=2))

    assert texts["title"] == "Level 2 / 2  (max)"
    assert not any(ARROW in text for text in texts.values())
    assert (texts["range"], texts["damage"]) == ("2 tiles", "200")
    assert texts["min_range"] == "2.6 tiles/s"


def test_a_plane_shows_its_own_record(tower_config, assets):
    plane = make_plane(tower_config, assets)
    plane.kills, plane.money_earned = 7, 210

    texts = stat_texts(plane)

    assert (texts["kills"], texts["earned"]) == ("7", "210 $")


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


@pytest.fixture
def plane(game):
    """A level-1 plane in the middle of the screen (the game is paused, so it
    stays put)."""
    p = TowerFactory.create(
        4, 8, 10, game.tower_config, game.assets, game.audio, game.tilemap.map_width
    )
    game.towers.append(p)
    game.camera.center_on(p.position)
    return p


@pytest.fixture
def ground(game, plane):
    """A missile tower two tiles left of the plane."""
    tower = TowerFactory.create(
        2, 8, 8, game.tower_config, game.assets, game.audio, game.tilemap.map_width
    )
    game.towers.insert(0, tower)
    return tower


def info_objects(game):
    panel = game.panel_manager["game"]
    return [panel[name] for name in TOWER_INFO_OBJECTS]


def frame(game):
    game._update_game(0)


def click(game, pos, button=1):
    game.test_mouse["pos"] = pos
    frame(game)  # the cursor tile follows the mouse
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button))
    frame(game)


def screen_pos(game, obj):
    p = game.camera.world_to_screen(obj.position)
    return (int(p.x), int(p.y))


def value(game, key):
    return game.panel_manager["game"][f"tower_info_{key}_value"].text


def label(game, key):
    return game.panel_manager["game"][f"tower_info_{key}_label"].text


def test_clicking_a_plane_opens_its_panel(game, plane):
    plane.kills, plane.money_earned = 3, 90

    click(game, screen_pos(game, plane))

    assert game.game_state.selected_tower is plane
    assert game.tower_info.tower is plane
    assert value(game, "kills") == "3"
    assert value(game, "earned") == "90 $"
    assert value(game, "damage") == f"100 {ARROW} 200"
    assert value(game, "range") == f"1.5 {ARROW} 2 tiles"
    assert value(game, "fire_rate") == "2.00/s"
    assert value(game, "hp") == "-"
    assert {key: label(game, key) for key in PLANE_LABELS} == PLANE_LABELS
    panel = game.panel_manager["game"]
    assert not panel["tower_info_hp_bar"].active  # no HP, no bar
    others = [o for o in info_objects(game) if o is not panel["tower_info_hp_bar"]]
    assert all(obj.active for obj in others)


def test_a_click_within_the_padding_still_hits_the_plane(game, plane):
    rect = plane.sprite_rect()
    world = (rect.right + ENEMY_CLICK_PADDING - 1, rect.centery)
    s = game.camera.world_to_screen(world)

    click(game, (int(s.x), int(s.y)))

    assert game.tower_info.tower is plane


def test_a_click_beyond_the_padding_misses_the_plane(game, plane):
    rect = plane.sprite_rect()
    world = (rect.right + ENEMY_CLICK_PADDING + 2, rect.centery)
    s = game.camera.world_to_screen(world)

    click(game, (int(s.x), int(s.y)))

    assert not game.tower_info.is_open


def test_a_click_in_the_corner_of_the_planes_sprite_hits_it(game, plane):
    rect = plane.sprite_rect()
    s = game.camera.world_to_screen((rect.left + 2, rect.top + 2))

    click(game, (int(s.x), int(s.y)))

    assert game.tower_info.tower is plane


def test_the_plane_beats_an_enemy_under_the_cursor(game, plane):
    enemy = Enemy(1, 1, level=1, waypoints=game.tilemap.waypoints, assets=game.assets)
    enemy.position = Vector2(plane.position)
    enemy.rect.center = enemy.position
    game.enemies.append(enemy)

    click(game, screen_pos(game, plane))

    assert game.game_state.selected_tower is plane
    assert game.game_state.selected_enemy is None


def test_the_plane_beats_a_ground_tower_under_it(game, plane):
    tower = TowerFactory.create(
        2, plane.row, plane.col, game.tower_config, game.assets, game.audio, MAP_WIDTH
    )
    game.towers.insert(0, tower)

    click(game, screen_pos(game, plane))

    assert game.game_state.selected_tower is plane


def test_selecting_a_plane_clears_the_enemy_selection(game, plane):
    enemy = Enemy(1, 1, level=1, waypoints=game.tilemap.waypoints, assets=game.assets)
    game.enemies.append(enemy)
    game.game_state.selected_enemy = enemy

    click(game, screen_pos(game, plane))

    assert game.game_state.selected_enemy is None
    assert game.tower_info.tower is plane


def test_selecting_an_enemy_closes_the_plane_panel(game, plane):
    click(game, screen_pos(game, plane))
    enemy = Enemy(1, 1, level=1, waypoints=game.tilemap.waypoints, assets=game.assets)
    enemy.position = Vector2(plane.position) + Vector2(250, -150)
    enemy.rect.center = enemy.position
    game.enemies.append(enemy)

    click(game, screen_pos(game, enemy))

    assert game.game_state.selected_enemy is enemy
    assert not game.tower_info.is_open


def test_selecting_a_ground_tower_switches_the_panel_and_its_labels(
    game, plane, ground
):
    click(game, screen_pos(game, plane))

    click(game, screen_pos(game, ground))

    assert game.tower_info.tower is ground
    assert {key: label(game, key) for key in GROUND_LABELS} == GROUND_LABELS
    assert game.panel_manager["game"]["tower_info_hp_bar"].active


def test_selecting_a_plane_switches_from_a_ground_tower(game, plane, ground):
    click(game, screen_pos(game, ground))

    click(game, screen_pos(game, plane))

    assert game.tower_info.tower is plane


def test_in_placement_mode_a_click_on_a_plane_places_instead(game, plane):
    game.game_state.money = 10_000
    game.tower_controller.buying_tower_type = 4
    count = len(game.towers)

    click(game, screen_pos(game, plane))

    assert len(game.towers) == count + 1
    assert game.game_state.selected_tower is None
    assert not game.tower_info.is_open


def test_clicking_elsewhere_closes_the_plane_panel(game, plane):
    click(game, screen_pos(game, plane))
    x, y = screen_pos(game, plane)

    click(game, (x - 300, y + 250))

    assert not game.tower_info.is_open


def test_right_click_closes_the_plane_panel(game, plane):
    click(game, screen_pos(game, plane))

    click(game, screen_pos(game, plane), button=3)

    assert not game.tower_info.is_open


def test_clicking_the_selected_plane_again_closes_its_panel(game, plane):
    click(game, screen_pos(game, plane))

    click(game, screen_pos(game, plane))

    assert not game.tower_info.is_open


def test_a_selected_plane_has_no_sell_button(game, plane):
    game.game_state.money = 10_000
    click(game, screen_pos(game, plane))
    x, y = screen_pos(game, plane)
    sell = (
        x + SELL_BTN_OFFSET.x + BTN_SIZE[0] // 2,
        y + SELL_BTN_OFFSET.y + BTN_SIZE[1] // 2,
    )

    click(game, sell)

    assert plane in game.towers
    assert game.game_state.money == 10_000


def test_the_panel_follows_the_plane_upgrade(game, plane):
    click(game, screen_pos(game, plane))
    game.game_state.plane_level = 2  # UPG PLANES bought

    game._tick()  # the plane picks up the new level on its update
    frame(game)

    assert plane.level == 2
    assert game.tower_info.tower is plane
    assert value(game, "damage") == "200"
    assert game.panel_manager["game"]["tower_info_title_text"].text.endswith("(max)")


def test_the_panel_closes_when_the_plane_leaves_the_map(game, plane):
    click(game, screen_pos(game, plane))
    plane.position.x = MAP_WIDTH + plane.sprite_rect().width  # past the right edge
    plane.rect.center = plane.position

    game._tick()  # off the map: removed at the start of the next tick
    game._tick()
    frame(game)

    assert plane not in game.towers
    assert game.game_state.selected_tower is None
    assert not game.tower_info.is_open
    assert not any(obj.active for obj in info_objects(game))


def test_the_plane_panel_stays_open_while_it_flies(game, plane):
    click(game, screen_pos(game, plane))
    game.game_state.is_started = True
    x = plane.position.x

    for _ in range(10):
        game._tick()
    frame(game)

    assert plane.position.x > x
    assert game.tower_info.tower is plane


def test_the_plane_panel_hides_with_the_hud(game, plane):
    click(game, screen_pos(game, plane))

    game.hud_slide.toggle()
    game.hud_slide.update(1000)

    bg = game.panel_manager["game"]["tower_info_bg"]
    with game.hud_slide.shifted():
        assert bg.rect.right <= 0
    assert not bg.visible


@pytest.mark.parametrize("size", [(1024, 768), (1920, 1080)])
def test_no_plane_label_runs_into_its_value(game, plane, size):
    game.game_state.selected_tower = plane
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)
    frame(game)

    panel = game.panel_manager["game"]
    for key in PLANE_LABELS:
        label_rect = panel[f"tower_info_{key}_label"].rect
        value_rect = panel[f"tower_info_{key}_value"].rect
        assert label_rect.right < value_rect.left, key


def test_drawing_the_plane_panel_does_not_raise(game, plane):
    click(game, screen_pos(game, plane))
    game.draw()


def test_a_planes_record_survives_save_and_load(game, plane):
    plane.kills, plane.money_earned = 4, 120
    game._save_game()
    game.towers.clear()

    game._load_game()

    (loaded,) = [t for t in game.towers if t.is_flying]
    assert (loaded.kills, loaded.money_earned) == (4, 120)
    assert loaded.position == plane.position
    assert game.game_state.selected_tower is None  # a load starts unselected
