# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is the short list of what changed. The [devlog](docs/devlog/README.md) has the detailed,
illustrated history of features and design decisions (options, choice and why), and
[docs/decisions](docs/decisions/README.md) has the architecture decision records.

Sections follow Keep a Changelog's order (Added, Changed, Deprecated, Removed, Fixed, Security).
"Development" is this project's extra last section, for tooling, CI and docs changes.

## [Unreleased]

Lines link their PR, or the commit for changes pushed straight to `main` before PRs were required.

### Added

- Clicking a tower opens an info panel with its level, kills, money earned, range, damage, fire
  rate and HP, and previews of what the next upgrade changes
  ([#28](https://github.com/vectorviolet/chokepoint/pull/28),
  [devlog](docs/devlog/2026-10-26-tower-info-panel.md)).
- Clicking a flying plane opens the same panel with its kills, splash, speed, damage and bomb rate
  ([#58](https://github.com/vectorviolet/chokepoint/pull/58),
  [devlog](docs/devlog/2026-10-27-plane-info-panel.md)).
- Clicking an enemy shows its HP as numbers next to its HP bar
  ([#47](https://github.com/vectorviolet/chokepoint/pull/47),
  [devlog](docs/devlog/2026-10-27-enemy-hp-on-click.md)).
- Tooltips on the tower buy buttons: name, one strength and one weakness
  ([#36](https://github.com/vectorviolet/chokepoint/pull/36),
  [devlog](docs/devlog/2026-10-26-buy-button-tooltips.md)).
- A pause menu on Esc or the HUD menu button: Back, Settings, Music on/off and Main menu
  ([#42](https://github.com/vectorviolet/chokepoint/pull/42),
  [devlog](docs/devlog/2026-10-26-pause-menu.md)).
- An optional auto-pause between waves, an hourglass toggle in the HUD saved in the settings
  ([#53](https://github.com/vectorviolet/chokepoint/pull/53),
  [devlog](docs/devlog/2026-10-27-auto-pause.md)).
- A keep-placing toggle (HUD button or Shift press) that keeps the tower type selected after each
  placement ([#48](https://github.com/vectorviolet/chokepoint/pull/48),
  [#72](https://github.com/vectorviolet/chokepoint/pull/72),
  [devlog](docs/devlog/2026-10-27-shift-placement.md),
  [devlog](docs/devlog/2026-10-28-placement-toggle.md)).
- A master volume slider in Settings, above SFX and BGM
  ([#73](https://github.com/vectorviolet/chokepoint/pull/73),
  [devlog](docs/devlog/2026-10-28-master-volume.md)).
- The heavy cannon has a blind spot: it can't hit enemies within 1.5 tiles, shown as a hole in its
  range ring and a row in the info panel
  ([#56](https://github.com/vectorviolet/chokepoint/pull/56),
  [devlog](docs/devlog/2026-10-27-cannon-blind-spot.md)).
- Life lost feedback: a bell and a red pulse at the screen edges when an enemy gets through
  ([#24](https://github.com/vectorviolet/chokepoint/pull/24)).
- Kill reward feedback: a floating "+$N" and coins flying to the money counter
  ([2a98c51](https://github.com/vectorviolet/chokepoint/commit/2a98c51)).
- A sound and a small effect when a tower is placed (dust) or sold (coins)
  ([#41](https://github.com/vectorviolet/chokepoint/pull/41),
  [devlog](docs/devlog/2026-10-26-place-sell-effects.md)).
- An explosion and a sound where each plane bomb lands, sized to its splash
  ([#49](https://github.com/vectorviolet/chokepoint/pull/49),
  [devlog](docs/devlog/2026-10-27-bomb-impacts-and-draw-order.md)).
- Tab hides the whole in-game HUD; a money or lives counter that changes peeks back for a moment
  ([c4f07cf](https://github.com/vectorviolet/chokepoint/commit/c4f07cf),
  [1bc4c4f](https://github.com/vectorviolet/chokepoint/commit/1bc4c4f)).
- A live battle plays behind the main menu
  ([e7cb023](https://github.com/vectorviolet/chokepoint/commit/e7cb023)).
- The credits screen has titled sections, the developer's name with GitHub and itch.io rows, and the
  VectorViolet lockup ([eaee5ec](https://github.com/vectorviolet/chokepoint/commit/eaee5ec),
  [83fd685](https://github.com/vectorviolet/chokepoint/commit/83fd685),
  [2a4f791](https://github.com/vectorviolet/chokepoint/commit/2a4f791),
  [a9f56b8](https://github.com/vectorviolet/chokepoint/commit/a9f56b8),
  [88b08ea](https://github.com/vectorviolet/chokepoint/commit/88b08ea)).
- `CREDITS.md` (replacing `ASSETS.md`) lists every asset's author and license, generated from
  `assets/SOURCES.yaml`; builds ship it with the license texts of every bundled library
  ([0bf865a](https://github.com/vectorviolet/chokepoint/commit/0bf865a),
  [7965095](https://github.com/vectorviolet/chokepoint/commit/7965095),
  [f89057a](https://github.com/vectorviolet/chokepoint/commit/f89057a),
  [823faca](https://github.com/vectorviolet/chokepoint/commit/823faca)).
- Hit enemies and towers flash white for a moment, with a small spark where the shot landed
  ([#104](https://github.com/vectorviolet/chokepoint/pull/104),
  [devlog](docs/devlog/2026-11-03-hit-feedback.md)).
- Killed enemies explode (tanks bigger) and destroyed towers explode and leave scorched rubble
  that fades out ([#109](https://github.com/vectorviolet/chokepoint/pull/109),
  [devlog](docs/devlog/2026-11-03-death-effects.md)).
- Settings > GAME has "Skip intro" (off by default; the game opens straight to the main menu on the
  next launch) and "Pause on focus loss" (on by default; a battle opens the pause menu when the
  window loses focus), and Settings > DISPLAY has "Reduce flashing" (off by default; no white hit
  flash and dimmer explosion fireballs). The map no longer scrolls at the screen edge while the
  window is unfocused
  ([#125](https://github.com/vectorviolet/chokepoint/pull/125),
  [devlog](docs/devlog/2026-11-04-settings-toggles.md)).
- A Language setting (English or Türkçe) on the Settings GAME tab, applied at once and saved; every
  player-visible text now comes from `config/lang/`
  ([#128](https://github.com/vectorviolet/chokepoint/pull/128),
  [devlog](docs/devlog/2026-11-04-language-setting.md)).
- The UPG PLANES button is now an icon (a plane with an arrow, no text, grayed once bought) and the
  U key upgrades the planes the same way
  ([#137](https://github.com/vectorviolet/chokepoint/pull/137),
  [devlog](docs/devlog/2026-11-04-planes-icon.md)).
- A GAME setting, Keep selection while buying (off by default): off, picking a tower to buy
  deselects the selected tower and closes its info panel; on, the selection and its range ring stay
  ([#136](https://github.com/vectorviolet/chokepoint/pull/136),
  [devlog](docs/devlog/2026-11-04-keep-selection-while-buying.md)).

### Changed

- The progression counter reads "Round" instead of "Level", which now means tower upgrades only;
  the README has new screenshots and a GIF
  ([#81](https://github.com/vectorviolet/chokepoint/pull/81),
  [#88](https://github.com/vectorviolet/chokepoint/pull/88),
  [devlog](docs/devlog/2026-10-30-round-counter.md)).
- Ground towers turn their barrels smoothly toward their target instead of snapping (cosmetic only)
  ([#89](https://github.com/vectorviolet/chokepoint/pull/89),
  [devlog](docs/devlog/2026-11-02-smooth-turret-turning.md)).
- A tower you can't afford can't be picked: its buy button is grayed out, and a click plays a
  "denied" sound and blinks the money counter. Blocked tiles tint the tower preview red, and the
  bought plane upgrade shows as maxed ([#72](https://github.com/vectorviolet/chokepoint/pull/72),
  [devlog](docs/devlog/2026-10-28-placement-toggle.md)).
- Planes are drawn above soldiers, tanks and explosions
  ([#61](https://github.com/vectorviolet/chokepoint/pull/61),
  [devlog](docs/devlog/2026-10-27-bomb-impacts-and-draw-order.md)).
- Bombs deal their damage where they land, and sounds no longer cut each other off (a pool of
  sound channels) ([#41](https://github.com/vectorviolet/chokepoint/pull/41),
  [#49](https://github.com/vectorviolet/chokepoint/pull/49),
  [ADR 0001](docs/decisions/0001-sfx-channel-pool.md),
  [ADR 0002](docs/decisions/0002-bombs-damage-at-landing.md)).
- Faster tower targeting with a spatial grid; the targets chosen are unchanged
  ([#51](https://github.com/vectorviolet/chokepoint/pull/51),
  [ADR 0004](docs/decisions/0004-grid-targeting.md)).
- The PLAY and SETTINGS titles use the logo green, and the MAX label, heart and sell images were
  replaced with licensed ones ([ce3b40f](https://github.com/vectorviolet/chokepoint/commit/ce3b40f),
  [3c52f32](https://github.com/vectorviolet/chokepoint/commit/3c52f32),
  [28c9257](https://github.com/vectorviolet/chokepoint/commit/28c9257)).
- pygamine updated from 0.20.1 to 0.27.0: VectorViolet splash and logos, splash fades, the sound
  channel pool, master volume
  ([eaee5ec](https://github.com/vectorviolet/chokepoint/commit/eaee5ec),
  [fbebe72](https://github.com/vectorviolet/chokepoint/commit/fbebe72),
  [4d75a5b](https://github.com/vectorviolet/chokepoint/commit/4d75a5b),
  [6a104ff](https://github.com/vectorviolet/chokepoint/commit/6a104ff),
  [#41](https://github.com/vectorviolet/chokepoint/pull/41),
  [#73](https://github.com/vectorviolet/chokepoint/pull/73)).
- Settings is split into tabs: Display (window size and mode) and Audio (the volume sliders), with
  keyboard navigation across the tabs and rows
  ([#121](https://github.com/vectorviolet/chokepoint/pull/121),
  [devlog](docs/devlog/2026-11-03-settings-tabs.md)).
- Text uses Fira Sans instead of Comic Neue, which lacks the Turkish letters Ğ ğ İ
  ([#128](https://github.com/vectorviolet/chokepoint/pull/128),
  [devlog](docs/devlog/2026-11-04-language-setting.md)).
- Bump pygamine to v0.30.0: InputMap (rebindable key actions) and TooltipManager (tooltips with key
  prompts). No game changes yet; key bindings and tooltips come in their own PRs. The game reads and
  sets `PanelManager.current_panel`, which is now a property in pygamine and behaves the same
  ([#142](https://github.com/vectorviolet/chokepoint/pull/142)).
- The plane-upgrade icon has the plane in the center with the upgrade arrow overlapping it, so it
  looks centered on its button
  ([#141](https://github.com/vectorviolet/chokepoint/issues/141),
  [devlog](docs/devlog/2026-11-04-planes-icon.md)).

### Removed

- The in-game music button; music is toggled from the pause menu and the menus
  ([#42](https://github.com/vectorviolet/chokepoint/pull/42)).
- 1,148 asset files nothing referenced, and a credits image that carried LinkedIn's logo
  ([25f075e](https://github.com/vectorviolet/chokepoint/commit/25f075e),
  [eaee5ec](https://github.com/vectorviolet/chokepoint/commit/eaee5ec)).

### Fixed

- No enemies spawned after continuing a saved run between waves
  ([#26](https://github.com/vectorviolet/chokepoint/pull/26)).
- An explicit 0 in the config (spawn interval, tank stats) was replaced by the default
  ([#27](https://github.com/vectorviolet/chokepoint/pull/27)).
- Shots in flight vanished when their tank died or escaped, or their tower was sold or destroyed;
  plane bombs vanished when their plane left the map
  ([#52](https://github.com/vectorviolet/chokepoint/pull/52),
  [#65](https://github.com/vectorviolet/chokepoint/pull/65),
  [ADR 0003](docs/decisions/0003-shots-outlive-their-source.md)).
- Planes disappeared with half their sprite still on the map
  ([#66](https://github.com/vectorviolet/chokepoint/pull/66),
  [devlog](docs/devlog/2026-10-28-planes-leave-the-map.md)).
- Music turned off in the settings came back on after the splash
  ([#57](https://github.com/vectorviolet/chokepoint/pull/57),
  [devlog](docs/devlog/2026-10-27-music-state-bug.md)).
- Skipping the splash with Space, Enter or a click also pressed PLAY
  ([#73](https://github.com/vectorviolet/chokepoint/pull/73)).
- A click placed a tower on the tile under last frame's cursor, which was wrong after a scroll and
  crashed before the first frame ([#91](https://github.com/vectorviolet/chokepoint/pull/91)).
- Planes drop only bombs that land on the map; the last bombs used to land past the right edge
  ([#97](https://github.com/vectorviolet/chokepoint/pull/97),
  [devlog](docs/devlog/2026-11-03-bombs-land-on-the-map.md)).
- The victory popup opened as round 26 started, with "Round 26" on the HUD behind it; it now opens
  as round 25 is cleared ([#105](https://github.com/vectorviolet/chokepoint/pull/105),
  [devlog](docs/devlog/2026-11-03-victory-on-clear.md)).
- Death effects: a tower's blast and rubble show even if it is sold the same moment; enemy kills no
  longer silence or cut short a falling tower's explosion
  ([#112](https://github.com/vectorviolet/chokepoint/pull/112)).
- The kill-reward coins and the money counter's pop are no longer drawn over the pause menu, victory
  or game over popups; the popups now cover everything from the run
  ([#93](https://github.com/vectorviolet/chokepoint/issues/93)).

### Development

- Faster tests: pytest-xdist runs them in parallel, and eight long simulation tests are marked
  `slow` and skipped by default; CI still runs everything
  ([#122](https://github.com/vectorviolet/chokepoint/issues/122)).
- An illustrated devlog and architecture decision records, with generated indexes checked in CI
  ([#68](https://github.com/vectorviolet/chokepoint/pull/68),
  [#76](https://github.com/vectorviolet/chokepoint/pull/76)).
- Tools: a load benchmark ([#39](https://github.com/vectorviolet/chokepoint/pull/39)), a play-test
  save script ([#64](https://github.com/vectorviolet/chokepoint/pull/64),
  [devlog](docs/devlog/2026-10-27-playtest-save.md),
  [ADR 0006](docs/decisions/0006-playtest-save-from-game-code.md)), a headless balance simulator
  with strategy bots ([#79](https://github.com/vectorviolet/chokepoint/pull/79),
  [devlog](docs/devlog/2026-10-29-balance-simulator.md),
  [ADR 0007](docs/decisions/0007-headless-balance-simulator.md)), a generated stats reference in
  `docs/stats/` ([#86](https://github.com/vectorviolet/chokepoint/pull/86),
  [devlog](docs/devlog/2026-11-02-stats-reference.md)) and a README capture script
  ([#81](https://github.com/vectorviolet/chokepoint/pull/81),
  [#88](https://github.com/vectorviolet/chokepoint/pull/88)).
- Code checks in CI: ruff ([01f45c8](https://github.com/vectorviolet/chokepoint/commit/01f45c8)),
  mypy with naming and type fixes ([#91](https://github.com/vectorviolet/chokepoint/pull/91),
  [devlog](docs/devlog/2026-11-02-type-checking.md),
  [ADR 0008](docs/decisions/0008-mypy-lenient-start.md)) and codespell with American English
  everywhere ([#92](https://github.com/vectorviolet/chokepoint/pull/92),
  [devlog](docs/devlog/2026-11-03-american-english.md)).
- CI runs on the merge queue, publishes the coverage badge to a `badges` branch and runs push
  builds on `main` only; the smoke test no longer writes to the real saves folder; the pygamine
  sync script checks out the pinned engine commit
  ([#35](https://github.com/vectorviolet/chokepoint/pull/35),
  [#74](https://github.com/vectorviolet/chokepoint/pull/74),
  [#77](https://github.com/vectorviolet/chokepoint/pull/77),
  [#78](https://github.com/vectorviolet/chokepoint/pull/78)).
- Assets regrouped by function, sounds split into `music/` and `sfx/`, every asset's source in
  `assets/SOURCES.yaml`, and `docs/ROADMAP.md` added
  ([77666fd](https://github.com/vectorviolet/chokepoint/commit/77666fd),
  [88581eb](https://github.com/vectorviolet/chokepoint/commit/88581eb),
  [823faca](https://github.com/vectorviolet/chokepoint/commit/823faca),
  [9f67bda](https://github.com/vectorviolet/chokepoint/commit/9f67bda)).
- Dependencies: Pillow 13.0.0 ([#80](https://github.com/vectorviolet/chokepoint/pull/80)),
  setuptools locked at 84.2.1 ([5a3828a](https://github.com/vectorviolet/chokepoint/commit/5a3828a)).
- pygamine updated to 0.28.0: sprites and the window are used without Optional checks
  (`require_image()`, the renderer StateObject keeps, the non-Optional window), and the 0-1 clamps
  use `clamp01()` ([#101](https://github.com/vectorviolet/chokepoint/pull/101)).
- `balance_sim.py --watch --strategy <name>` plays one bot's run in a game window, in real time
  ([#103](https://github.com/vectorviolet/chokepoint/pull/103),
  [devlog](docs/devlog/2026-11-03-watch-the-bots-play.md)).
- Dependabot opens one grouped PR a week with `uv.lock` updates (`.github/dependabot.yml`).
- A CodeRabbit config (`.coderabbit.yaml`) for a trial of automated PR reviews alongside the
  lead's review ([#124](https://github.com/vectorviolet/chokepoint/pull/124)).
- CodeRabbit no longer posts its docstring-coverage pre-merge warning
  ([#126](https://github.com/vectorviolet/chokepoint/pull/126)).
- pygamine bumped to 0.29.0 (localization and `Display`); test fakes updated for `app.display` ([#127](https://github.com/vectorviolet/chokepoint/pull/127)).
- The play-test save turns Skip intro on, so worktree play-tests open on the menu; the game's own
  default stays off ([#136](https://github.com/vectorviolet/chokepoint/pull/136)).

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
