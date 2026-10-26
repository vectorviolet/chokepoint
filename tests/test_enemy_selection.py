"""Clicking an enemy selects it and shows its HP as numbers (issue #7)."""

import pygame
from pygame import Rect
from pygame.math import Vector2

from domain.game_state import GameState
from gameplay.battle import BattleSimulation
from gameplay.combat.enemy import Enemy
from gameplay.combat.tower_placement import (
    ENEMY_CLICK_PADDING,
    TowerPlacementController,
)
from gameplay.towers import TowerFactory
from pygamine import Camera
from ui import hp_bar
from ui.enemy_hp_label import EnemyHpLabel, hp_text
from util.constants import TILE_SIZE, HALF_TILE

GAME_AREA = Rect(0, 0, 1536, 1080)
MAP_WIDTH = 3008
MAP_HEIGHT = 2176

# The camera starts at offset (0, 0) and scale 1, so screen == world here.
ENEMY_POS = (600, 500)


class FakeButton:
    def __init__(self, rect):
        self.rect = rect
        self.active = True

    def is_clicked(self, event, mouse_pos) -> bool:
        return False


def left_click():
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=1)


def right_click():
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=3)


def make_camera():
    return Camera(Rect(GAME_AREA), MAP_WIDTH, MAP_HEIGHT, scroll_rect=Rect(GAME_AREA))


def make_enemy(assets, pos, enemy_id=1, enemy_type=1):
    # Two waypoints far to the right: the enemy faces right and walks there.
    waypoints = [Vector2(pos), Vector2(pos) + Vector2(1000, 0)]
    return Enemy(enemy_id, enemy_type, 1, waypoints, assets)


def make_controller(tower_config, assets, enemies, towers=None):
    gs = GameState(start_money=1_000_000, start_lives=10)
    panel = {
        f"buy_tower_{i + 1}": FakeButton(Rect(1600 + i * 80, 20, 40, 40))
        for i in range(4)
    }
    controller = TowerPlacementController(
        towers if towers is not None else [],
        tower_config,
        assets,
        None,
        gs,
        make_camera(),
        {"game": panel},
        [[True] * 47 for _ in range(34)],
        MAP_WIDTH,
        Rect(GAME_AREA),
        enemies=enemies,
    )
    return controller, gs


def click(controller, pos, event=None):
    controller.update_cursor(pos)
    controller.handle_event(event or left_click(), pos)


def make_tower(tower_config, assets, row, col):
    return TowerFactory.create(1, row, col, tower_config, assets, None, MAP_WIDTH)


def tile_center(row, col):
    return (col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE)


# ── selecting ───────────────────────────────────────────────────────────────


