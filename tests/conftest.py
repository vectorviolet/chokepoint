"""Shared pytest setup and fixtures for chokepoint's app-level test suite.

Run from the repo root (`uv run pytest`, matching how __main__.py assumes
cwd == repo root for its own "config/..."-relative paths).
"""

import os

# Dummy SDL drivers so pygame can run headless (e.g. in CI) without opening a
# real window or probing for a sound device. Must be set before pygame is
# imported anywhere.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from pygamine import AssetManager, SaveStore
from util.config_loader import load_tower_config

pygame.init()
# RotatableObject/StateObject load images via convert_alpha(), which raises
# without a display surface. Application.__init__ normally provides one via
# set_resolution(); these tests construct game objects directly, with no
# Application/Game involved, so they need their own.
pygame.display.set_mode((1, 1))


@pytest.fixture(scope="session")
def assets() -> AssetManager:
    manager = AssetManager()
    manager.load_manifest("config/assets.yaml")
    missing = manager.validate()
    assert not missing, f"Missing assets: {missing}"
    return manager


@pytest.fixture(scope="session")
def tower_config():
    return load_tower_config()


class FakeContext:
    """Minimal stand-in for domain.protocols.IGameContext -- its docstring
    explicitly calls out lightweight test stubs as a valid implementer."""

    def __init__(self, *, map_width=3008, map_height=2176, speed=1):
        self.enemies = []
        self.towers = []
        self.speed = speed
        self.time_ms = 0.0
        self.map_width = map_width
        self.map_height = map_height
        self.money_earned = 0
        self.killed = []
        self.bombs_landed = []

    def increase_money(self, amount: int) -> None:
        self.money_earned += amount

    def enemy_killed(self, enemy) -> None:
        self.killed.append(enemy)
        self.increase_money(enemy.killMoney)

    def bomb_landed(self, position, radius: float) -> None:
        self.bombs_landed.append((position, radius))


@pytest.fixture(autouse=True)
def saves_in_tmp(tmp_path, monkeypatch):
    """Every test's SaveStore defaults to a temporary folder, never the
    repo's real saves/ -- a Game() under test saves and deletes its save
    like the real one does (a lost run deletes saves/save.json)."""
    monkeypatch.setattr(SaveStore.__init__, "__defaults__", (str(tmp_path / "saves"),))


@pytest.fixture
def ctx() -> FakeContext:
    return FakeContext()


@pytest.fixture
def fake_ticks(monkeypatch):
    """A controllable stand-in for pygame.time.get_ticks() -- the wall
    clock Game.update() measures frame time with. Gameplay timers run on
    game time instead (GameState.time_ms / a context's time_ms), which
    tests set directly.

    Set fake_ticks["t"] = <ms> to move the clock without real sleeps.
    """
    state = {"t": 0}
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: state["t"])
    return state
