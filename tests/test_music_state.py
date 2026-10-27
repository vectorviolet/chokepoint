"""The saved music on/off state across the splash and restarts (issue #54),
in a real Game() with saves and settings in a temporary directory.

The splash plays its clip through the game's own GameAudio, whose
play_music()/stop_music() clear the paused flag; the saved state must
survive that, and every music toggle must show what the audio is doing."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore

MENU_PANELS = ("main_menu", "play_menu", "credits", "settings")


class PlayedSplash:
    """Stands in for the real splash: its clip plays and stops through
    the game's GameAudio, as standard_splash_media(self.audio) does."""

    def __init__(self, audio, clip_path) -> None:
        self.audio = audio
        self.clip_path = clip_path

    def run(self, *args) -> None:
        self.audio.play_music(self.clip_path, loops=0)
        self.audio.stop_music()


class SkippedSplash:
    """A splash skipped at once: it never touches the audio."""

    def run(self, *args) -> None:
        pass


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return Game


def start(make_game, splash: str) -> Game:
    """Builds a Game and runs its startup splash, played or skipped."""
    game = make_game()
    if splash == "played":
        game.splash = PlayedSplash(game.audio, str(game.assets.sound_path("click")))
    else:
        game.splash = SkippedSplash()
    game.show_splash()
    return game


def save_music_on(make_game, music_on: bool) -> None:
    store = make_game().settings_store
    store.save({**store.load(), "music_on": music_on})


def assert_music_shows(game: Game, *, on: bool) -> None:
    assert game.audio.is_music_paused is (not on)
    for tab in MENU_PANELS:
        icon = game.panel_manager[tab]["music_toggle_icon"]
        assert icon.state == (None if on else "paused"), tab
    label = game.panel_manager["game"]["pause_music_text"].text
    assert label == ("MUSIC: ON" if on else "MUSIC: OFF")


@pytest.mark.parametrize("splash", ["played", "skipped"])
@pytest.mark.parametrize("music_on", [False, True])
def test_the_saved_music_state_survives_the_splash(make_game, splash, music_on):
    save_music_on(make_game, music_on)

    game = start(make_game, splash)

    assert_music_shows(game, on=music_on)


@pytest.mark.parametrize("splash", ["played", "skipped"])
def test_the_splash_does_not_flip_the_saved_state(make_game, splash):
    save_music_on(make_game, False)

    game = start(make_game, splash)
    game._save_settings()  # what quitting does

    assert game.settings_store.load()["music_on"] is False


@pytest.mark.parametrize("splashes", [("played", "played"), ("skipped", "played")])
@pytest.mark.parametrize("music_on", [False, True])
def test_quitting_and_restarting_twice_keeps_the_state(make_game, splashes, music_on):
    save_music_on(make_game, music_on)

    for splash in splashes:
        game = start(make_game, splash)
        assert_music_shows(game, on=music_on)
        game._save_settings()  # quit

    assert game.settings_store.load()["music_on"] is music_on


@pytest.mark.parametrize("music_on", [False, True])
def test_toggling_after_startup_keeps_icon_and_audio_in_sync(make_game, music_on):
    save_music_on(make_game, music_on)
    game = start(make_game, "played")

    game._toggle_music()
    assert_music_shows(game, on=not music_on)
    assert game.settings_store.load()["music_on"] is (not music_on)

    game._toggle_music()
    assert_music_shows(game, on=music_on)
    assert game.settings_store.load()["music_on"] is music_on
