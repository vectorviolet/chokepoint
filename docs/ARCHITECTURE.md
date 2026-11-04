# Architecture

A guided tour of how Chokepoint is put together, for people reading or changing the code. It
is deliberately high level: the code and its docstrings have the details, and
[`docs/decisions/`](decisions/README.md) records why the bigger choices were made. For how to
build and check changes, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Project layout

```
__main__.py            Entry point — injects src/ + src/pygamine/ into sys.path
src/app/game.py        Game class — wires all subsystems
src/domain/            Pure data (GameState, protocols)
src/gameplay/          Battle simulation, combat, tilemap, menu demo
src/gameplay/towers/   Tower hierarchy and factory
src/ui/                HUD, info panels, pause menu, tooltips, feedback effects
src/util/              Config loaders, constants
src/pygamine/          Pinned engine submodule (Application, Animator, PanelLoaderExt, ...)
config/                YAML: assets, panels, towers, enemies, waves
assets/                Images, sounds, fonts, Tiled map
scripts/               Smoke checks, play-test saves, media and documentation generators
docs/devlog/           Feature history and decisions with screenshots
docs/decisions/        Architecture decision records
docs/stats/            Generated stats reference (towers, enemies, waves)
```

The game is built on [pygamine](https://github.com/vectorviolet/pygamine), the author's own
engine layer on top of pygame-ce. It is pinned as a git submodule in `src/pygamine/`.

## Entry point and the Game class

`__main__.py` creates `Game()` and calls `game.run()`. `Game` (`src/app/game.py`) extends
`pygamine.Application` and is the top-level orchestrator. It wires every subsystem in
`__init__`, shows a splash screen, then hands control to the `Application` loop, which calls
`update()`, `draw()` and `handle_event()` every frame.

## Subsystems wired by Game

The main ones, each an attribute of `Game`:

| Object | Class | Responsibility |
|--------|-------|----------------|
| `game_state` | `GameState` | Pure data: money, lives, speed, round, started/won flags and the game clock; notifies listeners when money, lives or the round change |
| `camera` | `Camera` | Edge-scroll and zoom camera over the map; turns world positions into screen positions |
| `assets` | `AssetManager` | Loads every image and sound listed in `config/assets.yaml`, looked up by string key |
| `panel_manager` | `PanelManager` | Holds the named UI panels (main menu, credits, game); switching is one assignment |
| `tilemap` | `Tilemap` | The 47×34 tile map loaded from a Tiled `.tmx` file, pre-rendered once |
| `wave_manager` | `WaveManager` | Reads `config/waves.yaml`, spawns enemies on a timer and advances the round when a wave clears |
| `hud` | `GameHUD` | Money, lives, round and tower prices; follows `GameState` through its listeners |
| `tower_controller` | `TowerPlacementController` | Buying, placing, selecting, upgrading and selling towers |
| `menu_demo` | `MenuDemo` | A live battle that plays itself behind the menus (see below) |
| `tower_info`, `buy_tooltip` | `TowerInfoPanel`, `BuyTooltip` | The selected tower's stats and upgrade previews, and the hover tooltip on the buy buttons |
| feedback objects | `KillFeedback`, `LifeLostFeedback`, `PlaceSellFeedback`, `BombImpactFeedback`, `HitFeedback`, `DeathFeedback` | Cosmetic effects (floating rewards, coins, vignette, dust, explosions, hit flashes). They run on real time, so they play out while the game is paused |

## Battle simulation and the menu demo

The battle itself (ticking towers, enemies and waves, and drawing them through a camera) lives
in `BattleSimulation` (`src/gameplay/battle.py`). `Game` inherits it for the real game, and
`MenuDemo` (`src/gameplay/menu_demo.py`) inherits it too, as a separate world shown behind the
menus:

- It has its own state, towers, enemies, wave manager and camera, and shares only the tilemap
  and assets with the real game. It saves nothing, its towers are silent, and enemies that
  escape cost nothing.
- Each run is random: towers of every type stand along the path, pre-upgraded, and the run
  starts at a mid-game wave with denser waves than the real game. After a few waves, or when
  the defense is worn down, it fades out and a new run starts.

`Game` and `MenuDemo` differ only in a few hooks (a kill was paid, an enemy escaped, tower
positions changed): the real game adds rewards, game over and saving there.

## Fixed-tick timing

Gameplay runs on a fixed tick, independent of the frame rate. `Game.update()` measures real
frame time and runs one tick per `TICK_MS` of it (165 ticks per second, `TICKS_PER_SECOND` in
`src/util/constants.py`). Each tick advances the game clock by `TICK_MS × speed` while a round
is running, then updates towers and enemies.

- Per-tick motion is multiplied by the game speed (x1, x2, x4).
- Every gameplay timer (spawns, reloads, fuses, wave delays) compares against game time, never
  the wall clock, so pausing freezes it and x2/x4 speeds everything up in step.
- Input-driven motion (camera scrolling) and cosmetic effects use real time instead.

## Panels and localization

UI panels are defined in YAML (`config/panels.yaml`) and loaded by pygamine's `PanelLoaderExt`,
which adds template inheritance (`object_templates:`). Three object kinds are registered in
`game.py`: images (with hover states and nine-slice scaling), text, and animated sprites.

Every player-visible string lives in `config/lang/en.yaml` (the fallback) and `tr.yaml`
(Turkish), through pygamine's localization. Panels refer to strings by `text_key`; code uses
`tr("key")`. Money and decimal numbers go through helpers in `src/util/text.py`, so Turkish
gets its decimal comma. Switching language goes through `Game.set_language(code)`, which
re-renders every label. A language is added by dropping another `<code>.yaml` into
`config/lang`; tests check that both files have the same keys and that the fonts can draw
every glyph.

## Towers and targeting

`BaseTower` is abstract; `GroundTower` covers the gun, missile and cannon, and `PlaneTower`
the plane. `TowerFactory.create()` returns the right subclass, and stats come from
`config/towers.yaml` through `TowerConfig`. Missiles are homing `Projectile`s, guns and cannons
hit instantly with a `MuzzleFlash`, and planes drop `Bomb`s with splash damage. Shots already in
flight keep flying, and credit their source, after the tower that fired them is sold or
destroyed.

Targeting uses per-tick spatial grids (`src/gameplay/combat/targeting.py`): an `EnemyGrid` for
towers looking for the nearest enemy and a `TowerGrid` for armed tanks looking for a tower. They
must pick exactly what a full scan would, which `tests/test_targeting.py` checks against the
straightforward algorithms. Projectiles never import `Game`: they talk to it through the
`IGameContext` protocol.

## Config files

| File | Loaded by | Contents |
|------|-----------|----------|
| `config/assets.yaml` | `AssetManager.load_manifest()` | Image and sound keys with their folder and file name |
| `config/towers.yaml` | `config_loader.load_tower_config()` | Price, range, damage, fire rate and HP per tower level |
| `config/enemies.yaml` | `config_loader.load_enemy_stats()` | HP, speed, kill money and damage per enemy type |
| `config/waves.yaml` | `config_loader.load_wave_compositions()` | What each wave spawns |
| `config/lang/<code>.yaml` | pygamine localization | Every player-visible string |
| `config/panels.yaml` | `PanelLoaderExt.load()` | Panels, groups and object templates |

The [stats reference](stats/README.md) in `docs/stats/` is generated from these files by
`scripts/gen_stats.py`.

## Map and coordinates

Tiles are 64 px; the map is 47×34 tiles (3008×2176 px of world space). All entity positions are
world-space center points. The camera viewport is the whole window, and the map is larger, so
the camera edge-scrolls and zooms over it. The HUD floats over the map.
