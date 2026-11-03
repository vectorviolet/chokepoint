# Planes drop only bombs that land on the map
<!-- index | refs: #94, #59, PR #97 -->

**Date:** 2026-11-03 · **Area:** Feel, gameplay · **Issue:** [#94](https://github.com/vectorviolet/chokepoint/issues/94) · **PR:** [#97](https://github.com/vectorviolet/chokepoint/pull/97)

## Context

Since [#59](https://github.com/vectorviolet/chokepoint/issues/59) (PR #66) a plane flies on until
its whole sprite has left the map, and stops bombing once its center is past the right edge
(option (b) in [Planes leave the map whole](2026-10-28-planes-leave-the-map.md)). A bomb keeps the
plane's forward speed at release and slows with drag 0.94 per tick for its 600 ms fall, so it
lands ahead of where it was dropped. The last bombs could still land past the edge, where no
enemy ever walks.

## Options

No screenshots: nothing new is drawn, only where the last bombs land changes.

- **(b)** Keep the center rule. The last bomb lands up to about 33 px (level 1, speed 2) or 17 px
  (level 2, speed 1) past the edge. The blast radius is 96 / 128 px, so most of the explosion is
  still on the map.
- **(c)** Predict where a bomb would land (the plane's x plus its drift) and skip the drop when
  that point is past the map's width.

## Decision

(c), the owner's decision on 2026-11-03 (issue #94): stop earlier, so no bomb lands off the map.

The drift comes from `Bomb`'s own constants: `Bomb.landing_offset(velocity, game_speed)` mirrors
`Bomb.update()` (each tick it moves by velocity × speed, then drag scales the velocity by
0.94^speed) and returns the series' limit, velocity × speed / (1 − 0.94^speed). The fall's
remaining ticks add under 0.1 px, so the prediction never falls short however game time rounds
into ticks. The plane checks it every tick at the current game speed:

| Plane | x1 | x2 | x4 |
|---|---|---|---|
| Level 1 (speed 2) | 33.3 px | 34.4 px | 36.5 px |
| Level 2 (speed 1) | 16.7 px | 17.2 px | 18.2 px |

The plane still flies on until its whole sprite has left the map, and bombs already falling land as
before (orphan shots, [#62](https://github.com/vectorviolet/chokepoint/issues/62)).

## Rejected alternatives

- (b), the center rule: some bombs landed off the map, a wasted explosion the player can see.

## Result

`PlaneTower._bomb_would_land_past_the_edge()` replaces `_is_past_the_edge()`. Tests fly level 1 and
level 2 planes off the map at x1 and x2 and check that every bomb lands at or before the edge and
that the last one lands within one drop interval of it; that a bomb predicted to land exactly on
the edge is dropped and one half a pixel further is not; and that a real falling bomb drifts the
predicted distance to within 0.1 px. The orphan-bomb tests now start from the last bomb that lands
on the edge.

## Revisit if

- The game speed changes while a bomb falls: the prediction uses the speed at the drop, so a
  switch from x1 to x4 mid-fall can carry the last bomb up to about 3 px further.
- Bombs get a different drag, fall time or drop velocity: the prediction follows `Bomb`'s
  constants, but check the table above.
