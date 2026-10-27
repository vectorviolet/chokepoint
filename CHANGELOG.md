# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is the short list of what changed. The [devlog](docs/devlog/README.md) has the detailed,
illustrated history of features and design decisions (options, choice and why), and
[docs/decisions](docs/decisions/README.md) has the architecture decision records.

## [0.3.1] – 2026-10-25

### Removed

- The Kenney logo from the credits screen. It isn't covered by the CC0 license of Kenney's asset
  packs; the packs themselves stay credited by name and link.

### Changed

- The startup splash shows pygame-ce's "powered" logo instead of the original pygame logo.
- pygamine updated to 0.20.1.

### Added

- Credit for the music, "Clown" by Sakura Girl, on the credits screen and in `ASSETS.md`.

## [0.3.0] – 2026-10-25

### Changed

- Tower balance: Rapid gun $80 → $100, Missile $220/$480/$850 → $160/$340/$600, Cannon
  $380/$780 → $280/$560. Spamming Rapid guns used to beat every other build, and builds without
  them couldn't get past wave 8; now gun-only, missile/cannon and mixed builds can all win.
- Selling refunds 70% of everything spent on a tower. It used to refund the full price of its
  current level only, so moving a tower was free but selling an upgraded one lost what was paid
  for its earlier levels.
- The game plays the same at any frame rate. Gameplay runs in fixed steps, and every timer runs on
  a game clock that stops while paused. At 60 fps the game used to run at about a third of its
  speed.
- x2 and x4 speed now speed up everything (tower fire, spawns, bombs) instead of only movement,
  which made faster speeds much harder rather than just quicker.
- The camera opens on the path entrance rather than an empty corner of the map.
- Endless waves after wave 30 grow gradually from wave 30's mix instead of jumping to 73 Heavies.
- New Windows app icon.

### Added

- Right click cancels tower placement and clears the selection.

### Fixed

- Starting at a saved window size other than 1920×1080 kept a 1920×1080 map view until the window
  was resized: at 1280×720 the right side of the map, where enemies spawn, couldn't be reached, and
  at 16:10 sizes a black band showed under the map.
- The victory and game-over overlays left an uncovered strip on windows that aren't 16:9.
- The game slowed down while placing a tower (the placement grid now draws 3.5× faster).
- A plane could be selected and sold from the tile it launched from, after it had flown away.

## [0.2.1] – 2026-10-24

### Added

- Scrolling credits in place of the contact panel, restarting on every visit and crediting the
  bundled fonts.
- Tests for the modules that had no coverage.

### Changed

- Titles and buttons use bundled open fonts (Anton and Comic Neue, SIL OFL, credited in `ASSETS.md`)
  instead of the system Impact and Comic Sans, so the game looks the same on every machine.
- Enlarged and recolored the Play and Settings menu titles.
- Startup now opens with the shared splash all the sibling games use: the publisher clip, then
  the pygame logo.
- pygamine updated to 0.19.0, now at `vectorviolet/pygamine`; repo links point at `vectorviolet`.
- The smoke test now runs the game's real `run()`, splash included, instead of stepping frames by hand.

## [0.2.0] – 2026-08-12

### Added

- Game over popup instead of quitting on loss, and a victory popup when wave 25 is cleared.
- A Space-bar shortcut for starting/pausing the game.
- Real app-level test suite (61 tests) and a CI workflow running the `pygamine` engine suite + an app smoke test.

### Changed

- Continue moved above New Game on the Play menu.
- Renamed the `pygame_core` submodule/dependency to `pygamine`.
- Reverted `starting_money` to 200.

### Fixed

- Stale README/CLAUDE.md claims about planes and the enemy roster.
- Escaped anchor tags leaking as visible text in the itch.io description.
- Editable `pygame-core` install not actually taking effect.

## [0.1.4] – 2026-07-08

- Dynamic field of view: camera and UI reflow on canvas resize, shrink-to-fit when the window is
  smaller than authored.

## [0.1.3] – 2026-07-08

- Settings tab: screen-size picker, window mode picker, SFX/BGM volume sliders, Reset to Default.
- A game-save feature with a New Game/Continue/Back submenu.
- itch.io/storefront cover art; docs reorganized under `docs/`.

## [0.1.2] – 2026-07-08

- itch.io publish automation.
- Ignore OS junk files (`.DS_Store`, `Thumbs.db`).

## [0.1.1] – 2026-07-04

- Fixed a Python 3.12 crash in frozen builds.

## [0.1.0] – 2026-07-04

Initial release. Tower defense with an economy rebalance, tank enemies (rotating muzzle,
turret-killing fire), HP bars, and PyInstaller packaging with per-OS release CI.
