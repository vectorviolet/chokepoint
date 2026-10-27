"""Writes a ready-made play-test save (issue #63) into a folder, normally a
worktree's own saves/, so a PR can be play-tested at once with Continue:

    uv run python scripts/make_playtest_save.py --out saves

The run: --money coins (100,000), wave --level (10) about half spawned with
its enemies on the path, paused; one tower of every type at every level on
free build tiles beside the path, the plane upgrade bought and one plane in
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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "pygamine"))

DEFAULT_MONEY = 100_000
DEFAULT_LEVEL = 10
# Ground towers stand on build tiles this far from the path (in tiles, tile
# centre to path: beside it, never on it) and at least this far apart
# (Chebyshev).
NEAR_PATH_TILES = (0.9, 1.6)
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


def checkout_from_dot_git(root: Path) -> Path | None:
    """The main checkout, read from `root`'s .git without running git: a
    .git folder means `root` is it; a worktree's .git file points at
    <main>/.git/worktrees/<name>; a submodule's at <super>/.git/modules/...,
    which still makes `root` its own checkout. None if it can't be told."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return root
    if not dot_git.is_file():
        return None
    text = dot_git.read_text(encoding="utf-8", errors="replace").strip()
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = root / gitdir
    gitdir = gitdir.resolve()
    if gitdir.parent.name == "worktrees":
        return gitdir.parent.parent.parent
    if "modules" in gitdir.parts:
        return root
    return None


def main_checkout() -> Path | None:
    """The repository's main checkout -- the folder holding the player's real
    saves/. From a git worktree that's the parent of the shared .git folder.
    Asks git first, then reads .git itself; with no .git at all (an unpacked
    copy) this folder is the one with the real saves. None if it can't be
    told."""
    try:
        common = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        if not (ROOT / ".git").exists():
            return ROOT
        return checkout_from_dot_git(ROOT)
    common_dir = Path(common)
    if not common_dir.is_absolute():
        common_dir = ROOT / common_dir
    return common_dir.resolve().parent


def check_out_dir(out: Path, overwrite: bool, file_names: list[str]) -> Path:
    """`out` (already resolved), or RefusedError if writing there isn't safe."""
    main = main_checkout()
    if main is None:
        # The real saves/ can't be located: refuse any folder named saves
        # (or inside one) except within this checkout.
        inside_root = out == ROOT or ROOT in out.parents
        if "saves" in out.parts and not inside_root:
            raise RefusedError(
                f"can't find the main checkout, so refusing to write into a "
                f"saves folder outside {ROOT}"
            )
    else:
        real_saves = (main / "saves").resolve()
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


@contextmanager
def _cwd(path: Path) -> Iterator[None]:
    """The game loads config/ and assets/ relative to the cwd: run there,
    then go back."""
    before = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(before)


# ── building the run ─────────────────────────────────────────────────────────


def tiles_beside_path(game, count: int) -> list[tuple[int, int]]:
    """`count` free build tiles beside the path, nearest the entrance (where
    the camera opens) first, at least TOWER_SPACING_TILES apart."""
    from gameplay.menu_demo import tiles_near_path
    from util.constants import HALF_TILE, TILE_SIZE

    near, far = (tiles * TILE_SIZE for tiles in NEAR_PATH_TILES)
    entrance = game.tilemap.waypoints[0]
    taken = {t.get_blocking_position() for t in game.towers} - {None}
    candidates = [
        tile for tile in tiles_near_path(game.tilemap, near, far) if tile not in taken
    ]
    candidates.sort(
        key=lambda rc: entrance.distance_to(
            (rc[1] * TILE_SIZE + HALF_TILE, rc[0] * TILE_SIZE + HALF_TILE)
        )
    )
    chosen: list[tuple[int, int]] = []
    for row, col in candidates:
        if all(
            max(abs(row - r), abs(col - c)) >= TOWER_SPACING_TILES for r, c in chosen
        ):
            chosen.append((row, col))
            if len(chosen) == count:
                return chosen
    raise RuntimeError(f"only {len(chosen)} free build tiles beside the path")


