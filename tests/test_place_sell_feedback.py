"""Tower placed / sold: a sound and a short effect on the tile (dust when
placing, coins when selling), on real time and through the camera. Unit
tests drive PlaceSellFeedback directly; the rest go through the placement
controller or a real Game(), with saves in a temporary directory."""

import random
from functools import partial

import pygame
import pytest
from pygame import Rect
from pygame.math import Vector2

import app.game
from app.game import Game
from domain.game_state import GameState
from gameplay.combat.tower_placement import TowerPlacementController
from gameplay.menu_demo import MenuDemo
from gameplay.towers.base_tower import BTN_SIZE, SELL_BTN_OFFSET
from pygamine import Camera, SaveStore
from ui.place_sell_feedback import (
    COIN_LIFE_MS,
    COINS_PER_SALE,
    DUST_LIFE_MS,
    DUST_PUFFS,
    MAX_EFFECTS,
    PlaceSellFeedback,
)
from util.constants import HALF_TILE, TILE_SIZE

PLACE_SOUND = "sfx/place.ogg"
SELL_SOUND = "sfx/sell.ogg"


class SfxSpy:
    def __init__(self):
        self.played = []

    def __call__(self, path):
        self.played.append(path)


@pytest.fixture
def sfx():
    return SfxSpy()


@pytest.fixture
def feedback(assets, sfx):
    return PlaceSellFeedback(
        [assets.get_image(f"black_smoke_{i}") for i in range(13)],
        assets.get_image("coin_sheet"),
        sfx,
        PLACE_SOUND,
        SELL_SOUND,
        random.Random(1),
    )


class OffsetCamera:
    """Shifts the world by (-1000, -1000) at a zoom of 2; records what it saw."""

    scale = 2.0

    def __init__(self):
        self.seen = []

    def world_to_screen(self, pos):
        self.seen.append(Vector2(pos))
        return Vector2(pos) - Vector2(1000, 1000)


# ── PlaceSellFeedback ─────────────────────────────────────────────────────────


def test_placing_plays_the_place_sound_and_puffs_dust_on_the_tile(feedback, sfx):
    feedback.tower_placed((160, 224))

    assert sfx.played == [PLACE_SOUND]
    assert len(feedback.dust) == DUST_PUFFS
    assert not feedback.coins
    assert all(d.origin == Vector2(160, 224) for d in feedback.dust)
    for dust in feedback.dust:  # starts on the tile centre
        assert feedback.dust_position(dust) == Vector2(160, 224)
    feedback.update(DUST_LIFE_MS - 1)
    for dust in feedback.dust:  # and drifts out a little
        assert 0 < feedback.dust_position(dust).distance_to((160, 224)) < HALF_TILE


def test_selling_plays_the_sell_sound_and_bursts_coins_from_the_tile(feedback, sfx):
    feedback.tower_sold((160, 224))

    assert sfx.played == [SELL_SOUND]
    assert len(feedback.coins) == COINS_PER_SALE
    assert not feedback.dust
    for coin in feedback.coins:
        assert feedback.coin_position(coin) == Vector2(160, 224)
    feedback.update(150)
    for coin in feedback.coins:
        assert feedback.coin_position(coin).y < 224  # flung upwards


def test_effects_expire_after_their_life_in_real_time(feedback):
    feedback.update(1000)
    feedback.tower_placed((0, 0))
    feedback.tower_sold((0, 0))

    feedback.update(DUST_LIFE_MS - 1)
    assert feedback.dust and feedback.coins
    feedback.update(1)
    assert not feedback.dust and feedback.coins
    feedback.update(COIN_LIFE_MS - DUST_LIFE_MS)
    assert feedback.live_effects == 0


def test_the_cap_holds_but_the_sound_still_plays(feedback, sfx):
    for i in range(100):
        feedback.tower_placed((i, i))
        feedback.tower_sold((i, i))

    assert feedback.live_effects == MAX_EFFECTS
    assert len(sfx.played) == 200


def test_effects_free_up_room_as_they_end(feedback):
    for i in range(100):
        feedback.tower_sold((i, i))
    feedback.update(COIN_LIFE_MS)
    assert feedback.live_effects == 0

    feedback.tower_placed((0, 0))
    assert len(feedback.dust) == DUST_PUFFS


def test_drawing_runs_through_the_camera(feedback):
    camera = OffsetCamera()
    surface = pygame.Surface((200, 200))
    feedback.tower_placed((1100, 1100))
    feedback.tower_sold((1100, 1100))

    feedback.draw(surface, camera)

    assert len(camera.seen) == DUST_PUFFS + COINS_PER_SALE
    assert all(p == Vector2(1100, 1100) for p in camera.seen)
    assert surface.get_at((100, 100)) != pygame.Color(0, 0, 0)  # something drawn


def test_clear_drops_every_effect(feedback):
    feedback.tower_placed((0, 0))
    feedback.tower_sold((0, 0))

    feedback.clear()

    assert feedback.live_effects == 0


# ── through the placement controller ──────────────────────────────────────────

GAME_AREA = Rect(0, 0, 1536, 1080)


class FakeButton:
    def __init__(self, rect):
        self.rect = rect
        self.active = True

    def is_clicked(self, event, mouse_pos) -> bool:
        return False


