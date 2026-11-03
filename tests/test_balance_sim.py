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


def _new_sim(sim):
    import random

    from app.game import Game

    bots = sys.modules["balance_bots"]
    game = Game()
    game._start_new_game()
    tiles = bots.rank_tiles(game.tilemap, game.tower_config, random.Random(0))
    return game, sim.Sim(game, tiles)


def test_bot_waits_for_money_and_uses_the_placement_rules(sim):
    bots = sys.modules["balance_bots"]
    game, s = _new_sim(sim)
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


def test_upgrade_picks_the_first_bought_standing_tower(sim):
    bots = sys.modules["balance_bots"]
    game, s = _new_sim(sim)
    game.game_state.money = 10_000
    for _ in range(3):
        assert s.apply(bots.Place(bots.MISSILE)) == bots.DONE
    first, second, third = s.bought
    assert game.towers[0] is third  # the controller lists them newest first
    # The first one bought was destroyed this tick (not removed yet).
    first.hp = 0
    assert s.apply(bots.Upgrade(bots.MISSILE)) == bots.DONE
    assert (first.level, first.hp, second.level, third.level) == (1, 0, 2, 1)
    assert s.apply(bots.Upgrade(bots.MISSILE)) == bots.DONE
    assert third.level == 2  # the lowest level goes first
    # All destroyed: nothing left to upgrade.
    first.hp, second.hp, third.hp = 0, 0, 0
    assert s.apply(bots.Upgrade(bots.MISSILE)) == bots.SKIP
    assert s.totals()["lost"] == 3


def test_plane_launches_only_for_an_enemy_ahead_on_the_straight(sim):
    from pygame.math import Vector2

    from gameplay.combat.enemy import Enemy
    from util.constants import HALF_TILE, TILE_SIZE

    bots = sys.modules["balance_bots"]
    game, s = _new_sim(sim)
    game.game_state.money = 10_000
    row, col = s.plane_tile
    y = row * TILE_SIZE + HALF_TILE
    start_x = col * TILE_SIZE + HALF_TILE
    enemy = Enemy(1, 1, 1, game.tilemap.waypoints, game.assets)
    game.enemies.append(enemy)
    for x in (start_x - 40, s.straight_right + 40):  # behind it, past the end
        enemy.position = Vector2(x, y)
        assert s.apply(bots.LaunchPlane()) == bots.WAIT
        assert s.apply(bots.LaunchPlane(wait=False)) == bots.SKIP
    enemy.position = Vector2(start_x + 200, y)
    assert s.apply(bots.LaunchPlane()) == bots.DONE
    assert game.towers[-1] is s.bought[-1]
    assert game.towers[-1].tower_type == bots.PLANE


def test_plane_upgrade_goes_through_the_games_rule(sim, monkeypatch):
    bots = sys.modules["balance_bots"]
    game, s = _new_sim(sim)
    calls = []
    real = game._buy_plane_upgrade
    monkeypatch.setattr(game, "_buy_plane_upgrade", lambda: calls.append(1) or real())
    game.game_state.money = 4_999
    assert s.apply(bots.UpgradePlanes()) == bots.WAIT
    game.game_state.money = 5_000
    assert s.apply(bots.UpgradePlanes()) == bots.DONE
    assert (game.game_state.plane_level, game.game_state.money) == (2, 0)
    assert s.spent_by_type[bots.PLANE] == 5_000
    assert s.apply(bots.UpgradePlanes()) == bots.SKIP
    assert len(calls) == 2


def test_a_stuck_wave_raises_instead_of_spinning(sim, monkeypatch):
    import pytest

    from app.game import Game

    monkeypatch.setattr(sim, "MAX_WAVE_TICKS", 50)
    # A game that never starts: its clock stands still, like a pause the
    # simulator doesn't undo.
    monkeypatch.setattr(Game, "_set_started", lambda self, started: None)
    with pytest.raises(RuntimeError, match="hasn't ended after 50 ticks"):
        sim.run_strategy("gun_spam", waves=1)


# ── --watch (#100) ────────────────────────────────────────────────────────────


