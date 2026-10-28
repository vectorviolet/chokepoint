# Planes leave the map whole
<!-- index | refs: #59, PR #66 -->

**Date:** 2026-10-28 · **Area:** Gameplay, rendering · **Issue:** [#59](https://github.com/vectorviolet/chokepoint/issues/59) · **PR:** [#66](https://github.com/vectorviolet/chokepoint/pull/66)

## Context

A plane flies once across the map and is removed at the right edge. It vanished while half of its
sprite was still on the map.

**Cause:** `PlaneTower._is_off_map()` tested `position.x - rect.width / 2 > map_width`, but a plane's
`rect` stayed 0×0. Only rotating sizes a `RotatableObject`'s rect, and a plane never rotates. So the
test measured the plane's centre, not its sprite. The click hit-box (`sprite_rect()`, from #29)
already worked around the same 0×0 rect with its own size logic.

The issue was first closed on 2026-10-27: the gap is about 32 px, or about 0.1 s at the edge. After
checking it in play, the owner reopened it the same day: planes should leave the map completely.

## Options

No screenshots: the difference lasts a fraction of a second at the map's right edge.

- **A: Remove the plane when its centre crosses the edge** (the old behaviour). Half the sprite
  pops out of view.
- **B: Remove it once its whole sprite is past the edge.** It slides off the map.

## Decision

B, decided by the owner on 2026-10-27, after he checked it in play. The plane's `rect` is now sized
to its sprite when it is created and after the plane upgrade, so `_is_off_map()` and
`sprite_rect()` use one size. The plane is removed on the first tick where its sprite's left edge
is past `map_width`. The plane info panel stays open until then.

Lingering at the edge means the plane's last bombs are often still falling when it is removed. They
land as orphan shots ([#62](https://github.com/vectorviolet/chokepoint/issues/62)) and keep the
planes' draw layer, above enemies and bomb explosions, so they don't jump under a tank mid-fall.

## Bombs near the edge

**Pending owner decision.** While its sprite slides off, does the plane keep bombing? A bomb keeps
the plane's speed with drag 0.94 per tick, so it lands about `speed / (1 - drag)` ≈ 17 × speed px
ahead of where it was dropped. The options are:

- **(a)** Keep bombing until the plane is removed. Some bombs land off the map.
- **(b)** Stop once the plane's centre is past the edge. This is what PR #66 does for now. The last
  bombs can still land up to about 17 × speed px past the edge.
- **(c)** Drop only bombs whose predicted landing point is on the map.

## Rejected alternatives

- A: removing at the centre, as above.

## Result

PR #66. Tests: removal exactly when the sprite's left edge passes the edge (not its centre), the
info panel staying open until then, a departed plane's bombs drawn in the planes' layer, and the
orphan-bomb tests run through the plane's real exit.

## Revisit if

- Planes get a rotation, or a flight path that leaves the map by another edge.
