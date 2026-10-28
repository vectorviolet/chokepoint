"""Writes a ready-made play-test save (issue #63) into a folder, normally a
worktree's own saves/, so a PR can be play-tested at once with Continue:

    uv run python scripts/make_playtest_save.py --out saves

The run: --money coins (100,000), wave --level (10) about half spawned and
paused, its spawned enemies on the path (in long, high-level waves the first
ones reach the end while it fills, so fewer); one tower of every type at
every level on build tiles beside the path, the plane upgrade bought and one
plane starting its flight at the map's left edge. The settings: music and
SFX volume 0, music on, auto-pause off, windowed.

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
import re
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

# Paths compare as the OS does: case-insensitively on Windows, where
# `.../Saves` is the same folder as `.../saves`.
_normcase = os.path.normcase


def _key(path: Path) -> str:
    return _normcase(os.path.normpath(str(path)))


def is_within(path: Path, folder: Path) -> bool:
    """Whether `path` is `folder` or inside it (both resolved)."""
    p, f = _key(path), _key(folder)
    return p == f or p.startswith(f.rstrip(os.sep) + os.sep)


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _main_worktree_of(common_dir: Path) -> Path | None:
    """The main work tree of the git folder `common_dir`: its parent for a
    `.git` folder, else (a submodule's .git/modules/<name>) its
    core.worktree setting."""
    if common_dir.name == ".git":
        return common_dir.parent
    try:
        config = (common_dir / "config").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^\s*worktree\s*=\s*(.+?)\s*$", config, re.MULTILINE)
    if match is None:
        return None
    worktree = Path(match.group(1))
    return (worktree if worktree.is_absolute() else common_dir / worktree).resolve()


def checkout_from_dot_git(root: Path) -> Path | None:
    """The main checkout, read from `root`'s .git without running git: a
    .git folder, or a .git file pointing at a git folder of its own (a
    submodule), makes `root` the main checkout; a linked worktree's .git
    file points at <common>/worktrees/<name>, whose main work tree is the
    main checkout. None if it can't be told."""
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
    if gitdir.parent.name != "worktrees":
        return root
    return _main_worktree_of(gitdir.parent.parent)


def main_checkout() -> Path | None:
    """The repository's main checkout -- the folder holding the player's real
    saves/: the main work tree of the shared git folder (its parent for a
    .git folder; a submodule's core.worktree for one under .git/modules).
    With no git, or a copy that isn't a checkout of its
    own (no .git, or nested inside another repository), this folder is the
    one with the real saves; without git, .git is read directly. None if it
    can't be told."""
    toplevel = _git("rev-parse", "--show-toplevel")
    if toplevel is None:
        if not (ROOT / ".git").exists():
            return ROOT
        return checkout_from_dot_git(ROOT)
    if _key(Path(toplevel).resolve()) != _key(ROOT):
        return ROOT  # git answered for an outer repository
    common = _git("rev-parse", "--git-common-dir")
    if common is None:
        return checkout_from_dot_git(ROOT)
    common_dir = Path(common)
    if not common_dir.is_absolute():
        common_dir = ROOT / common_dir
    return _main_worktree_of(common_dir.resolve())


def check_out_dir(out: Path, overwrite: bool, file_names: list[str]) -> Path:
    """`out` (already resolved), or RefusedError if writing there isn't safe."""
    main = main_checkout()
    if main is None:
        # The real saves/ can't be located: refuse any folder named saves
        # (or inside one) except within this checkout.
        named_saves = any(_normcase(part) == _normcase("saves") for part in out.parts)
        if named_saves and not is_within(out, ROOT):
            raise RefusedError(
                f"can't find the main checkout, so refusing to write into a "
                f"saves folder outside {ROOT}"
            )
    else:
        real_saves = (main / "saves").resolve()
        if is_within(out, real_saves):
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
    """`count` build tiles beside the path, nearest the entrance (where the
    camera opens) first, at least TOWER_SPACING_TILES apart. Picked on a
    map with no towers yet."""
    from gameplay.path_geometry import tiles_near_path
    from util.constants import HALF_TILE, TILE_SIZE

    near, far = (tiles * TILE_SIZE for tiles in NEAR_PATH_TILES)
    entrance = game.tilemap.waypoints[0]
    candidates = sorted(
        tiles_near_path(game.tilemap, near, far),
        key=lambda rc: entrance.distance_to(
            (rc[1] * TILE_SIZE + HALF_TILE, rc[0] * TILE_SIZE + HALF_TILE)
        ),
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
    """Where the plane starts its flight: the map's left edge (as the menu
    demo's planes do, so it crosses the whole map), on the row of the path
    PLANE_PATH_TILES along it from the entrance."""
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
    return int(point.y // TILE_SIZE), 0


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
    spawned, then pauses. It runs under waves_only(): the towers hold fire,
    so the spawned enemies stay on the path, and enemies that reach its
    end (in long waves: the first of them, before half have spawned) cost
    no lives, so this can't end the run at any level. Returns how many
    reached the end."""
    gs = game.game_state
    gs.level = level
    gs.has_won = level > _win_wave()
    gs.is_started = True
    gs.speed = FILL_SPEED
    wm = game.wave_manager
    with game.waves_only() as escaped:
        for _ in range(MAX_FILL_TICKS):
            game._tick()
            if wm.wave_size and wm.spawned_count >= math.ceil(wm.wave_size / 2):
                break
        else:
            raise RuntimeError("the wave never got half spawned")
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
    escaped = fill_wave(game, level)
    # The plane last: placed before, it would fly off the map while filling.
    game.game_state.plane_level = 2  # UPG PLANES bought
    add_tower(game, PLANE_TYPE, 2, *plane_tile(game))
    gs = game.game_state
    gs.money = money
    gs.selected_tower = None
    gs.selected_enemy = None
    return escaped


def settings_for_playtest(game) -> None:
    """Music and SFX at volume 0, music on (not paused), auto-pause between
    waves off -- set here rather than left to config/settings.yaml."""
    game.audio.set_music_volume(0.0)
    game.audio.set_sfx_volume(0.0)
    if game.audio.is_music_paused:
        game.audio.resume_music()
    game.auto_pause = False


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
            settings_for_playtest(game)
            game._save_game()
            game._save_settings()
            game.settings_store.save(windowed(game.settings_store.load()))
            out.mkdir(parents=True, exist_ok=True)
            written = []
            for src in (game.save_store.path, game.settings_store.path):
                shutil.copyfile(src, out / src.name)
                written.append(out / src.name)
    wm = game.wave_manager
    note = f" ({escaped} reached the end while it filled)" if escaped else ""
    report(
        f"wave {level}: {wm.spawned_count} of {wm.wave_size} enemies spawned, "
        f"{len(game.enemies)} on the path{note}"
    )
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
