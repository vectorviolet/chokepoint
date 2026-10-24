# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
