# Performance: hundreds of enemies and towers

Spike test for issue #12: how the frame rate holds up with hundreds of enemies
and towers, measured with `scripts/benchmark_load.py`. This document records
the numbers and the hotspots behind them. No fixes have been made yet; each one
listed below was tried only as a monkeypatched prototype so it could be
measured. Which of them to adopt is a follow-up decision.

## How to run it

From the repo root:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python scripts/benchmark_load.py
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python scripts/benchmark_load.py --profile
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy uv run python scripts/benchmark_load.py \
    --loads 100x50 --speeds 4 --zooms fit --frames 300
```

The default run takes about 80 s (90 s with `--profile`). Options:
`--loads` (pairs of enemies x towers, default `30x20,100x50,300x150,600x300`),
`--speeds` (`1,4`), `--zooms` (`1` or `fit`, the farthest zoom-out that shows the
whole map), `--frames` (120 measured frames per scenario), `--warmup` (20),
`--seed` (12) and `--profile` (cProfile the last scenario in a separate run).
Like the smoke test, the script sends every save to a temporary folder and fails
if the real `saves/` changes. `tests/test_benchmark_load.py` runs it at tiny
counts in CI.

## Method

- A real `Game()` on the game panel, 1920x1080, waves off, lives infinite.
- **Enemies:** seeded random points along the path. Types 1 to 6 are weighted
  4:3:2:2:1:1, so tanks are included, at wave level 15 with HP x5 so most of them
  survive the measured frames. Between frames, outside the timed sections, any
  enemy that was killed or escaped is replaced, so the count stays fixed.
- **Towers:** all four types in round-robin order, ground towers at max level.
  Ground towers go on the build tiles nearest the path. Planes (type 4) fly
  across the map at seeded random rows. Destroyed towers and planes that have
  left the map are replaced between frames.
- **One frame** is one `_tick()` (simulation) plus one `draw()` (the whole frame,
  HUD included), and each is timed separately with `perf_counter`. The table
  reports the mean, p95 and max in ms over 120 frames.
- **Fixed tick:** `TICKS_PER_SECOND = 165`, the same as the window's fps cap, so
  at the cap one tick runs per frame. **Speed x4 does not run more ticks.** Each
  tick advances game time by `TICK_MS * speed` and moves things `speed` times
  farther, so x4 means more shots, hits, kills and sounds per tick. At a display
  rate of f FPS, a frame runs 165/f ticks.
- **Sim load** is `165 * tick_mean / 1000`, the share of each real second spent
  simulating. At 100% or more the simulation can't keep real time at any frame
  rate, and the game falls into slow motion. Per frame, the backlog is capped at
  `MAX_FRAME_MS` = 250 ms.
- **FPS** is the highest frame rate at which the simulation still keeps real
  time: `(1000 - 165 * tick) / draw`, capped at 165, or "slow-mo" when the sim
  load is 100% or more. "FPS (p95)" applies the p95 tick and draw to every frame,
  so it is a pessimistic bound.
- **Headless caveat:** the dummy video driver draws into a software surface and
  never presents it to a screen. Draw times here therefore understate the cost
  on a real display. The simulation numbers are unaffected.
- Run-to-run noise is about 10 to 15% on means. Maxima are single frames and
  noisy.

## Machine

| | |
|---|---|
| CPU | 13th Gen Intel Core i7-13620H (10 cores / 16 threads) |
| RAM | 24 GB |
| OS | Windows 11 Education 10.0.26200 |
| Python | CPython 3.13.14 |
| pygame-ce | 2.5.7 (SDL 2.32.10), `SDL_VIDEODRIVER=dummy` |
| Commit | `origin/main` at 7716508 |

## Results (baseline, 2026-10-26)

Times are in ms.

| enemies | towers | speed | zoom | tick mean | tick p95 | tick max | draw mean | draw p95 | draw max | sim load | FPS (mean) | FPS (p95) | kills |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 20 | x1 | 1 | 0.64 | 0.93 | 5.67 | 2.06 | 2.66 | 5.47 | 11% | 165 | 165 | 0 |
| 30 | 20 | x4 | 1 | 1.18 | 3.54 | 17.09 | 2.43 | 3.12 | 4.57 | 20% | 165 | 133 | 1 |
| 30 | 20 | x1 | fit | 0.64 | 0.96 | 5.28 | 2.62 | 3.42 | 4.09 | 11% | 165 | 165 | 0 |
| 30 | 20 | x4 | fit | 1.24 | 4.72 | 12.28 | 2.97 | 5.17 | 8.65 | 20% | 165 | 43 | 1 |
| 100 | 50 | x1 | 1 | 2.63 | 3.48 | 23.44 | 2.83 | 3.86 | 5.44 | 43% | 165 | 110 | 0 |
| 100 | 50 | x4 | 1 | 4.46 | 16.85 | 40.50 | 3.02 | 4.05 | 10.23 | 74% | 87 | slow-mo | 2 |
| 100 | 50 | x1 | fit | 2.47 | 3.13 | 18.18 | 3.44 | 4.64 | 5.56 | 41% | 165 | 104 | 0 |
| 100 | 50 | x4 | fit | 4.55 | 16.85 | 42.72 | 3.86 | 4.97 | 8.72 | 75% | 65 | slow-mo | 2 |
| 300 | 150 | x1 | 1 | 14.49 | 17.50 | 60.65 | 3.88 | 4.64 | 8.33 | 239% | slow-mo | slow-mo | 0 |
| 300 | 150 | x4 | 1 | 21.36 | 60.87 | 125.74 | 4.96 | 7.06 | 13.01 | 353% | slow-mo | slow-mo | 2 |
| 300 | 150 | x1 | fit | 15.86 | 20.55 | 82.07 | 6.56 | 8.61 | 9.32 | 262% | slow-mo | slow-mo | 0 |
| 300 | 150 | x4 | fit | 21.57 | 64.95 | 152.02 | 7.77 | 9.87 | 10.48 | 356% | slow-mo | slow-mo | 2 |
| 600 | 300 | x1 | 1 | 48.41 | 56.51 | 137.72 | 5.86 | 7.64 | 9.33 | 799% | slow-mo | slow-mo | 0 |
| 600 | 300 | x4 | 1 | 66.55 | 150.32 | 304.20 | 8.60 | 11.80 | 14.89 | 1098% | slow-mo | slow-mo | 19 |
| 600 | 300 | x1 | fit | 53.71 | 64.54 | 137.94 | 11.56 | 14.29 | 19.21 | 886% | slow-mo | slow-mo | 0 |
| 600 | 300 | x4 | fit | 66.39 | 157.01 | 306.00 | 14.38 | 18.57 | 20.98 | 1095% | slow-mo | slow-mo | 19 |

### What this means

- **Real play is fine on average.** The largest authored wave (25) has 33
  enemies, and they spawn over time, so fewer than that are alive at once.
  Endless mode grows waves past wave 30. A late-game defence is assumed to have
  roughly 20 to 40 towers. The `30 x 20` rows
  use about 11 to 20% of the simulation budget and run at the 165 FPS cap.
- **There are stutter spikes even at real-game sizes.** Single ticks of 5 to 17
  ms at `30 x 20`, and 18 to 43 ms at `100 x 50`, against a 6 ms frame at 165
  FPS. They come from shot sounds (hotspot 2 below), they are worst at x4, and
  they show up as hitches whenever several towers fire in the same tick.
- **The simulation, not drawing, is what breaks first.** At `100 x 50` x4 the sim
  load is about 75%. At `300 x 150` and above, the game can't keep real time
  (240% to 1100% load) and would run in slow motion. Drawing stays under 15 ms
  even at `600 x 300` (headless).
- **Zooming out to fit the whole map adds about 25 to 100% to draw time**, because
  every sprite is rescaled every frame (hotspot 4 below).

## Hotspots

Profile of `600 x 300`, x4, zoom fit, 120 frames (run with `--profile`;
profiler overhead roughly doubles the times):

| function | tottime | cumtime | calls | note |
|---|---:|---:|---:|---|
| `GroundTower.work` | 6.1 s | 10.6 s | 27k | 70% of the whole tick |
| `Vector2.length` | 2.2 s | 2.2 s | 16.5M | called from `work`: one per tower-enemy pair per tick |
| `Tank._nearest_tower` | 1.8 s | 2.8 s | 12k | |
| `BaseTower.maxHP` | 0.7 s | 0.7 s | 3.6M | property, called from `_nearest_tower` |
| `SoundManager.play_sound` | 1.1 s | 1.1 s | 675 | **1.7 ms per call** |
| `pygame.transform.rotate` | 0.8 s | 0.8 s | 44k | towers re-rotate every tick |
| `scale_by` / `transform.scale` | 1.1 s | 1.1 s | 182k | every sprite, every frame, when zoom is not 1 |

1. **Tower targeting is O(towers x enemies) every tick.**
   `GroundTower.work()` builds a list of `enemy.position - self.position` vectors
   and a list of their `.length()` values for **every** enemy, for every ground
   tower, on every tick. That is about 135,000 pairs per tick at `600 x 300`.
2. **Every shot loads its sound from disk.**
   `pygamine.SoundManager.play_sound()` calls `mixer.Sound(path)`, which reads
   and decodes the file each time a tower fires (about 1.7 ms per shot). This
   causes the tick spikes even at real-game sizes, and the cost multiplies at
   x4. It lives in the **pygamine submodule**.
3. **Tank targeting is O(tanks x towers)**, and it reads the `maxHP` property,
   which indexes the config, for every tower and every tank on every tick.
4. **Rotation and zoom scaling are recomputed every frame.**
   `rotate_to_delta()` calls `pygame.transform.rotate` on every tick, even when
   the angle hasn't changed. When zoom is not 1, `Camera.scale_image()` rescales
   every sprite's image on every frame (pygamine).

## Proposed fixes (measured as prototypes; not implemented)

Each fix was monkeypatched in at runtime by a throwaway script, with no change to
the repo, and measured with the same benchmark. The ms values are tick means,
with the p95 in brackets, at zoom 1. Each column is a separate run, so allow
for 10 to 15% noise.

| scenario | baseline | + sound cache | + sound, grid, tank | all five |
|---|---:|---:|---:|---:|
| 30 x 20, x4 | 1.18 (3.54), max 17.1 | | 0.61 (0.91), max 3.8 | 0.61 (0.97) |
| 100 x 50, x1 | 2.63 (3.48), max 23.4 | 2.32 (3.43), max 4.8 | 1.77 (2.50), max 4.0 | 1.41 (2.25) |
| 100 x 50, x4 | 4.46 (16.85) | 3.97 (5.04) | 2.32 (3.81) | 2.13 (3.45) |
| 300 x 150, x1 | 14.49 (17.50) | | 6.70 (9.53) | 5.85 (8.35) |
| 600 x 300, x1 | 48.41 (56.51) | 47.89 (56.33) | 14.94 (19.51) | 13.01 (16.29) |
| 600 x 300, x4 | 66.55 (150.32) | 54.17 (66.97) | 19.17 (29.90) | 17.74 (26.71) |
| 600 x 300, x1, fit: draw | 11.56 | | 11.23 | 8.40 |

In priority order:

1. **Cache `mixer.Sound` objects per path** in `pygamine.SoundManager.play_sound`
   (or in `GameAudio.play_sfx`), loading each file once. This removes the tick
   spikes at every load (the `100 x 50` x4 tick p95 goes from 16.9 to 5.0 ms) and
   is the one fix that matters for today's real game. It is a small change, but
   it is in the **pygamine submodule**, so it needs its own submodule PR.
2. **A spatial grid for tower targeting.** Once per tick, bucket enemies into
   128 px cells. Each tower then scans only the cells its range covers, and
   compares `distance_squared_to` against `range**2` without building lists.
   The behaviour is the same: it picks the nearest enemy within range. This
   brought `600 x 300` from 48 to 20 ms per tick by itself, and from 48 to 15 ms
   together with fixes 1 and 3. Just switching to `min(...,
   key=distance_squared_to)` without the grid gained only about 20%, because
   the cost is the Python loop over every pair.
3. **Tank targeting:** skip planes with a cheap check (`hp is None` or the
   tower type) instead of the `maxHP` property, and use `distance_squared_to`.
   This is a small additional gain, included in the "+ sound, grid, tank" column.
4. **Skip re-rotating** when the whole-degree angle hasn't changed (in
   `RotatableObject.rotate_to_angle`), and **cache scaled images per zoom
   level** in `Camera.scale_image` (pygamine), for example in a `WeakKeyDictionary`
   keyed by surface. Together these cut `fit` draw time at `600 x 300` from
   11.6 to 8.4 ms. They help only when zoomed out or with many towers, so they
   are low priority.

Even with all five fixes, `300 x 150` sits at about 100% sim load. That count
is about 10 times what the game spawns, and the remaining cost is spread across
enemy movement, projectiles and draws. Going further would mean a design change,
such as a lower `TICKS_PER_SECOND` (which needs retuning all per-tick speeds) or
targeting less often than every tick. That is a design decision, outside the
scope of this spike.

**Recommendation:** fix 1 (sound cache) is worth doing now, because it removes
the hitches players can actually hit. Fixes 2 and 3 are worth doing if endless
mode, or later waves, are meant to grow to 100 or more enemies on screen. Fix 4
is optional.
