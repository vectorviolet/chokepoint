"""Kill reward feedback: the floating "+$N" (game time) and the coins flying
to the money counter (real time). Unit tests drive KillFeedback directly;
the rest play a real Game(), with saves in a temporary directory."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.battle import BattleSimulation
from gameplay.combat.enemy import Enemy
from gameplay.menu_demo import MenuDemo
from pygamine import SaveStore
from ui.kill_feedback import (
    COIN_FLIGHT_MS,
    COIN_STAGGER_MS,
    COINS_PER_KILL,
    MAX_EFFECTS,
    TEXT_LIFE_MS,
    KillFeedback,
)

LAST_COIN_LANDS = COIN_FLIGHT_MS + (COINS_PER_KILL[1] - 1) * COIN_STAGGER_MS


@pytest.fixture
def feedback(assets):
    return KillFeedback(
        assets.get_image("coin_sheet"),
        assets.font_path("comic_neue_bold"),
        random.Random(1),
    )


# ── KillFeedback ──────────────────────────────────────────────────────────────


def test_a_kill_makes_one_text_with_its_reward_and_a_few_coins(feedback):
    feedback.add_kill((100, 200), 35, (400, 300), now_ms=0)

    assert [t.amount for t in feedback.texts] == [35]
    assert feedback.texts[0].position == Vector2(100, 200)
    assert COINS_PER_KILL[0] <= len(feedback.coins) <= COINS_PER_KILL[1]


def test_the_text_expires_after_its_life_in_game_time(feedback):
    feedback.add_kill((0, 0), 10, (0, 0), now_ms=1000)

    feedback.update(16, now_ms=1000 + TEXT_LIFE_MS - 1)
    assert feedback.texts

    feedback.update(16, now_ms=1000 + TEXT_LIFE_MS)
    assert not feedback.texts


def test_pausing_freezes_the_text_but_the_coins_still_land(feedback):
    feedback.add_kill((0, 0), 10, (0, 0), now_ms=500)

    for _ in range(120):  # two seconds of real time, game time stopped
        feedback.update(1000 / 60, now_ms=500)

    assert feedback.texts  # frozen in place
    assert not feedback.coins  # the flight to the HUD runs on real time


def test_the_coins_land_after_their_flight_and_pop_the_counter(feedback):
    feedback.add_kill((0, 0), 10, (0, 0), now_ms=0)

    feedback.update(COIN_FLIGHT_MS - 1, now_ms=0)
    assert feedback.coins and not feedback.is_popping

    feedback.update(1, now_ms=0)  # the first coin lands
    assert feedback.is_popping
    feedback.update(LAST_COIN_LANDS, now_ms=0)
    assert not feedback.coins


def test_the_cap_holds_under_mass_kills(feedback):
    for i in range(200):
        feedback.add_kill((i, i), 10, (i, i), now_ms=0)

    assert feedback.live_effects == MAX_EFFECTS


def test_effects_free_up_room_as_they_end(feedback):
    for i in range(200):
        feedback.add_kill((i, i), 10, (i, i), now_ms=0)
    feedback.update(LAST_COIN_LANDS, now_ms=TEXT_LIFE_MS)
    assert feedback.live_effects == 0

    feedback.add_kill((0, 0), 10, (0, 0), now_ms=TEXT_LIFE_MS)
    assert len(feedback.texts) == 1


def test_drawing_runs_through_the_camera(feedback):
    class Camera:
        def __init__(self):
            self.seen = []

        def world_to_screen(self, pos):
            self.seen.append(Vector2(pos))
            return Vector2(pos) - Vector2(1000, 1000)

    camera = Camera()
    surface = pygame.Surface((200, 200))
    feedback.add_kill((1100, 1100), 10, (100, 100), now_ms=0)

    feedback.draw_texts(surface, camera, now_ms=0)
    feedback.draw_coins(surface, (10, 10))
    feedback.update(COIN_FLIGHT_MS, now_ms=0)
    feedback.draw_pop(surface, pygame.Rect(0, 0, 50, 20))

    assert camera.seen == [Vector2(1100, 1100)]


# ── in the game ───────────────────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    return g


def kill_one(game, assets):
    enemy = Enemy(1, 1, level=1, waypoints=game.tilemap.waypoints, assets=assets)
    game.enemies.append(enemy)
    enemy.decrease_hp(enemy.maxHP, game)
    return enemy


def play(game, fake_ticks, ms, fps=60):
    for _ in range(round(ms / (1000 / fps))):
        fake_ticks["t"] += 1000 / fps
        game.update()


def test_a_kill_in_the_game_pays_once_and_shows_its_reward(game, assets):
    money = game.game_state.money

    enemy = kill_one(game, assets)

    assert game.game_state.money == money + enemy.killMoney
    assert [t.amount for t in game.kill_feedback.texts] == [enemy.killMoney]
    assert game.kill_feedback.texts[0].position == enemy.position


def test_the_text_runs_on_game_time_in_the_game(game, assets, fake_ticks):
    kill_one(game, assets)
    game.game_state.is_started = False

    play(game, fake_ticks, TEXT_LIFE_MS * 2)
    assert game.kill_feedback.texts  # paused: still there

    game.game_state.is_started = True
    game.game_state.speed = 4
    play(game, fake_ticks, TEXT_LIFE_MS / 4 + 50)
    assert not game.kill_feedback.texts  # x4: gone in a quarter of the time


def test_coins_fly_to_the_counter_even_while_the_hud_is_hidden(
    game, assets, fake_ticks, monkeypatch
):
    game.hud_slide.toggle()
    play(game, fake_ticks, 300)
    targets = []
    monkeypatch.setattr(
        game.kill_feedback, "draw_coins", lambda surface, target: targets.append(target)
    )

    kill_one(game, assets)
    play(game, fake_ticks, 250)  # the money counter has peeked back by now
    game.draw()

    assert targets == [game.panel_manager["game"]["coin_image"].rect.center]
    assert game.hud_slide.offset("money") == (0, 0)  # drawn where they land


def test_a_new_game_clears_the_effects(game, assets):
    kill_one(game, assets)

    game._start_new_game()

    assert game.kill_feedback.live_effects == 0


def test_the_menu_demo_has_no_kill_effects(tilemap_and_assets):
    tilemap, assets, tower_config = tilemap_and_assets
    demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))
    enemy = demo.enemies[0]

    enemy.decrease_hp(enemy.maxHP, demo)  # must not raise

    assert enemy not in demo.enemies
    assert type(demo)._on_enemy_killed is BattleSimulation._on_enemy_killed
    assert not hasattr(demo, "kill_feedback")


@pytest.fixture
def tilemap_and_assets(assets, tower_config):
    from gameplay.tilemap import Tilemap

    return Tilemap("assets/maps/tiled_tilemap.tmx"), assets, tower_config
