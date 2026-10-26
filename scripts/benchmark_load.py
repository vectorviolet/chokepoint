"""Load benchmark (issue #12): frame times with hundreds of enemies and towers.

Builds a real Game(), switches to the game panel, fills the map with a fixed
number of enemies and towers, then times the simulation tick (`_tick()`) and
the full frame draw (`draw()`) separately, frame by frame. Prints one table
row per scenario. Run headless from the repo root:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python scripts/benchmark_load.py

Options (see --help): --loads 30x20,100x50,300x150,600x300 (enemies x towers),
--speeds 1,4, --zooms 1,fit, --frames, --warmup, --seed, --profile.

How a scenario is held steady:
- Waves are off; enemies are placed at seeded random points along the path
  (types 1-6, at wave LEVEL), with HP multiplied by HP_SCALE so most survive
  the measured frames. Killed or escaped enemies are replaced between frames,
  outside the timed sections, so the count stays at the target. Lives are
  effectively infinite.
- Towers are a round-robin mix of all four types at their max level: ground
  towers (1-3) on the buildable tiles nearest the path, planes (4) flying
  across at seeded random rows. Destroyed towers and planes that left the map
  are replaced between frames too.

What one "frame" here is: one `_tick()` plus one `draw()`, i.e. the game at
its 165 FPS cap (TICKS_PER_SECOND = 165 = window fps, so one tick per frame).
Game speed x4 does NOT run more ticks: each tick advances game time by
TICK_MS * speed and moves things speed times further, so x4 mostly means more
shots and kills per tick. At a lower display rate f, a frame runs 165/f
ticks; the highest frame rate the game can sustain while the simulation keeps
real time is therefore

    fps_max = (1000 - 165 * tick_ms) / draw_ms     (capped at 165)

and the simulation alone needs 165 * tick_ms < 1000 (the "sim load" column);
past that the game falls into slow motion whatever the frame rate.

Headless (dummy SDL video driver) draws into a software surface and never
presents it, so draw times understate a real display's cost.

Safe to run locally: every Game() saves into a temporary folder
(smoke_test.saves_redirected()), and the script fails if the real saves/
changed by a single byte.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import os
import platform
import pstats
import random
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "src")
sys.path.insert(0, "src/pygamine")

from smoke_test import REAL_SAVES, saves_redirected, snapshot  # noqa: E402

LEVEL = 15  # enemy stats scale with the wave level
HP_SCALE = 5  # enemies this many times tougher, so the count stays steady
ENEMY_TYPE_WEIGHTS = {1: 4, 2: 3, 3: 2, 4: 2, 5: 1, 6: 1}
TOWER_TYPES = (1, 2, 3, 4)
GROUND_TYPES = (1, 2, 3)
PLANE_TYPE = 4
TICKS_PER_SECOND = 165  # util.constants; re-read in main() and checked


def parse_loads(text: str) -> list[tuple[int, int]]:
    loads = []
    for item in text.split(","):
        enemies, towers = item.lower().split("x")
        loads.append((int(enemies), int(towers)))
    return loads


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values),
        "p95": percentile(values, 95),
        "max": max(values),
    }


def fps_max(tick_ms: float, draw_ms: float) -> float:
    """Highest frame rate at which the simulation still keeps real time."""
    budget = 1000 - TICKS_PER_SECOND * tick_ms
    if budget <= 0:
        return 0.0
    return min(float(TICKS_PER_SECOND), budget / draw_ms)


class LoadScenario:
    """A Game filled with `enemy_count` enemies and `tower_count` towers,
    topped back up between frames."""

    def __init__(self, game, enemy_count: int, tower_count: int, seed: int) -> None:
        from pygame.math import Vector2

        from gameplay.menu_demo import _distance_to_path
        from util.constants import HALF_TILE, TILE_SIZE

        self.game = game
        self.rng = random.Random(seed)
        self.enemy_count = enemy_count
        self.towers_lost = 0
        self._next_id = 1_000_000

        path = game.tilemap.waypoints
        self._segments = [(a, b, a.distance_to(b)) for a, b in zip(path, path[1:])]
        self._path_length = sum(length for *_, length in self._segments)

        tiles = []
        for row, cells in enumerate(game.tilemap.buildable_grid):
            for col, buildable in enumerate(cells):
                if buildable:
                    centre = Vector2(
                        col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE
                    )
                    tiles.append((_distance_to_path(centre, path), row, col))
        tiles.sort()

        types = [TOWER_TYPES[i % len(TOWER_TYPES)] for i in range(tower_count)]
        ground = [t for t in types if t in GROUND_TYPES]
        if len(ground) > len(tiles):
            raise SystemExit(f"{len(ground)} ground towers, {len(tiles)} build tiles")
        self._ground_slots = [
            (tower_type, row, col) for tower_type, (_, row, col) in zip(ground, tiles)
        ]
        self._plane_count = len(types) - len(ground)
        self._rows = len(game.tilemap.buildable_grid)

        game.towers.clear()
        game.enemies.clear()
        self._ground: dict[tuple[int, int], object] = {}
        self._planes: list = []
        self.top_up(initial=True)

    # ── building ──────────────────────────────────────────────────────────────

    def _tower(self, tower_type: int, row: int, col: int):
        from gameplay.towers import TowerFactory

        game = self.game
        tower = TowerFactory.create(
            tower_type,
            row,
            col,
            game.tower_config,
            game.assets,
            game.audio,
            game.tilemap.map_width,
        )
        if tower_type in GROUND_TYPES and tower.max_level > 1:
            tower.level = tower.max_level
            tower.load(game.assets.image_path(f"tower_{tower_type}_lvl{tower.level}"))
            tower.hp = tower.maxHP
        return tower

    def _plane(self, spread: bool):
        plane = self._tower(PLANE_TYPE, self.rng.randrange(self._rows), 0)
        if spread:  # the first wave of planes starts strung across the map
            plane.position.x = self.rng.uniform(0, self.game.tilemap.map_width)
            plane.rect.center = plane.position
        return plane

    def _enemy(self):
        from gameplay.combat.enemy import Enemy
        from gameplay.combat.tank import Tank
        from gameplay.combat.wave_manager import TANK_TYPES

        game = self.game
        enemy_type = self.rng.choices(
            list(ENEMY_TYPE_WEIGHTS), weights=list(ENEMY_TYPE_WEIGHTS.values())
        )[0]
        cls = Tank if enemy_type in TANK_TYPES else Enemy
        self._next_id += 1
        enemy = cls(
            self._next_id, enemy_type, LEVEL, game.tilemap.waypoints, game.assets
        )
        enemy.maxHP *= HP_SCALE
        enemy.hp = enemy.maxHP
        # A seeded random point along the path (never its very end).
        distance = self.rng.uniform(0, 0.95 * self._path_length)
        for index, (a, b, length) in enumerate(self._segments):
            if distance <= length or index == len(self._segments) - 1:
                t = 0 if length == 0 else min(1.0, distance / length)
                enemy.position = a + (b - a) * t
                enemy.rect.center = enemy.position
                enemy.waypoint_index = index + 1
                enemy._face_toward(b)
                break
            distance -= length
        return enemy

    def top_up(self, initial: bool = False) -> None:
        """Replaces what the last frame removed (outside the timed sections)."""
        game = self.game
        missing = self.enemy_count - len(game.enemies)
        if missing > 0:
            game.enemies.extend(self._enemy() for _ in range(missing))

        present = set(map(id, game.towers))
        for tower_type, row, col in self._ground_slots:
            tower = self._ground.get((row, col))
            if tower is None or id(tower) not in present:
                if tower is not None:
                    self.towers_lost += 1
                tower = self._tower(tower_type, row, col)
                self._ground[(row, col)] = tower
                game.towers.append(tower)
        self._planes = [p for p in self._planes if id(p) in present]
        while len(self._planes) < self._plane_count:
            plane = self._plane(spread=initial)
            self._planes.append(plane)
            game.towers.append(plane)


def build_game(speed: int, zoom: str):
    from app.game import Game

    game = Game()
    game.panel_manager.current_panel = "game"
    game.wave_manager = None  # the scenario controls the enemies
    gs = game.game_state
    gs.is_started = True
    gs.speed = speed
    gs.level = LEVEL
    gs.lives = 10**9
    gs.money = 10**9
    centre = (game.tilemap.map_width / 2, game.tilemap.map_height / 2)
    if zoom == "fit":  # zoomed all the way out: the whole map on screen
        game.camera._zoom_at(game.game_area.center, 0.0)
    else:
        game.camera.scale = float(zoom)
    game.camera.center_on(centre)
    return game


def run_scenario(
    enemies: int,
    towers: int,
    speed: int,
    zoom: str,
    frames: int,
    warmup: int,
    seed: int,
    profiler: cProfile.Profile | None = None,
) -> dict:
    game = build_game(speed, zoom)
    scenario = LoadScenario(game, enemies, towers, seed)
    counted_kills = []

    def count_kill(enemy, _original=game._on_enemy_killed):
        counted_kills.append(enemy)
        _original(enemy)

    game._on_enemy_killed = count_kill
    lives_before = game.game_state.lives

    tick_ms: list[float] = []
    draw_ms: list[float] = []
    perf = time.perf_counter
    for frame in range(warmup + frames):
        scenario.top_up()
        if profiler and frame >= warmup:
            profiler.enable()
        t0 = perf()
        game._tick()
        t1 = perf()
        game.draw()
        t2 = perf()
        if profiler and frame >= warmup:
            profiler.disable()
        if frame >= warmup:
            tick_ms.append((t1 - t0) * 1000)
            draw_ms.append((t2 - t1) * 1000)

    tick = summarize(tick_ms)
    draw = summarize(draw_ms)
    return {
        "enemies": enemies,
        "towers": towers,
        "speed": speed,
        "zoom": zoom,
        "tick": tick,
        "draw": draw,
        "fps_mean": fps_max(tick["mean"], draw["mean"]),
        "fps_p95": fps_max(tick["p95"], draw["p95"]),
        "sim_load": TICKS_PER_SECOND * tick["mean"] / 1000,
        "kills": len(counted_kills),
        "escaped_lives": lives_before - game.game_state.lives,
        "towers_lost": scenario.towers_lost,
        "frames": frames,
    }


HEADER = (
    "| enemies | towers | speed | zoom "
    "| tick mean | tick p95 | tick max "
    "| draw mean | draw p95 | draw max "
    "| sim load | FPS (mean) | FPS (p95) | kills |"
)


def format_row(r: dict) -> str:
    t, d = r["tick"], r["draw"]
    return (
        f"| {r['enemies']} | {r['towers']} | x{r['speed']} | {r['zoom']} "
        f"| {t['mean']:.2f} | {t['p95']:.2f} | {t['max']:.2f} "
        f"| {d['mean']:.2f} | {d['p95']:.2f} | {d['max']:.2f} "
        f"| {r['sim_load']:.0%} | {_fps(r['fps_mean'])} | {_fps(r['fps_p95'])} "
        f"| {r['kills']} |"
    )


def _fps(value: float) -> str:
    """0 means the simulation can't keep real time: slow motion."""
    return f"{value:.0f}" if value > 0 else "slow-mo"


