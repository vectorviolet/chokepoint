"""Headless boot check -- catches config/panel wiring mistakes that only
surface once objects are actually built (e.g. a panels.yaml entry missing a
required key). Run locally with:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python scripts/smoke_test.py

Requires cwd = repo root (matches how __main__.py and CI both invoke it).

Safe to run locally: every Game() it builds saves into a temporary folder
(see saves_redirected()), never the player's real saves/. The script
snapshots saves/ before and after and fails if a single byte changed.
"""

import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml

sys.path.insert(0, "src")
sys.path.insert(0, "src/pygamine")

REAL_SAVES = Path("saves")


def check_config_yaml() -> None:
    for path in sorted(Path("config").glob("*.yaml")):
        yaml.safe_load(path.read_text(encoding="utf-8"))
        print(f"  {path}: OK")


@contextmanager
def saves_redirected() -> Iterator[Path]:
    """Points every SaveStore's default directory at a temporary folder
    while active -- the same mechanism as tests/conftest.py's saves_in_tmp
    fixture -- so a Game() built here never touches the real saves/."""
    from pygamine import SaveStore

    original = SaveStore.__init__.__defaults__
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        saves = Path(tmp) / "saves"
        SaveStore.__init__.__defaults__ = (str(saves),)
        try:
            yield saves
        finally:
            SaveStore.__init__.__defaults__ = original


def snapshot(directory: Path) -> dict[str, bytes] | None:
    """Every file under `directory` and its exact bytes (None if absent)."""
    if not directory.exists():
        return None
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def boot_game() -> None:
    from app.game import Game

    game = Game()
    for panel in ("main_menu", "play_menu", "credits", "settings", "game"):
        game.panel_manager.current_panel = panel
        game.update()
        game.draw()
        print(f"  {panel}: OK")


def run_game_briefly() -> None:
    # The path the steps above never touch: the splash, any run() override
    # and the hand-off into the main loop (a crash there once shipped unseen).
    from app.game import Game
    from pygamine.devtools.smoke import run_briefly

    frames = run_briefly(Game())
    print(f"  splash + {frames} main-loop frames via the real run(): OK")


def main() -> None:
    before = snapshot(REAL_SAVES)
    print("Validating config/*.yaml...")
    check_config_yaml()
    with saves_redirected() as tmp_saves:
        print(f"Saves redirected to {tmp_saves}")
        print("Booting Game() and rendering every panel...")
        boot_game()
        print("Running the real run() -- splash and main loop -- briefly...")
        run_game_briefly()
    if snapshot(REAL_SAVES) != before:
        raise SystemExit(f"Smoke test FAILED: it changed the real {REAL_SAVES}/")
    print(f"  {REAL_SAVES}/ unchanged: OK")
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
