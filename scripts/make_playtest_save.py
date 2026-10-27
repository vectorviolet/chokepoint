"""Writes a ready-made play-test save (issue #63) into a folder, normally a
worktree's own saves/, so a PR can be play-tested at once with Continue:

    uv run python scripts/make_playtest_save.py --out saves

The run: --money coins (100,000), wave --level (10) about half spawned with
its enemies on the path, paused; one tower of every type at every level on
free build tiles along the path, the plane upgrade bought and one plane in
the air. The settings: music and SFX volume 0, music on, windowed.

It builds all of this with the real game: a Game() whose saving is
redirected to a temporary folder (saves_redirected() from smoke_test.py),
serialized by the game's own save code. Only the two resulting files,
save.json and settings.json, are copied into --out.

Refuses to overwrite existing files without --overwrite, and never writes
into the main checkout's own saves/ (the player's real saves).
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "pygamine"))

DEFAULT_MONEY = 100_000
DEFAULT_LEVEL = 10
# Ground towers stand on build tiles at most this far from the path (in
# tiles, tile centre to path) and at least this far apart (Chebyshev).
NEAR_PATH_TILES = 1.6
TOWER_SPACING_TILES = 2
# The plane is placed over the path this far along it from the entrance.
PLANE_PATH_TILES = 4.0
# Ticks are run at this speed while the wave fills up, then speed goes
# back to 1 for the save.
FILL_SPEED = 4
MAX_FILL_TICKS = 100_000


class RefusedError(Exception):
    """The output folder isn't safe to write: nothing was written."""


# ── where it may write ───────────────────────────────────────────────────────


def main_checkout() -> Path:
    """The repository's main checkout -- the folder holding the player's real
    saves/. From a git worktree that's the parent of the shared .git folder;
    without git, this checkout itself (the safe assumption)."""
    try:
        common = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ROOT
    common_dir = Path(common)
    if not common_dir.is_absolute():
        common_dir = ROOT / common_dir
    return common_dir.resolve().parent


def check_out_dir(out: Path, overwrite: bool, file_names: list[str]) -> Path:
    """`out` resolved, or RefusedError if writing there isn't safe."""
    out = out.resolve()
    real_saves = (main_checkout() / "saves").resolve()
    if out == real_saves or real_saves in out.parents:
        raise RefusedError(
            f"refusing to write into the main checkout's real saves folder "
            f"({real_saves}); use a worktree's own saves/ or another folder"
        )
    if out.exists() and not out.is_dir():
        raise RefusedError(f"{out} exists and is not a folder")
    existing = [name for name in file_names if (out / name).exists()]
    if existing and not overwrite:
        raise RefusedError(
            f"{', '.join(existing)} already in {out}; pass --overwrite to replace"
        )
    return out


# ── building the run ─────────────────────────────────────────────────────────