def test_watch_needs_exactly_one_strategy(sim, capsys):
    with pytest.raises(SystemExit):
        sim.parse_args(["--watch"])
    assert "--watch needs exactly one --strategy" in capsys.readouterr().err
    assert sim.parse_args(["--watch", "--strategy", "minimal"]).watch


def test_watched_run_draws_writes_nothing_and_leaves_saves_alone(
    sim, tmp_path, monkeypatch, capsys
):
    from app.game import Game
    from smoke_test import snapshot  # scripts/ is on sys.path via balance_sim

    real_saves = sim.ROOT / "saves"
    before = snapshot(real_saves)
    drawn = []
    real_draw = Game.draw
    monkeypatch.setattr(Game, "draw", lambda self: drawn.append(1) or real_draw(self))
    out = tmp_path / "out"
    sim.main(["--watch", "--strategy", "gun_spam", "--out", str(out)], frames=5)
    assert len(drawn) == 5
    assert not out.exists()
    assert snapshot(real_saves) == before
    assert "gun_spam: stopped (watched; nothing written)" in capsys.readouterr().out


def _watcher(sim, monkeypatch, waves=1):
    import pygame

    watch = _load("balance_watch")
    run = sim.StrategyRun(
        "gun_spam",
        waves,
        game_class=watch.watched_game_class(sim._sim_game_class()),
        keep_camera=True,
    )
    watcher = watch.Watcher(run, lambda: sim.watch_summary(run))
    # The mouse rests mid-window: no edge scrolling.
    center = watcher.game._canvas.get_rect().center
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: center)
    return watcher, pygame


def _key(pygame, key, text=""):
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=text)


def test_watch_keys_pause_change_speed_and_quit(sim, monkeypatch):
    watcher, pygame = _watcher(sim, monkeypatch)
    gs = watcher.game.game_state
    assert gs.speed == 4  # the bot's default speed
    watcher.handle_event(_key(pygame, pygame.K_MINUS, "-"))
    watcher.handle_event(_key(pygame, pygame.K_MINUS, "-"))
    watcher.handle_event(_key(pygame, pygame.K_MINUS, "-"))
    assert gs.speed == 1  # stops at x1
    watcher.handle_event(_key(pygame, pygame.K_EQUALS, "+"))
    assert gs.speed == 2
    # Paused: the game's ticks are dropped, fast-forward too.
    watcher.handle_event(_key(pygame, pygame.K_SPACE, " "))
    watcher.handle_event(_key(pygame, pygame.K_f, "f"))
    ticks = watcher.run.result.ticks
    for _ in range(3):
        watcher.frame()
    assert watcher.run.result.ticks == ticks
    watcher.handle_event(_key(pygame, pygame.K_SPACE, " "))
    watcher.frame()
    assert watcher.run.result.ticks > ticks  # fast-forward ticks on
    watcher.handle_event(_key(pygame, pygame.K_ESCAPE))
    assert not watcher.running


def test_watched_run_matches_headless_and_shows_its_summary(sim, monkeypatch):
    watcher, pygame = _watcher(sim, monkeypatch)
    camera = watcher.game.camera
    view = (pygame.Vector2(camera._offset), camera.scale)
    summaries = []
    monkeypatch.setattr(watcher, "_draw_summary", lambda canvas: summaries.append(1))
    watcher.handle_event(_key(pygame, pygame.K_f, "f"))
    for _ in range(2_000):
        watcher.frame()
        if watcher.run.finished:
            break
    assert watcher.run.finished
    # The bot bought towers, but the camera stayed where the viewer left it.
    assert watcher.run.sim.bought
    assert (pygame.Vector2(camera._offset), camera.scale) == view
    watcher.frame()
    assert summaries
    headless = sim.run_strategy("gun_spam", waves=1)
    assert watcher.run.result.rows == headless.rows
    assert watcher.run.result.ticks == headless.ticks
    lines = sim.watch_summary(watcher.run)
    assert lines[0] == "gun_spam: cleared 1 of 1"
    assert "Waves cleared: 1" in lines
