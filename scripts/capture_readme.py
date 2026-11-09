"""Capture README media from the current game, with every save redirected.

Run from the project root: uv run --group build python scripts/capture_readme.py
(add --covers <folder> for the itch.io cover candidates, 630x500, outside docs/).
Writes docs/preview.gif, docs/plane-run.gif and docs/screenshots/01-17 (#13).
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
# clip, each shrunk by this factor first (only their colors matter).
PALETTE_SAMPLES = 12
PALETTE_SAMPLE_REDUCE = 4
# The tank fight: a tank (round TANK_LEVEL) this far (px) behind the staged
# towers' middle; staging runs at most MAX_STAGE_FRAMES frames to reach a shot.
TANK_LEVEL = 25
TANK_LEAD = 120
MAX_STAGE_FRAMES = 600
TANK_BLAST_FRAMES = (
    4  # frames after the blast starts: the blast fades, the rubble stays
)
# Where the cursor rests when it should touch nothing (over bare map).
IDLE_MOUSE = (5, 5)
# itch.io's cover size, the logo's width as a share of it, its bottom margin,
# and each candidate's framing: (focus as a fraction of the frame, zoom).
COVER_SIZE = (630, 500)
LOGO_WIDTH_SHARE = 0.7
LOGO_MARGIN = 24
COVER_FRAMING = (((0.5, 0.5), 1.0), ((0.5, 0.45), 1.4), ((0.55, 0.5), 1.6))


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
    """One 256-color palette for the whole clip, built from frames sampled
    across it, so colors that only appear later (fire, coins, HP bars) are
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


def step(game, frame_ms: float, frames: int) -> None:
    for _ in range(frames):
        game._update_game(frame_ms)


def pin_mouse(game, position: tuple[int, int]) -> None:
    """The cursor at `position` for as long as this capture runs: the real
    mouse has no say in a headless run."""
    game.mouse.update = lambda: None
    game.mouse.position = position


def tile_center_screen(game, row: int, col: int) -> tuple[int, int]:
    from util.constants import HALF_TILE, TILE_SIZE

    point = game.camera.world_to_screen(
        (col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE)
    )
    return int(point.x), int(point.y)


def advance_enemy(enemy, pixels: float) -> None:
    """Walks `enemy` `pixels` along its path from where it stands."""
    walked = 0.0
    last = enemy.position.copy()
    while walked < pixels and not enemy.reached_end():
        enemy.move(1)
        walked += enemy.position.distance_to(last)
        last = enemy.position.copy()


def hide_hud(game, frame_ms: float) -> None:
    """Tab: the HUD slides off the screen edges (a kill's counter peek would
    bring a counter back, so the shot is taken as soon as it has settled)."""
    game.hud_slide.toggle()
    step(game, frame_ms, 3)


