# Type checking: mypy and asserts instead of silent guards
<!-- index | refs: #37, PR #91 -->

**Date:** 2026-11-02 · **Area:** Tooling, code · **Issue:** [#37](https://github.com/vectorviolet/chokepoint/issues/37) · **PR:** [#91](https://github.com/vectorviolet/chokepoint/pull/91)

## Context

Issue #37 started as a naming review (`maxHP`, `killMoney`, an `id` parameter shadowing the
built-in). While making those changes locally, the owner also fixed what the IDE's type checker
flagged: `int` game times that were really floats, `render(..., 2, ...)` where a bool was meant,
tuples passed where a `Vector2` was expected. Where a value could be None by its type, the fix was
an `if not x: return`. Together with a half-finished rename, those edits broke the game and were
set aside. Nothing in CI checked types, so the hints in the code were never verified.

## Options

No screenshots: this changes no visuals.

- A: silent guards (`if not x: return`) wherever the checker sees a possible None.
- B: `assert x is not None` where the value can't be None, real handling only where it can, and
  mypy in CI with lenient settings.
- C: as B, but strict mypy on the whole code at once.

## Decision

B, agreed with the owner on 2026-11-02 (the plan in #37). An assert states the invariant and
fails loudly if it ever breaks; a silent guard would skip a frame of drawing or a game step and
hide the bug. mypy runs as its own CI job ("Type check (mypy)") with default checks on `src/`,
so new type mistakes show up without a large up-front cleanup. The setup is in
[ADR 0008](../decisions/0008-mypy-lenient-start.md).

The one place where None really happened was tower placement. A click used the tile the cursor
was on at the previous frame, which is None before the first frame and out of date if the camera
scrolled since. Placement now works out the tile from the click itself, and so does the preview.

## Rejected alternatives

- Silent guards (A): they hide broken invariants, and the owner's local version showed how easily
  they paper over a half-done change.
- Strict mypy now (C): hundreds of changes in one PR, mostly annotations in code that works; it
  can be tightened step by step instead.

## Result

`maxHP` → `max_hp` and `killMoney` → `kill_money`; mypy passes on `src/` with a few targeted
ignores listed in the ADR; balance simulations give identical results before and after.

## Revisit if

- pygamine's `require_component` (pygamine#14) is released: switch the renderer asserts to it.
- The mixins (`app.game_events`, `app.game_save`) get a typed `self`, so their mypy exemptions can go.
