"""scripts/balance_sim.py (#70): a tiny run plays through, its output is
the same for the same seed, and the bots buy through the game's rules."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sim():
    return _load("balance_sim")


def _quiet(*args):
    pass


def test_tiny_run_is_deterministic_and_writes_its_tables(sim, tmp_path):
    outputs = []
    for run in ("a", "b"):
        out = tmp_path / run
        (result,) = sim.run(["gun_cannon"], waves=3, seed=5, out=out, report=_quiet)
        outputs.append({p.name: p.read_bytes() for p in sorted(out.iterdir())})
    assert outputs[0] == outputs[1]
    assert sorted(outputs[0]) == ["gun_cannon.csv", "report.md"]

    assert [row["wave"] for row in result.rows] == [1, 2, 3]
    assert result.died_at is None
    first = result.rows[0]
    # The opener's two guns came out of the starting 200 money.
    assert first["spent"] == 200
    assert first["killed"] + first["escaped"] == 6  # wave 1: six grunts
    assert first["dmg_gun"] > 0 and first["dmg_cannon"] == 0
    assert "| gun_cannon | cleared 3 of 3 |" in outputs[0]["report.md"].decode()


def test_money_spent_and_earned_add_up(sim):
    (result,) = sim.run(["missile"], waves=2, seed=1, report=_quiet)
    money = 200  # config/settings.yaml starting_money
    for row in result.rows:
        money += row["earned"] - row["spent"]
        assert row["money"] == money
        # All income is kill money, credited to the tower that killed.
        assert row["earned"] == sum(
            row[f"earned_{name}"] for name in ("gun", "missile", "cannon", "plane")
        )


def test_bot_waits_for_money_and_uses_the_placement_rules(sim):
    from app.game import Game

    import random

    bots = sys.modules["balance_bots"]
    game = Game()
    game._start_new_game()
    s = sim.Sim(game, random.Random(0))
    game.game_state.money = 150
    assert s.apply(bots.Place(bots.GUN)) == bots.DONE
    assert s.apply(bots.Place(bots.GUN)) == bots.WAIT  # 50 left: saves up
    assert game.game_state.money == 50
    (tower,) = game.towers
    assert game.tilemap.buildable_grid[tower.row][tower.col]
    # Its tile is taken now: the next gun goes elsewhere.
    game.game_state.money = 100
    assert s.apply(bots.Place(bots.GUN)) == bots.DONE
    assert len({(t.row, t.col) for t in game.towers}) == 2
    assert s.apply(bots.Upgrade(bots.GUN)) == bots.SKIP  # guns have one level


def test_planes_start_at_the_left_end_of_the_longest_straight(sim):
    from types import SimpleNamespace

    from pygame.math import Vector2

    bots = sys.modules["balance_bots"]
    # Two segments at y=576 form one straight 1216 px long (x 1408..2624),
    # longer than the single 1100 px one at y=900.
    path = [(2624, 0), (2624, 576), (2048, 576), (1408, 576), (1408, 900)]
    path += [(2508, 900)]
    tilemap = SimpleNamespace(waypoints=[Vector2(p) for p in path])
    assert bots.plane_tile(tilemap) == (576 // 64, 1408 // 64)


class _FakeSim:
    """Records the steps a bot plays; money decides DONE or WAIT."""

    def __init__(self, level, money):
        self.gs = type("GS", (), {"level": level, "lives": 10})()
        self.money = money
        self.played = []

    def apply(self, step):
        bots = sys.modules["balance_bots"]
        if self.money <= 0:
            return bots.WAIT
        self.money -= 1
        self.played.append(step)
        return bots.DONE


def test_bot_plays_its_opener_then_switches_cycle_at_the_phase_wave(sim):
    bots = sys.modules["balance_bots"]
    bot = bots.PlaneSpam()
    early = _FakeSim(level=5, money=len(bots.GUN_OPENER) + 3)
    bot.act(early)
    assert early.played == [*bots.GUN_OPENER, *bots.GUN_CANNON_CYCLE[:3]]
    late = _FakeSim(level=bots.PLANES_FROM_WAVE, money=6)
    bot.act(late)
    # The plane phase starts from its own first step.
    assert late.played == [bots.LaunchPlane()] * 5 + [bots.UpgradePlanes()]
