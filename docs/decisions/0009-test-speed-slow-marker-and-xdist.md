# 0009. Faster tests: a slow marker and parallel runs
<!-- index | refs: #122 -->

- **Status:** Accepted
- **Date:** 2026-11-03
- **Issues / PRs:** [#122](https://github.com/vectorviolet/chokepoint/issues/122)

## Context

The app's test suite (1,146 tests) took about 14 minutes in CI and 6.5 minutes locally, so
full runs were skipped and every PR waited. Profiling showed no single culprit: the slowest test
takes 4.5 seconds, and the time is a long tail of tests that build a `Game()` (about 0.4 s each,
mostly the menu demo's warm-up and YAML parsing) or play a simulated battle.

## Decision

- Tests are run in parallel with pytest-xdist (`-n auto`), a dev dependency. Each worker is a
  separate process, so pygame's display, the mixer and `GameAudio`'s class state are per worker;
  `tmp_path` and the autouse `saves_in_tmp` fixture keep every test's saves in its own folder.
  The suite passed several runs in a row with it.
- Eight tests that play whole battles or run scripts end to end (3+ seconds each) carry
  `@pytest.mark.slow`. `addopts = '-m "not slow"'` skips them by default; CI runs `-m ""`, so it
  still runs every test.

## Alternatives rejected

- Cheaper `Game()` construction (skipping the menu demo warm-up in tests): it would change what
  the tests exercise, and parallel runs already cut the time far more.
- Removing or shortening the long simulated battles: they pin the game's exact behavior, so
  shortening them would weaken them.
