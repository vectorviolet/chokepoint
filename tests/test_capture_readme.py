"""scripts/capture_readme.py (#87, #13): it writes every README and store image
(and the cover candidates) into the folder it's given, the same bytes on a
second run, and only ever into its own temporary saves.

The capture runs in a subprocess (it sets SDL drivers, sys.path and a window
of its own), at a tiny size, wave 1 and a few frames. In there, SaveStore's
default folder -- where a Game() really saves -- is pointed at a folder this
test watches, so only the script's own saves_redirected() keeps the game's
settings and save out of it."""

import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIZE = (640, 360)
FRAMES = 3
FPS = 10  # capture_readme.FPS
NAMES = [
    "preview.gif",
    "plane-run.gif",
    "screenshots/01_menu.png",
    "screenshots/02_gameplay.png",
    "screenshots/03_upgrades.png",
    "screenshots/04_pause.png",
    "screenshots/05_settings_display.png",
    "screenshots/06_settings_audio.png",
    "screenshots/07_settings_game.png",
    "screenshots/08_placing_tower.png",
    "screenshots/09_unbuildable_tile.png",
    "screenshots/10_buy_tooltip.png",
    "screenshots/11_tank_fight.png",
    "screenshots/12_plane_bombing.png",
    "screenshots/13_enemy_hp.png",
    "screenshots/14_turkish.png",
    "screenshots/15_victory.png",
    "screenshots/16_game_over.png",
    "screenshots/17_hud_hidden.png",
]
COVERS = ["covers/cover_1.png", "covers/cover_2.png", "covers/cover_3.png"]
COVER_SIZE = (630, 500)  # itch.io's cover size
# Runs the script as __main__ with SaveStore's default folder moved to
# argv[1]; the rest of argv goes to the script.
RUNNER = """
import runpy, sys
sys.path[:0] = ["src", "src/pygamine"]
from pygamine import SaveStore
SaveStore.__init__.__defaults__ = (sys.argv[1],)
sys.argv = ["capture_readme.py", *sys.argv[2:]]
runpy.run_path("scripts/capture_readme.py", run_name="__main__")
"""


def _capture(out: Path, watched_saves: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            RUNNER,
            str(watched_saves),
            "--out",
            str(out),
            "--size",
            f"{SIZE[0]}x{SIZE[1]}",
            "--frames",
            str(FRAMES),
            "--level",
            "1",
            "--covers",
            str(out / "covers"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_capture_is_complete_reproducible_and_keeps_out_of_real_saves(tmp_path):
    watched_saves = tmp_path / "real_saves"
    runs = [tmp_path / "first", tmp_path / "second"]
    for out in runs:
        _capture(out, watched_saves)

    assert not watched_saves.exists(), "the capture wrote into the real saves"
    for name in NAMES:
        with Image.open(runs[0] / name) as image:
            assert image.size == SIZE
            if name.endswith(".gif"):
                assert image.info["loop"] == 0, name
            if name == "preview.gif":
                # Pillow merges identical frames; their durations add up.
                total = 0
                for i in range(image.n_frames):
                    image.seek(i)
                    total += image.info["duration"]
                assert total == FRAMES * 1000 // FPS
        assert (runs[0] / name).read_bytes() == (runs[1] / name).read_bytes(), name
    for name in COVERS:
        with Image.open(runs[0] / name) as image:
            assert image.size == COVER_SIZE
        assert (runs[0] / name).read_bytes() == (runs[1] / name).read_bytes(), name
