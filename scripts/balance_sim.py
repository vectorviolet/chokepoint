"""Headless balance simulator (issue #70): plays whole runs with scripted
strategy bots and writes per-wave numbers.

    uv run python scripts/balance_sim.py                       # every strategy
    uv run python scripts/balance_sim.py --strategy gun_spam --waves 10
    uv run python scripts/balance_sim.py --watch --strategy gun_cannon

Each strategy plays a fresh run in a real Game() -- the game's own
towers, enemies, waves, money and lives -- with nothing drawn, ticking as
fast as the CPU allows at the game's top speed (x4, --game-speed) until
--waves are cleared or the run is lost. The victory popup after wave 25 is
answered with Continue, as a player would. The bots (scripts/balance_bots.py)
buy through the game's own placement rules and money.

Output, in --out (default docs/balance): one CSV per strategy (a row per
wave) and report.md (a summary table, then a table per strategy). Both are
deterministic for a given --seed and options: the game itself has no
randomness, and the seed only breaks ties between equally good build tiles.

Saves: the Game() saves into a temporary folder (saves_redirected() from
smoke_test.py, the same mechanism as the tests), and the script fails if
the real saves/ changed. A lost run deletes its save like the real game,
so this matters (see CLAUDE.md).

--watch (issue #100) plays one --strategy in a game window instead, drawn
by the game with its HUD, in real time (scripts/balance_watch.py). The run
is the same as headless, step for step, while the speed stays at
--game-speed (+/- in the window change the timing, so results can differ
from then on); it writes no CSV or report.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
from collections.abc import Iterator
from contextlib import chdir, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

# No sound. The video driver isn't set here: run() picks the dummy one for
# headless runs (nothing drawn), and --watch keeps the real one.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "pygamine"))

from balance_bots import (  # noqa: E402
    DONE,
    PLANE,
    SKIP,
    STRATEGIES,
    TOWER_NAMES,
    WAIT,
    LaunchPlane,
    Place,
    Upgrade,
    UpgradePlanes,
    longest_straight,
    plane_tile,
    rank_tiles,
)
from pygame.math import Vector2  # noqa: E402
from util.constants import HALF_TILE, TILE_SIZE  # noqa: E402

DEFAULT_WAVES = 40
DEFAULT_SEED = 70
DEFAULT_GAME_SPEED = 4  # the game's top speed (the HUD's x4)
DECISION_MS = 500  # game time between a bot's looks at its money
TYPES = (1, 2, 3, 4)
# A wave that hasn't ended after this many ticks is a stuck run (the
# longest wave of the reference run takes under 10,000 at x4).
MAX_WAVE_TICKS = 300_000


# ── the game under simulation ────────────────────────────────────────────────


def _sim_game_class():
    from app.game import Game

    class SimGame(Game):
        """The real game, counting kills and escapes per wave."""

        killed = 0
        escaped = 0

        def _on_enemy_killed(self, enemy) -> None:
            self.killed += 1
            super()._on_enemy_killed(enemy)

        def _on_enemy_escaped(self, enemy) -> None:
            self.escaped += 1
            super()._on_enemy_escaped(enemy)

        def game_tick(self) -> None:
            """The game's own tick. StrategyRun.step() calls this, so a
            watched game can route Game.update()'s ticks to step()."""
            super()._tick()

    return SimGame


