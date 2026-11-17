"""Where saves live: the user-data folder in the packaged build, the cwd-relative `saves/`
from source and in the browser (ADR 0011)."""

import platform
import sys

import pygame
import pytest

from app.game import Game
from pygamine import SaveStore, user_data_dir
from util.paths import packaged_saves_dir

from test_web import FakeWindow


def test_from_source_there_is_no_packaged_folder(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert packaged_saves_dir() is None


def test_frozen_saves_go_to_the_user_data_folder(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert packaged_saves_dir() == user_data_dir("chokepoint") / "saves"
    assert packaged_saves_dir().parts[-3:] == ("VectorViolet", "chokepoint", "saves")


@pytest.fixture
def quiet_game(monkeypatch, fake_ticks):
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))


def test_frozen_game_stores_in_the_user_data_folder(monkeypatch, tmp_path, quiet_game):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    game = Game()
    expected = packaged_saves_dir()
    assert expected is not None
    assert game.settings_store.directory == expected
    assert game.save_store.directory == expected
    assert tmp_path in expected.parents  # never the real user folder in tests
    game._save_settings()
    assert (expected / "settings.json").exists()


def test_source_game_keeps_the_default_folder(monkeypatch, tmp_path, quiet_game):
    monkeypatch.delattr(sys, "frozen", raising=False)
    game = Game()  # conftest's saves_in_tmp moved SaveStore's default into tmp_path
    assert game.settings_store.directory == tmp_path / "saves"
    assert game.save_store.directory == tmp_path / "saves"


def test_web_keeps_its_local_storage_keys(monkeypatch, quiet_game):
    """Browser saves must not move: the key is `pygamine:saves/<name>.json`."""
    window = FakeWindow()
    monkeypatch.setattr(platform, "window", window, raising=False)
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(
        SaveStore.__init__, "__defaults__", ("saves",)
    )  # undo saves_in_tmp
    game = Game()
    game._save_settings()
    assert "pygamine:saves/settings.json" in window.localStorage.items
