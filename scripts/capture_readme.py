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
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "pygamine"))
sys.path.insert(0, str(ROOT / "scripts"))

import pygame
from PIL import Image, ImageFilter

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
LOGO_WIDTH_SHARE = 0.6
# The cover logo: one transparent PNG, scaled to this share of the cover's
# width. To use a redesigned title, replace this file (or change the path).
LOGO_PATH = ROOT / "assets" / "images" / "branding" / "logo.png"
# "plain", "outline" (dark outline and drop shadow), "band" (a translucent
# dark band behind it) or "both" (the outlined logo on the band).
LOGO_STYLE = "both"
LOGO_OUTLINE_PX = 3  # a dark outline this thick around the letters
LOGO_SHADOW_OFFSET = 3
LOGO_SHADOW_BLUR = 3
LOGO_SHADOW_OPACITY = 0.6
LOGO_BAND_OPACITY = 0.6  # a black band across the cover behind the logo
LOGO_BAND_PADDING = 6
LOGO_MARGIN = 8  # the logo sits at the top, over the grass above the sand


@dataclass(frozen=True)
class CoverScene:
    """One cover candidate: the pattern of tower types (each at its top level) filling
    the build tiles along the upper road, planes and enemies on it, the wave round, and the crop
    (center as fractions of the frame, zoom)."""

    towers: tuple[int, ...]
    planes: int
    enemies: tuple[int, ...]
    level: int
    focus: tuple[float, float]
    zoom: float


# The cover frames come from COVER_FRAMES frames of each scene, after a warm-up.
COVER_FRAMES = 160
COVER_WARMUP = 20
COVER_TOWER_SPACING = 1
COVER_TOWER_COUNT = 24
# Tiles from the road's middle: the two rows of build tiles above it, one below.
COVER_TOWER_BAND = (0.9, 3.2)
COVER_ENEMY_GAP = 70  # px along the road between the staged enemies
COVER_ENEMY_LEAD = 150  # px the middle one stands before the road's center
COVER_SCENES = (
    # Tank fight: tanks and heavies under fire from every ground type.
    CoverScene(
        (3, 2, 1, 3, 2, 1, 2, 3, 1, 2), 0, (5, 4, 3, 5, 2, 4, 1), 25, (0.6, 0.43), 2.05
    ),
    # Plane bomb run: two planes over the road, guns and missiles below.
    CoverScene(
        (1, 2, 1, 3, 1, 2, 1, 2), 2, (1, 2, 1, 3, 2, 1, 4), 22, (0.6, 0.43), 2.05
    ),
    # Missile swarm: mostly missile towers and a fast crowd.
    CoverScene(
        (2, 2, 2, 2, 3, 2, 2, 1, 2, 2), 1, (2, 2, 3, 2, 4, 2, 3), 24, (0.6, 0.43), 2.05
    ),
)


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


def place_enemy(game, enemy_type: int, level: int, distance: float) -> None:
    """An enemy of `enemy_type` `distance` px along the path from its start."""
    from gameplay.combat.enemy import Enemy
    from gameplay.combat.tank import Tank

    cls = Tank if enemy_type in (5, 6) else Enemy
    enemy = cls(
        1000 + len(game.enemies),
        enemy_type,
        level,
        game.tilemap.waypoints,
        game.assets,
    )
    advance_enemy(enemy, distance)
    game.enemies.append(enemy)


def busyness(game) -> int:
    """How much is going on: shots and bombs in flight, bursts, planes."""
    from gameplay.towers import PlaneTower

    shots = sum(len(t.bullets) for t in game.towers)
    shots += sum(len(e.bullets) for e in game.enemies if hasattr(e, "bullets"))
    shots += len(game.orphan_shots)
    bursts = len(game.bomb_impacts.explosions) + len(game.death_feedback.enemy_blasts)
    bursts += 2 * len(game.death_feedback.tower_blasts)
    planes = sum(isinstance(t, PlaneTower) for t in game.towers)
    return shots + 3 * bursts + 2 * planes


