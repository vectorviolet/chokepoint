# 0001. SFX channel pool; drop the new sound when full
<!-- index | refs: pygamine#1, pygamine PR #2, #3 -->

- **Status:** Accepted
- **Date:** 2026-10-26
- **Issues / PRs:** [pygamine#1](https://github.com/vectorviolet/pygamine/issues/1), [pygamine PR #2](https://github.com/vectorviolet/pygamine/pull/2) (released in pygamine v0.26.0), adopted in Chokepoint by [PR #41](https://github.com/vectorviolet/chokepoint/pull/41) for [#3](https://github.com/vectorviolet/chokepoint/issues/3)

## Context

pygamine's `GameAudio.play_sfx()` played every sound effect on one shared mixer channel
(`SFX_CHANNEL = 1`), so each new sound stopped the one before it. In a busy fight, tower shots cut
each other off, and any longer sound was cut by the next shot. Chokepoint had worked around it once,
by giving the life-lost bell its own mixer channel 2 ([#2](https://github.com/vectorviolet/chokepoint/issues/2),
[PR #24](https://github.com/vectorviolet/chokepoint/pull/24)). The place/sell sounds (#3) and bomb
impact sounds (#4) needed an engine fix instead of more dedicated channels.

Separately, the load benchmark ([`docs/PERFORMANCE.md`](../PERFORMANCE.md), hotspot 2) found that
every shot decoded its sound file from disk again, about 1.7 ms per call, causing tick spikes.

## Decision

In pygamine v0.26.0:

- `play_sfx()` plays each sound on a free channel from a pool, 16 by default (19 mixer channels in
  total).
- Channels 0-2 are reserved and never used by the pool: 0 is the music, 1 and 2 stay free for a
  game's own use. Chokepoint's bell keeps channel 2.
- **When every pool channel is busy, the new sound is dropped** (`play_sfx()` returns `None`). This
  default was decided by the owner. `steal_oldest=True` instead stops the sound that has played
  longest.
- A per-sound copy limit exists (`max_copies_per_sound`) but is off by default.
- The SFX volume is kept by `GameAudio` and applied to every pool channel, including sounds already
  playing.
- Each sound file is decoded once and cached.

## Consequences

- Sounds overlap instead of cutting each other off, and the SFX slider covers all of them.
- Under heavy load some new sounds are silently skipped. Features that need a sound to be heard
  rarely, but reliably, must cap their own rate rather than rely on the pool: the bomb impact
  sound is capped at 1 per 150 ms and 3 per second in `BombImpactFeedback`, and a sound the full
  pool drops doesn't count toward that cap.
- The sound cache removes the per-shot decoding spikes measured in `docs/PERFORMANCE.md`.
- Chokepoint's bell still uses its own reserved channel 2. Moving it to `play_sfx` is a planned
  follow-up once channel 2 can be released (a breaking change for other users of it).

## Alternatives considered

- **Steal the oldest sound** when the pool is full: available as an option, not the default.
- **More dedicated channels per game feature**, like the bell's: pygamine#1 says the place/sell and
  bomb sounds need the engine fix instead, and shots would still cut each other off on channel 1.
