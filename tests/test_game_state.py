import pytest

from domain.game_state import GameState


def test_initial_state():
    gs = GameState(start_money=200, start_lives=10)
    assert gs.money == 200
    assert gs.lives == 10
    assert gs.level == 1
    assert gs.speed == 1
    assert gs.is_started is False
    assert gs.selected_tower is None
    assert gs.plane_level == 1
    assert gs.has_won is False


def test_increase_money_updates_balance_and_fires_listeners():
    gs = GameState(start_money=100, start_lives=10)
    seen = []
    gs.add_money_listener(seen.append)

    gs.increase_money(50)

    assert gs.money == 150
    assert seen == [150]


def test_decrease_money_updates_balance_and_fires_listeners():
    gs = GameState(start_money=100, start_lives=10)
    seen = []
    gs.add_money_listener(seen.append)

    gs.decrease_money(30)

    assert gs.money == 70
    assert seen == [70]


def test_decrease_money_can_go_negative():
    # No spend-guard at this layer -- callers (tower purchase/upgrade) are
    # responsible for checking affordability before calling this.
    gs = GameState(start_money=10, start_lives=10)
    gs.decrease_money(50)
    assert gs.money == -40


def test_decrease_lives_clamps_at_zero():
    gs = GameState(start_money=200, start_lives=3)
    gs.decrease_lives(10)
    assert gs.lives == 0


def test_decrease_lives_fires_listeners_with_clamped_value():
    gs = GameState(start_money=200, start_lives=3)
    seen = []
    gs.add_lives_listener(seen.append)

    gs.decrease_lives(2)
    gs.decrease_lives(5)  # would go to -4 unclamped

    assert seen == [1, 0]
    assert gs.lives == 0


def test_advance_level_increments_and_fires_listeners():
    gs = GameState(start_money=200, start_lives=10)
    seen = []
    gs.add_level_listener(seen.append)

    gs.advance_level()
    gs.advance_level()

    assert gs.level == 3
    assert seen == [2, 3]


def test_multiple_listeners_on_same_event_all_fire():
    gs = GameState(start_money=200, start_lives=10)
    a, b = [], []
    gs.add_money_listener(a.append)
    gs.add_money_listener(b.append)

    gs.increase_money(5)

    assert a == [205]
    assert b == [205]


# ── game clock ───────────────────────────────────────────────────────────────


def test_tick_does_not_advance_game_time_while_paused():
    gs = GameState(start_money=0, start_lives=1)

    gs.tick()

    assert gs.time_ms == 0.0


def test_tick_advances_game_time_by_one_tick_scaled_by_speed():
    from util.constants import TICK_MS

    gs = GameState(start_money=0, start_lives=1)
    gs.is_started = True

    gs.tick()
    assert gs.time_ms == pytest.approx(TICK_MS)

    gs.speed = 4
    gs.tick()
    assert gs.time_ms == pytest.approx(5 * TICK_MS)
