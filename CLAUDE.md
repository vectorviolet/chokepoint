# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Game

```bash
cd chokepoint
python __main__.py         # or: uv run python __main__.py
```

## Testing

```bash
uv run --group dev pytest tests/ -q                      # this app's own logic tests
uv run --group dev pytest tests/ --cov --cov-report=term  # with coverage
```

`tests/conftest.py` runs pygame headless (`SDL_VIDEODRIVER=dummy`) and points every
`SaveStore` at a temporary folder (the autouse `saves_in_tmp` fixture).

**Asset sources:** every file under `assets/` must be listed in `assets/SOURCES.yaml` with its
source (a pack, `own`, or `unknown` plus a `todo`) and its original file name. Each source needs
its license text in `licenses/assets/<source>.txt`. CREDITS.md's asset section is generated from
`SOURCES.yaml` by `scripts/gen_credits.py`; don't edit it by hand (the Music, Software and
Trademarks sections around it are hand-written). `tests/test_sources.py` enforces all of this.
Never add an asset whose origin and license you can't state.

**Code style:** run `uv run --group dev ruff format .` and `uv run --group dev ruff check .`
before every commit. Formatting is Black-compatible (`[tool.ruff.format]` in `pyproject.toml`);
lint is pyflakes-only (`[tool.ruff.lint]`). CI fails on `ruff format --check .` and on lint
errors. Keep pure reformatting out of feature commits; a repo-wide reformat goes in its own
commit, with its hash added to `.git-blame-ignore-revs`.

**Always run simulations and tests in a temporary folder, never against the real `saves/`.**
A `Game()` saves and deletes its save exactly like the real game does: losing a run deletes
`saves/save.json`, and one headless balance simulation once deleted the player's real save
that way. So:

- Tests rely on the `saves_in_tmp` fixture; don't bypass it.
- Any ad-hoc script that builds a `Game()` (balance sims, screenshot or GIF recorders,
  benchmarks) must redirect saves before it does. For example:
  `monkeypatch`/patch `SaveStore` to `directory=<temp dir>`, or replace `SaveStore.save` and
  `SaveStore.delete` with no-ops. Alternatively, run it with a temporary directory as the cwd.
- Never run such a script in a way that can write to, overwrite or delete `saves/`.

### Building a distributable

`pyinstaller chokepoint.spec --noconfirm` produces a standalone onedir bundle in
`dist/` (bundling `assets/` + `config/`); the tag-triggered
`.github/workflows/release.yml` builds Windows/macOS/Linux zips and publishes a
GitHub Release. Because the game loads assets/config by **cwd-relative** paths,
`__main__.py` chdirs into `util.paths.resource_root()` at startup — which is the
project root from source and `sys._MEIPASS` when frozen — so the same relative
paths resolve in both. `config_loader` anchors to that root too.

## Working with git

- Before every push, run `git fetch` and `git log origin/main..HEAD --oneline`; push only if
  every listed commit is intended. Otherwise stop and report.
- Never push a commit that points a submodule at a commit not yet on its remote; push the
  submodule first and check it's on origin.
- Only one agent session works in a repo at a time. If HEAD or the working tree changes
  unexpectedly, stop and report.

## Architecture

### Entry point → Game class

`__main__.py` creates `Game()` and calls `game.run()`. `Game` (in `src/app/game.py`) extends `pygamine.Application` and is the top-level orchestrator: it wires all subsystems in `__init__`, runs a splash screen, then hands control to the `Application` base class loop which calls `update()` / `draw()` / `handle_event()` each frame.

### Subsystems wired by Game

