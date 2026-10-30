"""Capture README media from the current game, with every save redirected.

Run from the project root: uv run --group build python scripts/capture_readme.py
The staged wave uses the play-test helpers; these are source-build screenshots,
not a claim about the latest published release. No player save is loaded.
"""

import os
import sys
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "pygamine"))
sys.path.insert(0, str(ROOT / "scripts"))

import pygame
from PIL import Image

from make_playtest_save import add_tower, build_run, main_checkout, tower_specs
from smoke_test import saves_redirected, snapshot

SIZE = (1920, 1080)
FPS = 10
SECONDS = 6


def save_image(game, name: str) -> None:
    game.draw()
    path = ROOT / "docs" / "screenshots" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.frombytes(
        "RGB", game.window.get_size(), pygame.image.tobytes(game.window, "RGB")
    ).save(path, optimize=True)
    print(f"Captured {path.relative_to(ROOT)}")


def stage_battle(game) -> None:
    from gameplay.path_geometry import tiles_near_path
    from util.constants import HALF_TILE, TILE_SIZE

    build_run(game, money=2574, level=15)
    game.auto_pause = False
    game.game_state.plane_level = 1
    game.towers.clear()
    game._clear_orphan_shots()
    path = game.tilemap.waypoints
    horizontal = [(a, b) for a, b in zip(path, path[1:]) if a.y == b.y]
    # The first straight is where this staged wave's enemies are advancing.
    a, b = horizontal[0]
    center = a.lerp(b, 0.5)
    candidates = sorted(
        tiles_near_path(game.tilemap, 0.9 * TILE_SIZE, 1.6 * TILE_SIZE),
        key=lambda rc: center.distance_to(
            (rc[1] * TILE_SIZE + HALF_TILE, rc[0] * TILE_SIZE + HALF_TILE)
        ),
    )
    chosen = []
    specs = tower_specs(game.tower_config)
    for row, col in candidates:
        if all(max(abs(row - r), abs(col - c)) >= 3 for r, c in chosen):
            chosen.append((row, col))
        if len(chosen) == len(specs):
            break
    if len(chosen) != len(specs):
        raise RuntimeError("Not enough distinct tower positions for the capture")
    for (tower_type, level), (row, col) in zip(specs, chosen):
        add_tower(game, tower_type, level, row, col)
    # Keep the camera fixed while rendering headlessly; there is no live mouse.
    game.camera.update_with_mouse = lambda *_: None
    game.camera.center_on(center)
    game._set_started(True)
    game._sync_game_ui()
    for _ in range(15):
        game._update_game(1000 / FPS)


def capture_preview(game) -> None:
    frames = []
    for _ in range(FPS * SECONDS):
        game._update_game(1000 / FPS)
        game.draw()
        frame = Image.frombytes(
            "RGB", game.window.get_size(), pygame.image.tobytes(game.window, "RGB")
        )
        frames.append(frame)
    palette = frames[0].quantize(colors=256)
    indexed = [
        frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames
    ]
    indexed[0].save(
        ROOT / "docs" / "preview.gif",
        save_all=True,
        append_images=indexed[1:],
        duration=1000 // FPS,
        loop=0,
        optimize=True,
    )
    print("Captured docs/preview.gif")


def capture() -> None:
    # Importing Game is harmless; constructing it only happens inside the guard.
    from app.game import Game
    from pygamine import SaveStore

    with saves_redirected():
        SaveStore("settings").save(
            {
                "window_size": list(SIZE),
                "window_mode": "windowed",
                "master_volume": 0,
                "music_volume": 0,
                "sfx_volume": 0,
            }
        )
        game = Game()
        game.menu_demo._rng.seed(44)
        game.menu_demo._start_run()
        for _ in range(30):
            game.menu_demo.update(100)
        save_image(game, "01_menu.png")

        stage_battle(game)
        save_image(game, "02_gameplay.png")
        tower = next(t for t in game.towers if t.tower_type == 2 and t.level == 1)
        game.game_state.selected_tower = tower
        game.tower_info.show(tower)
        save_image(game, "03_upgrades.png")
        game._open_pause_menu()
        save_image(game, "04_pause.png")
        game._close_pause_menu()
        game.game_state.selected_tower = None
        game.tower_info.show(None)
        capture_preview(game)
        game.panel_manager.current_panel = "settings"
        save_image(game, "05_settings.png")
        pygame.quit()


def main() -> None:
    os.chdir(ROOT)
    paths = {ROOT / "saves"}
    if main_root := main_checkout():
        paths.add(main_root / "saves")
    before = {path: snapshot(path) for path in paths}
    try:
        capture()
    finally:
        if any(snapshot(path) != saved for path, saved in before.items()):
            raise RuntimeError("Capture changed a real save directory")
    print("All real save directories unchanged.")


if __name__ == "__main__":
    main()
