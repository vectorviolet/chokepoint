"""scripts/make_playtest_save.py (#63): the play-test save it writes loads in
a real Game() as described, and it refuses unsafe output folders."""

import importlib.util
import json
import math
import os
import shutil
import subprocess
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
    assert game.audio.master_volume() == 0
    assert game.audio.music_volume() == 0
    assert game.audio.sfx_volume() == 0
    assert not game.audio.is_music_paused  # music on, just at volume 0
    assert game.window_settings()["window_mode"] == "windowed"
    assert game.auto_pause is False
    settings = json.loads((out / "settings.json").read_text())
    assert settings["auto_pause_between_waves"] is False

    assert game._has_saved_game()
    game._load_game()  # what the play menu's Continue does
    gs = game.game_state
    assert game.panel_manager.current_panel == "game"
    assert gs.money == script.DEFAULT_MONEY == 100_000
    assert gs.level == script.DEFAULT_LEVEL == 10
    assert not gs.is_started  # paused
    assert gs.lives == game._starting_lives

    wm = game.wave_manager
    assert wm.spawned_count == math.ceil(wm.wave_size / 2) < wm.wave_size
    assert len(game.enemies) == wm.spawned_count  # all on the path
    assert any(e.waypoint_index > 1 for e in game.enemies)  # walking it

    from gameplay.towers import GROUND_TOWER_TYPES, PLANE_TYPE

    ground = sorted((t.tower_type, t.level) for t in game.towers if not t.is_flying)
    expected = [
        (tower_type, level)
        for tower_type in GROUND_TOWER_TYPES
        for level in range(1, tower_config.max_levels[tower_type - 1] + 1)
    ]
    assert ground == expected
    tiles = [t.get_blocking_position() for t in game.towers if not t.is_flying]
    assert len(set(tiles)) == len(tiles)
    assert all(game.tilemap.buildable_grid[r][c] for r, c in tiles)

    assert gs.plane_level == 2
    planes = [t for t in game.towers if t.is_flying]
    assert len(planes) == 1 and planes[0].level == 2
    assert planes[0].tower_type == PLANE_TYPE
    assert not planes[0].should_remove()  # in the air over the map
    assert planes[0].col == 0  # at the start of its flight: crosses the map


@pytest.mark.parametrize("level", [1, 30, 100])
def test_any_level_gives_a_paused_half_spawned_wave(script, tmp_path, level):
    """Past the towers (and the win wave) too: a long wave whose first
    enemies reach the end while it fills mustn't end the run (#64 review)."""
    from app.game import Game

    reports = []
    script.make_playtest_save(tmp_path / "saves", level=level, report=reports.append)
    game = Game()
    game._load_game()
    gs = game.game_state
    assert gs.level == level
    assert gs.lives == game._starting_lives
    assert not gs.is_started
    wm = game.wave_manager
    assert wm.spawned_count == math.ceil(wm.wave_size / 2)
    # In long waves the first enemies reach the end while it fills: the
    # report says how many are really on the path.
    assert 0 < len(game.enemies) <= wm.spawned_count
    assert f"{len(game.enemies)} on the path" in reports[0]
    assert len(game.towers) == len(script.tower_specs(game.tower_config)) + 1


