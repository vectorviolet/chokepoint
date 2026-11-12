"""The money number lags the real balance until each kill coin lands (#189). The balance
itself is paid on the kill, as before. The game tests run for both styles, count_up and
odometer. Unit tests drive KillFeedback and GameHUD directly; the rest play a real Game(),
with saves in a temporary directory."""

import random
from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from gameplay.combat.enemy import Enemy
from pygamine import SaveStore
from ui.game_hud import GameHUD
from ui.kill_feedback import (
    COIN_FLIGHT_MS,
    COIN_STAGGER_MS,
    COINS_PER_KILL,
    MAX_EFFECTS,
    KillFeedback,
)
from util.config_loader import hud_settings, load_settings

LAST_COIN_LANDS = COIN_FLIGHT_MS + (COINS_PER_KILL[1] - 1) * COIN_STAGGER_MS
FRAME_MS = 1000 / 60


# ── KillFeedback: the shares in flight ────────────────────────────────────────


@pytest.fixture
def feedback(assets):
    return KillFeedback(
        assets.get_image("coin_sheet"),
        assets.font_path("fira_sans_bold"),
        random.Random(1),
    )


def test_a_kills_coins_carry_its_whole_reward_between_them(feedback):
    feedback.add_kill((0, 0), 37, (0, 0), now_ms=0)

    assert feedback.pending_money == 37
    assert sum(coin.value for coin in feedback.coins) == 37


def test_a_reward_smaller_than_its_coins_still_adds_up(feedback):
    feedback.add_kill((0, 0), 1, (0, 0), now_ms=0)

    assert feedback.pending_money == 1


def test_the_shares_are_as_even_as_whole_coins_allow(feedback):
    feedback.add_kill((0, 0), 4, (0, 0), now_ms=0)

    shares = [coin.value for coin in feedback.coins]
    assert sum(shares) == 4
    assert max(shares) - min(shares) <= 1


def test_each_landing_coin_releases_its_share(feedback):
    feedback.add_kill((0, 0), 40, (0, 0), now_ms=0)
    count = len(feedback.coins)
    first = min(feedback.coins, key=lambda coin: coin.delay_ms)

    feedback.update(COIN_FLIGHT_MS, now_ms=0)  # only the first coin has landed

    assert len(feedback.coins) == count - 1
    assert feedback.pending_money == 40 - first.value
    feedback.update(LAST_COIN_LANDS, now_ms=0)
    assert feedback.pending_money == 0


def test_a_kill_with_no_room_for_coins_holds_nothing_back(feedback):
    while feedback.live_effects < MAX_EFFECTS:
        feedback.add_kill((0, 0), 10, (0, 0), now_ms=0)
    held = feedback.pending_money

    feedback.add_kill((0, 0), 10, (0, 0), now_ms=0)  # no room: no coins, no text

    assert feedback.pending_money == held


def test_settle_keeps_the_pictures_but_releases_the_shares(feedback):
    feedback.add_kill((0, 0), 40, (0, 0), now_ms=0)
    count = len(feedback.coins)

    feedback.settle()

    assert feedback.pending_money == 0
    assert len(feedback.coins) == count


def test_clear_releases_everything(feedback):
    feedback.add_kill((0, 0), 40, (0, 0), now_ms=0)

    feedback.clear()

    assert feedback.pending_money == 0


def test_with_reduce_flashing_the_coins_hold_nothing_back_and_the_counter_never_pops(
    feedback,
):
    feedback.reduce_flashing = True

    feedback.add_kill((0, 0), 40, (0, 0), now_ms=0)
    assert feedback.pending_money == 0
    feedback.update(LAST_COIN_LANDS, now_ms=0)
    assert feedback.is_popping  # a coin landed, as in the normal case...

    surface = pygame.Surface((100, 100))
    surface.fill((10, 20, 30))
    surface.fill((200, 100, 50), pygame.Rect(40, 40, 10, 10))
    feedback.draw_pop(surface, pygame.Rect(35, 35, 20, 20))

    # ...but the counter isn't scaled: the pixels around it stay as they were.
    assert surface.get_at((34, 45))[:3] == (10, 20, 30)
    assert surface.get_at((55, 45))[:3] == (10, 20, 30)