class Sim:
    """A bot's hands: applies its steps to the game with the game's own
    rules. Every purchase goes through here, so spending is tracked."""

    def __init__(self, game, tiles: dict, *, keep_camera: bool = False) -> None:
        """`tiles`: rank_tiles() for this game's map and towers.
        `keep_camera`: put the camera back after each purchase."""
        self.game = game
        self.keep_camera = keep_camera
        self.gs = game.game_state
        self.tiles = tiles
        self.plane_tile = plane_tile(game.tilemap)
        self.straight_right = longest_straight(game.tilemap)[2]
        self.bought: list = []  # every tower ever bought, alive or not
        self._bought_at: dict[int, int] = {}  # id(tower) -> purchase order
        self.spent_by_type = dict.fromkeys(TYPES, 0)

    def apply(self, step) -> str:
        if isinstance(step, Place):
            return self._place(step)
        if isinstance(step, Upgrade):
            return self._upgrade(step)
        if isinstance(step, LaunchPlane):
            return self._launch_plane(step)
        if isinstance(step, UpgradePlanes):
            return self._upgrade_planes()
        raise TypeError(f"unknown step {step!r}")

    def _price(self, tower_type: int, level: int = 1) -> int:
        return self.game.tower_config.prices[tower_type - 1][level - 1]

    def _buy(self, tower_type: int, row: int, col: int) -> bool:
        """Places through the placement controller, as a click on the
        tile in placement mode would: its own placeability and money
        checks, and it takes the money."""
        controller = self.game.tower_controller
        towers = self.game.towers
        before = len(towers)
        controller.buying_tower_type = tower_type
        # A click on the tile's center, with the camera brought over it.
        camera = self.game.camera
        # center_on() moves only the offset, never the zoom.
        view = Vector2(camera._offset) if self.keep_camera else None
        center = (col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE)
        camera.center_on(center)
        controller._handle_tower_purchase(tuple(camera.world_to_screen(center)))
        controller.buying_tower_type = 0
        if view is not None:
            camera._offset.update(view)
        if len(towers) == before:
            return False
        # The controller puts a ground tower first and a plane last.
        tower = towers[-1] if tower_type == PLANE else towers[0]
        assert tower.tower_type == tower_type and (tower.row, tower.col) == (row, col)
        self._bought_at[id(tower)] = len(self.bought)
        self.bought.append(tower)
        self.spent_by_type[tower_type] += tower.buy_price
        return True

    def _place(self, step: Place) -> str:
        if self.gs.money < self._price(step.tower_type):
            return WAIT
        taken = self.game.tower_controller.tower_positions
        for ring in (step.ring, "any"):
            for row, col in self.tiles[(step.tower_type, ring)]:
                if (row, col) not in taken and self._buy(step.tower_type, row, col):
                    return DONE
        return SKIP  # no free tile anywhere

    def _upgrade(self, step: Upgrade) -> str:
        candidates = [
            t
            for t in self.game.towers
            if t.tower_type == step.tower_type
            and not t.is_max_level()
            # Destroyed this tick but not removed yet: the next tick does.
            and not t.should_remove()
        ]
        if not candidates:
            return SKIP
        # The lowest level, the first bought on a tie.
        tower = min(candidates, key=lambda t: (t.level, self._bought_at[id(t)]))
        price = tower.upgrade_price
        if self.gs.money < price:
            return WAIT
        # A click on the tower's own upgrade button.
        camera = self.game.camera
        level = tower.level
        tower.upgrade(tower._upgrade_hit_rect(camera).center, self.gs, camera)
        self.gs.selected_tower = None
        if tower.level == level:
            raise RuntimeError(f"upgrading {tower} was refused")
        self.spent_by_type[step.tower_type] += price
        return DONE

    def _launch_plane(self, step: LaunchPlane) -> str:
        if not self._enemy_ahead_on_straight():
            return WAIT if step.wait else SKIP
        if self.gs.money < self._price(PLANE):
            return WAIT
        return DONE if self._buy(PLANE, *self.plane_tile) else WAIT

    def _enemy_ahead_on_straight(self) -> bool:
        """Whether an enemy is on the plane's straight ahead of it: between
        where the plane starts and the straight's right end, within the
        bomb radius of its row, so the plane flying right can reach it."""
        from util.constants import HALF_TILE, TILE_SIZE

        row, col = self.plane_tile
        y = row * TILE_SIZE + HALF_TILE
        start_x = col * TILE_SIZE + HALF_TILE
        radius = self.game.tower_config.ranges[PLANE - 1][self.gs.plane_level - 1]
        return any(
            abs(e.position.y - y) <= radius
            and start_x <= e.position.x <= self.straight_right
            for e in self.game.enemies
        )

    def _upgrade_planes(self) -> str:
        if self.gs.plane_level != 1:
            return SKIP
        price = self._price(PLANE, 2)
        # The HUD button's own rule (GameEventsMixin._buy_plane_upgrade).
        if not self.game._buy_plane_upgrade():
            return WAIT
        self.spent_by_type[PLANE] += price
        return DONE

    # ── per-type totals ──────────────────────────────────────────────────────

    def totals(self) -> dict:
        """Cumulative damage, kill money and towers lost per type."""
        out = {
            "damage": dict.fromkeys(TYPES, 0),
            "earned": dict.fromkeys(TYPES, 0),
            "lost": 0,
        }
        for tower in self.bought:
            out["damage"][tower.tower_type] += tower.damage_dealt
            out["earned"][tower.tower_type] += tower.money_earned
            if not tower.is_flying and tower.should_remove():
                out["lost"] += 1
        return out