def _path_points(waypoints) -> list[tuple[float, float, float]]:
    """The path sampled every few pixels: (x, y, distance from the entrance)."""
    points = []
    travelled = 0.0
    for a, b in zip(waypoints, waypoints[1:]):
        length = a.distance_to(b)
        steps = max(1, int(length // 8))
        for i in range(steps):
            p = a.lerp(b, i / steps)
            points.append((p.x, p.y, travelled + length * i / steps))
        travelled += length
    last = waypoints[-1]
    points.append((last.x, last.y, travelled))
    return points


def tiles_along_path(game, count: int) -> list[tuple[int, int]]:
    """`count` free build tiles beside the path, in order from its entrance,
    at least TOWER_SPACING_TILES apart."""
    from util.constants import TILE_SIZE

    points = _path_points(game.tilemap.waypoints)
    grid = game.tilemap.buildable_grid
    taken = {t.get_blocking_position() for t in game.towers} - {None}
    candidates = []
    for row, cells in enumerate(grid):
        for col, buildable in enumerate(cells):
            if not buildable or (row, col) in taken:
                continue
            cx, cy = (col + 0.5) * TILE_SIZE, (row + 0.5) * TILE_SIZE
            dist, along = min((math.hypot(cx - x, cy - y), s) for x, y, s in points)
            if dist <= NEAR_PATH_TILES * TILE_SIZE:
                candidates.append((along, row, col))
    chosen: list[tuple[int, int]] = []
    for _, row, col in sorted(candidates):
        if all(
            max(abs(row - r), abs(col - c)) >= TOWER_SPACING_TILES for r, c in chosen
        ):
            chosen.append((row, col))
            if len(chosen) == count:
                return chosen
    raise RuntimeError(f"only {len(chosen)} free build tiles along the path")


def plane_tile(game) -> tuple[int, int]:
    """The tile over the path PLANE_PATH_TILES along it from the entrance."""
    from util.constants import TILE_SIZE

    target = PLANE_PATH_TILES * TILE_SIZE
    x, y, _ = min(
        _path_points(game.tilemap.waypoints), key=lambda p: abs(p[2] - target)
    )
    return int(y // TILE_SIZE), int(x // TILE_SIZE)


def tower_specs(tower_config) -> list[tuple[int, int]]:
    """(type, level) for every level of every ground tower type, from
    config/towers.yaml. The plane (type 4) upgrades globally instead."""
    return [
        (tower_type, level)
        for tower_type, max_level in enumerate(tower_config.max_levels, start=1)
        if tower_type != 4
        for level in range(1, max_level + 1)
    ]


def add_tower(game, tower_type: int, level: int, row: int, col: int):
    """A tower as the game builds it (TowerFactory) at `level`, the way
    restoring a saved tower sets its level."""
    from gameplay.towers import TowerFactory

    tower = TowerFactory.create(
        tower_type,
        row,
        col,
        game.tower_config,
        game.assets,
        game.audio,
        game.tilemap.map_width,
    )
    tower.level = level
    if level != 1:
        tower.load(game.assets.image_path(f"tower_{tower_type}_lvl{level}"))
    tower.hp = tower.maxHP
    game.towers.append(tower)
    return tower


def fill_wave(game, level: int) -> None:
    """Runs wave `level` from its start until about half its enemies have
    spawned, then pauses."""
    gs = game.game_state
    gs.level = level
    gs.has_won = level > _win_wave()
    gs.is_started = True
    gs.speed = FILL_SPEED
    wm = game.wave_manager
    for _ in range(MAX_FILL_TICKS):
        game._tick()
        if wm._spawn_queue and wm._queue_index >= math.ceil(len(wm._spawn_queue) / 2):
            break
    else:
        raise RuntimeError("the wave never got half spawned")
    gs.is_started = False
    gs.speed = 1


def _win_wave() -> int:
    from app.game import WIN_WAVE

    return WIN_WAVE


def build_run(game, money: int, level: int) -> None:
    game._start_new_game()
    fill_wave(game, level)
    specs = tower_specs(game.tower_config)
    for (tower_type, tower_level), (row, col) in zip(
        specs, tiles_along_path(game, len(specs))
    ):
        add_tower(game, tower_type, tower_level, row, col)
    game.game_state.plane_level = 2  # UPG PLANES bought
    add_tower(game, 4, 2, *plane_tile(game))
    gs = game.game_state
    gs.money = money
    gs.lives = game._starting_lives
    gs.selected_tower = None
    gs.selected_enemy = None


def mute(game) -> None:
    """Music and SFX at volume 0, music on (not paused)."""
    game.audio.set_music_volume(0.0)
    game.audio.set_sfx_volume(0.0)
    if game.audio.is_music_paused:
        game.audio.resume_music()


def windowed(settings: dict) -> dict:
    """`settings` in windowed mode. The headless window this runs in is
    never switched (its display may be tiny): the mode is set in the saved
    settings, and their window size dropped, so the game picks its best fit
    for the player's own screen."""
    settings = dict(settings, window_mode="windowed")
    settings.pop("window_size", None)
    return settings


def make_playtest_save(
    out: Path,
    *,
    money: int = DEFAULT_MONEY,
    level: int = DEFAULT_LEVEL,
    overwrite=False,
) -> list[Path]:
    """Writes save.json and settings.json into `out`; returns their paths."""
    os.chdir(ROOT)  # the game loads config/ and assets/ relative to the cwd
    from pygamine import SaveStore
    from smoke_test import saves_redirected

    names = [SaveStore("save").path.name, SaveStore("settings").path.name]
    out = check_out_dir(out, overwrite, names)

    from app.game import Game

    with saves_redirected():
        game = Game()
        build_run(game, money, level)
        mute(game)
        game._save_game()
        game._save_settings()
        game.settings_store.save(windowed(game.settings_store.load()))
        sources = [game.save_store.path, game.settings_store.path]
        out.mkdir(parents=True, exist_ok=True)
        written = []
        for src in sources:
            shutil.copyfile(src, out / src.name)
            written.append(out / src.name)
    return written


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a play-test save.json and settings.json into a folder."
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="folder to write into, e.g. this worktree's saves",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="replace existing files"
    )
    parser.add_argument("--money", type=int, default=DEFAULT_MONEY)
    parser.add_argument("--level", type=int, default=DEFAULT_LEVEL)
    args = parser.parse_args(argv)
    if args.level < 1:
        parser.error("--level must be 1 or more")
    if args.money < 0:
        parser.error("--money can't be negative")
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    try:
        written = make_playtest_save(
            args.out.resolve(),
            money=args.money,
            level=args.level,
            overwrite=args.overwrite,
        )
    except RefusedError as e:
        raise SystemExit(f"make_playtest_save: {e}") from None
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
