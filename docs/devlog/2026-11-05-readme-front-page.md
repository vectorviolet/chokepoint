# README as a front page
<!-- index | refs: #157 -->

**Date:** 2026-11-05 · **Area:** Docs · **Issue:** [#157](https://github.com/vectorviolet/chokepoint/issues/157)

## Context

The README was 299 lines, and about half of it was contributor process: checks, the play-test
save, asset sources, code style, releases. Gameplay numbers and the enemy and tower tables sat
in it too, next to the generated stats reference that already carries them. Popular open-source
game READMEs stay short (Shattered Pixel Dungeon 27 lines, Endless Sky 50, OpenRA 60,
Mindustry 80, Unciv 136) and keep numbers in a wiki and process in CONTRIBUTING.md. The README
is also the first page a visitor to the owner's portfolio sees.

## Options

No screenshots: this changes no visuals.

- A: keep everything in the README.
- B: a minimal README of about 30 lines.
- C: a front-page README, with the contributor material in `CONTRIBUTING.md` and the code tour
  in `docs/ARCHITECTURE.md`.

## Decision

C, the owner's decision on 2026-11-05 (issue #157). The README keeps the logo, badges, pitch,
GIF, download, screenshots, controls and credits, and gains a features list, a short
numberless overview of towers and enemies, an "Under the hood" section, links and an author
section. Numbers live on the wiki's stats pages.

## Rejected alternatives

- Keep it all (A): half the page stays process that players never need.
- A 30-line README (B): too little for a portfolio reader to see what the project does.

## Result

The README went from 299 lines to 137. Contributor sections moved to `CONTRIBUTING.md`, and
the project layout and architecture overview to `docs/ARCHITECTURE.md`.

## Revisit if

- The wiki stats pages stop being generated, since the README now only links them.
