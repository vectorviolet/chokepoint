# 0010. The web build: pygbag, localStorage saves, an async loop, web-only settings
<!-- index | refs: #152, PR #187 -->

- **Status:** Accepted
- **Date:** 2026-11-12
- **Issues / PRs:** [#152](https://github.com/vectorviolet/chokepoint/issues/152), [PR #187](https://github.com/vectorviolet/chokepoint/pull/187)

## Context

Chokepoint should play in a desktop browser on itch.io (no mobile). pygame-ce runs in the browser
through WebAssembly; [pygbag](https://github.com/pygame-web/pygbag) packages a pygame project for it
(`sys.platform == "emscripten"`). A spike showed what differs from desktop: the browser's single
thread must get control back every frame, pygbag 0.9.3 has no persistent file system, translucent
blits are about 6 times slower, MP3 is refused, there are no threads, and a page can't quit,
resize its window or enter fullscreen without a user gesture.

## Decision

- **Package with pygbag**, from a staged folder (`main.py` from `web/main.py`, `src/`, `assets/`,
  `config/`). The entry point runs `Application.run_async()` (pygamine), the same loop as `run()`
  with an `await asyncio.sleep(0)` per frame. `__main__.py` and the desktop builds are unchanged.
- **Saves and settings go to the browser's `localStorage`**, through pygamine's `SaveStore`. The
  game doesn't change; if storage is blocked it starts with its defaults.
- **Platform checks go through `util/web.py`**: `is_web()` (read at call time, so tests can patch
  `sys.platform`), `open_in_new_tab()`, `is_fullscreen()` and `toggle_fullscreen()`. Nothing else
  touches pygbag's `platform.window`.
- **The web build has its own settings and Exit**: no window size, window mode becomes a Fullscreen
  toggle (`Game.cycle_window_mode()` is overridden, so F11 and the row do the same), no splash,
  and Exit opens the `thanks` panel instead of quitting. The desktop paths are the same code as
  before.
- **Music is OGG for every platform**, one file.
- **Translucent blits use `ALPHA_BLIT`** (pygamine), which is `0` outside the browser.

## Consequences

- Every new feature runs in two places. Anything that quits, opens windows, uses threads, files
  outside saves, or blocks in its own loop needs a web answer. Tests pretend to be the browser by
  patching `sys.platform` and `platform.window` (`tests/test_web.py`).
- New translucent full-screen blits should pass `special_flags=ALPHA_BLIT`.
- Assets must be formats the browser's SDL can decode (OGG, not MP3).
- The CI build script and the release job (an `html5` channel on itch.io) are the next PR; this one
  ships only the game code that they build.
- Not covered by the automatic tests: the real browser. The pygbag build was checked by hand in
  Chrome for this PR.

## Alternatives considered

- **Pyodide or a hand-made emscripten build.** More work for the same result; pygbag is built for
  pygame-ce.
- **A virtual file system for saves (IndexedDB mount).** pygbag 0.9.3 has no persistent mount;
  `localStorage` is synchronous and big enough for these small JSON files.
- **A second, web-only game class.** It would drift from the desktop game; `is_web()` branches in
  the few places that differ keep one code path.
