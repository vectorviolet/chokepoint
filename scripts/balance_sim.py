"""Headless balance simulator (issue #70): plays whole runs with scripted
strategy bots and writes per-wave numbers.

    uv run python scripts/balance_sim.py                       # every strategy
    uv run python scripts/balance_sim.py --strategy gun_spam --waves 10

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
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
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
    plane_tile,
    rank_tiles,
)

DEFAULT_WAVES = 40
DEFAULT_SEED = 70
DEFAULT_GAME_SPEED = 4  # the game's top speed (the HUD's x4)
DECISION_MS = 500  # game time between a bot's looks at its money
TYPES = (1, 2, 3, 4)
# A wave that hasn't ended after this much game time is a stuck run.
MAX_WAVE_MS = 30 * 60 * 1000


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

    return SimGame


class Sim:
    """A bot's hands: applies its steps to the game with the game's own
    rules. Every purchase goes through here, so spending is tracked."""

    def __init__(self, game, rng: random.Random) -> None:
        self.game = game
        self.gs = game.game_state
        self.tiles = rank_tiles(game.tilemap, game.tower_config, rng)
        self.plane_tile = plane_tile(game.tilemap)
        self.bought: list = []  # every tower ever bought, alive or not
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
        before = len(self.game.towers)
        controller.buying_tower_type = tower_type
        controller.cursor_row, controller.cursor_col = row, col
        controller._handle_tower_purchase(self.game.game_area.center)
        controller.buying_tower_type = 0
        if len(self.game.towers) == before:
            return False
        tower = next(
            t
            for t in self.game.towers
            if t.tower_type == tower_type
            and (t.row, t.col) == (row, col)
            and t not in self.bought
        )
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
            if t.tower_type == step.tower_type and not t.is_max_level()
        ]
        if not candidates:
            return SKIP
        tower = min(candidates, key=lambda t: t.level)  # oldest on a tie
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
        if not self._enemies_on_plane_row():
            return WAIT if step.wait else SKIP
        if self.gs.money < self._price(PLANE):
            return WAIT
        return DONE if self._buy(PLANE, *self.plane_tile) else WAIT

    def _enemies_on_plane_row(self) -> bool:
        from util.constants import HALF_TILE, TILE_SIZE

        y = self.plane_tile[0] * TILE_SIZE + HALF_TILE
        radius = self.game.tower_config.ranges[PLANE - 1][self.gs.plane_level - 1]
        return any(abs(e.position.y - y) <= radius for e in self.game.enemies)

    def _upgrade_planes(self) -> str:
        if self.gs.plane_level != 1:
            return SKIP
        price = self._price(PLANE, 2)
        if self.gs.money < price:
            return WAIT
        # What the HUD's UPG PLANES button does (GameEventsMixin
        # ._handle_upgrade_plane_button) once its click is accepted.
        self.gs.plane_level = 2
        self.gs.decrease_money(price)
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
            if tower.hp is not None and tower.hp <= 0:
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

    @property
    def waves_cleared(self) -> int:
        return sum(1 for r in self.rows if r["cleared"])


def run_strategy(
    name: str,
    waves: int = DEFAULT_WAVES,
    seed: int = DEFAULT_SEED,
    game_speed: int = DEFAULT_GAME_SPEED,
) -> RunResult:
    """Plays one run of strategy `name`. The caller has redirected saves
    and set the cwd to the repo root."""
    started = time.perf_counter()
    game = _sim_game_class()()
    game._start_new_game()
    gs = game.game_state
    gs.speed = game_speed
    sim = Sim(game, random.Random(seed))
    bot = STRATEGIES[name]()
    result = RunResult(name)

    wave_start = {"money": gs.money, "lives": gs.lives, "spent": 0, "time": 0.0}
    previous = sim.totals()

    def spent_total() -> int:
        return sum(sim.spent_by_type.values())

    def record(wave: int, cleared: bool) -> None:
        nonlocal previous
        now = sim.totals()
        spent = spent_total() - wave_start["spent"]
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
            "towers": sum(1 for t in game.towers if not t.is_flying),
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
        result.rows.append(row)
        bot.wave_ended(lost)
        previous = now
        game.killed = game.escaped = 0
        wave_start.update(
            money=gs.money, lives=gs.lives, spent=spent_total(), time=gs.time_ms
        )

    gs.add_level_listener(lambda level: record(level - 1, cleared=True))

    bot.act(sim)
    game._set_started(True)
    next_decision = gs.time_ms + DECISION_MS
    while gs.level <= waves:
        game._tick()
        result.ticks += 1
        if game._victory_popup_open:  # wave 25 cleared: Continue
            game._close_victory_popup()
            game._set_started(True)
        if game._gameover_popup_open:
            result.died_at = gs.level
            record(gs.level, cleared=False)
            break
        if gs.time_ms >= next_decision:
            bot.act(sim)
            next_decision = gs.time_ms + DECISION_MS
        if gs.time_ms - wave_start["time"] > MAX_WAVE_MS:
            raise RuntimeError(f"{name}: wave {gs.level} never ended")
    result.seconds = time.perf_counter() - started
    return result


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
    """Runs `strategies` in order, writing their output into `out` (if
    given). Saves are redirected; fails if the real saves/ changed."""
    from make_playtest_save import _cwd
    from smoke_test import REAL_SAVES, saves_redirected, snapshot

    results = []
    with _cwd(ROOT):
        real_saves = ROOT / REAL_SAVES
        before = snapshot(real_saves)
        with saves_redirected():
            for name in strategies:
                result = run_strategy(name, waves, seed, game_speed)
                results.append(result)
                report(
                    f"{name}: {_reached(result, waves)}, "
                    f"{result.ticks} ticks in {result.seconds:.1f} s"
                )
        if snapshot(real_saves) != before:
            raise SystemExit(f"balance_sim FAILED: it changed {real_saves}")
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for result in results:
            write_csv(result, out / f"{result.strategy}.csv")
        write_report(
            results, out / "report.md", waves=waves, seed=seed, game_speed=game_speed
        )
    return results


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
    args = parser.parse_args(argv)
    if args.waves < 1:
        parser.error("--waves must be 1 or more")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
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
