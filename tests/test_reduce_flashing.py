"""Reduce flashing (#117): with the flag on a hit shows no white flash (the
spark stays) and explosion fireballs are drawn at REDUCED_FIREBALL_ALPHA
(smoke and rubble unchanged); off, everything is as before. The flag is
passed to the feedback classes, so the menu demo follows it too."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.menu_demo import MenuDemo
from pygamine import SaveStore
from ui.bomb_impact_feedback import (
    EXPLOSION_FRAMES,
    FRAME_MS,
    REDUCED_FIREBALL_ALPHA,
    TOTAL_FRAMES,
    BombImpactFeedback,
    ExplosionFrames,
)
from ui.death_feedback import DeathFeedback
from ui.hit_feedback import HitFeedback


class Camera:
    scale = 1.0

    def world_to_screen(self, pos):
        return Vector2(pos)

    def scale_image(self, image):
        return image


class Target:
    def __init__(self):
        self.position = Vector2(100, 100)
        self.image = pygame.Surface((20, 20), pygame.SRCALPHA)
        self.image.fill((200, 30, 30, 255))

    def flash_parts(self):
        return [(self.image, Vector2(self.position))]


def canvas() -> pygame.Surface:
    return pygame.Surface((300, 300), pygame.SRCALPHA)


def alpha_sum(surface: pygame.Surface) -> int:
    return sum(pygame.image.tobytes(surface, "RGBA")[3::4])


def pixels(surface: pygame.Surface) -> bytes:
    return pygame.image.tobytes(surface, "RGBA")


# ── the hit flash ─────────────────────────────────────────────────────────────


def flash_alpha(reduce: bool) -> int:
    feedback = HitFeedback(rng=random.Random(1), reduce_flashing=reduce)
    target = Target()
    feedback.target_hit(target, (150, 100))
    surface = canvas()
    feedback.draw_flash(surface, Camera(), target)
    return alpha_sum(surface)


def test_the_white_flash_is_drawn_when_off():
    assert flash_alpha(reduce=False) > 0


def test_no_white_flash_is_drawn_when_on():
    assert flash_alpha(reduce=True) == 0


def test_the_spark_stays_when_on():
    feedback = HitFeedback(rng=random.Random(1), reduce_flashing=True)
    feedback.target_hit(Target(), (150, 100))
    feedback.update(20)
    surface = canvas()

    feedback.draw_sparks(surface, Camera())

    assert alpha_sum(surface) > 0


def test_the_flag_can_change_while_a_flash_plays():
    feedback = HitFeedback(rng=random.Random(1))
    target = Target()
    feedback.target_hit(target, (150, 100))
    feedback.reduce_flashing = True
    surface = canvas()

    feedback.draw_flash(surface, Camera(), target)

    assert alpha_sum(surface) == 0


# ── the explosions ────────────────────────────────────────────────────────────


def test_reduced_frames_dim_only_the_fireball(assets):
    frames = ExplosionFrames(assets)
    size = 64
    normal = frames.frames(size)
    reduced = frames.frames(size, reduced=True)

    for i in range(EXPLOSION_FRAMES):  # smoke + fireball
        smoke = pygame.transform.smoothscale(
            assets.get_image(f"black_smoke_{i}"), (size, size)
        )
        fire = pygame.transform.smoothscale(
            assets.get_image(f"explosion_{i}"), (size, size)
        )
        fire.set_alpha(REDUCED_FIREBALL_ALPHA)
        expected = pygame.Surface((size, size), pygame.SRCALPHA)
        expected.blit(smoke, (0, 0))
        expected.blit(fire, (0, 0))
        assert pixels(reduced[i]) == pixels(expected)
        assert alpha_sum(reduced[i]) < alpha_sum(normal[i])
    for i in range(EXPLOSION_FRAMES, TOTAL_FRAMES):  # smoke only: unchanged
        assert pixels(reduced[i]) == pixels(normal[i])


def bomb_alpha(assets, reduce: bool) -> int:
    feedback = BombImpactFeedback(
        assets, None, frames=ExplosionFrames(assets), reduce_flashing=reduce
    )
    feedback.bomb_landed((150, 150), 40)
    feedback.update(FRAME_MS * 2)  # into the fireball
    surface = canvas()
    feedback.draw(surface, Camera())
    return alpha_sum(surface)


def test_a_bomb_impact_is_dimmer_when_on_and_unchanged_when_off(assets):
    off = bomb_alpha(assets, reduce=False)
    assert 0 < bomb_alpha(assets, reduce=True) < off
    assert bomb_alpha(assets, reduce=False) == off


def death_alpha(assets, reduce: bool) -> int:
    feedback = DeathFeedback(
        assets, None, frames=ExplosionFrames(assets), reduce_flashing=reduce
    )
    feedback.enemy_died((150, 150), is_tank=False)
    feedback.update(FRAME_MS * 2)
    surface = canvas()
    feedback.draw_blasts(surface, Camera())
    return alpha_sum(surface)


def test_a_death_blast_is_dimmer_when_on_and_unchanged_when_off(assets):
    off = death_alpha(assets, reduce=False)
    assert 0 < death_alpha(assets, reduce=True) < off
    assert death_alpha(assets, reduce=False) == off


def test_the_rubble_decal_is_unchanged_when_on(assets):
    drawn = []
    for reduce in (False, True):
        feedback = DeathFeedback(
            assets, None, frames=ExplosionFrames(assets), reduce_flashing=reduce
        )
        feedback.tower_destroyed((150, 150))
        surface = canvas()
        feedback.draw_decals(surface, Camera())
        drawn.append(surface)

    assert pixels(drawn[0]) == pixels(drawn[1])
    assert alpha_sum(drawn[0]) > 0


# ── the game and the menu demo ────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return Game()


def flags(battle) -> list[bool]:
    return [
        battle.hit_feedback.reduce_flashing,
        battle.bomb_impacts.reduce_flashing,
        battle.death_feedback.reduce_flashing,
    ]


def test_the_default_is_off(game):
    assert game.reduce_flashing is False
    assert flags(game) == [False] * 3
    assert flags(game.menu_demo) == [False] * 3


def test_setting_it_reaches_the_game_and_the_menu_demo_at_once(game):
    game.reduce_flashing = True

    assert flags(game) == [True] * 3
    assert flags(game.menu_demo) == [True] * 3

    game.reduce_flashing = False

    assert flags(game) == [False] * 3
    assert flags(game.menu_demo) == [False] * 3


def test_a_standalone_menu_demo_takes_the_flag(game):
    demo = MenuDemo(
        game.tilemap,
        game.assets,
        game.tower_config,
        (1280, 720),
        random.Random(1),
        reduce_flashing=True,
    )

    assert flags(demo) == [True] * 3
