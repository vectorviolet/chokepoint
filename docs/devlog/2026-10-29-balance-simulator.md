# Balance simulator
<!-- index | refs: #70, #10 -->

**Date:** 2026-10-29 · **Area:** Tooling, balance · **Issue:** [#70](https://github.com/vectorviolet/chokepoint/issues/70) · **PR:** not merged when this entry was written

## Context

After a full playtest on 2026-10-27 the owner reported four things: waves 1 to 10 almost always
cost lives, waves 10 to 25 are trivial with rapid guns plus heavy cannons, from wave 25 tanks
wreck the tower lines, and plane spam wins late because a plane's kill money exceeds its cost.
Nobody can play 30+ waves of every strategy by hand after each change, so issue #70 asked for a
headless simulator with strategy bots, and numbers for each observation, before any balance
change (#10, the owner's).

## Options

How to simulate:

- **The real game, headless:** a `Game()` ticked as fast as possible, nothing drawn, bots buying
  through the game's own placement and upgrade code.
- **A separate balance model** (DPS against HP, a spreadsheet): fast, but it misses targeting,
  shot travel, the cannon's blind spot, tanks destroying towers and overkill.
- **The menu demo's battle:** already headless-friendly, but it has its own rules (denser waves,
  free escapes, random towers).

How bots decide: small fixed plans (an opener, then a repeated cycle of purchases, waiting when
the next one isn't affordable) or a search for the best play. The issue asked for "small, readable"
policies.

## Decision

The real game, headless, with fixed-plan bots (the issue specifies a real `Game()` with saves
redirected). Details in [ADR 0007](../decisions/0007-headless-balance-simulator.md) and the method
in [docs/BALANCE.md](../BALANCE.md). Choices the issue left open were made by Claude and are listed
in the PR for the owner: x4 game speed, a 6-gun opener for every build but gun_spam and minimal,
planes from wave 20 placed at the left end of the longest straight, and "minimal" as guns bought
only after a leak.

Two first attempts showed why the details matter: bots that saved for a cannon, missile or plane
from the start lost every life by wave 6 to 9 (the early waves pay 24 to 84 money each), and
planes started at the map's left edge on the "best" row crossed it before any enemy arrived and
did no damage at all.

No balance number changed. A small statistics counter was added: `BaseTower.damage_dealt` (enemy HP
each tower's hits took, overkill not counted), not saved and not shown.

## Rejected alternatives

- A separate balance model: it can't show tanks destroying towers or planes missing, which two of
  the four observations are about.
- Synthetic mouse clicks for the bots: the same placement and upgrade code, but tied to the
  camera and HUD layout.

## Result

There is nothing visual to show: the result is tables. Headline numbers (seed 70, 40 waves, about
8 minutes for all six strategies):

| strategy | result | lives lost 1-10 | lost 11-25 | lost 26+ | ROI plane |
|---|---|---:|---:|---:|---:|
| gun_spam | died in wave 32 (map full, 50,168 unspent) | 4 | 0 | 6 | |
| gun_cannon | cleared 40 | 4 | 0 | 0 | |
| missile | cleared 40 | 7 | 0 | 0 | |
| plane_spam | died in wave 29 | 4 | 0 | 6 | 0.08 |
| mixed | cleared 40 | 4 | 0 | 0 | 0.09 |
| minimal | died in wave 12 | 9 | 1 | 0 | |

Observations 1 (early lives) and 2 (easy mid-game) are confirmed; 3 (tank wall) in part: tanks
destroy dozens of towers a wave and kill gun-only builds, but builds with cannons or missiles hold
to 40 by rebuilding everything; 4 (planes pay for themselves) is refuted in these runs, planes
earning about 8% of their cost. Full tables in [docs/balance/report.md](../balance/report.md).

```bash
uv run python scripts/balance_sim.py                                   # all strategies, 40 waves
uv run python scripts/balance_sim.py --strategy gun_cannon --waves 10
```
