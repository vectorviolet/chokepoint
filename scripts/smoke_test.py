"""Headless boot check -- catches config/panel wiring mistakes that only
surface once objects are actually built (e.g. a panels.yaml entry missing a
required key). Run locally with:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python scripts/smoke_test.py

Requires cwd = repo root (matches how __main__.py and CI both invoke it).
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")
sys.path.insert(0, "src/pygamine")


def check_config_yaml() -> None:
    for path in sorted(Path("config").glob("*.yaml")):
        yaml.safe_load(path.read_text(encoding="utf-8"))
        print(f"  {path}: OK")


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
    print("Validating config/*.yaml...")
    check_config_yaml()
    print("Booting Game() and rendering every panel...")
    boot_game()
    print("Running the real run() -- splash and main loop -- briefly...")
    run_game_briefly()
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