class FeedbackSpy:
    def __init__(self):
        self.placed = []
        self.sold = []

    def tower_placed(self, world_pos):
        self.placed.append(Vector2(world_pos))

    def tower_sold(self, world_pos):
        self.sold.append(Vector2(world_pos))


@pytest.fixture
def controller(tower_config, assets):
    camera = Camera(Rect(GAME_AREA), 3008, 2176, scroll_rect=Rect(GAME_AREA))
    gs = GameState(start_money=1_000_000, start_lives=10)
    panel = {
        f"buy_tower_{i + 1}": FakeButton(Rect(1600 + i * 80, 20, 40, 40))
        for i in range(4)
    }
    spy = FeedbackSpy()
    c = TowerPlacementController(
        [],
        tower_config,
        assets,
        None,
        gs,
        camera,
        {"game": panel},
        [[True] * 47 for _ in range(34)],
        3008,
        Rect(GAME_AREA),
        feedback=spy,
    )
    return c, spy, gs, camera


def click(controller, pos):
    controller.update_cursor(pos)
    controller.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1), pos)


def test_buying_a_tower_tells_the_feedback_its_tile(controller):
    c, spy, gs, camera = controller
    c.buying_tower_type = 1
    screen = camera.world_to_screen((5 * TILE_SIZE + 5, 5 * TILE_SIZE + 5))

    click(c, (screen.x, screen.y))

    tower = c._towers[0]
    assert spy.placed == [Vector2(5 * TILE_SIZE + HALF_TILE, 5 * TILE_SIZE + HALF_TILE)]
    assert tower.position == spy.placed[0]
    assert not spy.sold


def test_a_refused_purchase_makes_no_feedback(controller):
    c, spy, gs, camera = controller
    gs.money = 0
    c.buying_tower_type = 1
    screen = camera.world_to_screen((5 * TILE_SIZE + 5, 5 * TILE_SIZE + 5))

    click(c, (screen.x, screen.y))

    assert not c._towers and not spy.placed


def test_selling_a_tower_tells_the_feedback_its_tile(controller):
    c, spy, gs, camera = controller
    c.buying_tower_type = 1
    screen = camera.world_to_screen((5 * TILE_SIZE + 5, 5 * TILE_SIZE + 5))
    click(c, (screen.x, screen.y))
    tower = c._towers[0]
    gs.selected_tower = tower

    sell = (
        camera.world_to_screen(tower.position)
        + SELL_BTN_OFFSET
        + Vector2(BTN_SIZE[0] / 2, BTN_SIZE[1] / 2)
    )
    click(c, (sell.x, sell.y))

    assert tower not in c._towers
    assert spy.sold == [Vector2(tower.position)]


# ── in the game ───────────────────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    return g


def play(game, fake_ticks, ms, fps=60):
    for _ in range(round(ms / (1000 / fps))):
        fake_ticks["t"] += 1000 / fps
        game.update()


def test_the_game_plays_its_sounds_through_play_sfx(game, monkeypatch):
    played = []
    monkeypatch.setattr(game.place_sell_feedback, "_play_sfx", played.append)

    game.place_sell_feedback.tower_placed((100, 100))
    game.place_sell_feedback.tower_sold((100, 100))

    assert played == [
        str(game.assets.sound_path("tower_placed")),
        str(game.assets.sound_path("tower_sold")),
    ]
    assert game.tower_controller._feedback is game.place_sell_feedback


@pytest.fixture
def quiet(game, monkeypatch):
    monkeypatch.setattr(game.place_sell_feedback, "_play_sfx", lambda path: None)
    return game.place_sell_feedback


def test_the_effects_play_out_while_the_game_is_paused(game, quiet, fake_ticks):
    game.game_state.is_started = False
    play(game, fake_ticks, 100)
    quiet.tower_placed((100, 100))
    quiet.tower_sold((100, 100))

    play(game, fake_ticks, DUST_LIFE_MS / 2)
    assert quiet.dust and quiet.coins  # moving, not frozen
    assert all(quiet.dust_position(d) != Vector2(100, 100) for d in quiet.dust)
    game.draw()  # drawn through the game's camera without trouble

    play(game, fake_ticks, COIN_LIFE_MS + 50)
    assert quiet.live_effects == 0
    assert game.game_state.time_ms == 0  # game time never moved


def test_game_speed_does_not_hurry_the_effects(game, quiet, fake_ticks):
    game.game_state.is_started = True
    game.game_state.speed = 4
    play(game, fake_ticks, 100)
    quiet.tower_placed((100, 100))

    play(game, fake_ticks, DUST_LIFE_MS / 2)
    assert quiet.dust  # x4 would have ended them long ago

    play(game, fake_ticks, DUST_LIFE_MS / 2 + 50)
    assert not quiet.dust


def test_a_new_game_clears_the_effects(game, quiet):
    quiet.tower_sold((100, 100))

    game._start_new_game()

    assert quiet.live_effects == 0


def test_the_menu_demo_has_no_place_or_sell_feedback(assets, tower_config):
    from gameplay.tilemap import Tilemap

    tilemap = Tilemap("assets/maps/tiled_tilemap.tmx")
    demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))

    assert demo.towers  # it builds its towers itself, without a controller
    assert not hasattr(demo, "place_sell_feedback")
    assert not hasattr(demo, "tower_controller")