def test_a_click_selects_the_enemy_under_the_cursor(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    other = make_enemy(assets, (1200, 800), enemy_id=2)
    controller, gs = make_controller(tower_config, assets, [enemy, other])

    click(controller, ENEMY_POS)

    assert gs.selected_enemy is enemy


def test_a_click_within_the_padding_still_hits(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    controller, gs = make_controller(tower_config, assets, [enemy])

    click(controller, (enemy.rect.right + ENEMY_CLICK_PADDING - 2, ENEMY_POS[1]))

    assert gs.selected_enemy is enemy


def test_a_click_beyond_the_padding_misses(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    controller, gs = make_controller(tower_config, assets, [enemy])

    click(controller, (enemy.rect.right + ENEMY_CLICK_PADDING + 4, ENEMY_POS[1]))

    assert gs.selected_enemy is None


def test_of_overlapping_enemies_the_one_drawn_on_top_is_selected(tower_config, assets):
    below = make_enemy(assets, ENEMY_POS, enemy_id=1)
    on_top = make_enemy(assets, (ENEMY_POS[0] + 10, ENEMY_POS[1]), enemy_id=2)
    # Enemies are drawn in list order, so the later one is on top.
    controller, gs = make_controller(tower_config, assets, [below, on_top])

    click(controller, ENEMY_POS)

    assert gs.selected_enemy is on_top


def test_clicking_the_selected_enemy_again_keeps_it_selected(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    controller, gs = make_controller(tower_config, assets, [enemy])

    click(controller, ENEMY_POS)
    click(controller, ENEMY_POS)

    assert gs.selected_enemy is enemy


def test_the_hit_area_follows_the_enemy_as_it_moves(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    controller, gs = make_controller(tower_config, assets, [enemy])
    for _ in range(100):
        enemy.move(1)
    assert enemy.position.x > ENEMY_POS[0] + 50

    click(controller, (int(enemy.position.x), int(enemy.position.y)))

    assert gs.selected_enemy is enemy


# ── deselecting ─────────────────────────────────────────────────────────────


def test_a_click_elsewhere_clears_the_selection(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    controller, gs = make_controller(tower_config, assets, [enemy])
    click(controller, ENEMY_POS)

    click(controller, (100, 900))

    assert gs.selected_enemy is None


def test_a_right_click_clears_the_selection(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    controller, gs = make_controller(tower_config, assets, [enemy])
    click(controller, ENEMY_POS)

    click(controller, (100, 900), right_click())

    assert gs.selected_enemy is None


# ── towers and placement ────────────────────────────────────────────────────


def test_clicking_a_tower_clears_the_enemy_selection(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    tower = make_tower(tower_config, assets, row=12, col=2)
    controller, gs = make_controller(tower_config, assets, [enemy], [tower])
    click(controller, ENEMY_POS)

    click(controller, tile_center(12, 2))

    assert gs.selected_tower is tower
    assert gs.selected_enemy is None


def test_selecting_an_enemy_deselects_the_tower(tower_config, assets):
    enemy = make_enemy(assets, ENEMY_POS)
    tower = make_tower(tower_config, assets, row=12, col=2)
    controller, gs = make_controller(tower_config, assets, [enemy], [tower])
    click(controller, tile_center(12, 2))
    assert gs.selected_tower is tower

    click(controller, ENEMY_POS)

    assert gs.selected_enemy is enemy
    assert gs.selected_tower is None


def test_in_placement_mode_a_click_on_an_enemy_places_instead_of_selecting(
    tower_config, assets
):
    enemy = make_enemy(assets, ENEMY_POS)
    towers = []
    controller, gs = make_controller(tower_config, assets, [enemy], towers)
    controller.buying_tower_type = 1

    click(controller, ENEMY_POS)

    assert gs.selected_enemy is None
    assert len(towers) == 1
    assert controller.buying_tower_type == 0


# ── the numbers ─────────────────────────────────────────────────────────────


class FakeCtx:
    def __init__(self, enemies):
        self.enemies = enemies
        self.killed = []

    def enemy_killed(self, enemy):
        self.killed.append(enemy)


def test_the_numbers_show_current_and_max_hp(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    enemy.maxHP = 420
    enemy.hp = 320

    assert hp_text(enemy) == "320 / 420"


def test_the_numbers_follow_damage(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    full = hp_text(enemy)

    enemy.decrease_hp(7, FakeCtx([enemy]))

    assert full == f"{enemy.maxHP} / {enemy.maxHP}"
    assert hp_text(enemy) == f"{enemy.maxHP - 7} / {enemy.maxHP}"


def test_the_numbers_never_go_below_zero(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    enemy.hp = -15

    assert hp_text(enemy) == f"0 / {enemy.maxHP}"


def test_the_label_is_drawn_right_of_the_bar_and_rerendered_on_change(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    camera = make_camera()
    label = EnemyHpLabel(assets.font_path("anton"))
    surface = pygame.Surface(GAME_AREA.size)
    surface.fill((1, 2, 3))

    label.draw(surface, camera, enemy)

    bar = hp_bar.bar_rect(camera, enemy.position)
    changed = [
        (x, y)
        for x in range(bar.right, bar.right + 80)
        for y in range(bar.centery - 10, bar.centery + 10)
        if surface.get_at((x, y))[:3] != (1, 2, 3)
    ]
    assert changed
    assert all(x >= bar.right for x, _ in changed)
    first = label._label
    label.draw(surface, camera, enemy)
    assert label._label is first  # unchanged text isn't re-rendered
    enemy.hp -= 1
    label.draw(surface, camera, enemy)
    assert label._label is not first


def test_nothing_is_drawn_without_a_selection(assets):
    label = EnemyHpLabel(assets.font_path("anton"))
    surface = pygame.Surface((50, 50))
    surface.fill((1, 2, 3))

    label.draw(surface, make_camera(), None)

    assert surface.get_at((25, 25))[:3] == (1, 2, 3)


# ── death and escape (the battle tick) ──────────────────────────────────────


class FakeTilemap:
    map_width = MAP_WIDTH
    map_height = MAP_HEIGHT


class Battle(BattleSimulation):
    def __init__(self, enemies):
        self.towers = []
        self.enemies = enemies
        self.wave_manager = None
        self.tilemap = FakeTilemap()
        self.game_state = GameState(start_money=0, start_lives=10)
        self.game_state.is_started = True


def test_the_selection_clears_when_the_enemy_dies(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    battle = Battle([enemy])
    battle.game_state.selected_enemy = enemy

    enemy.decrease_hp(enemy.maxHP, battle)
    battle._tick()

    assert battle.game_state.selected_enemy is None


def test_the_selection_clears_when_the_enemy_escapes(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    enemy.waypoint_index = len(enemy.waypoints)  # at the end of the path
    battle = Battle([enemy])
    battle.game_state.selected_enemy = enemy

    battle._tick()

    assert enemy not in battle.enemies
    assert battle.game_state.selected_enemy is None


def test_the_selection_survives_a_tick_while_the_enemy_lives(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    battle = Battle([enemy])
    battle.game_state.selected_enemy = enemy

    battle._tick()

    assert battle.game_state.selected_enemy is enemy


def test_the_selected_enemy_bar_shows_even_at_full_health(assets):
    enemy = make_enemy(assets, ENEMY_POS)
    battle = Battle([enemy])
    camera = make_camera()
    bar = hp_bar.bar_rect(camera, enemy.position)

    def bar_pixel():
        surface = pygame.Surface(GAME_AREA.size)
        surface.fill((1, 2, 3))
        battle.tilemap.draw = lambda surface, camera: None
        battle._draw_battle(surface, camera)
        return surface.get_at((bar.centerx, bar.centery))[:3]

    assert bar_pixel() != hp_bar.health_color(1.0)
    battle.game_state.selected_enemy = enemy
    assert bar_pixel() == hp_bar.health_color(1.0)
