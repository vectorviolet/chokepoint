# 0004. Grid targeting with identical target choice

- **Status:** Accepted
- **Date:** 2026-10-27
- **Issues / PRs:** [#40](https://github.com/vectorviolet/chokepoint/issues/40), [PR #51](https://github.com/vectorviolet/chokepoint/pull/51); measured in [#12](https://github.com/vectorviolet/chokepoint/issues/12), [PR #39](https://github.com/vectorviolet/chokepoint/pull/39)

## Context

Every tick, each ground tower computed the distance to every enemy, and each tank to every tower:
O(towers x enemies). The load benchmark (`scripts/benchmark_load.py`,
[`docs/PERFORMANCE.md`](../PERFORMANCE.md)) showed `GroundTower.work` taking about 70% of the tick,
with 16.5 million `Vector2.length` calls in 120 frames at 600 enemies x 300 towers. A throwaway patch
in #12 measured the fix: the 600 x 300 tick went from 48 ms to about 20 ms with a grid alone, while
squared distances without a grid gained only about 20%, because the cost was the Python loop over
every pair.

Real games are much smaller (the largest authored wave has 33 enemies), so the fix had to be free of
behaviour changes and cheap at small sizes.

## Decision

- Per-tick spatial grids with 128 px cells, in `src/gameplay/combat/targeting.py`:
  - `EnemyGrid`: ground towers scan only the cells their range covers. Built lazily once per tick;
    rebuilt if kills shrink the enemy list during the tick.
  - `TowerGrid`: tanks search rings of cells outward until no unsearched cell can hold a closer
    tower. Planes are left out once per tick.
- A squared-distance pre-filter (against `range**2`, with a 1e-9 relative margin) skips what can't
  be an answer; the remaining candidates are compared with the same `Vector2` calls as before.
- **The choice must be exactly the old one:** towers pick the nearest enemy by `length()`, the first
  in the list on a tie, range inclusive; tanks pick the nearest tower at any distance, first on a
  tie. The heavy cannon's later blind spot (#11) is an inner radius, exclusive at its edge.
- Tick rate and retarget frequency are unchanged.

## Consequences

Tick times from `docs/PERFORMANCE.md` (ms, zoom 1; the machine was noisy, small rows swing
±50%):

| enemies x towers | speed | tick mean before | tick mean after | sim load before → after |
|---:|---:|---:|---:|---:|
| 30 x 20 | x1 | 0.29 | 0.44 | 5% → 7% |
| 100 x 50 | x4 | 2.82 | 1.79 | 47% → 29% |
| 300 x 150 | x1 | 14.56 | 11.62 | 240% → 192% |
| 600 x 300 | x1 | 48.42 | 14.90 | 799% → 246% |
| 600 x 300 | x4 | 54.31 | 18.66 | 896% → 308% |

Targeting alone, timed per tick: 0.05 → 0.10 ms at 10 x 20, even at 30 x 20, 28.8 → 5.0 ms at
600 x 300. So the grid costs about 0.05 ms per tick at tiny sizes, breaks even around 30 enemies and
wins from there.

- `tests/test_targeting.py` keeps the old algorithms as references and checks the grids against
  them on seeded random layouts (ties, cell borders, range boundaries, kills between towers) and on
  a whole menu-demo battle, tick by tick. Any change to targeting must keep these passing or
  deliberately change the reference.
- `GroundTower.update` and friends take an optional `enemy_grid`; without one, a grid is built for
  that call, so old callers and tests keep working.
- 300 x 150 is still above the real-time limit. Going further needs a design change (a lower tick
  rate or retargeting less often), which is out of scope and would change game feel.

## Alternatives considered

- **Squared distances without a grid:** about 20% faster; not enough.
- **Lower `TICKS_PER_SECOND` or retarget less often:** changes game feel and needs every per-tick
  speed retuned; left to the owner as a separate decision.