# ── settings ──────────────────────────────────────────────────────────────────


def test_the_shipped_style_is_count_up():
    assert hud_settings()["money_style"] == "count_up"


def test_an_unknown_style_is_refused(tower_config):
    with pytest.raises(ValueError, match="money_style"):
        GameHUD(None, tower_config, None, money_style="spinning")  # type: ignore[arg-type]


# ── in the game ───────────────────────────────────────────────────────────────


@pytest.fixture(params=["count_up", "odometer"])
def style(request):
    return request.param


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks, style):
    def settings():
        loaded = load_settings()
        loaded["hud"]["money_style"] = style
        return loaded

    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(app.game, "load_settings", settings)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    g.game_state.is_started = True
    return g


def kill(game, assets):
    enemy = Enemy(1, 1, level=1, waypoints=game.tilemap.waypoints, assets=assets)
    game.enemies.append(enemy)
    enemy.decrease_hp(enemy.max_hp, game)
    return enemy


def play(game, fake_ticks, ms):
    for _ in range(round(ms / FRAME_MS)):
        fake_ticks["t"] += FRAME_MS
        game.update()


def shown(game) -> int:
    """What the HUD number reads, whichever style draws it."""
    return int(game.hud.coin_text.text)


def test_the_balance_is_paid_on_the_kill_but_the_number_waits(game, assets):
    before = game.game_state.money

    enemy = kill(game, assets)

    assert game.game_state.money == before + enemy.kill_money
    assert game.hud.shown_money == before
    assert shown(game) == before


def test_the_number_climbs_with_each_coin_and_ends_on_the_balance(
    game, assets, fake_ticks
):
    kill(game, assets)
    seen = [shown(game)]

    for _ in range(round(LAST_COIN_LANDS / FRAME_MS) + 2):
        play(game, fake_ticks, FRAME_MS)
        seen.append(shown(game))

    assert seen == sorted(seen)  # only ever up
    assert len(set(seen)) > 2  # in steps, one per coin
    assert seen[-1] == game.game_state.money
    assert game.kill_feedback.pending_money == 0


def test_a_burst_of_kills_never_desyncs(game, assets, fake_ticks):
    start = game.game_state.money
    for _ in range(8):  # far more than the effect cap can show
        for _ in range(6):
            kill(game, assets)
        play(game, fake_ticks, 50)
        assert start <= shown(game) <= game.game_state.money
        assert game.kill_feedback.live_effects <= MAX_EFFECTS

    play(game, fake_ticks, 2 * LAST_COIN_LANDS)

    assert shown(game) == game.game_state.money


def test_spending_lowers_the_number_at_once_and_it_still_converges(
    game, assets, fake_ticks
):
    kill(game, assets)
    play(game, fake_ticks, 100)
    before = shown(game)

    game.game_state.decrease_money(50)

    assert shown(game) == before - 50
    play(game, fake_ticks, 2 * LAST_COIN_LANDS)
    assert shown(game) == game.game_state.money


def test_the_number_never_goes_negative_when_spending_more_than_it_shows(
    game, assets, fake_ticks
):
    game.game_state.money = 10
    game.hud.refresh()
    kill(game, assets)

    game.game_state.decrease_money(10)  # the balance is part of the reward alone now

    assert shown(game) == 0
    play(game, fake_ticks, 2 * LAST_COIN_LANDS)
    assert shown(game) == game.game_state.money


def test_the_buy_buttons_follow_the_real_balance_not_the_number(game, assets):
    price = game.tower_config.prices[0][0]
    game.game_state.money = price - 1
    game.hud.refresh()
    assert game.panel_manager["game"]["buy_tower_1"].state == "disabled"

    enemy = Enemy(1, 1, level=1, waypoints=game.tilemap.waypoints, assets=assets)
    game.enemies.append(enemy)
    enemy.kill_money = 5
    enemy.decrease_hp(enemy.max_hp, game)

    assert game.hud.shown_money == price - 1  # the coins haven't landed
    assert (
        game.panel_manager["game"]["buy_tower_1"].state is None
    )  # but it's affordable