def free_tile_near(game, anchor, rows_away: int) -> tuple[int, int]:
    """A build tile `rows_away` rows below the path's first straight, near
    `anchor`'s column, in the open between the staged towers."""
    from util.constants import TILE_SIZE

    row = int(anchor.y // TILE_SIZE) + rows_away
    col = int(anchor.x // TILE_SIZE) - 5
    grid = game.tilemap.buildable_grid
    taken = game.tower_controller.tower_positions
    for dc in range(8):
        for c in (col + dc, col - dc):
            if grid[row][c] and (row, c) not in taken:
                return row, c
    raise RuntimeError("no free build tile for the placement shot")


def stage_tank_fight(game, frame_ms: float) -> None:
    """Towers a tank is shooting at: the nearest is nearly dead and falls
    to its next shell, the others are hurt. Runs until the destroyed
    tower's blast and rubble are on screen."""
    from gameplay.combat.tank import Tank

    game._start_new_game()
    game.auto_pause = False
    center = battle_center(game)
    tiles = tiles_beside_path(game, 3, anchor=center, spacing_tiles=TOWER_SPACING_TILES)
    towers = [
        add_tower(game, tower_type, 1, row, col)
        for tower_type, (row, col) in zip((1, 2, 3), tiles)
    ]
    tank = Tank(1, 5, TANK_LEVEL, game.tilemap.waypoints, game.assets)
    advance_enemy(tank, game.tilemap.waypoints[0].distance_to(center) + TANK_LEAD)
    game.enemies.append(tank)
    by_distance = sorted(towers, key=lambda t: t.position.distance_to(tank.position))
    by_distance[0].hp = 15  # falls to the next shell
    for tower in by_distance[1:]:
        tower.hp = tower.max_hp * 2 // 3
    game.game_state.level = TANK_LEVEL
    game.game_state.money = MONEY
    game.camera.update_with_mouse = lambda *_: None
    game.camera.center_on(center)
    game._set_started(True)
    game._sync_game_ui()
    for _ in range(MAX_STAGE_FRAMES):
        step(game, frame_ms, 1)
        if game.death_feedback.tower_blasts:
            step(game, frame_ms, TANK_BLAST_FRAMES)
            return
    raise RuntimeError("the tank never destroyed a tower")


def stage_plane_run(
    game, frame_ms: float, level: int, clip: list[Image.Image] | None = None
):
    """The staged wave on the path's first straight with a plane crossing it
    and dropping bombs. Returns the plane; runs until its bombs have burst,
    adding each frame to `clip` if given."""
    from gameplay.towers import PLANE_TYPE
    from util.constants import TILE_SIZE

    game._start_new_game()
    game.auto_pause = False
    center = battle_center(game)
    fill_wave(game, level)
    game.game_state.plane_level = 2
    row = int(center.y // TILE_SIZE)
    plane = add_tower(game, PLANE_TYPE, 2, row, int(center.x // TILE_SIZE) - 9)
    game.game_state.money = MONEY
    game.camera.update_with_mouse = lambda *_: None
    game.camera.center_on(center)
    game._set_started(True)
    game._sync_game_ui()
    for _ in range(MAX_STAGE_FRAMES):
        step(game, frame_ms, 1)
        if clip is not None:
            clip.append(grab_frame(game))
        if len(game.bomb_impacts.explosions) >= 2 and plane.position.x > center.x:
            return plane
    raise RuntimeError("the plane's bombs never burst")


def pick_enemy(game, enemy_type: int):
    """The enemy of `enemy_type` farthest along the path."""
    candidates = [e for e in game.enemies if e.enemy_type == enemy_type]
    assert candidates, f"no enemy of type {enemy_type} on the path"
    return max(candidates, key=lambda e: e.waypoint_index)


def cover(frame: Image.Image, focus: tuple[float, float], zoom: float) -> Image.Image:
    """A COVER_SIZE crop of `frame` around `focus` (fractions of its size),
    `zoom` times tighter than the biggest crop of that shape, with the logo
    near the bottom."""
    width, height = frame.size
    crop_h = height / zoom
    crop_w = crop_h * COVER_SIZE[0] / COVER_SIZE[1]
    left = min(max(focus[0] * width - crop_w / 2, 0), width - crop_w)
    top = min(max(focus[1] * height - crop_h / 2, 0), height - crop_h)
    box = (round(left), round(top), round(left + crop_w), round(top + crop_h))
    image = frame.crop(box).resize(COVER_SIZE, Image.Resampling.LANCZOS)
    image = image.convert("RGBA")
    logo = Image.open(ROOT / "assets" / "images" / "branding" / "logo.png")
    logo_w = round(COVER_SIZE[0] * LOGO_WIDTH_SHARE)
    logo = logo.convert("RGBA").resize(
        (logo_w, round(logo.height * logo_w / logo.width)), Image.Resampling.LANCZOS
    )
    image.alpha_composite(
        logo, ((COVER_SIZE[0] - logo_w) // 2, COVER_SIZE[1] - logo.height - LOGO_MARGIN)
    )
    return image.convert("RGB")


def capture(
    out: Path,
    size=SIZE,
    frames: int = FPS * SECONDS,
    level: int = LEVEL,
    covers: Path | None = None,
) -> None:
    """Writes out/screenshots/*.png and out/preview.gif (and, with `covers`,
    the cover candidates into that folder). Needs the cwd to be the project
    root (the game loads config/ and assets/ relative to it)."""
    # Importing Game is harmless; constructing it only happens inside the guard.
    from app.game import Game
    from pygamine import SaveStore
    from util.constants import TILE_SIZE, WIN_WAVE

    frame_ms = 1000 / FPS
    clean: list[Image.Image] = []
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
        save_image(game, out, "05_settings_display.png")
        for i, key in enumerate(("audio", "game")):
            game._show_settings_tab(key)
            save_image(game, out, f"0{6 + i}_settings_{key}.png")
        game._show_settings_tab("display")
        game.panel_manager.current_panel = "game"

        # Placing a tower: the range ring on a free tile, the same pick on
        # the path (red: it can't be built on), and the buy tooltip.
        stage_battle(game, frame_ms, level)
        center = battle_center(game)
        game.tower_controller.buying_tower_type = 2
        pin_mouse(game, tile_center_screen(game, *free_tile_near(game, center, 2)))
        step(game, frame_ms, 2)
        save_image(game, out, "08_placing_tower.png")
        on_path = (int(center.y // TILE_SIZE), int(center.x // TILE_SIZE) - 3)
        pin_mouse(game, tile_center_screen(game, *on_path))
        step(game, frame_ms, 2)
        save_image(game, out, "09_unbuildable_tile.png")
        game.tower_controller.buying_tower_type = 0
        pin_mouse(game, game.panel_manager["game"]["buy_tower_2"].rect.center)
        step(game, frame_ms, 2)
        save_image(game, out, "10_buy_tooltip.png")
        pin_mouse(game, IDLE_MOUSE)

        stage_tank_fight(game, frame_ms)
        save_image(game, out, "11_tank_fight.png")

        plane = stage_plane_run(game, frame_ms, level)
        game.game_state.selected_tower = plane
        step(game, frame_ms, 1)
        save_image(game, out, "12_plane_bombing.png")

        run: list[Image.Image] = []
        stage_plane_run(game, frame_ms, level, run)
        save_gif(run, out / "plane-run.gif", FPS)

        stage_battle(game, frame_ms, level)
        enemy = pick_enemy(game, 1)
        enemy.hp = enemy.max_hp * 3 // 5
        game.game_state.selected_enemy = enemy
        step(game, frame_ms, 1)
        save_image(game, out, "13_enemy_hp.png")

        game.set_language("tr")
        pin_mouse(game, game.panel_manager["game"]["buy_tower_3"].rect.center)
        game.game_state.selected_enemy = None
        step(game, frame_ms, 2)
        save_image(game, out, "14_turkish.png")
        game.set_language("en")
        pin_mouse(game, IDLE_MOUSE)

        stage_battle(game, frame_ms, WIN_WAVE)
        game._trigger_victory()
        save_image(game, out, "15_victory.png")
        game._close_victory_popup()
        stage_battle(game, frame_ms, level)
        game.game_state.decrease_lives(game.game_state.lives)
        game._trigger_game_over()
        save_image(game, out, "16_game_over.png")
        game._close_gameover_popup()

        stage_battle(game, frame_ms, level)
        hide_hud(game, frame_ms)
        save_image(game, out, "17_hud_hidden.png")
        clean.append(grab_frame(game))
        stage_tank_fight(game, frame_ms)
        hide_hud(game, frame_ms)
        clean.append(grab_frame(game))
        stage_plane_run(game, frame_ms, level)
        hide_hud(game, frame_ms)
        clean.append(grab_frame(game))
    if covers is not None:
        covers.mkdir(parents=True, exist_ok=True)
        for i, (frame, (focus, zoom)) in enumerate(zip(clean, COVER_FRAMING), 1):
            path = covers / f"cover_{i}.png"
            cover(frame, focus, zoom).save(path, optimize=True)
            print(f"Captured {path}")


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
    parser.add_argument(
        "--covers",
        type=Path,
        help="also write 630x500 cover candidates into this folder",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    out = args.out.resolve()
    os.chdir(ROOT)
    before = {path: snapshot(path) for path in real_save_dirs()}
    try:
        capture(out, args.size, args.frames, args.level, args.covers)
    finally:
        pygame.quit()
        if any(snapshot(path) != saved for path, saved in before.items()):
            raise RuntimeError("Capture changed a real save directory")
    print("All real save directories unchanged.")


if __name__ == "__main__":
    main()
