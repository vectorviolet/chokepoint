# 0002. Bombs deal damage at landing; the explosion is cosmetic
<!-- index | refs: #4, PR #49 -->

- **Status:** Accepted
- **Date:** 2026-10-27
- **Issues / PRs:** [#4](https://github.com/vectorviolet/chokepoint/issues/4), [PR #49](https://github.com/vectorviolet/chokepoint/pull/49)

## Context

A plane's `Bomb` used to turn into an `Explosion` bullet when it landed. That bullet both dealt the
splash damage and drew the smoke-and-fireball animation, on game time. Issue #4 asked for a visible
and audible impact, and the owner decided (2026-10-27) that the damage is applied at the moment of
impact while the visual is cosmetic and plays out on real time, also while paused. Game logic and
cosmetics therefore needed different clocks.

## Decision

- `Bomb._detonate` deals the splash damage at once, on game time, in the tick the bomb lands.
- It then reports the landing through `IGameContext.bomb_landed(position, radius)`. The context's
  `BombImpactFeedback` shows the explosion and plays the sound on its own real-time clock.
- The old `Explosion` bullet is removed.

## Consequences

- Damage timing no longer depends on an animation; pausing or x2/x4 never changes when or how much
  damage is dealt.
- Projectiles still never import `Game`: the feedback goes through the `IGameContext` protocol, which
  gained `bomb_landed()`.
- The explosion is drawn by the game (and silently by the menu demo), at most 24 at once, cleared on
  new game and load. In-flight explosions are not part of the save.
- Tests that checked damage through the old `Explosion` were rewritten for damage at landing.
- The same split applies to later effects: game state on game time, cosmetics on real time (as the
  place/sell effects in PR #41 already did).

## Alternatives considered

- **Keep the `Explosion` bullet on game time:** the animation would freeze when paused and speed up
  at x4, which the owner did not want.