def test_pausing_mid_flight_shows_the_balance_at_once(game, assets, fake_ticks):
    for _ in range(5):
        kill(game, assets)
    play(game, fake_ticks, 100)
    assert shown(game) < game.game_state.money

    game._open_pause_menu()
    play(game, fake_ticks, 20)

    assert shown(game) == game.game_state.money
    play(game, fake_ticks, 2 * LAST_COIN_LANDS)
    assert shown(game) == game.game_state.money


def test_the_wave_pause_shows_the_balance_at_once(game, assets, fake_ticks):
    kill(game, assets)
    game.game_state.is_started = False

    play(game, fake_ticks, 20)

    assert shown(game) == game.game_state.money


@pytest.mark.parametrize("popup", ["_trigger_victory", "_trigger_game_over"])
def test_victory_and_game_over_show_the_balance_at_once(
    game, assets, fake_ticks, popup
):
    kill(game, assets)
    play(game, fake_ticks, 100)
    assert shown(game) < game.game_state.money

    getattr(game, popup)()
    play(game, fake_ticks, 20)

    assert shown(game) == game.game_state.money


def test_saving_mid_flight_saves_the_balance_and_loading_shows_it(
    game, assets, fake_ticks
):
    for _ in range(4):
        kill(game, assets)
    play(game, fake_ticks, 100)
    balance = game.game_state.money
    assert shown(game) < balance
    game._save_game()
    assert game.save_store.load()["game_state"]["money"] == balance

    game._load_game()

    assert game.game_state.money == balance
    assert shown(game) == balance
    assert game.kill_feedback.pending_money == 0
    play(game, fake_ticks, 2 * LAST_COIN_LANDS)
    assert shown(game) == balance


def test_a_new_game_shows_the_starting_money(game, assets):
    for _ in range(4):
        kill(game, assets)

    game._start_new_game()

    assert shown(game) == game.game_state.money == game._starting_money


def test_reduce_flashing_shows_the_balance_with_no_animation(game, assets, fake_ticks):
    game.set_toggle("reduce_flashing", True)

    for _ in range(4):
        kill(game, assets)

    assert shown(game) == game.game_state.money
    assert game.kill_feedback.pending_money == 0
    assert not game.hud._odometer.is_rolling(game.hud._clock_ms)
    play(game, fake_ticks, 2 * LAST_COIN_LANDS)
    assert shown(game) == game.game_state.money


def test_turning_reduce_flashing_on_mid_flight_snaps(game, assets, fake_ticks):
    for _ in range(4):
        kill(game, assets)
    play(game, fake_ticks, 100)
    assert shown(game) < game.game_state.money

    game.set_toggle("reduce_flashing", True)

    assert shown(game) == game.game_state.money
    assert not game.hud._odometer.is_rolling(game.hud._clock_ms)


def test_the_game_draws_in_both_styles_while_coins_land(game, assets, fake_ticks):
    for _ in range(6):
        kill(game, assets)

    for _ in range(round(LAST_COIN_LANDS / FRAME_MS) + 2):
        play(game, fake_ticks, FRAME_MS)
        game.draw()

    assert shown(game) == game.game_state.money


def test_only_the_odometer_style_rolls_digits(game, assets, fake_ticks, style):
    kill(game, assets)
    play(game, fake_ticks, COIN_FLIGHT_MS + 20)  # the first coins have landed

    assert game.hud._odometer.is_rolling(game.hud._clock_ms) == (style == "odometer")

    play(game, fake_ticks, 2 * LAST_COIN_LANDS)
    assert not game.hud._odometer.is_rolling(game.hud._clock_ms)
    if style == "odometer":
        assert game.hud._odometer.text == str(game.game_state.money)


def test_the_odometer_draws_inside_the_money_plate(game, assets, fake_ticks, style):
    if style != "odometer":
        pytest.skip("the count-up style has no odometer")
    game.game_state.money = 1234
    game.hud.refresh()
    surface = pygame.Surface(game.window.get_size(), pygame.SRCALPHA)

    game.hud.draw_money_odometer(surface)

    plate = game.hud.coin_text.rect
    ink = pygame.mask.from_surface(surface).get_bounding_rects()
    assert ink
    assert all(plate.contains(rect) for rect in ink)
