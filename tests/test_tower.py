from pygame.math import Vector2

from domain.game_state import GameState
from towers import TowerFactory
from towers.base_tower import BTN_SIZE, SELL_BTN_OFFSET, UPGRADE_BTN_OFFSET

PLANE_TYPE = 4
GROUND_TYPE = 1
MAP_WIDTH = 3008


class IdentityCamera:
    """world_to_screen with zero offset/zoom -- screen coords == world
    coords, so hit-rect math in tests is just plain arithmetic."""

    def world_to_screen(self, world_pos) -> Vector2:
        return Vector2(world_pos)


def make_tower(tower_config, assets, tower_type=GROUND_TYPE, row=0, col=0):
    return TowerFactory.create(
        tower_type, row, col, tower_config, assets, audio=None, map_width=MAP_WIDTH
    )


def test_stats_come_from_tower_config(tower_config, assets):
    tower = make_tower(tower_config, assets)
    assert tower.range == tower_config.ranges[GROUND_TYPE - 1][0]
    assert tower.damage == tower_config.damages[GROUND_TYPE - 1][0]
    assert tower.speed == tower_config.speeds[GROUND_TYPE - 1][0]
    assert tower.max_level == tower_config.max_levels[GROUND_TYPE - 1]
    assert tower.buy_price == tower_config.prices[GROUND_TYPE - 1][0]


def test_plane_has_no_max_hp_and_ground_tower_does(tower_config, assets):
    plane = make_tower(tower_config, assets, tower_type=PLANE_TYPE)
    ground = make_tower(tower_config, assets, tower_type=GROUND_TYPE)

    assert plane.maxHP is None
    assert plane.hp is None
    assert ground.maxHP == tower_config.hps[GROUND_TYPE - 1][0]
    assert ground.hp == ground.maxHP


def test_decrease_hp_on_ground_tower_reduces_hp(tower_config, assets):
    tower = make_tower(tower_config, assets)
    start_hp = tower.hp

    tower.decrease_hp(10)

    assert tower.hp == start_hp - 10


def test_decrease_hp_on_plane_is_a_no_op(tower_config, assets):
    plane = make_tower(tower_config, assets, tower_type=PLANE_TYPE)
    plane.decrease_hp(9999)
    assert plane.hp is None


def test_should_remove_once_hp_drops_to_zero_or_below(tower_config, assets):
    tower = make_tower(tower_config, assets)
    assert not tower.should_remove()

    tower.decrease_hp(tower.maxHP)
    assert tower.should_remove()


def test_plane_never_should_remove_from_hp(tower_config, assets):
    # Planes are invulnerable to Tank fire -- see Tank._nearest_tower, which
    # excludes maxHP=None towers from targeting entirely.
    plane = make_tower(tower_config, assets, tower_type=PLANE_TYPE)
    plane.decrease_hp(9999)
    assert not plane.should_remove()


def test_upgrade_price_is_the_next_levels_price(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2)  # 3 levels
    assert tower.upgrade_price == tower_config.prices[2 - 1][1]


def _click_at(offset: Vector2, tower_position: Vector2) -> tuple:
    """A point safely inside the button rect anchored at tower_position + offset."""
    center = tower_position + offset + Vector2(BTN_SIZE[0] / 2, BTN_SIZE[1] / 2)
    return (center.x, center.y)


def test_upgrade_succeeds_on_a_hit_with_enough_money(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2)
    gs = GameState(start_money=tower.upgrade_price, start_lives=10)
    camera = IdentityCamera()

    tower.upgrade(_click_at(UPGRADE_BTN_OFFSET, tower.position), gs, camera)

    assert tower.level == 2
    assert gs.money == 0
    assert gs.selected_tower is tower
    assert tower.hp == tower.maxHP  # refilled on upgrade


def test_upgrade_does_nothing_when_click_misses_the_button(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2)
    gs = GameState(start_money=tower.upgrade_price, start_lives=10)
    camera = IdentityCamera()

    tower.upgrade((tower.position.x + 10_000, tower.position.y), gs, camera)

    assert tower.level == 1
    assert gs.money == tower.upgrade_price


def test_upgrade_does_nothing_when_money_is_insufficient(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2)
    gs = GameState(start_money=tower.upgrade_price - 1, start_lives=10)
    camera = IdentityCamera()

    tower.upgrade(_click_at(UPGRADE_BTN_OFFSET, tower.position), gs, camera)

    assert tower.level == 1
    assert gs.money == tower.upgrade_price - 1


def test_upgrade_does_nothing_at_max_level(tower_config, assets):
    tower = make_tower(
        tower_config, assets, tower_type=GROUND_TYPE
    )  # 1 level, already maxed
    gs = GameState(start_money=1_000_000, start_lives=10)
    camera = IdentityCamera()

    tower.upgrade(_click_at(UPGRADE_BTN_OFFSET, tower.position), gs, camera)

    assert tower.level == 1
    assert gs.money == 1_000_000


def test_sell_refunds_money_and_removes_tower_when_selected(tower_config, assets):
    tower = make_tower(tower_config, assets)
    towers = [tower]
    gs = GameState(start_money=0, start_lives=10)
    gs.selected_tower = tower
    camera = IdentityCamera()

    tower.sell(_click_at(SELL_BTN_OFFSET, tower.position), gs, towers, camera)

    assert gs.money == tower.sell_price
    assert tower not in towers


def test_sell_does_nothing_when_tower_is_not_selected(tower_config, assets):
    tower = make_tower(tower_config, assets)
    towers = [tower]
    gs = GameState(start_money=0, start_lives=10)
    gs.selected_tower = None
    camera = IdentityCamera()

    tower.sell(_click_at(SELL_BTN_OFFSET, tower.position), gs, towers, camera)

    assert gs.money == 0
    assert tower in towers


# ── sell price ───────────────────────────────────────────────────────────────


def test_sell_price_refunds_seventy_percent_of_everything_spent(tower_config, assets):
    from towers.base_tower import SELL_REFUND

    missile_prices = tower_config.prices[1]
    tower = make_tower(tower_config, assets, tower_type=2)

    assert SELL_REFUND == 0.7
    assert tower.sell_price == int(missile_prices[0] * 0.7)

    tower.level = 3
    assert tower.sell_price == int(sum(missile_prices[:3]) * 0.7)


def test_selected_tower_ui_draws_upgrade_and_sell_buttons(tower_config, assets):
    import pygame
    from pygamine import Camera

    camera = Camera(pygame.Rect(0, 0, 800, 600), 3008, 2176)
    surface = pygame.Surface((800, 600))
    gs = GameState(start_money=0, start_lives=10)

    upgradable = make_tower(tower_config, assets, tower_type=2, row=4, col=4)
    upgradable.draw_selected_ui(surface, gs, camera)
    upgradable.draw_range(surface, camera)

    maxed = make_tower(tower_config, assets, tower_type=1, row=4, col=6)
    maxed.draw_selected_ui(surface, gs, camera)  # shows the MAX badge instead