def plane_tile(game) -> tuple[int, int]:
    """The tile over the path PLANE_PATH_TILES along it from the entrance."""
    from util.constants import TILE_SIZE

    path = game.tilemap.waypoints
    left = PLANE_PATH_TILES * TILE_SIZE
    point = path[-1]
    for a, b in zip(path, path[1:]):
        length = a.distance_to(b)
        if left <= length:
            point = a.lerp(b, left / length) if length else a
            break
        left -= length
    return int(point.y // TILE_SIZE), int(point.x // TILE_SIZE)


def tower_specs(tower_config) -> list[tuple[int, int]]:
    """(type, level) for every level of every ground tower type, levels from
    config/towers.yaml. The plane upgrades globally instead."""
    from gameplay.towers import GROUND_TOWER_TYPES

    return [
        (tower_type, level)
        for tower_type in GROUND_TOWER_TYPES
        for level in range(1, tower_config.max_levels[tower_type - 1] + 1)
    ]


def add_tower(game, tower_type: int, level: int, row: int, col: int):
    from gameplay.towers import TowerFactory

    tower = TowerFactory.create(
        tower_type,
        row,
        col,
        game.tower_config,
        game.assets,
        game.audio,
        game.tilemap.map_width,
        level=level,
    )
    game.towers.append(tower)
    return tower


def fill_wave(game, level: int) -> int:
    """Runs wave `level` from its start until about half its enemies have
    spawned, then pauses. Enemies that reach the end of the path meanwhile
    (only in long waves) cost no lives, so this can't end the run at any
    level; how many did is returned."""
    gs = game.game_state
    gs.level = level
    gs.has_won = level > _win_wave()
    gs.is_started = True
    gs.speed = FILL_SPEED
    wm = game.wave_manager
    escaped = []
    # An instance attribute shadows Game's hook (lives, game over) while
    # filling.
    game._on_enemy_escaped = escaped.append
    try:
        for _ in range(MAX_FILL_TICKS):
            game._tick()
            half = math.ceil(len(wm._spawn_queue) / 2)
            if wm._spawn_queue and wm._queue_index >= half:
                break
        else:
            raise RuntimeError("the wave never got half spawned")
    finally:
        del game._on_enemy_escaped
    gs.is_started = False
    gs.speed = 1
    return len(escaped)


def _win_wave() -> int:
    from app.game import WIN_WAVE

    return WIN_WAVE


def build_run(game, money: int, level: int) -> int:
    """The play-test run in `game`; returns fill_wave()'s escape count."""
    from gameplay.towers import PLANE_TYPE

    game._start_new_game()
    specs = tower_specs(game.tower_config)
    for (tower_type, tower_level), (row, col) in zip(
        specs, tiles_beside_path(game, len(specs))
    ):
        add_tower(game, tower_type, tower_level, row, col)
    # The towers hold fire while the wave fills: the save is meant to have
    # the spawned half of the wave on the path, not already shot down.
    towers = list(game.towers)
    game.towers.clear()
    try:
        escaped = fill_wave(game, level)
    finally:
        game.towers.extend(towers)
    # The plane last: placed before, it would fly off the map while filling.
    game.game_state.plane_level = 2  # UPG PLANES bought
    add_tower(game, PLANE_TYPE, 2, *plane_tile(game))
    gs = game.game_state
    gs.money = money
    gs.lives = game._starting_lives
    gs.selected_tower = None
    gs.selected_enemy = None
    return escaped


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
    overwrite: bool = False,
    report=print,
) -> list[Path]:
    """Writes save.json and settings.json into `out` (relative to the
    caller's cwd); returns their paths. The cwd is restored afterwards."""
    out = Path(out).resolve()
    with _cwd(ROOT):
        from pygamine import SaveStore
        from smoke_test import saves_redirected

        names = [SaveStore("save").path.name, SaveStore("settings").path.name]
        out = check_out_dir(out, overwrite, names)

        from app.game import Game

        with saves_redirected():
            game = Game()
            escaped = build_run(game, money, level)
            mute(game)
            game._save_game()
            game._save_settings()
            game.settings_store.save(windowed(game.settings_store.load()))
            out.mkdir(parents=True, exist_ok=True)
            written = []
            for src in (game.save_store.path, game.settings_store.path):
                shutil.copyfile(src, out / src.name)
                written.append(out / src.name)
    note = f"; {escaped} more reached the end while it filled" if escaped else ""
    report(f"wave {level}: {len(game.enemies)} enemies on the path{note}")
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
            args.out,
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
