"""scripts/build_web.py (#152): what the web stage includes and leaves out.
pygbag itself is never run here (it needs internet)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_web.py"


@pytest.fixture(scope="module")
def build_web():
    spec = importlib.util.spec_from_file_location("build_web", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def staged(build_web, tmp_path_factory):
    """Staged once for the module; the tests only read it."""
    return build_web.stage(tmp_path_factory.mktemp("web") / "chokepoint")


def _files(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


def test_stage_has_the_entry_point_as_main_py(staged):
    real = SCRIPT.parent.parent / "web" / "main.py"
    assert (staged / "main.py").read_bytes() == real.read_bytes()


def test_stage_has_the_game_engine_config_and_assets(staged):
    assert (staged / "src" / "app" / "game.py").is_file()
    assert (staged / "src" / "pygamine" / "pygamine" / "__init__.py").is_file()
    assert (staged / "config" / "settings.yaml").is_file()
    assert (staged / "assets" / "sounds" / "music" / "bg.ogg").is_file()
    assert (staged / "assets" / "SOURCES.yaml").is_file()
    # Logos the web menu still draws (config/assets.yaml, source: branding).
    branding = staged / "src" / "pygamine" / "pygamine" / "branding"
    assert (branding / "vectorviolet" / "lockup-dark-solid.png").is_file()


def test_stage_leaves_out_everything_the_browser_never_uses(staged):
    files = _files(staged)
    top = {f.split("/")[0] for f in files}
    assert top == {"main.py", "src", "config", "assets"}  # no tests, saves, .git
    assert not any(f.startswith("src/pygamine/") and "/tests/" in f for f in files)
    assert not any("__pycache__" in f or f.endswith(".pyc") for f in files)
    assert "assets/maps/tiled_project.tiled-project" not in files
    assert not any("branding/vectorviolet/splash" in f for f in files)
    assert not any(f.endswith(".mp3") for f in files)
    # Only the engine's package is staged, not its repo (docs, tests, lock file).
    assert {f.split("/")[2] for f in files if f.startswith("src/pygamine/")} == {
        "pygamine"
    }


def test_stage_has_every_module_and_package_of_src(staged):
    src = SCRIPT.parent.parent / "src"
    for item in src.iterdir():
        if item.name in ("pygamine", "__pycache__") or item.suffix == ".pyc":
            continue
        assert (staged / "src" / item.name).exists(), f"src/{item.name} not staged"


def test_stage_copies_top_level_modules_of_src(build_web, tmp_path):
    root = tmp_path / "repo"
    (root / "web").mkdir(parents=True)
    (root / "web" / "main.py").write_text("")
    (root / "src" / "pygamine" / "pygamine").mkdir(parents=True)
    (root / "src" / "pygamine" / "pygamine" / "__init__.py").write_text("")
    (root / "src" / "helper.py").write_text("X = 1")
    (root / "config").mkdir()
    (root / "assets").mkdir()
    staged = build_web.stage(tmp_path / "out", root=root)
    assert (staged / "src" / "helper.py").read_text() == "X = 1"


def test_stage_is_not_pyinstallers_work_path(build_web):
    assert build_web.STAGE_DIR != build_web.BUILD_DIR / "chokepoint"
    assert build_web.STAGE_DIR.name == "chokepoint"  # pygbag's app name


def test_stage_vendors_pure_python_yaml_only(staged):
    yaml_files = _files(staged / "src" / "yaml")
    assert "__init__.py" in yaml_files
    assert not any(f.endswith((".so", ".pyd")) for f in yaml_files)


def test_stage_replaces_an_old_stage(build_web, tmp_path):
    dest = tmp_path / "chokepoint"
    dest.mkdir()
    (dest / "stale.txt").write_text("old")
    build_web.stage(dest)
    assert not (dest / "stale.txt").exists()


def test_stage_stops_with_a_clear_message_without_the_submodule(build_web, tmp_path):
    root = tmp_path / "repo"
    (root / "web").mkdir(parents=True)
    (root / "web" / "main.py").write_text("")
    with pytest.raises(SystemExit, match="submodule"):
        build_web.stage(tmp_path / "out", root=root)


def test_pygbag_is_pinned_and_run_with_can_close(build_web, monkeypatch, tmp_path):
    calls = []

    class Done:
        returncode = 0

    def fake_run(command):
        calls.append(command)
        index = tmp_path / "build" / "web" / "index.html"
        index.parent.mkdir(parents=True)
        index.write_text("<html>")
        return Done()

    monkeypatch.setattr(build_web.shutil, "which", lambda name: "uvx")
    monkeypatch.setattr(build_web.subprocess, "run", fake_run)
    build_web.run_pygbag(tmp_path)
    (command,) = calls
    assert f"pygbag=={build_web.PYGBAG_VERSION}" in command
    assert command[command.index("--can_close") + 1] == "1"
    assert command[-2:] == ["--build", str(tmp_path)]


def test_pygbag_failure_is_retried_once_then_reported(build_web, monkeypatch, tmp_path):
    attempts = []

    class Failed:
        returncode = 1

    monkeypatch.setattr(build_web.shutil, "which", lambda name: "uvx")
    monkeypatch.setattr(
        build_web.subprocess, "run", lambda command: attempts.append(1) or Failed()
    )
    with pytest.raises(SystemExit, match="internet"):
        build_web.run_pygbag(tmp_path)
    assert len(attempts) == 2


def test_pygbag_success_on_the_retry_is_accepted(build_web, monkeypatch, tmp_path):
    results = [1, 0]

    class Result:
        def __init__(self, code):
            self.returncode = code

    def fake_run(command):
        code = results.pop(0)
        if code == 0:
            index = tmp_path / "build" / "web" / "index.html"
            index.parent.mkdir(parents=True)
            index.write_text("<html>")
        return Result(code)

    monkeypatch.setattr(build_web.shutil, "which", lambda name: "uvx")
    monkeypatch.setattr(build_web.subprocess, "run", fake_run)
    build_web.run_pygbag(tmp_path)
    assert results == []
