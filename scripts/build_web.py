"""Build the browser version of the game with pygbag (issue #152, ADR 0010).

    uv run python scripts/build_web.py              # stage, build, write build/web/
    uv run python scripts/build_web.py --stage-only # only stage (no pygbag, no internet)

The staged folder (build/web-stage/chokepoint/) holds only what the web build needs:
`web/main.py` as `main.py`, the app's `src/` packages, pygamine's package
(without its splash clip, which the web build never shows), `config/`,
`assets/` (without the Tiled editor project), and PyYAML's pure-Python files
(the browser has no compiled PyYAML). No tests, no .git, no saves.

pygbag is pinned and run through `uvx`; it downloads the browser runtime, so
the build needs internet. The result is build/web/ with index.html at its root,
ready to zip or to push to itch.io's html5 channel. The loading and "click to
play" page is our own template (web/template.tmpl) instead of pygbag's stock one;
the logo it shows is copied next to index.html.
"""

import argparse
import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
# Not build/chokepoint: PyInstaller's work path is there. The folder's own name
# is the app name pygbag gives the bundle (chokepoint.apk).
STAGE_DIR = BUILD_DIR / "web-stage" / "chokepoint"
OUT_DIR = BUILD_DIR / "web"

PYGBAG_VERSION = "0.9.3"
# pygbag 0.9.3 ships its own browser Python; this only picks the host
# interpreter that runs the pygbag tool itself.
PYGBAG_HOST_PYTHON = "3.12"

ENTRY_POINT = ROOT / "web" / "main.py"
# The loading / "click to play" page (pygbag's stock one is unreadable).
TEMPLATE = ROOT / "web" / "template.tmpl"
# The logo the template shows, copied to build/web/logo.png.
LOGO = ROOT / "assets" / "images" / "branding" / "logo.png"
# Copied whole into the stage.
COPIED_DIRS = ("config", "assets")
# Paths (relative to the folder named in the comment) the web build never reads.
EXCLUDED_ASSETS = ("maps/tiled_project.tiled-project",)  # the Tiled editor project
EXCLUDED_PYGAMINE = (
    "branding/vectorviolet/splash",  # video frames of the splash screen
    "branding/vectorviolet/splash.ogg",
)
# Never copied from anywhere.
_IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")


def _ignore(
    root: Path, excluded: tuple[str, ...]
) -> Callable[[str, list[str]], set[str]]:
    """A shutil.copytree `ignore` that also drops the `excluded` paths of `root`."""
    skip = {Path(rel).as_posix() for rel in excluded}

    def ignore(directory: str, names: list[str]) -> set[str]:
        dropped = set(_IGNORED(directory, names))
        here = Path(directory).relative_to(root)
        dropped.update(n for n in names if (here / n).as_posix() in skip)
        return dropped

    return ignore


def vendor_yaml(dest_src: Path) -> None:
    """Copy PyYAML's pure-Python package into `dest_src/yaml`."""
    spec = importlib.util.find_spec("yaml")
    assert spec is not None and spec.origin is not None, "PyYAML is not installed"
    package = Path(spec.origin).parent
    shutil.copytree(
        package,
        dest_src / "yaml",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so", "*.pyd"),
    )


def stage(dest: Path = STAGE_DIR, root: Path = ROOT) -> Path:
    """Build a clean stage folder at `dest` and return it. An old one is removed."""
    entry = root / "web" / "main.py"
    if not entry.is_file():
        raise SystemExit(f"Missing web entry point: {entry}")
    pygamine = root / "src" / "pygamine" / "pygamine"
    if not pygamine.is_dir():
        raise SystemExit(
            f"Missing {pygamine}: run `git submodule update --init` first."
        )
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    shutil.copy2(entry, dest / "main.py")
    src = dest / "src"
    src.mkdir()
    for item in sorted((root / "src").iterdir()):
        # src/pygamine is the engine's repo: only its package goes in.
        if item.name in ("pygamine", "__pycache__") or item.suffix == ".pyc":
            continue
        if item.is_dir():
            shutil.copytree(item, src / item.name, ignore=_IGNORED)
        else:
            shutil.copy2(item, src / item.name)
    shutil.copytree(
        pygamine,
        src / "pygamine" / "pygamine",
        ignore=_ignore(pygamine, EXCLUDED_PYGAMINE),
    )
    for name in COPIED_DIRS:
        excluded = EXCLUDED_ASSETS if name == "assets" else ()
        shutil.copytree(root / name, dest / name, ignore=_ignore(root / name, excluded))
    vendor_yaml(src)
    return dest


def run_pygbag(stage_dir: Path, template: Path = TEMPLATE) -> None:
    """Run pygbag on the stage, once more if the first try fails (flaky network)."""
    uvx = shutil.which("uvx")
    if uvx is None:
        raise SystemExit("uvx is needed to run the pinned pygbag; install uv first.")
    command = [
        uvx,
        "--python",
        PYGBAG_HOST_PYTHON,
        f"pygbag=={PYGBAG_VERSION}",
        "--can_close",
        "1",
        "--template",
        str(template),
        "--build",
        str(stage_dir),
    ]
    for attempt in (1, 2):
        result = subprocess.run(command)
        if (
            result.returncode == 0
            and (stage_dir / "build" / "web" / "index.html").is_file()
        ):
            return
        if attempt == 1:
            print(
                "pygbag failed; retrying once (it needs internet)...", file=sys.stderr
            )
    raise SystemExit(
        "pygbag failed twice. It downloads the browser runtime, so check the "
        "internet connection and run the script again."
    )


def build() -> Path:
    """Stage, run pygbag and copy the result to build/web/. Returns that folder."""
    stage_dir = stage()
    run_pygbag(stage_dir)
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    shutil.copytree(stage_dir / "build" / "web", OUT_DIR)
    shutil.copy2(LOGO, OUT_DIR / "logo.png")
    return OUT_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="only create the stage folder; don't run pygbag (no internet needed)",
    )
    args = parser.parse_args(argv)
    if args.stage_only:
        print(f"Staged: {stage()}")
        return 0
    print(f"Web build ready: {build()} (open index.html through a web server)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
