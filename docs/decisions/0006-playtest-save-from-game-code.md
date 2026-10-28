# 0006. Play-test save built from game code

- **Status:** Accepted (implementation in [PR #64](https://github.com/vectorviolet/chokepoint/pull/64), open when this was written)
- **Date:** 2026-10-27
- **Issues / PRs:** [#63](https://github.com/vectorviolet/chokepoint/issues/63), [PR #64](https://github.com/vectorviolet/chokepoint/pull/64)

## Context

The owner play-tests each PR in its own worktree and wanted every one to start from the same
ready-made run (100,000 money, mid wave 10, every tower at every level, muted). The save and
settings formats change as features land (for example per-tower kills and money in PR #28, the
auto-pause setting in PR #53). A play-test save must also never touch the real `saves/` folder: a headless script
once deleted the player's real save (see CLAUDE.md).

## Decision

`scripts/make_playtest_save.py` builds the save with the real game code: a `Game()` under
`saves_redirected()` (from `scripts/smoke_test.py`), set up as specified, then written by the game's
own `_save_game()` and `_save_settings()`. This was the owner's requirement in #63. Only
`save.json` and `settings.json` are written, into a folder given with `--out`.

Guards: `--out` is required; existing files are not overwritten without `--overwrite`; an `--out`
inside the main checkout's own `saves/` is refused, comparing paths case-insensitively on
Windows. The main checkout is the main work tree of the shared git folder (also for submodules and
their worktrees); a copy nested in another repository, or with no `.git`, is its own. Without git,
`.git` is read directly. If it still can't be found, any `saves` folder outside the current
checkout is refused.

Building the run: towers are placed first, then the wave fills to about half spawned under
`BattleSimulation.waves_only()` (towers idle, no fighting, escapes cost no lives), so any
`--level` works. In long, high-level waves many of the first enemies reach the end while it
fills, so fewer than half the wave is on the path; the script prints the real number. The plane
is added after the fill, at the map's left edge. The script uses public API only:
`TowerFactory.create(..., level=)` (shared with the save restore and the menu demo),
`WaveManager.spawned_count` / `wave_size`, `waves_only()` and `gameplay.path_geometry`.

## Consequences

- The save always matches the current format; no fixture to update by hand.
- The script depends on game internals (`_save_game`, tower placement, wave state); changes there
  can break it. `tests/test_make_playtest_save.py` runs it and loads the result with a real `Game()`,
  so CI catches that.
- Building the save runs real game code, so the saves-isolation rule applies to it like to any
  other script.

## Alternatives considered

- **A checked-in `save.json`:** not discussed in the issue; it would go stale with every format
  change.