# ── one run ──────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    strategy: str
    rows: list[dict] = field(default_factory=list)
    died_at: int | None = None  # the wave the run was lost in
    ticks: int = 0
    seconds: float = 0.0
    tiles: dict | None = None  # the rank_tiles() it used

    @property
    def waves_cleared(self) -> int:
        return sum(1 for r in self.rows if r["cleared"])


class StrategyRun:
    """One run of a strategy, played a tick at a time by step(): the
    headless loop (run_strategy()) and a watched window (Watcher) drive the
    same steps. The caller has redirected saves and set the cwd to the repo
    root. `tiles`: rank_tiles() for `seed`, shared between runs (computed
    here if None). `keep_camera`: a purchase leaves the camera where it was
    (a watched run's view is the viewer's; headless runs leave it on the
    last tile bought, as they always have)."""

    def __init__(
        self,
        name: str,
        waves: int = DEFAULT_WAVES,
        seed: int = DEFAULT_SEED,
        game_speed: int = DEFAULT_GAME_SPEED,
        tiles: dict | None = None,
        *,
        game_class=None,
        keep_camera: bool = False,
    ) -> None:
        self.waves = waves
        self.game = game = (game_class or _sim_game_class())()
        # The run never stops between waves. (A player's setting; with saves
        # redirected, nothing here reaches their settings file.)
        game.auto_pause = False
        game._start_new_game()
        self.gs = gs = game.game_state
        gs.speed = game_speed
        if tiles is None:
            tiles = rank_tiles(game.tilemap, game.tower_config, random.Random(seed))
        self.sim = Sim(game, tiles, keep_camera=keep_camera)
        self.bot = STRATEGIES[name]()
        self.result = RunResult(name, tiles=tiles)
        self._wave_start = {
            "money": gs.money,
            "lives": gs.lives,
            "spent": 0,
            "time": 0.0,
            "tick": 0,
        }
        self._previous = self.sim.totals()
        gs.add_level_listener(lambda level: self._record(level - 1, cleared=True))

        self.bot.act(self.sim)
        game._set_started(True)
        self._next_decision = gs.time_ms + DECISION_MS

    @property
    def finished(self) -> bool:
        """--waves cleared, or the run lost."""
        return self.result.died_at is not None or self.gs.level > self.waves

    def spent(self) -> int:
        """Everything spent so far: towers, upgrades, UPG PLANES."""
        return sum(self.sim.spent_by_type.values())

    def step(self) -> None:
        """One game tick, then what the bot and the run do after it."""
        game, gs, result = self.game, self.gs, self.result
        game.game_tick()
        result.ticks += 1
        if game._victory_popup_open:  # wave 25 cleared: Continue
            game._close_victory_popup()
            game._set_started(True)
        if game._gameover_popup_open:
            result.died_at = gs.level
            self._record(gs.level, cleared=False)
            return
        if gs.time_ms >= self._next_decision:
            self.bot.act(self.sim)
            self._next_decision = gs.time_ms + DECISION_MS
        if result.ticks - self._wave_start["tick"] > MAX_WAVE_TICKS:
            state = "running" if gs.is_started else "paused"
            raise RuntimeError(
                f"{result.strategy}: wave {gs.level} hasn't ended after "
                f"{MAX_WAVE_TICKS} ticks (game {state}, {len(game.enemies)} "
                "enemies on the path)"
            )

    def _record(self, wave: int, cleared: bool) -> None:
        game, gs, sim = self.game, self.gs, self.sim
        wave_start, previous = self._wave_start, self._previous
        now = sim.totals()
        spent = self.spent() - wave_start["spent"]
        lost = wave_start["lives"] - gs.lives
        row = {
            "wave": wave,
            "cleared": cleared,
            "lives": gs.lives,
            "lives_lost": lost,
            "money": gs.money,
            "earned": gs.money - wave_start["money"] + spent,
            "spent": spent,
            "killed": game.killed,
            "escaped": game.escaped,
            # Towers destroyed this tick are still listed until the next.
            "towers": sum(
                1 for t in game.towers if not t.is_flying and not t.should_remove()
            ),
            "towers_lost": now["lost"] - previous["lost"],
            "wave_s": round((gs.time_ms - wave_start["time"]) / 1000, 1),
        }
        for t in TYPES:
            key = TOWER_NAMES[t]
            row[f"dmg_{key}"] = now["damage"][t] - previous["damage"][t]
            row[f"earned_{key}"] = now["earned"][t] - previous["earned"][t]
            row[f"spent_total_{key}"] = sim.spent_by_type[t]
            row[f"earned_total_{key}"] = now["earned"][t]
            row[f"roi_{key}"] = (
                round(now["earned"][t] / sim.spent_by_type[t], 2)
                if sim.spent_by_type[t]
                else ""
            )
        self.result.rows.append(row)
        self.bot.wave_ended(lost)
        self._previous = now
        game.killed = game.escaped = 0
        wave_start.update(
            money=gs.money,
            lives=gs.lives,
            spent=self.spent(),
            time=gs.time_ms,
            tick=self.result.ticks,
        )


