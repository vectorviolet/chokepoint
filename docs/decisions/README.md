# Architecture Decision Records

Code and system choices that shape more than one feature: what we decided, why, and what it costs.
The story behind features and UI choices, with screenshots, is in the
[devlog](../devlog/README.md).

Status is **Accepted** (in force), **Superseded** (replaced by a later ADR, linked), or **Proposed**
(not decided yet). An ADR is not edited after it is accepted, except to change its status or add
links; a changed decision gets a new ADR that supersedes the old one.

## Records

| # | Title | Status | Date | Issues / PRs |
|---|---|---|---|---|
| [0001](0001-sfx-channel-pool.md) | SFX channel pool; drop the new sound when full | Accepted | 2026-10-26 | pygamine#1, pygamine PR #2, #3 |
| [0002](0002-bombs-damage-at-landing.md) | Bombs deal damage at landing; the explosion is cosmetic | Accepted | 2026-10-27 | #4, PR #49 |
| [0003](0003-shots-outlive-their-source.md) | Shots in flight outlive their source | Accepted | 2026-10-27 | #50, PR #52, #62, PR #65 |
| [0004](0004-grid-targeting.md) | Grid targeting with identical target choice | Accepted | 2026-10-27 | #40, PR #51 |
| [0005](0005-panel-content-independent-of-placement.md) | Panel content independent of its placement | Accepted | 2026-10-27 | #33 |
| [0006](0006-playtest-save-from-game-code.md) | Play-test save built from game code | Accepted | 2026-10-27 | #63, PR #64 |

## Adding an ADR

Add one when a PR makes an architecture or system choice: a new mechanism other code must follow,
a rule about game time vs real time, a data format, a performance trade-off. Take the next number,
name the file `NNNN-short-title.md`, and add a row above.

## Template

```markdown
# NNNN. Title

- **Status:** Accepted
- **Date:** YYYY-MM-DD
- **Issues / PRs:** [#N](https://github.com/vectorviolet/chokepoint/issues/N), [PR #M](https://github.com/vectorviolet/chokepoint/pull/M)

## Context

The forces at play: the problem, the constraints, what was measured.

## Decision

What we do, stated so that later code can follow it.

## Consequences

What gets easier, what gets harder, what must now be kept true (and which tests check it).

## Alternatives considered

- The alternative, and why not.
```
