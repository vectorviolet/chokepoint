"""Capture README media from the current game, with every save redirected.

Run from the project root: uv run --group build python scripts/capture_readme.py
The staged wave uses the play-test helpers; these are source-build screenshots,
not a claim about the latest published release. No player save is loaded.

The game is built with a fixed seed, so two runs write byte-identical files.
The audio driver is the dummy one: the volumes shown on Settings play nothing.
--out, --size, --frames and --level exist for tests/test_capture_readme.py.
"""

import argparse
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

from make_playtest_save import (
    add_tower,
    fill_wave,
    main_checkout,
    tiles_beside_path,
    tower_specs,
)
from smoke_test import saves_redirected, snapshot

SIZE = (1920, 1080)
FPS = 10
SECONDS = 6
SEED = 44
# The staged run: wave LEVEL half spawned, with MONEY in the bank.
LEVEL = 15
MONEY = 2574
# The staged towers stand at least this many tiles apart.
TOWER_SPACING_TILES = 3
# Shown on the Settings screenshot (silent: the audio driver is a dummy).
VOLUMES = {"master_volume": 0.8, "music_volume": 0.6, "sfx_volume": 0.8}
# The GIF's one palette is built from this many frames spread evenly over the
# clip, each shrunk by this factor first (only their colours matter).
PALETTE_SAMPLES = 12
PALETTE_SAMPLE_REDUCE = 4


def grab_frame(game) -> Image.Image:
    """The game's next frame, drawn and copied off the window."""
    game.draw()
    return Image.frombytes(
        "RGB", game.window.get_size(), pygame.image.tobytes(game.window, "RGB")
    )


def save_image(game, out: Path, name: str) -> None:
    path = out / "screenshots" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    grab_frame(game).save(path, optimize=True)
    print(f"Captured {path}")


def battle_center(game):
    """The middle of the path's first straight, where the staged wave's
    enemies are advancing."""
    path = game.tilemap.waypoints
    a, b = next((a, b) for a, b in zip(path, path[1:]) if a.y == b.y)
    return a.lerp(b, 0.5)


def stage_battle(game, frame_ms: float, level: int) -> None:
    """A new run with one tower of every ground type and level beside the
    path's first straight, wave `level` half spawned, then started."""
    game._start_new_game()
    game.auto_pause = False
    center = battle_center(game)
    specs = tower_specs(game.tower_config)
    tiles = tiles_beside_path(
        game, len(specs), anchor=center, spacing_tiles=TOWER_SPACING_TILES
    )
    for (tower_type, tower_level), (row, col) in zip(specs, tiles):
        add_tower(game, tower_type, tower_level, row, col)
    fill_wave(game, level)
    game.game_state.money = MONEY
    # Keep the camera fixed while rendering headlessly; there is no live mouse.
    game.camera.update_with_mouse = lambda *_: None
    game.camera.center_on(center)
    game._set_started(True)
    game._sync_game_ui()
    for _ in range(15):
        game._update_game(frame_ms)


def palette_indices(frame_count: int) -> list[int]:
    """Up to PALETTE_SAMPLES frame indices spread evenly over the clip,
    first and last included."""
    k = min(PALETTE_SAMPLES, frame_count)
    if k == 1:
        return [0]
    return sorted({round(i * (frame_count - 1) / (k - 1)) for i in range(k)})


def save_gif(frames: list[Image.Image], path: Path, fps: int) -> None:
    """One 256-colour palette for the whole clip, built from frames sampled
    across it, so colours that only appear later (fire, coins, HP bars) are
    in it too."""
    samples = [
        frames[i].reduce(PALETTE_SAMPLE_REDUCE) for i in palette_indices(len(frames))
    ]
    width, height = samples[0].size
    sheet = Image.new("RGB", (width, height * len(samples)))
    for i, sample in enumerate(samples):
        sheet.paste(sample, (0, i * height))
    palette = sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    indexed = [
        frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    indexed[0].save(
        path,
        save_all=True,
        append_images=indexed[1:],
        duration=1000 // fps,
        loop=0,
        optimize=True,
    )
    print(f"Captured {path}")


def capture(
    out: Path, size=SIZE, frames: int = FPS * SECONDS, level: int = LEVEL
) -> None:
    """Writes out/screenshots/*.png and out/preview.gif. Needs the cwd to be
    the project root (the game loads config/ and assets/ relative to it)."""
    # Importing Game is harmless; constructing it only happens inside the guard.
    from app.game import Game
    from pygamine import SaveStore

    frame_ms = 1000 / FPS
    with saves_redirected():
        SaveStore("settings").save(
            {"window_size": list(size), "window_mode": "windowed", **VOLUMES}
        )
        game = Game(seed=SEED)
        for _ in range(30):
            game.menu_demo.update(frame_ms)
        save_image(game, out, "01_menu.png")

        stage_battle(game, frame_ms, level)
        save_image(game, out, "02_gameplay.png")
        tower = next(t for t in game.towers if t.tower_type == 2 and t.level == 1)
        game.game_state.selected_tower = tower
        game.tower_info.show(tower)
        save_image(game, out, "03_upgrades.png")
        game._open_pause_menu()
        save_image(game, out, "04_pause.png")
        game._close_pause_menu()
        game.game_state.selected_tower = None
        game.tower_info.show(None)
        clip = []
        for _ in range(frames):
            game._update_game(frame_ms)
            clip.append(grab_frame(game))
        save_gif(clip, out / "preview.gif", FPS)
        game.panel_manager.current_panel = "settings"
        save_image(game, out, "05_settings.png")


def real_save_dirs() -> set[Path]:
    paths = {ROOT / "saves"}
    if main_root := main_checkout():
        paths.add(main_root / "saves")
    return paths


def _size(text: str) -> tuple[int, int]:
    width, height = (int(n) for n in text.lower().split("x"))
    return width, height


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture the README media.")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    parser.add_argument(
        "--size", type=_size, default=SIZE, help="window size, WIDTHxHEIGHT"
    )
    parser.add_argument("--frames", type=int, default=FPS * SECONDS)
    parser.add_argument("--level", type=int, default=LEVEL)
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    out = args.out.resolve()
    os.chdir(ROOT)
    before = {path: snapshot(path) for path in real_save_dirs()}
    try:
        capture(out, args.size, args.frames, args.level)
    finally:
        pygame.quit()
        if any(snapshot(path) != saved for path, saved in before.items()):
            raise RuntimeError("Capture changed a real save directory")
    print("All real save directories unchanged.")


if __name__ == "__main__":
    main()