def machine_info() -> str:
    import pygame

    cpu = platform.processor() or platform.machine()
    return (
        f"{platform.system()} {platform.release()} ({platform.version()}), "
        f"CPU: {cpu} ({os.cpu_count()} logical), "
        f"Python {platform.python_version()}, pygame-ce {pygame.version.ver} "
        f"(SDL {'.'.join(map(str, pygame.get_sdl_version()))}), "
        f"video driver: {os.environ.get('SDL_VIDEODRIVER')}"
    )


def main(argv: list[str] | None = None) -> list[dict]:
    global TICKS_PER_SECOND

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--loads", default="30x20,100x50,300x150,600x300")
    parser.add_argument("--speeds", default="1,4")
    parser.add_argument("--zooms", default="1,fit")
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument(
        "--profile",
        action="store_true",
        help="then cProfile the last scenario again and print its top functions",
    )
    args = parser.parse_args(argv)

    from util import constants

    TICKS_PER_SECOND = constants.TICKS_PER_SECOND

    combos = [
        (enemies, towers, int(speed), zoom)
        for enemies, towers in parse_loads(args.loads)
        for zoom in args.zooms.split(",")
        for speed in args.speeds.split(",")
    ]

    before = snapshot(REAL_SAVES)
    results = []
    with saves_redirected():
        print(machine_info())
        print(
            f"TICKS_PER_SECOND={TICKS_PER_SECOND}, frames={args.frames} "
            f"(+{args.warmup} warm-up), seed={args.seed}, level={LEVEL}, "
            f"HP x{HP_SCALE}; times in ms\n"
        )
        print(HEADER)
        print(_separator())
        for combo in combos:
            result = run_scenario(*combo, args.frames, args.warmup, args.seed)
            results.append(result)
            print(format_row(result), flush=True)
        if args.profile:
            # A separate run: profiler overhead must not skew the table.
            profiler = cProfile.Profile()
            run_scenario(*combos[-1], args.frames, args.warmup, args.seed, profiler)
            print_profile(profiler, combos[-1])
    if snapshot(REAL_SAVES) != before:
        raise SystemExit(f"Benchmark FAILED: it changed the real {REAL_SAVES}/")
    return results


def print_profile(profiler: cProfile.Profile, combo: tuple) -> None:
    enemies, towers, speed, zoom = combo
    root = str(Path.cwd()) + os.sep
    for key in ("tottime", "cumulative"):
        out = io.StringIO()
        pstats.Stats(profiler, stream=out).sort_stats(key).print_stats(20)
        print(
            f"\ncProfile ({enemies} enemies x {towers} towers, x{speed}, "
            f"zoom {zoom}; a separate run, its times include profiler overhead), "
            f"sorted by {key}:"
        )
        print(_trim_profile(out.getvalue()).replace(root, ""))


def _separator() -> str:
    return "|" + "---:|" * (HEADER.count("|") - 1)


def _trim_profile(text: str) -> str:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "ncalls" in line)
    return "\n".join(line for line in lines[start:] if line.strip())


if __name__ == "__main__":
    main()
