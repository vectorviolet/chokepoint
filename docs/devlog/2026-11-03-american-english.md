# American English spelling, checked in CI
<!-- index | refs: #90, PR #92 -->

**Date:** 2026-11-03 · **Area:** Docs, tooling · **Issue:** [#90](https://github.com/vectorviolet/chokepoint/issues/90) · **PR:** [#92](https://github.com/vectorviolet/chokepoint/pull/92)

## Context

The repo mixed British and American spelling: center, color, gray, behavior and defense were
spelled the British way in comments, docs and some of our own names (a local variable beside
pygame's `center`, a comment about color above a `color` argument, a "grayed" helper next to
`pygame.transform.grayscale`). Nothing checked spelling, so each new change could go either way.
(This entry avoids writing the British forms, so codespell stays clean on it too.)

## Options

No screenshots: this changes no visuals.

- A: American English everywhere, enforced by codespell in CI.
- B: British English everywhere.
- C: leave it mixed.

## Decision

A, the owner's decision on 2026-11-02 (issue #90): code, comments, docstrings, docs, devlog and
our own identifiers. pygame, the standard library and most libraries spell their APIs the American
way (`color`, `center`, `grayscale`), so the code reads one way throughout.

codespell runs in a new CI job, "Spelling (codespell)", with its typo dictionaries plus the
British-to-American one; the config is `[tool.codespell]` in `pyproject.toml`. Asset file names and
anything read from disk keep their spelling: Kenney's `button_grey` image stays as it is.

## Rejected alternatives

- British (B): every pygame and standard library name we call (`color`, `center`, `grayscale`)
  would still be American, so the code would stay mixed.
- Leave it mixed (C): the inconsistency keeps growing, and searches for one spelling miss the
  other.

## Result

One pure spelling commit (49 files, listed in `.git-blame-ignore-revs` so `git blame` skips it) and
a codespell job that fails on new British spellings or typos. No player-visible game text changed;
balance simulations give identical results before and after.
