"""The Master volume slider in Settings (issue #45), in a real Game() with
saves and settings in a temporary directory. GameAudio (pygamine v0.27.0)
plays the music at master x music and every SFX at master x SFX."""

from functools import partial

import pygame
import pytest
from pygame import mixer

import app.game
from app.game import Game
from pygamine import SaveStore


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return Game


@pytest.fixture
def game(make_game):
    return make_game()


def settings(game):
    return game.panel_manager["settings"]


def test_the_slider_sits_above_sfx_and_music_in_the_same_style(game):
    panel = settings(game)
    master, sfx, music = (
        panel[f"{name}_volume_slider"] for name in ("master", "sfx", "music")
    )

    assert master.rect.bottom < sfx.rect.top < music.rect.top
    assert master.rect.size == sfx.rect.size == music.rect.size
    assert master.rect.centerx == sfx.rect.centerx
    assert panel["master_volume_label_text"].text == "MASTER VOLUME"


def test_it_starts_at_100_percent(game):
    assert game.audio.master_volume() == 1.0
    assert settings(game)["master_volume_slider"].value == 1.0
    assert settings(game)["master_volume_value_text"].text == "100%"


def test_moving_it_scales_music_and_sfx_live_but_not_their_own_sliders(game):
    game.audio.set_music_volume(0.8)
    game.audio.set_sfx_volume(0.6)

    settings(game)["master_volume_slider"].on_change(0.5)

    assert settings(game)["master_volume_value_text"].text == "50%"
    assert game.audio.master_volume() == pytest.approx(0.5)
    assert game.audio.effective_music_volume() == pytest.approx(0.4)
    assert game.audio.effective_sfx_volume() == pytest.approx(0.3)
    # ...and it reached the mixer (SDL_AUDIODRIVER=dummy, so it's always up)
    assert mixer.get_init(), "the mixer should be initialised by Game()"
    assert mixer.Channel(0).get_volume() == pytest.approx(0.4, abs=0.01)
    assert mixer.Channel(1).get_volume() == pytest.approx(0.3, abs=0.01)
    game._bind_settings_ui()
    assert settings(game)["music_volume_value_text"].text == "80%"
    assert settings(game)["sfx_volume_value_text"].text == "60%"


def test_it_is_saved_and_restored(game, make_game):
    settings(game)["master_volume_slider"].on_change(0.3)
    game._save_settings()

    assert game.settings_store.load()["master_volume"] == pytest.approx(0.3)
    restarted = make_game()
    assert restarted.audio.master_volume() == pytest.approx(0.3)
    assert settings(restarted)["master_volume_slider"].value == pytest.approx(0.3)
    assert settings(restarted)["master_volume_value_text"].text == "30%"


def test_old_settings_without_it_load_at_100_percent(game, make_game):
    game.audio.set_master_volume(0.2)  # class-wide: a stale value must not leak
    game.settings_store.save({"music_on": True, "sfx_volume": 0.5})

    restarted = make_game()

    assert restarted.audio.master_volume() == 1.0
    assert restarted.audio.sfx_volume() == 0.5


@pytest.mark.parametrize(
    "saved, expected",
    [
        ({"master_volume": None, "sfx_volume": None, "music_volume": None}, 1.0),
        ({"master_volume": "loud", "sfx_volume": "0.5", "music_volume": [1]}, 1.0),
        ({"master_volume": True, "sfx_volume": False, "music_volume": {}}, 1.0),
        ({"master_volume": 3, "sfx_volume": 1.5, "music_volume": 7}, 1.0),
        ({"master_volume": -1, "sfx_volume": -0.5, "music_volume": -3}, 0.0),
    ],
    ids=["null", "string", "other-types", "too-high", "too-low"],
)
def test_broken_saved_volumes_fall_back_or_are_clamped(make_game, saved, expected):
    make_game().settings_store.save({"music_on": True, **saved})

    restarted = make_game()

    for name in ("master", "sfx", "music"):
        assert getattr(restarted.audio, f"{name}_volume")() == expected
        assert settings(restarted)[f"{name}_volume_slider"].value == expected


def test_reset_to_defaults_sets_it_back_to_100_percent(game):
    settings(game)["master_volume_slider"].on_change(0.25)

    game._reset_settings()

    assert game.audio.master_volume() == 1.0
    assert settings(game)["master_volume_slider"].value == 1.0
    assert settings(game)["master_volume_value_text"].text == "100%"
    assert game.settings_store.load()["master_volume"] == 1.0


@pytest.mark.parametrize(
    "size", [(1024, 576), (1280, 800), (1366, 768), (1920, 1080), (1920, 1200)]
)
def test_the_settings_screen_still_fits(game, size):
    game.set_resolution(size)
    game.set_windowed()
    screen = pygame.Rect((0, 0), game.window.get_size())
    panel = settings(game)

    for name in ("master", "sfx", "music"):
        for part in ("label_text", "value_text", "slider"):
            assert screen.contains(panel[f"{name}_volume_{part}"].rect)
    assert not panel["music_volume_slider"].rect.colliderect(panel["reset"].rect)
    assert not panel["music_volume_slider"].rect.colliderect(panel["back"].rect)