def run_strategy(
    name: str,
    waves: int = DEFAULT_WAVES,
    seed: int = DEFAULT_SEED,
    game_speed: int = DEFAULT_GAME_SPEED,
    tiles: dict | None = None,
) -> RunResult:
    """Plays one run of strategy `name` headless, as fast as the CPU
    allows. The caller has redirected saves and set the cwd to the repo
    root. `tiles`: rank_tiles() for `seed`, shared between runs (computed
    here if None)."""
    started = time.perf_counter()
    run = StrategyRun(name, waves, seed, game_speed, tiles)
    while not run.finished:
        run.step()
    run.result.seconds = time.perf_counter() - started
    return run.result


# ── output ───────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "wave",
    "cleared",
    "lives",
    "lives_lost",
    "money",
    "earned",
    "spent",
    "killed",
    "escaped",
    "towers",
    "towers_lost",
    "wave_s",
    *(f"dmg_{TOWER_NAMES[t]}" for t in TYPES),
    *(f"earned_{TOWER_NAMES[t]}" for t in TYPES),
    *(f"spent_total_{TOWER_NAMES[t]}" for t in TYPES),
    *(f"earned_total_{TOWER_NAMES[t]}" for t in TYPES),
    *(f"roi_{TOWER_NAMES[t]}" for t in TYPES),
]


def write_csv(result: RunResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result.rows)


def _md_table(header: list[str], rows: list[list], left: int = 0) -> list[str]:
    """A Markdown table; its first `left` columns aligned left."""
    lines = ["| " + " | ".join(header) + " |"]
    lines.append(
        "|" + "|".join("---" if i < left else "---:" for i in range(len(header))) + "|"
    )
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines


