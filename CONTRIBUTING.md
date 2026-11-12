# Contributing to Chokepoint

How to build, check and change the game. The [README](README.md) is the player-facing front
page, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains how the code fits together.

## Running from source

See the README's [Running from source](README.md#running-from-source). Python 3.12+ is
required, and [uv](https://docs.astral.sh/uv/) is recommended. The other dependencies
(pygame-ce, colorama, pyyaml, pytmx) are resolved from `pyproject.toml` and `uv.lock`.

## Development and checks

Run these commands from the `chokepoint` project folder:

```bash
uv run --group dev pytest tests/ -q
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python scripts/smoke_test.py  # headless
```

The tests and smoke test redirect saves to temporary folders. Any custom script that creates
a `Game()` must do the same: normal gameplay can overwrite a save, and losing a run deletes it.

For a ready-made run **inside a separate worktree**, use:

```bash
uv run python scripts/make_playtest_save.py --out saves
uv run python __main__.py
```

Press **Continue** for a paused round-10 run with $100,000, towers at every level and muted
audio. The generator always refuses the main checkout's real saves. Replacing existing
generated files in the worktree requires `--overwrite`.

Refresh the README media from the current game with:

```bash
uv run --group build python scripts/capture_readme.py
```

This captures screenshots and a six-second GIF headlessly, using temporary saves and checking
that the real save directories remain unchanged.

## Stats reference

Every tower level, enemy and wave with its numbers (price, range, DPS, HP and kill money per
wave, each wave's enemies) is in [`docs/stats/`](docs/stats/README.md), generated from the config
by `scripts/gen_stats.py`: [towers](docs/stats/towers.md), [enemies](docs/stats/enemies.md),
[waves](docs/stats/waves.md). After changing the config, run
`uv run python scripts/gen_stats.py` and commit the pages with it; CI fails when they are stale.
A workflow also mirrors them to the project [wiki](https://github.com/vectorviolet/chokepoint/wiki/Stats).

## Asset sources

Every file under `assets/` is listed in `assets/SOURCES.yaml` with its source:

- **A pack**, given by its slug (for example `kenney-ui-pack`). The entry also gives the file's
  path inside that pack as `original`. Images built from several pack files list them under
  `composited_from` instead. Edited pack files say what changed under `modified`.
- **`own`**, for files made for this game.
- **`unknown`**, for files whose origin or license isn't confirmed yet. Each needs a `todo` that
  says what to do; the credits list them as "not yet verified".

The `packs` section names each pack, its author, URL, license and what the game uses it for.
Each pack's own license text is in `licenses/assets/<slug>.txt`, and every build ships it.

When you add, replace or remove an asset:

1. Update `assets/SOURCES.yaml`, and add `licenses/assets/<slug>.txt` for any new pack.
2. Run `uv run python scripts/gen_credits.py` to regenerate CREDITS.md's asset section. Don't
   edit that section by hand.
3. Run the tests. `tests/test_sources.py` fails if a file is missing from `SOURCES.yaml`, if a
   listed file doesn't exist, if a pack has no license text, or if CREDITS.md is out of date.

Only ship assets whose license allows bundling them in a distributed game; resolve every
`unknown` entry before the next release.

## Code style

- **Formatting:** Black-compatible, enforced by `ruff format` (line length 88, double quotes,
  otherwise Black's defaults; see `[tool.ruff.format]` in `pyproject.toml`).
- **Lint:** `ruff check`, deliberately narrow (pyflakes rules only).
- **CI:** runs both. The `src/pygamine` submodule is excluded; it has its own setup.

Run both locally before committing:

```bash
uv run --group dev ruff format .          # reformat
uv run --group dev ruff check .           # lint
uv run --group dev ruff format --check .  # what CI runs: fails if anything would be reformatted
```

The commit that first applied the formatter is listed in `.git-blame-ignore-revs`. To have
`git blame` skip it and show the real author of each line:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

## Building a standalone bundle

Builds are produced by [PyInstaller](https://pyinstaller.org/) from `chokepoint.spec`, which bundles `assets/` and `config/` alongside the executable (onedir). To build locally for your current OS:

```bash
uv sync --group build
uv run pyinstaller chokepoint.spec --noconfirm
```

The result lands in `dist/chokepoint/` (`dist/Chokepoint.app` on macOS).

### Cutting a release

Prepare a **Release x.y.z** PR with the version and changelog changes first. After required
CI passes and the owner merges it through the merge queue, the owner creates and pushes the
matching `vx.y.z` tag on that merged commit. Protected release tags cannot be moved or deleted.

The tag triggers [`.github/workflows/release.yml`](.github/workflows/release.yml), which builds
on each OS, builds the browser version, zips each bundle, attaches all four to a GitHub Release, and
pushes each build to its [itch.io](https://umutcanekinci.itch.io/chokepoint) channel (`windows`,
`linux`, `osx`, `html5`) via [Butler](https://itch.io/docs/butler/). Use **Run workflow** to build
without publishing.

### The browser version (itch.io `html5` channel)

`scripts/build_web.py` stages a clean bundle (`web/main.py` as `main.py`, `src/`, `config/`,
`assets/`, vendored PyYAML; no tests, saves or `.git`) and runs the pinned
[pygbag](https://github.com/pygame-web/pygbag) on it. It writes `build/web/` with `index.html` at its
root. pygbag downloads the browser runtime, so the build needs internet (the script retries once).
Locally: `uv run python scripts/build_web.py`, then serve `build/web/` with any web server
(`python -m http.server`) and open it in a desktop browser. `--stage-only` skips pygbag; CI runs
that on every PR.

After the **first** release that pushes an `html5` build, the owner sets it up once on the itch.io
edit page (the tag run can't do this):

1. Uploads: the `html5` file appears; tick **This file will be played in the browser**.
2. Under "Embed options" pick the viewport size (for example 1280 x 720) and a **Fullscreen
   button**; leave mobile friendly off (the game needs a keyboard and mouse).
3. Save, and open the page's Run game button to play-test it.

Today the canvas fills the browser window (or the embed frame) and the UI scales with it, so a
different embed size changes the layout rather than letterboxing it.

## Contributing

1. Fork this repository.
2. Clone your fork: `git clone --recurse-submodules https://github.com/<you>/chokepoint.git`
3. Create a branch: `git checkout -b feature/<your-feature>`
4. Run the tests, smoke test and Ruff checks.
5. Stage the intended file paths explicitly, commit, and push your branch.
6. Open a pull request. Feature and design-decision PRs include a devlog entry;
   architecture changes include an ADR.
7. After lead review and the owner's playtest, the owner queues the PR with **Merge when ready**.
   Required CI also runs on the merge group; do not push directly to protected `main`.
