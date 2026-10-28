# Music button state after a restart
<!-- index | refs: #54, PR #57 -->

**Date:** 2026-10-27 · **Area:** Audio, bug · **Issue:** [#54](https://github.com/vectorviolet/chokepoint/issues/54) · **PR:** [#57](https://github.com/vectorviolet/chokepoint/pull/57)

## Context

The owner reported that sometimes, after quitting and restarting, the music button showed the
opposite of what was playing ("off" while music played), and toggling kept the two reversed.

**Cause:** `Game.__init__` restored a saved `music_on: false` by pausing the music. `show_splash()`
then ran the splash and only afterwards read whether the music was paused. But the splash plays its
clip through the game's own `GameAudio`, and `play_music()` / `stop_music()` reset the paused flag.
So after a played splash the music always started while the icon (set before the splash) still said
"off", and quitting saved `music_on: true`. Skipping the splash avoided it, which is why it happened
only sometimes.

## Options

No screenshots: the bug is a mismatch between the icon and what you hear. The issue suggested
applying the saved state after the splash, independent of what the splash does with the audio (for
example by reading it before `super().show_splash()`); no other approach was tried.

## Decision

Read the paused flag before `super().show_splash()`, start the music after it, pause it again if it
was off, then refresh every music icon and the pause menu's Music label (`_refresh_music_toggles()`).
The fix is in `src/app/game.py` only; the splash and pygamine are unchanged.

## Result

Merged in PR #57. `tests/test_music_state.py` uses a fake splash that plays and stops a clip through
the game's audio, and a skipped one, and checks quit → restart → quit → restart for both values.
