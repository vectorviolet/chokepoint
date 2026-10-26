"""Plane bomb impact: an explosion sized to the splash radius and a capped
sound where each bomb lands, on real time and through the camera. Unit
tests drive BombImpactFeedback directly; the rest go through a real Game()
(saves in a temporary directory) or the menu demo."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.combat.projectile import Bomb
from gameplay.menu_demo import MenuDemo
from gameplay.towers import TowerFactory
from pygamine import SaveStore
from ui.bomb_impact_feedback import (
    FRAME_MS,
    LIFE_MS,
    MAX_EXPLOSIONS,
    SIZE_FACTOR,
    SOUND_MIN_GAP_MS,
    SOUND_WINDOW_MS,
    SOUNDS_PER_WINDOW,
    TOTAL_FRAMES,
    BombImpactFeedback,
)

SOUND = "sfx/boom.ogg"
PLANE_TYPE = 4


class SfxSpy:
    """Stands in for GameAudio.play_sfx: records each call and returns a
    channel (any non-None), or None to act as a full pool."""

    def __init__(self):
        self.played = []
        self.pool_full = False

    def __call__(self, path):
        self.played.append(path)
        return None if self.pool_full else object()


@pytest.fixture
def sfx():
    return SfxSpy()


@pytest.fixture
def feedback(assets, sfx):
    return BombImpactFeedback(assets, sfx, SOUND)


class OffsetCamera:
    """Shifts the world by (-1000, -1000) at a zoom of 2; records what it saw."""

    scale = 2.0

    def __init__(self):
        self.seen = []

    def world_to_screen(self, pos):
        self.seen.append(Vector2(pos))
        return Vector2(pos) - Vector2(1000, 1000)


# ── BombImpactFeedback ────────────────────────────────────────────────────────


def test_an_impact_shows_an_explosion_at_the_landing_point(feedback, sfx):
    feedback.bomb_landed((640, 320), 96)

    assert len(feedback.explosions) == 1
    explosion = feedback.explosions[0]
    assert explosion.position == Vector2(640, 320)
    assert explosion.radius == 96
    assert sfx.played == [SOUND]


@pytest.mark.parametrize("radius", [96, 128])
def test_the_explosion_is_sized_to_the_splash_radius(feedback, radius):
    feedback.bomb_landed((0, 0), radius)

    side = round(2 * radius * SIZE_FACTOR)
    assert feedback.world_size(radius) == side
    frames = feedback._frames(side)
    assert len(frames) == TOTAL_FRAMES
    assert all(f.get_size() == (side, side) for f in frames)


def test_drawing_runs_through_the_camera_at_its_zoom(feedback):
    feedback.bomb_landed((1100, 1100), 40)
    feedback.update(FRAME_MS * 2)  # into the fireball
    camera = OffsetCamera()
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)

    feedback.draw(surface, camera)

    assert camera.seen == [Vector2(1100, 1100)]
    side = round(feedback.world_size(40) * camera.scale)  # 160 screen px
    drawn = surface.get_bounding_rect()
    assert drawn.width <= side and drawn.height <= side
    assert drawn.collidepoint(100, 100)  # centred on the landing point on screen
    assert drawn.width > side / 2  # and about as wide as the splash circle


def test_the_animation_advances_and_ends_on_its_own_clock(feedback):
    feedback.bomb_landed((0, 0), 96)
    explosion = feedback.explosions[0]
    assert feedback.frame_index(explosion) == 0

    feedback.update(FRAME_MS * 3)
    assert feedback.frame_index(explosion) == 3

    feedback.update(LIFE_MS - FRAME_MS * 3 - 1)
    assert feedback.explosions  # last frame still showing
    feedback.update(1)
    assert not feedback.explosions


def test_at_most_max_explosions_the_oldest_make_room(feedback):
    for i in range(MAX_EXPLOSIONS + 5):
        feedback.bomb_landed((i, 0), 96)

    assert len(feedback.explosions) == MAX_EXPLOSIONS
    assert feedback.explosions[0].position == Vector2(5, 0)
    assert feedback.explosions[-1].position == Vector2(MAX_EXPLOSIONS + 4, 0)


def test_impact_sounds_are_spaced_out(feedback, sfx):
    feedback.bomb_landed((0, 0), 96)
    feedback.update(SOUND_MIN_GAP_MS - 1)
    feedback.bomb_landed((10, 0), 96)  # too soon: shown, not heard

    assert len(feedback.explosions) == 2
    assert sfx.played == [SOUND]

    feedback.update(1)
    feedback.bomb_landed((20, 0), 96)
    assert len(sfx.played) == 2


def test_impact_sounds_are_capped_per_window(feedback, sfx):
    """A steady stream of impacts (planes at x4) plays at most
    SOUNDS_PER_WINDOW sounds in any SOUND_WINDOW_MS."""
    starts = []
    for _ in range(40):
        before = len(sfx.played)
        feedback.bomb_landed((0, 0), 96)
        if len(sfx.played) > before:
            starts.append(feedback.now_ms)
        feedback.update(SOUND_MIN_GAP_MS)

    assert starts
    for t in starts:
        assert sum(1 for s in starts if t <= s < t + SOUND_WINDOW_MS) <= (
            SOUNDS_PER_WINDOW
        )
    assert len(starts) < 40


def test_a_sound_dropped_by_a_full_pool_does_not_count(feedback, sfx):
    sfx.pool_full = True
    feedback.bomb_landed((0, 0), 96)
    sfx.pool_full = False
    feedback.bomb_landed((0, 0), 96)  # same instant: the first one never played

    assert len(sfx.played) == 2


def test_without_play_sfx_impacts_are_silent(assets):
    silent = BombImpactFeedback(assets, play_sfx=None)

    silent.bomb_landed((0, 0), 96)

    assert len(silent.explosions) == 1


def test_clear_drops_every_explosion_and_the_sound_history(feedback, sfx):
    feedback.bomb_landed((0, 0), 96)

    feedback.clear()
    feedback.bomb_landed((0, 0), 96)  # no gap needed after a clear

    assert len(feedback.explosions) == 1
    assert len(sfx.played) == 2


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


@pytest.fixture
def played(game, monkeypatch):
    calls = []

    def spy(path):
        calls.append(path)
        return object()

    monkeypatch.setattr(game.bomb_impacts, "_play_sfx", spy)
    return calls


def drop_bomb(game, position):
    plane = TowerFactory.create(
        PLANE_TYPE,
        0,
        0,
        game.tower_config,
        game.assets,
        audio=None,
        map_width=game.tilemap.map_width,
    )
    plane.position = Vector2(position)
    plane.now = game.game_state.time_ms
    bomb = Bomb(plane, Vector2(0, 0))
    plane.bullets.append(bomb)
    game.towers.append(plane)
    return plane, bomb


def test_a_bomb_landing_in_the_game_explodes_with_its_sound(game, played, fake_ticks):
    game.game_state.is_started = True
    plane, bomb = drop_bomb(game, (900, 700))

    play(game, fake_ticks, Bomb.FALL_DURATION_MS + 50)

    assert bomb not in plane.bullets
    assert len(game.bomb_impacts.explosions) == 1
    explosion = game.bomb_impacts.explosions[0]
    assert explosion.position == bomb.position
    assert explosion.radius == plane.range
    assert played == [str(game.assets.sound_path("bomb_impact"))]
    game.draw()  # drawn in the battle through the game's camera


def test_the_explosion_plays_out_while_the_game_is_paused(game, played, fake_ticks):
    game.game_state.is_started = True
    drop_bomb(game, (900, 700))
    play(game, fake_ticks, Bomb.FALL_DURATION_MS + 50)
    explosion = game.bomb_impacts.explosions[0]
    frame = game.bomb_impacts.frame_index(explosion)

    game.game_state.is_started = False  # paused
    paused_at = game.game_state.time_ms
    play(game, fake_ticks, FRAME_MS * 3)
    assert game.bomb_impacts.frame_index(explosion) > frame  # not frozen
    game.draw()

    play(game, fake_ticks, LIFE_MS)
    assert not game.bomb_impacts.explosions
    assert game.game_state.time_ms == paused_at  # game time never moved


def test_x4_speed_does_not_hurry_the_explosion(game, played, fake_ticks):
    game.bomb_impacts.bomb_landed((900, 700), 96)
    game.game_state.is_started = True
    game.game_state.speed = 4

    play(game, fake_ticks, LIFE_MS / 2)
    assert game.bomb_impacts.explosions  # x4 would have ended it already

    play(game, fake_ticks, LIFE_MS / 2 + 50)
    assert not game.bomb_impacts.explosions


def test_a_new_game_clears_the_explosions(game, played):
    game.bomb_impacts.bomb_landed((900, 700), 96)

    game._start_new_game()

    assert not game.bomb_impacts.explosions


def test_loading_a_save_clears_the_explosions(game, played):
    game._save_game()
    game.bomb_impacts.bomb_landed((900, 700), 96)

    game._load_game()

    assert not game.bomb_impacts.explosions


# ── the menu demo ─────────────────────────────────────────────────────────────


@pytest.fixture
def demo(assets, tower_config):
    from gameplay.tilemap import Tilemap

    tilemap = Tilemap("assets/maps/tiled_tilemap.tmx")
    return MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))


def test_the_menu_demo_shows_explosions_without_sound(demo):
    assert demo.bomb_impacts._play_sfx is None
    assert not demo.bomb_impacts.explosions  # pre-warm impacts were cleared

    demo.bomb_landed(Vector2(500, 500), 96)
    assert len(demo.bomb_impacts.explosions) == 1
    demo.draw(pygame.Surface((1280, 720)))

    demo.update(LIFE_MS + 10)  # in real time, like the game's
    assert all(e.position != Vector2(500, 500) for e in demo.bomb_impacts.explosions)


def test_the_menu_demos_bombs_explode_where_they_land(demo):
    plane = TowerFactory.create(
        PLANE_TYPE, 0, 0, demo._tower_config, demo._assets, demo._audio, 3008
    )
    plane.position = Vector2(700, 700)
    plane.now = demo.game_state.time_ms
    bomb = Bomb(plane, Vector2(0, 0))
    plane.bullets.append(bomb)
    demo.towers.append(plane)

    for _ in range(int(Bomb.FALL_DURATION_MS / 1000 * 165) + 5):
        demo._tick()

    assert any(e.position == bomb.position for e in demo.bomb_impacts.explosions)
