# Shift keeps placing
<!-- index | refs: #9, PR #48 -->

> **Superseded** by [the keep-placing toggle](2026-10-28-placement-toggle.md) (#69): holding Shift
> was tiring and set off Windows' Sticky Keys prompt, so a Shift *press* now flips a HUD toggle.

**Date:** 2026-10-27 · **Area:** Controls · **Issue:** [#9](https://github.com/vectorviolet/chokepoint/issues/9) · **PR:** [#48](https://github.com/vectorviolet/chokepoint/pull/48)

## Context

Placing a tower ends placement mode, so building a row of the same tower takes a button click (or
hotkey) per tower. Issue #9 asked that holding Shift keep the tower type selected after placing,
while it is still affordable.

## Options

No screenshots: the change is in input handling and looks the same on screen.

- **What ends it:** releasing Shift could end placement mode at once, or the next placement without
  Shift could end it. PR #48 chose the second: releasing Shift ends nothing by itself.
- **Running out of money:** the last affordable placement ends placement mode, as it does today.
- **Planes:** they need no free tile, so with Shift each click launches another plane. They follow
  the same rule as other towers.
- **A visual hint** ("Shift keeps placing" in the tooltip or HUD) was not added.

## Decision

Defaults chosen by Claude in PR #48, approved by the owner at merge. Shift is read at the moment of
placement (`event.mod`, or `pygame.key.get_mods()` because mouse events carry no `mod`). Right click
still cancels at any time.

One fix came with it: a placed tower's tile is marked taken at once. Before, it was refreshed only on
the next simulation tick, so two fast Shift-clicks on one tile could have stacked two towers.

## Result

Merged in PR #48, with 8 headless tests in `tests/test_tower_placement.py`.

## Revisit if

- Players don't discover the feature: add the hint that was left out.
