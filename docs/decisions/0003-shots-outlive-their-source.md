# 0003. Shots in flight outlive their source

- **Status:** Accepted
- **Date:** 2026-10-27
- **Issues / PRs:** [#50](https://github.com/vectorviolet/chokepoint/issues/50), [PR #52](https://github.com/vectorviolet/chokepoint/pull/52) (plane bombs, merged); [#62](https://github.com/vectorviolet/chokepoint/issues/62), [PR #65](https://github.com/vectorviolet/chokepoint/pull/65) (all shooters, open when this was written)

## Context

A shot in flight lives in its shooter's `bullets` list and is only updated while the shooter is in
`towers` or `enemies`. So when the shooter went away, its shots vanished:

- a plane leaving the map took its falling bombs with it: no explosion, no damage (#50);
- a tank dying or escaping took its shell, and a tower sold or destroyed took its missile (#62).

The owner's rule (#62, 2026-10-27): **once a shot is fired, it must not be destroyed when its source
is destroyed, sold or removed.** It keeps flying and hits or misses exactly as it would have. This
applies to any future shooter too.

## Decision

- PR #52 kept a plane's in-flight bombs in `BattleSimulation.orphan_bombs` after the plane was
  removed.
- PR #65 generalises that into one mechanism, `BattleSimulation.orphan_shots`, replacing
  `orphan_bombs`:
  - Shot types that can outlive their source say so with `outlives_source = True` (missile
    `Projectile`, `Bomb`, `TankBullet`). Instant hits (muzzle flashes) don't; they land in the same
    tick.
  - Orphan shots update in the same phase of the tick as their source's shots would, so they land on
    the same tick, and are drawn where those shots would be.
  - Kills and money stay credited to the original source object.
  - They freeze while paused and are cleared on new game, on load and between menu demo runs.

## Consequences

- Planes do slightly more damage near the right edge of the map (their last bombs now hit); selling a
  tower right after it fires no longer cancels the shot.
- Kills credited to a removed tower or plane don't show anywhere, since it can't be selected.
- In-flight shots are still not saved (`GameSaveMixin` skips bullets).
- A new shooter type only has to set `outlives_source` on its shot class.

## Alternatives considered

- **One carry-over list per shooter type** (extending `orphan_bombs` with similar lists): #62 asked
  explicitly for one general mechanism.
- **Leave it (shots vanish):** #50 offered closing it as intended behaviour because of the small
  damage increase near the edge. The owner merged the fix instead and then made the general rule in
  #62.
