"""scripts/capture_readme.py (#87): it runs headless at a small size, writes
every README image into the folder it's given, writes the same bytes on a
second run, and never touches the real save directories."""

import importlib.util
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "capture_readme.py"
SIZE = (960, 540)
FRAMES = 3
NAMES = [
    "preview.gif",
    "screenshots/01_menu.png",
    "screenshots/02_gameplay.png",
    "screenshots/03_upgrades.png",
    "screenshots/04_pause.png",
    "screenshots/05_settings.png",
]


def _load_script():
    spec = importlib.util.spec_from_file_location("capture_readme", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capture_is_complete_reproducible_and_leaves_real_saves_alone(tmp_path):
    script = _load_script()
    snapshot = script.snapshot
    real = script.real_save_dirs()
    before = {path: snapshot(path) for path in real}

    runs = [tmp_path / "first", tmp_path / "second"]
    for out in runs:
        script.capture(out, size=SIZE, frames=FRAMES)

    for name in NAMES:
        with Image.open(runs[0] / name) as image:
            assert image.size == SIZE
            if name.endswith(".gif"):
                assert image.n_frames == FRAMES
        assert (runs[0] / name).read_bytes() == (runs[1] / name).read_bytes(), name
    assert {path: snapshot(path) for path in real} == before