def _reached(result: RunResult, waves: int) -> str:
    if result.died_at is not None:
        return f"died in wave {result.died_at}"
    return f"cleared {result.waves_cleared} of {waves}"


def summary_rows(results: list[RunResult], waves: int) -> list[list]:
    rows = []
    for r in results:
        last = r.rows[-1] if r.rows else {}
        rows.append(
            [
                r.strategy,
                _reached(r, waves),
                last.get("lives", ""),
                sum(row["lives_lost"] for row in r.rows if row["wave"] <= 10),
                sum(row["lives_lost"] for row in r.rows if 10 < row["wave"] <= 25),
                sum(row["lives_lost"] for row in r.rows if row["wave"] > 25),
                sum(row["spent"] for row in r.rows),
                sum(row["earned"] for row in r.rows),
                last.get("money", ""),
                sum(row["towers_lost"] for row in r.rows),
                *(last.get(f"roi_{TOWER_NAMES[t]}", "") for t in TYPES),
            ]
        )
    return rows


SUMMARY_HEADER = [
    "strategy",
    "result",
    "lives left",
    "lives lost 1-10",
    "lost 11-25",
    "lost 26+",
    "spent",
    "earned",
    "money left",
    "towers lost",
    "ROI gun",
    "ROI missile",
    "ROI cannon",
    "ROI plane",
]

WAVE_HEADER = [
    "wave",
    "lives",
    "lost",
    "money",
    "earned",
    "spent",
    "killed",
    "escaped",
    "towers",
    "towers lost",
    "dmg gun",
    "dmg missile",
    "dmg cannon",
    "dmg plane",
    "ROI gun",
    "ROI missile",
    "ROI cannon",
    "ROI plane",
]


def wave_rows(result: RunResult) -> list[list]:
    keys = [
        "wave",
        "lives",
        "lives_lost",
        "money",
        "earned",
        "spent",
        "killed",
        "escaped",
        "towers",
        "towers_lost",
        *(f"dmg_{TOWER_NAMES[t]}" for t in TYPES),
        *(f"roi_{TOWER_NAMES[t]}" for t in TYPES),
    ]
    return [[row[k] if row[k] != "" else "-" for k in keys] for row in result.rows]


