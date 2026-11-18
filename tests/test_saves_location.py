"""Where saves live: the user-data folder in the packaged build, the cwd-relative `saves/`
from source and in the browser (ADR 0011)."""

import sys
from pathlib import Path

import pygame
import pytest

from app.game import Game
from pygamine import SaveStore, user_data_dir


@pytest.fixture
def quiet_game(monkeypatch, fake_ticks):
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))


def test_frozen_game_stores_in_the_user_data_folder(monkeypatch, tmp_path, quiet_game):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setattr(sys, "_MEIPASS", str(Path.cwd()), raising=False)
    game = Game()
    expected = user_data_dir("chokepoint") / "saves"
    assert expected.parts[-3:] == ("VectorViolet", "chokepoint", "saves")
    assert game.settings_store.directory == expected
    assert game.save_store.directory == expected
    assert tmp_path in expected.parents  # never the real user folder in tests
    game._save_settings()
    assert (expected / "settings.json").exists()


def test_source_game_keeps_the_default_folder(monkeypatch, tmp_path, quiet_game):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    game = Game()  # conftest's saves_in_tmp moved SaveStore's default into tmp_path
    assert game.settings_store.directory == tmp_path / "saves"
    assert game.save_store.directory == tmp_path / "saves"


def test_web_keeps_its_local_storage_keys(monkeypatch, tmp_path, quiet_game, browser):
    """Browser saves must not move: the key is `pygamine:saves/<name>.json`."""
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    # The key needs the real relative default "saves". Save from tmp_path (after Game()
    # has loaded its assets from the repo), so that even if a write ever missed
    # localStorage it would land in tmp_path, never the repo's saves/.
    monkeypatch.setattr(SaveStore.__init__, "__defaults__", ("saves",))
    game = Game()
    monkeypatch.chdir(tmp_path)
    game._save_settings()
    assert "pygamine:saves/settings.json" in browser.localStorage.items
