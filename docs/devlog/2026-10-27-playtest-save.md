# Play-test save

**Date:** 2026-10-27 · **Area:** Tooling · **Issue:** [#63](https://github.com/vectorviolet/chokepoint/issues/63) · **PR:** [#64](https://github.com/vectorviolet/chokepoint/pull/64) (open when this entry was written)

## Context

The owner play-tests every PR in its own worktree. Each time, a run had to be built up first:
earning money, reaching a later wave, buying every tower. Issue #63 (owner request, 2026-10-27)
asked for a script that writes a ready-made save into a given folder.

## Options

How to produce the save:

- **Build it with the real game code**: start a `Game()` with saves redirected, set up the run, and
  write it with the game's own save functions.
- **A hand-written or checked-in `save.json`**: not discussed in the issue; listed here for
  contrast. It would break whenever the save format changes.

## Decision

Built with the game code (owner, in the issue: "It builds the save with the real game code, so it
always matches the current save format"). The contents were also specified by the owner: 100,000
money, wave 10 about halfway through and paused, one tower of every type at every level, UPG PLANES
bought with a plane in the air, music and SFX volume 0. See
[ADR 0006](../decisions/0006-playtest-save-from-game-code.md).

Details in PR #64: the script refuses to run without `--out`, refuses to overwrite without
`--overwrite`, and refuses to write into the main checkout's own `saves/`. `window_size` is left out
of the settings so the game picks its best fit for the screen.

After code review on PR #64:
- The towers are placed before the wave fills but hold fire while it does. When they fired, wave
  10 kept only 1 of its 7 spawned enemies, and the issue asks for half the wave on the path.
- While the wave fills, enemies that reach the end cost no lives and can't end the run, so any
  `--level` works (tested up to 200). The script reports how many got through.
- The plane is added last, because placed earlier it would fly off the map during the fill.
- The main checkout is found with git, or by reading `.git` when git isn't available. If it still
  can't be found, the script refuses any `saves` folder outside the current checkout.

## Rejected alternatives

- A checked-in save file: it would go stale with every save format change.

## Result

<img src="img/63-playtest-save.png" width="640">

Continue after running the script: wave 10, 100000 coins, the towers and plane at the top of the
path. PR #64 was still open when this entry was written.

```bash
uv run python scripts/make_playtest_save.py --out saves
uv run python __main__.py   # Play → Continue
```