def write_report(
    results: list[RunResult], path: Path, *, waves: int, seed: int, game_speed: int
) -> None:
    from balance_bots import STRATEGIES

    lines = [
        "# Balance simulation",
        "",
        "Generated by `scripts/balance_sim.py` (see docs/BALANCE.md); "
        f"--waves {waves}, --seed {seed}, --game-speed {game_speed}.",
        "ROI is a tower type's kill money so far divided by everything spent "
        "on it so far (purchases and upgrades; UPG PLANES counts for planes).",
        "Damage is enemy HP taken in that wave, overkill not counted.",
        "",
        "## Summary",
        "",
        *_md_table(SUMMARY_HEADER, summary_rows(results, waves), left=2),
    ]
    for r in results:
        lines += [
            "",
            f"## {r.strategy}",
            "",
            STRATEGIES[r.strategy].description[0].upper()
            + STRATEGIES[r.strategy].description[1:]
            + ". "
            + _reached(r, waves).capitalize()
            + ".",
            "",
            *_md_table(WAVE_HEADER, wave_rows(r)),
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── entry point ──────────────────────────────────────────────────────────────


def run(
    strategies: list[str],
    *,
    waves: int = DEFAULT_WAVES,
    seed: int = DEFAULT_SEED,
    game_speed: int = DEFAULT_GAME_SPEED,
    out: Path | None = None,
    report=print,
) -> list[RunResult]:
    """Runs `strategies` in order, headless, writing their output into
    `out` (if given). Saves are redirected; fails if the real saves/
    changed."""
    # Nothing is drawn. (A test's conftest, or the caller, may have chosen
    # the driver already.)
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    results = []
    with _saves_guarded():
        tiles = None  # the same for every strategy: same map and seed
        for name in strategies:
            result = run_strategy(name, waves, seed, game_speed, tiles)
            tiles = result.tiles
            results.append(result)
            report(
                f"{name}: {_reached(result, waves)}, "
                f"{result.ticks} ticks in {result.seconds:.1f} s"
            )
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for result in results:
            write_csv(result, out / f"{result.strategy}.csv")
        write_report(
            results, out / "report.md", waves=waves, seed=seed, game_speed=game_speed
        )
    return results


@contextmanager
def _saves_guarded() -> Iterator[None]:
    """Runs in the repo root with saves redirected to a temporary folder;
    fails if the real saves/ changed all the same. (Not make_playtest_save's
    _cwd(): importing that script picks the dummy video driver, which
    would keep a --watch window from opening.)"""
    from smoke_test import REAL_SAVES, saves_redirected, snapshot

    with chdir(ROOT):
        real_saves = ROOT / REAL_SAVES
        before = snapshot(real_saves)
        with saves_redirected():
            yield
        if snapshot(real_saves) != before:
            raise SystemExit(f"balance_sim FAILED: it changed {real_saves}")


def watch(
    name: str,
    *,
    waves: int = DEFAULT_WAVES,
    seed: int = DEFAULT_SEED,
    game_speed: int = DEFAULT_GAME_SPEED,
    frames: int | None = None,
) -> StrategyRun:
    """Plays strategy `name` in a game window (scripts/balance_watch.py)
    until Esc or the window is closed, or `frames` frames are drawn (for
    tests). View-only: nothing is written, and saves are redirected as for
    run()."""
    from balance_watch import Watcher, watched_game_class

    with _saves_guarded():
        run = StrategyRun(
            name,
            waves,
            seed,
            game_speed,
            game_class=watched_game_class(_sim_game_class()),
            keep_camera=True,
        )
        Watcher(run, lambda: watch_summary(run)).loop(frames)
    return run


def watch_summary(run: StrategyRun) -> list[str]:
    """The lines a watched window shows once its run has ended."""
    result = run.result
    return [
        f"{result.strategy}: {_reached(result, run.waves)}",
        f"Waves cleared: {result.waves_cleared}",
        f"Lives: {run.gs.lives}",
        f"Money spent: {run.spent():,}",
        "Esc to close",
    ]


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--strategy",
        choices=sorted(STRATEGIES),
        help="run only this strategy (default: all)",
    )
    parser.add_argument("--waves", type=int, default=DEFAULT_WAVES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--game-speed",
        type=int,
        choices=(1, 2, 4),
        default=DEFAULT_GAME_SPEED,
        help="the in-game speed setting (default: x4, the top speed)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "balance",
        help="folder for the CSVs and report.md (default: docs/balance)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="play one --strategy in a game window, in real time, writing "
        "nothing (Space pause, +/- speed, F fast-forward, Esc quit)",
    )
    args = parser.parse_args(argv)
    if args.waves < 1:
        parser.error("--waves must be 1 or more")
    if args.watch and args.strategy is None:
        parser.error("--watch needs exactly one --strategy")
    return args


def main(argv=None, *, frames: int | None = None) -> None:
    """`frames`: a watched run stops after this many frames (for tests)."""
    args = parse_args(argv)
    if args.watch:
        watched = watch(
            args.strategy,
            waves=args.waves,
            seed=args.seed,
            game_speed=args.game_speed,
            frames=frames,
        )
        state = _reached(watched.result, args.waves) if watched.finished else "stopped"
        print(f"{args.strategy}: {state} (watched; nothing written)")
        return
    strategies = [args.strategy] if args.strategy else list(STRATEGIES)
    started = time.perf_counter()
    run(
        strategies,
        waves=args.waves,
        seed=args.seed,
        game_speed=args.game_speed,
        out=args.out,
    )
    print(f"total {time.perf_counter() - started:.1f} s; wrote {args.out}")


if __name__ == "__main__":
    main()