def stage_cover_scene(game, frame_ms: float, scene: CoverScene) -> Image.Image:
    """A crowded stretch of the upper road: upgraded towers of mixed types
    on both sides, planes bombing, tanks and a wave on the road. Runs
    COVER_FRAMES frames and returns the busiest one, HUD hidden, the camera
    on the road; the cover crop leaves the lower road out."""
    from gameplay.towers import PLANE_TYPE
    from util.constants import TILE_SIZE

    game._start_new_game()
    game.auto_pause = False
    center = battle_center(game)
    fill_wave(game, scene.level)
    tiles = tiles_beside_path(
        game,
        COVER_TOWER_COUNT,
        anchor=center,
        band_tiles=COVER_TOWER_BAND,
        spacing_tiles=COVER_TOWER_SPACING,
    )
    for tower_type, (row, col) in zip(cycle(scene.towers), tiles):
        max_level = game.tower_config.max_levels[tower_type - 1]
        add_tower(game, tower_type, max_level, row, col)
    game.game_state.plane_level = 2
    row = int(center.y // TILE_SIZE)
    for i in range(scene.planes):
        col = int(center.x // TILE_SIZE) - 9 - i * 7
        add_tower(game, PLANE_TYPE, 2, row, col)
    ahead = game.tilemap.waypoints[0].distance_to(center)
    for i, enemy_type in enumerate(scene.enemies):
        place_enemy(
            game,
            enemy_type,
            scene.level,
            ahead - COVER_ENEMY_LEAD + (i - 3) * COVER_ENEMY_GAP,
        )
    game.game_state.money = MONEY
    game.camera.update_with_mouse = lambda *_: None
    game.camera.center_on(center)
    game._set_started(True)
    game._sync_game_ui()
    hide_hud(game, frame_ms)
    best, best_score = None, -1
    for frame in range(COVER_FRAMES):
        step(game, frame_ms, 1)
        score = busyness(game)
        if frame >= COVER_WARMUP and score > best_score:
            best, best_score = grab_frame(game), score
    assert best is not None
    return best


def logo_layers(logo: Image.Image, style: str) -> Image.Image:
    """`logo` (RGBA) ready to composite: as is ("plain"), or on a dark
    outline and a soft drop shadow ("outline"), padded by their size."""
    if style in ("plain", "band"):
        return logo
    assert style in ("outline", "both"), f"unknown logo style {style!r}"
    pad = LOGO_OUTLINE_PX + LOGO_SHADOW_OFFSET + LOGO_SHADOW_BLUR * 3
    canvas = Image.new("RGBA", (logo.width + 2 * pad, logo.height + 2 * pad))
    canvas.paste(logo, (pad, pad))
    alpha = canvas.getchannel("A")
    outline = alpha.filter(ImageFilter.MaxFilter(2 * LOGO_OUTLINE_PX + 1))
    shadow = Image.new("L", canvas.size)
    shadow.paste(outline, (LOGO_SHADOW_OFFSET, LOGO_SHADOW_OFFSET))
    shadow = shadow.filter(ImageFilter.GaussianBlur(LOGO_SHADOW_BLUR))
    shadow = shadow.point(lambda v: round(v * LOGO_SHADOW_OPACITY))
    layered = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layered.paste((0, 0, 0, 255), mask=shadow)
    dark = Image.new("RGBA", canvas.size, (10, 10, 10, 255))
    layered.paste(dark, mask=outline)
    layered.alpha_composite(canvas)
    return layered


def cover(
    frame: Image.Image,
    focus: tuple[float, float],
    zoom: float,
    logo_style: str = LOGO_STYLE,
) -> Image.Image:
    """A COVER_SIZE crop of `frame` around `focus` (fractions of its size),
    `zoom` times tighter than the biggest crop of that shape, with the logo
    at the top in `logo_style` (see LOGO_STYLE)."""
    width, height = frame.size
    crop_h = height / zoom
    crop_w = crop_h * COVER_SIZE[0] / COVER_SIZE[1]
    left = min(max(focus[0] * width - crop_w / 2, 0), width - crop_w)
    top = min(max(focus[1] * height - crop_h / 2, 0), height - crop_h)
    box = (round(left), round(top), round(left + crop_w), round(top + crop_h))
    image = frame.crop(box).resize(COVER_SIZE, Image.Resampling.LANCZOS)
    image = image.convert("RGBA")
    logo = Image.open(LOGO_PATH)
    logo_w = round(COVER_SIZE[0] * LOGO_WIDTH_SHARE)
    logo = logo.convert("RGBA").resize(
        (logo_w, round(logo.height * logo_w / logo.width)), Image.Resampling.LANCZOS
    )
    x = (COVER_SIZE[0] - logo_w) // 2
    if logo_style in ("band", "both"):
        band_h = LOGO_MARGIN + logo.height + LOGO_BAND_PADDING
        band = Image.new(
            "RGBA", (COVER_SIZE[0], band_h), (0, 0, 0, round(255 * LOGO_BAND_OPACITY))
        )
        image.alpha_composite(band, (0, 0))
    layered = logo_layers(logo, logo_style)
    inset = (layered.width - logo.width) // 2
    image.alpha_composite(layered, (x - inset, LOGO_MARGIN - inset))
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
        if covers is not None:
            covers.mkdir(parents=True, exist_ok=True)
            for i, scene in enumerate(COVER_SCENES, 1):
                frame = stage_cover_scene(game, frame_ms, scene)
                path = covers / f"cover_{i}.png"
                cover(frame, scene.focus, scene.zoom).save(path, optimize=True)
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
