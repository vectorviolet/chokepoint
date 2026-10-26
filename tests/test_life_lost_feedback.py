"""Life lost: the bell and the red vignette pulse. Unit tests drive
LifeLostFeedback directly (with the mixer channel faked); the rest play a
real Game(), with saves in a temporary directory."""

import random
from functools import partial

import pygame
import pytest

import app.game
import ui.life_lost_feedback as llf
from app.game import Game
from gameplay.menu_demo import MenuDemo
from gameplay.tilemap import Tilemap
from pygamine import SaveStore
from ui.life_lost_feedback import (
    ALERT_CHANNEL,
    ATTACK_MS,
    FADE_MS,
    MAX_STRENGTH,
    LifeLostFeedback,
)

PULSE_MS = ATTACK_MS + FADE_MS


class FakeChannel:
    played = []  # (channel id, sound, volume) for every play

    def __init__(self, channel_id):
        self.id = channel_id
        self.volume = 1.0

    def set_volume(self, volume):
        self.volume = volume

    def play(self, sound):
        FakeChannel.played.append((self.id, sound, self.volume))


@pytest.fixture
def channels(monkeypatch):
    """Fakes only the bell's channel; music and SFX keep the real mixer."""
    FakeChannel.played = []
    real = llf.mixer.Channel
    monkeypatch.setattr(
        llf.mixer,
        "Channel",
        lambda i: FakeChannel(i) if i == ALERT_CHANNEL else real(i),
    )
    return FakeChannel.played


@pytest.fixture
def feedback(assets, channels):
    pygame.mixer.init()
    return LifeLostFeedback(assets.sound_path("life_lost"), lambda: 0.3)


# ── LifeLostFeedback ──────────────────────────────────────────────────────────


def test_a_lost_life_starts_a_pulse(feedback):
    assert not feedback.is_active and feedback.strength == 0

    feedback.lives_lost(1)
    feedback.update(ATTACK_MS)

    assert feedback.is_active
    assert feedback.strength == pytest.approx(1.0)


def test_the_pulse_fades_out(feedback):
    feedback.lives_lost(1)
    feedback.update(ATTACK_MS)
    feedback.update(FADE_MS / 2)
    halfway = feedback.strength
    assert 0 < halfway < 1

    feedback.update(FADE_MS / 2)

    assert feedback.strength == 0
    assert not feedback.is_active


def test_lives_lost_together_make_a_stronger_pulse(feedback):
    feedback.lives_lost(2)
    feedback.update(ATTACK_MS)

    assert feedback.strength == pytest.approx(2.0)


def test_losses_stack_on_a_pulse_still_showing_up_to_the_cap(feedback):
    feedback.lives_lost(1)
    feedback.update(ATTACK_MS)
    feedback.lives_lost(1)
    feedback.update(ATTACK_MS)
    assert feedback.strength == pytest.approx(min(MAX_STRENGTH, 2.0))

    for _ in range(5):
        feedback.lives_lost(3)
        feedback.update(ATTACK_MS)

    assert feedback.strength == pytest.approx(MAX_STRENGTH)


def test_the_bell_plays_on_its_own_channel_at_the_sfx_volume(feedback, channels):
    feedback.lives_lost(1)
    feedback.lives_lost(2)

    assert [(ch, vol) for ch, _, vol in channels] == [
        (ALERT_CHANNEL, 0.3),
        (ALERT_CHANNEL, 0.3),
    ]


def test_no_lives_lost_does_nothing(feedback, channels):
    feedback.lives_lost(0)

    assert not feedback.is_active
    assert channels == []


def test_the_vignette_tints_the_edges_not_the_middle(feedback):
    surface = pygame.Surface((320, 180))
    surface.fill((0, 0, 0))
    feedback.lives_lost(1)
    feedback.update(ATTACK_MS)

    feedback.draw(surface)

    edge, middle = surface.get_at((1, 90)), surface.get_at((160, 90))
    assert edge.r > 60 and edge.g == 0
    assert middle == pygame.Color(0, 0, 0)


def test_the_vignette_follows_the_canvas_size(feedback):
    feedback.lives_lost(1)
    feedback.update(ATTACK_MS)

    for size in ((320, 180), (200, 300)):
        surface = pygame.Surface(size)
        surface.fill((0, 0, 0))
        feedback.draw(surface)
        assert surface.get_at((size[0] - 2, size[1] // 2)).r > 60


# ── in the game ───────────────────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks, channels):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    g.game_state.is_started = True
    g.update()  # the first frame measures 0 ms; start the wall clock now
    return g


def play(game, fake_ticks, ms, fps=60):
    for _ in range(round(ms / (1000 / fps))):
        fake_ticks["t"] += 1000 / fps
        game.update()


def escape(game, damage):
    enemy = type("E", (), {"damage": damage, "reached_end": lambda self: True})()
    game.enemies.append(enemy)
    game._update_enemies()


def test_an_escape_pulses_and_rings_the_bell(game, channels):
    game.audio.set_sfx_volume(0.4)

    escape(game, damage=1)

    assert game.life_lost_feedback.is_active
    assert [ch for ch, _, _ in channels] == [ALERT_CHANNEL]
    assert channels[0][2] == pytest.approx(0.4, abs=0.01)


def test_the_pulse_runs_on_real_time_whatever_the_speed(game, fake_ticks):
    strengths = []
    for speed in (1, 4):
        game.life_lost_feedback.clear()
        game.game_state.speed = speed
        escape(game, damage=1)
        play(game, fake_ticks, ATTACK_MS + FADE_MS / 2)
        strengths.append(round(game.life_lost_feedback.strength, 3))

    assert strengths[0] == strengths[1] > 0


def test_it_plays_out_while_paused(game, fake_ticks):
    escape(game, damage=1)
    game.game_state.is_started = False

    play(game, fake_ticks, PULSE_MS + 50)

    assert not game.life_lost_feedback.is_active


def test_the_last_life_shows_game_over_instead(game, channels):
    game.game_state.lives = 2

    escape(game, damage=5)

    assert game.game_state.lives == 0
    assert game._gameover_popup_open
    assert not game.life_lost_feedback.is_active
    assert channels == []


def test_the_menu_demo_stays_silent(assets, tower_config, channels):
    demo = MenuDemo(
        Tilemap("assets/maps/tiled_tilemap.tmx"),
        assets,
        tower_config,
        (1280, 720),
        random.Random(1),
    )
    for enemy in demo.enemies:
        enemy.waypoint_index = len(enemy.waypoints)  # all at the exit

    demo._update_enemies()

    assert channels == []
    assert not hasattr(demo, "life_lost_feedback")
