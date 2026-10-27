# No sliver of the Level counter after Tab

**Date:** 2026-10-26 · **Area:** UI, bug · **Issue:** [#43](https://github.com/vectorviolet/chokepoint/issues/43) · **PR:** [#46](https://github.com/vectorviolet/chokepoint/pull/46)

## Context

Tab slides the HUD off the screen edges ([#23](https://github.com/vectorviolet/chokepoint/issues/23)).
Once the level reached two digits, a thin strip of the Level counter stayed visible at the left
edge.

**Cause:** `HudSlide` measured each group's slide distance once, in `bind()`. The level text lays
itself out wider when it changes ("Level 1" → "Level 12" moves its right edge from 76 to 84 px), but
the distance stayed at 76 px, so 8 px stayed on screen. The money and lives counters had the same
risk.

## Options

<table>
<tr>
<td><img src="img/43-level-sliver-before.png" width="400"><br>The bug, zoomed 3x: the dark strip at the left is the Level counter.</td>
</tr>
</table>

- Re-measure the distance when a slide starts.
- Re-measure every time the offset is used.

## Decision

Re-measure every time (default chosen by Claude, approved by the owner at merge):
`_Group.distance` became a property computed from the objects' current resting rects each time the
offset is taken. That also covers text that changes while the HUD is already hidden, for example
when a wave ends or the money counter peeks back.

## Rejected alternatives

- Measuring only when the slide starts: a counter that grows while the HUD is hidden would show a
  sliver again.

## Result

<table>
<tr>
<td><img src="img/43-hud-hidden-before.png" width="300"><br>Before: HUD hidden at level 12.</td>
<td><img src="img/43-hud-hidden-after.png" width="300"><br>After: nothing left on screen.</td>
</tr>
</table>

Merged in PR #46. A test compares the screen's left strip at level 12 with level 1, pixel by pixel.
