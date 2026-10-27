"""scripts/make_playtest_save.py (#63): the play-test save it writes loads in
a real Game() as described, and it refuses unsafe output folders."""

import importlib.util
import json
from pathlib import Path

import pytest

from pygamine import SaveStore

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make_playtest_save.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("make_playtest_save", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


def test_save_loads_in_a_real_game_as_described(script, tmp_path, tower_config):
    from app.game import Game

    # saves_in_tmp points every SaveStore at tmp_path/saves: write there,
    # then a fresh Game() reads its settings there and Continue loads it.
    out = tmp_path / "saves"
    script.main(["--out", str(out)])
    assert sorted(p.name for p in out.iterdir()) == ["save.json", "settings.json"]

    game = Game()
    assert game.audio.music_volume() == 0
    assert game.audio.sfx_volume() == 0
    assert not game.audio.is_music_paused  # music on, just at volume 0
    assert game.window_settings()["window_mode"] == "windowed"

    assert game._has_saved_game()
    game._load_game()  # what the play menu's Continue does
    gs = game.game_state
    assert game.panel_manager.current_panel == "game"
    assert gs.money == script.DEFAULT_MONEY == 100_000
    assert gs.level == script.DEFAULT_LEVEL == 10
    assert not gs.is_started  # paused
    assert gs.lives == game._starting_lives

    queue = game.wave_manager._spawn_queue
    spawned = game.wave_manager._queue_index
    assert 0 < spawned < len(queue)
    assert spawned >= len(queue) // 2
    assert len(game.enemies) == spawned  # all on the path, none killed yet
    assert any(e.waypoint_index > 1 for e in game.enemies)  # walking it

    ground = sorted((t.tower_type, t.level) for t in game.towers if not t.is_flying)
    expected = [
        (tower_type, level)
        for tower_type, max_level in enumerate(tower_config.max_levels, start=1)
        if tower_type != 4
        for level in range(1, max_level + 1)
    ]
    assert ground == expected
    tiles = [t.get_blocking_position() for t in game.towers if not t.is_flying]
    assert len(set(tiles)) == len(tiles)
    assert all(game.tilemap.buildable_grid[r][c] for r, c in tiles)

    assert gs.plane_level == 2
    planes = [t for t in game.towers if t.is_flying]
    assert len(planes) == 1 and planes[0].level == 2
    assert not planes[0].should_remove()  # in the air over the map


def test_options_set_money_and_level(script, tmp_path):
    script.main(["--out", str(tmp_path), "--money", "1234", "--level", "3"])
    saved = json.loads((tmp_path / "save.json").read_text())["game_state"]
    assert saved["money"] == 1234
    assert saved["level"] == 3


def test_out_is_required(script):
    with pytest.raises(SystemExit):
        script.parse_args([])


def test_refuses_to_overwrite_without_flag(script, tmp_path):
    (tmp_path / "save.json").write_text('{"keep": 1}')
    with pytest.raises(SystemExit, match="--overwrite"):
        script.main(["--out", str(tmp_path)])
    assert (tmp_path / "save.json").read_text() == '{"keep": 1}'
    assert not (tmp_path / "settings.json").exists()

    script.main(["--out", str(tmp_path), "--overwrite"])
    assert "game_state" in json.loads((tmp_path / "save.json").read_text())


@pytest.mark.parametrize("sub", ["saves", "saves/nested"])
def test_refuses_the_main_checkouts_real_saves(script, tmp_path, monkeypatch, sub):
    main = tmp_path / "main_checkout"
    monkeypatch.setattr(script, "main_checkout", lambda: main)
    target = main / sub
    with pytest.raises(SystemExit, match="real saves"):
        script.main(["--out", str(target), "--overwrite"])
    assert not target.exists()


def test_main_checkout_is_found_by_git(script):
    """From the main checkout or any worktree, the folder whose saves/ is
    refused holds the shared .git."""
    assert (script.main_checkout() / ".git").is_dir()


def test_leaves_the_default_saves_folder_alone(script, tmp_path):
    out = tmp_path / "elsewhere"
    script.main(["--out", str(out)])
    # The SaveStore default (tmp_path/saves via saves_in_tmp) stays untouched:
    # the build's own Game() saved into a redirected temporary folder.
    assert not (tmp_path / "saves").exists()
    assert SaveStore("save").directory == tmp_path / "saves"
