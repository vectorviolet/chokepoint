# 0007. Headless balance simulator on the real game
<!-- index | refs: #70, #10 -->

- **Status:** Accepted
- **Date:** 2026-10-29
- **Issues / PRs:** [#70](https://github.com/vectorviolet/chokepoint/issues/70), [#10](https://github.com/vectorviolet/chokepoint/issues/10)

## Context

Balance changes (#10, the owner's call) need numbers: nobody can play 30+ waves of every
strategy by hand after each change. The owner reported four observations from a playtest (hard
early waves, easy mid-game, a late tank wall, planes that pay for themselves) and wanted them
confirmed or refuted with data. A headless script once deleted the player's real save, so any
tool that builds a `Game()` must keep saves isolated.

## Decision

`scripts/balance_sim.py` plays whole runs in a real `Game()` (a subclass that only counts kills
and escapes), ticking `_tick()` as fast as the CPU allows with nothing drawn, at in-game speed x4
by default (`--game-speed`). Everything that decides the outcome is the game's own code: waves,
enemy stats, targeting, money and lives, the victory popup (answered with Continue) and game
over.

Strategy bots (`scripts/balance_bots.py`) are short lists of steps (an opener, then a repeated
cycle) played strictly in order, waiting when the next step isn't affordable. They buy through
the game's rules: placement through `TowerPlacementController` (its placeability and money
checks), upgrades through the tower's own upgrade button, UPG PLANES as the HUD does. Build
tiles are ranked once per run by how much path they cover within the tower's range (outside the
cannon's blind spot), with the seed breaking ties; planes start at the left end of the path's
longest horizontal straight and fly along it.

Per-tower damage is counted by a new `BaseTower.damage_dealt` (enemy HP taken, overkill not
counted), recorded in `Enemy.decrease_hp` next to the existing kill credit. It is statistics
only: not saved, not shown, and it changes no outcome (`tests/test_enemy.py`).

Output: a CSV per strategy (a row per wave) and `report.md`, in `docs/balance/` by default.
Saves go to a temporary folder (`saves_redirected()` from the smoke test), and the script fails
if the real `saves/` changed.

## Consequences

- A balance change can be judged by re-running one command and diffing `docs/balance/`.
- Results are deterministic for a seed and options (`tests/test_balance_sim.py` runs a 3-wave run
  twice and compares the files byte for byte); the game itself has no randomness, so the seed only
  breaks tile ties.
- The bots are simple, readable policies, not optimal players. Results say what *these* plans
  do; a strategy that loses may only mean its plan is poor. Bot choices are listed in
  `docs/BALANCE.md`.
- x4 runs the game's real x4 (four times the motion per tick), which a player also uses; `--game-
  speed 1` is available when that difference matters.
- The script reaches into a few game internals (`_tick`, `_start_new_game`, the controller's
  `_handle_tower_purchase`, the victory and game-over popups); the CI test catches breakage.

## Alternatives considered

- **A separate, simplified balance model** (spreadsheet or pure-math DPS vs HP): fast, but it
  misses targeting, travel time, the cannon's blind spot, tanks destroying towers and overkill,
  which is exactly where the owner's observations live.
- **Driving the game with synthetic mouse events:** closest to a player, but it ties the bots to
  screen positions, the camera and the HUD layout for no gain in fidelity; the placement and
  upgrade code paths used are the same ones the clicks reach.
- **Building on `MenuDemo`:** it has its own rules (denser waves, free escapes, random towers),
  so it doesn't measure the real game.