def test_cwd_is_restored(script, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script.main(["--out", "relative_out"])
    assert Path.cwd() == tmp_path
    # A relative --out is the caller's, not the repository's.
    assert (tmp_path / "relative_out" / "save.json").exists()


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
    refused holds the repository's .git (a folder, or a file in a
    submodule)."""
    try:
        subprocess.run(
            ["git", "-C", str(script.ROOT), "rev-parse", "--git-common-dir"],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    assert (script.main_checkout() / ".git").exists()


def _no_git(monkeypatch, script, root):
    def fail(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(script.subprocess, "run", fail)
    monkeypatch.setattr(script, "ROOT", root)


def test_without_git_a_worktree_finds_the_main_checkout(script, tmp_path, monkeypatch):
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    gitdir = main / ".git" / "worktrees" / "wt"
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n")
    _no_git(monkeypatch, script, worktree)
    assert script.main_checkout() == main.resolve()
    with pytest.raises(script.RefusedError):
        script.check_out_dir((main / "saves").resolve(), True, [])
    script.check_out_dir((worktree / "saves").resolve(), True, [])  # allowed


def test_without_git_a_submodule_worktree_finds_the_submodule(
    script, tmp_path, monkeypatch
):
    """A linked worktree of a submodule: its common git folder is
    <super>/.git/modules/<name>, whose core.worktree is the submodule's
    main checkout."""
    sub = tmp_path / "super" / "sub"
    sub.mkdir(parents=True)
    modules = tmp_path / "super" / ".git" / "modules" / "sub"
    (modules / "worktrees" / "wt").mkdir(parents=True)
    (modules / "config").write_text("[core]\n\tworktree = ../../../sub\n")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {modules / 'worktrees' / 'wt'}\n")
    _no_git(monkeypatch, script, worktree)
    assert script.main_checkout() == sub.resolve()


def test_without_git_a_plain_copy_is_its_own_checkout(script, tmp_path, monkeypatch):
    _no_git(monkeypatch, script, tmp_path)
    assert script.main_checkout() == tmp_path
    with pytest.raises(script.RefusedError):
        script.check_out_dir((tmp_path / "saves").resolve(), True, [])


def test_unknown_checkout_refuses_saves_folders_outside_it(
    script, tmp_path, monkeypatch
):
    root = tmp_path / "wt"
    root.mkdir()
    (root / ".git").write_text("not a gitdir line")
    _no_git(monkeypatch, script, root)
    assert script.main_checkout() is None
    for out in (tmp_path / "saves", tmp_path / "other" / "saves" / "sub"):
        with pytest.raises(script.RefusedError, match="main checkout"):
            script.check_out_dir(out.resolve(), True, [])
    script.check_out_dir((root / "saves").resolve(), True, [])  # its own
    script.check_out_dir((tmp_path / "elsewhere").resolve(), True, [])


def test_saves_is_refused_in_any_letter_case(script, tmp_path, monkeypatch):
    """Windows paths are case-insensitive: .../Saves is the real saves/.
    Simulated here so it's checked on every OS."""
    main = tmp_path / "main"
    monkeypatch.setattr(script, "_normcase", str.lower)
    monkeypatch.setattr(script, "main_checkout", lambda: main)
    for name in ("Saves", "SAVES", "saves"):
        with pytest.raises(script.RefusedError, match="real saves"):
            script.check_out_dir(main / name / "x", True, [])
    # ...and so is the fallback guard's check for a folder named saves.
    monkeypatch.setattr(script, "main_checkout", lambda: None)
    with pytest.raises(script.RefusedError, match="main checkout"):
        script.check_out_dir(tmp_path / "other" / "Saves", True, [])


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive paths: Windows")
def test_saves_is_refused_in_any_letter_case_on_windows(script, tmp_path, monkeypatch):
    main = tmp_path / "main"
    monkeypatch.setattr(script, "main_checkout", lambda: main)
    with pytest.raises(script.RefusedError, match="real saves"):
        script.check_out_dir(Path(str(main / "SaVeS").upper()), True, [])


# ── with real git repositories ───────────────────────────────────────────────


def _git(*args, cwd):
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "protocol.file.allow=always",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git("init", "-q", cwd=path)
    (path / "f.txt").write_text("x")
    _git("add", "f.txt", cwd=path)
    _git("commit", "-q", "-m", "init", cwd=path)
    return path


@pytest.fixture
def git_available():
    if shutil.which("git") is None:
        pytest.skip("git not installed")


def test_git_linked_worktree(script, tmp_path, monkeypatch, git_available):
    main = _repo(tmp_path / "main")
    _git("worktree", "add", "-q", str(tmp_path / "wt"), cwd=main)
    monkeypatch.setattr(script, "ROOT", (tmp_path / "wt").resolve())
    assert script._key(script.main_checkout()) == script._key(main.resolve())


def test_git_submodule_is_its_own_checkout(
    script, tmp_path, monkeypatch, git_available
):
    """Its git folder lives in <super>/.git/modules: the real saves are
    still the submodule's own, not the superproject's .git/modules/saves."""
    sub_origin = _repo(tmp_path / "sub_origin")
    sup = _repo(tmp_path / "super")
    _git("submodule", "add", "-q", str(sub_origin), "sub", cwd=sup)
    sub = (sup / "sub").resolve()
    monkeypatch.setattr(script, "ROOT", sub)
    assert script._key(script.main_checkout()) == script._key(sub)
    with pytest.raises(script.RefusedError, match="real saves"):
        script.check_out_dir(sub / "saves", True, [])


def test_copy_nested_in_another_repo_is_its_own_checkout(
    script, tmp_path, monkeypatch, git_available
):
    """git answers for the outer repository; the copy holds the real saves."""
    outer = _repo(tmp_path / "outer")
    copy = outer / "games" / "chokepoint"
    copy.mkdir(parents=True)
    monkeypatch.setattr(script, "ROOT", copy.resolve())
    assert script.main_checkout() == copy.resolve()
    with pytest.raises(script.RefusedError, match="real saves"):
        script.check_out_dir((copy / "saves").resolve(), True, [])


def test_leaves_the_default_saves_folder_alone(script, tmp_path):
    out = tmp_path / "elsewhere"
    script.main(["--out", str(out)])
    # The SaveStore default (tmp_path/saves via saves_in_tmp) stays untouched:
    # the build's own Game() saved into a redirected temporary folder.
    assert not (tmp_path / "saves").exists()
    assert SaveStore("save").directory == tmp_path / "saves"