| Object | Class | Responsibility |
|--------|-------|----------------|
| `game_state` | `GameState` | Pure data (money, lives, speed, level, is_started, has_won) plus the game clock `time_ms`; fires listener callbacks on money/lives/level change |
| `camera` | `Camera` | Edge-scroll/zoom camera over the map; its viewport (`game_area`) is the whole canvas. Applies the world→screen offset to all drawn entities |
| `assets` | `AssetManager` | Loads all images/sounds from `config/assets.yaml`; accessed via string keys everywhere |
| `panel_manager` | `PanelManager` | Holds named panels ("main_menu", "credits", "game"); switching is `panel_manager.current_panel = "name"` |
| `tilemap` | `Tilemap` | 47×34 tile grid loaded from a Tiled `.tmx`; pre-rendered once after splash |
| `wave_manager` | `WaveManager` | Reads `config/waves.yaml`; spawns enemies on a timer; advances `game_state.level` when wave clears. `on_wave_cleared` fires once per wave as its last enemy goes; `Game` uses it for auto-pause between waves (the HUD's hourglass toggle, the global `auto_pause_between_waves` setting), which pauses the run there until start is pressed |
| `hud` | `GameHUD` | Draws money, lives, level, tower prices; subscribes to `GameState` listeners |
| `tower_controller` | `TowerPlacementController` | Handles buy/place/select/upgrade/sell; shares the `towers` list reference |
| `menu_demo` | `MenuDemo` | A live battle that plays itself behind the menu panels (see below) |
| `hud_slide` | `HudSlide` | Tab slides the in-game HUD (counters, control buttons, tower bar) off the screen edges and back, drawn-only and on real time; money/lives counters peek back for 1.5 s when they change. `toggle()` is the entry point for a future on-screen button |
| `tower_info` | `TowerInfoPanel` | The selected tower's info panel (`tower_info_*` objects in `config/panels.yaml`): kills, money earned, range, damage, fire rate, HP bar, and "current → next" upgrade previews below max level. Refreshed every frame from `_selected_tower()`; slides away with the HUD on Tab. Kills/money are credited to the tower whose shot or bomb landed the killing blow (`Enemy.decrease_hp(..., source=tower)`) and saved with it |
| `buy_tooltip` | `BuyTooltip` | Hovering a buy button shows the tower's name and one-line strength/weakness (`name` + `tooltip` per tower in `config/towers.yaml`, loaded by `config_loader.load_tower_tooltips()`) on the `buy_tooltip_*` objects in `config/panels.yaml`, sized to the text and placed above the button, clamped to the screen. Hidden while the HUD is hidden or sliding; takes no clicks |
| `kill_feedback` | `KillFeedback` | Kill rewards: a floating "+$N" over the kill (game time) and coins flying to the money counter (real time), capped at `MAX_EFFECTS`. Fed by the `_on_enemy_killed` hook; the menu demo has none |
| `life_lost_feedback` | `LifeLostFeedback` | A bell (its own reserved mixer channel 2, outside pygamine's SFX pool, at the SFX volume) and a red edge vignette pulsing ~0.4 s when lives are lost; stacks up to `MAX_STRENGTH`, real time. Skipped on the last life (game over) and absent from the menu demo |
| `place_sell_feedback` | `PlaceSellFeedback` | Placing a tower: a thud and a dust puff on its tile; selling: a coin clink and coins bursting from the tile. Sounds via `audio.play_sfx` (the SFX pool); effects in world space through the camera, on real time (cosmetic: they play out while paused and ignore x2/x4), capped at `MAX_EFFECTS`. Told by the placement controller (`feedback=`); the menu demo has none |

### Panel / UI system

Panels are defined in `config/panels.yaml` and loaded by `PanelLoaderExt` (in `src/pygamine/pygamine/panels/panel_loader_ext.py`, the engine submodule), which extends the base `PanelLoader` with **object-level template inheritance** via `object_templates:`.

Three factory types are registered in `game.py`:
- `"object"` (default) → `panel_factory.make_factory(assets)` → creates `GuiObject` or `HoverableGuiObject`
- `"text"` → `panel_factory.make_text_factory(assets)` → creates `TextObject`
- `"animated"` → `panel_factory.make_animated_factory(assets)` → creates animated sprite objects

YAML keys for image objects: `position`, `size`, `asset`, `hover`, `states`, `nine_slice`, `extends`.  
YAML keys for text objects: `type: text`, `position`, `text`, `font`, `font_size`, `color`.

`nine_slice` uses `core.image.nine_slice_scale()` — `corner` is the corner region size **in source pixels**. Only edges/center are stretched; corners are pixel-perfect.

### Towers

`BaseTower` (abstract) → `GroundTower` (types 1–3) or `PlaneTower` (type 4). `TowerFactory.create()` returns the right subclass. Stats come from `config/towers.yaml` via `TowerConfig` (indexed `[type-1][level-1]`).

- Types 1 & 3: instant-hit `MuzzleFlash` at barrel tips (twin barrels for type 1 and type 3 lvl 2)
- Type 2: homing `Projectile`
- Type 4: plane that flies across the map, dropping `Bomb` projectiles (splash damage) along its path

### Projectiles / IGameContext

`Projectile` and `MuzzleFlash` (in `src/gameplay/combat/projectile.py`) receive an `IGameContext` on `update()`. `Game` satisfies this protocol via `.enemies`, `.towers`, `.speed`, `.time_ms`, `.map_width`, `.map_height`, and `.increase_money()`. This avoids circular imports — projectiles never import `Game`.

### Rendering order (game panel)

Tilemap → towers + bullets → enemies → border lines → HUD → tower placement overlay (cursor + range ring)

### Config files

| File | Loaded by | Structure |
|------|-----------|-----------|
| `config/assets.yaml` | `AssetManager.load_manifest()` | `{images: {key: {folder, name}}, sounds: {key: {folder, name}}}` |
| `config/towers.yaml` | `config_loader.load_tower_config()`, `load_tower_tooltips()` | Produces `TowerConfig` dataclass with `.prices`, `.max_levels`, `.ranges`, `.damages`, `.speeds`; plus each tower's buy-tooltip `name` and `tooltip: {strength, weakness}` |
| `config/enemies.yaml` | `config_loader.load_enemy_stats()` | HP/speed/kill_money/damage per enemy type |
| `config/waves.yaml` | `config_loader.load_wave_compositions()` | `{wave_num: [[enemy_type, count], ...]}` |
| `config/panels.yaml` | `PanelLoaderExt.load()` | Panels + groups + optional `object_templates` |

### Coordinate system

Tile size is 64 px. Map is 47×34 tiles = 3008×2176 px world space. The camera viewport is the whole canvas (whatever window size is in use); the map is larger than it, so the `Camera` edge-scrolls and zooms over it, opening on the path entrance. The HUD floats over the map: counters top-left, buttons top-right, tower bar bottom-centre. All entity positions are world-space center points stored as `pygame.math.Vector2`.

### Battle simulation and the menu demo

The battle itself -- ticking towers, enemies and waves, and drawing them
through a camera -- lives in `BattleSimulation` (`src/gameplay/battle.py`).
`Game` inherits it for the real game. `MenuDemo` (`src/gameplay/menu_demo.py`)
inherits it too, as a separate world shown behind the menus:

- It has its own `GameState`, towers, enemies, wave manager and camera, and it shares
  only the tilemap and assets with the real game. It has no save store, its
  towers play no sound, and enemies that escape cost nothing.
- Each run is random. Towers of every type stand along the path, pre-upgraded. A run
  starts at a mid-game wave, pre-warmed while the screen is black, and its waves
  are denser than the real game's. Planes fly bombing runs. The camera eases
  between groups of enemies.
- After a few waves, or when the defence is worn down, it fades out and a new run starts.

Hooks: `_on_enemy_killed()` runs after a kill is paid (`Game` adds the reward
feedback). `_on_enemy_escaped()` handles lives (`Game` adds game over and deletes the
save). `_on_tower_positions()` passes the occupied build tiles on (`Game` gives
them to the placement controller).

### Simulation timing

Gameplay runs on a fixed tick, independent of the frame rate: `Game.update()` measures real frame time and `_update_game()` runs one `_tick()` per `TICK_MS` of it (`TICKS_PER_SECOND = 165` in `util/constants.py`, the cap the per-tick speeds were tuned at). Each tick advances `GameState.time_ms` by `TICK_MS × speed` while the game is started, then updates towers and enemies.

- Per-tick motion (enemy/projectile/plane/bomb speeds in code and config) is multiplied by `speed`.
- Every gameplay timer (spawn intervals, reloads, tank fire, fuses, flashes, wave delays) compares against game time (`game_state.time_ms`, `ctx.time_ms`, or an owner's `.now`), never `pygame.time.get_ticks()`, so pausing freezes it and x2/x4 runs it faster in step with motion.
- Input-driven motion (camera edge scroll, the menu demo's camera) follows real time instead.
- Tests set game time directly (`gs.time_ms`, `ctx.time_ms`, `tower.now`); the `fake_ticks` fixture only drives the wall clock `update()` reads.

### Adding a new tower type

1. Add stats to `config/towers.yaml`
2. Subclass `BaseTower` (or reuse `GroundTower` if behaviour matches)
3. Register in `TowerFactory.create()`
4. Add assets to `config/assets.yaml`: sprites in `assets/images/towers/`, the buy button in `assets/images/hud/tower_bar/`
5. Add buy button to `config/panels.yaml` and price display to `GameHUD`