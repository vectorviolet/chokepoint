# Round counter wording
<!-- index | refs: PR #81 -->

**Date:** 2026-10-30 · **Area:** UI · **PR:** [#81](https://github.com/vectorviolet/chokepoint/pull/81)

## Context

While reviewing the refreshed README screenshots, the owner requested "Round" instead of
"Level" for the top-left counter, as a more accurate name for progress through enemy groups.
Tower and plane upgrades already use "Level".

## Options

| Existing label | Requested label |
|---|---|
| ![Top-left counter reading Level 15](img/81-counter-level.png) | ![Top-left counter reading Round 15](img/81-counter-round.png) |

These are native-size crops from the 1920×1080 gameplay captures.

## Decision

Use "Round" for the top-left counter and victory subtitle, as requested by the owner.
Use the same wording in the README and refresh its screenshots and animation. Tower and
plane upgrade levels retain "Level".

## Rejected alternatives

- Keep "Level" for the counter: it uses the same term as tower upgrades for a different concept.

## Result

The HUD starts at "Round 1" and updates that wording as the run advances, a save is loaded,
or the window is resized. The victory subtitle reads "Round 25 cleared". Progression and
save keys are unchanged. Included in PR #81.
