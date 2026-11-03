"""Plane bomb impact: an explosion and a sound where each bomb lands.

The damage is dealt by the bomb itself, on game time, at the moment it
lands (gameplay.combat.projectile.Bomb). Everything here is cosmetic:

- The explosion -- the smoke + fireball animation that used to be drawn as
  a bullet -- is sized to the bomb's splash radius and lives in the world,
  so it's drawn through the camera (follows scroll and zoom). It runs on
  real time (frame_ms), like PlaceSellFeedback: it plays out while the game
  is paused, and x2/x4 speed doesn't hurry it.
- The sound goes through GameAudio.play_sfx (the pooled SFX channels, at
  the SFX volume), capped here so a plane's run -- or several planes at
  x4 -- doesn't stack into clipping: at most one impact sound starts per
  SOUND_MIN_GAP_MS, and at most SOUNDS_PER_WINDOW within SOUND_WINDOW_MS.
  An impact over the cap shows its explosion without a sound.

With the reduce-flashing flag on (`reduce_flashing`, set by the owner from
the Settings toggle) the fireball is drawn at REDUCED_FIREBALL_ALPHA; the
smoke is unchanged.

At most MAX_EXPLOSIONS play at once; past that the oldest one (closest to
its end) makes room. The menu demo shows the explosions without sound
(play_sfx=None).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

import pygame
from pygame.math import Vector2

FRAME_MS = 55  # real time per frame of the animation (~18 fps)
TOTAL_FRAMES = 13  # smoke frames; the fireball covers the first EXPLOSION_FRAMES
EXPLOSION_FRAMES = 9
LIFE_MS = FRAME_MS * TOTAL_FRAMES
# The sprite's side, as a share of the splash circle's diameter. The Kenney
# fireball and smoke fill roughly the middle 85-90% of their frames, so 1.0
# reads as "the blast covers the splash circle".
SIZE_FACTOR = 1.0
MAX_EXPLOSIONS = 24
# "Reduce flashing" draws the fireball at this opacity (255: solid); the smoke
# keeps its own.
REDUCED_FIREBALL_ALPHA = 128

SOUND_MIN_GAP_MS = 150  # real time between two impact sounds starting
SOUND_WINDOW_MS = 1000
SOUNDS_PER_WINDOW = 3


@dataclass
class _Explosion:
    position: Vector2  # world: where the bomb landed
    radius: float  # world px: the bomb's splash radius
    born_ms: float  # on the feedback's own real-time clock


class SfxRateCap:
    """Plays one sound through the SFX pool, at most once per
    SOUND_MIN_GAP_MS and SOUNDS_PER_WINDOW times within SOUND_WINDOW_MS of
    the caller's real-time clock. Shared by the bomb impacts and the death
    effects (ui.death_feedback), each with its own cap."""

    def __init__(self, play_sfx: Callable[[str], object] | None, sound) -> None:
        """play_sfx: GameAudio.play_sfx, or None for no sound at all (the
        menu demo); sound: the sound file's path, or None."""
        self._play_sfx = play_sfx
        self._sound = str(sound) if sound is not None else None
        self._starts: deque[float] = deque()  # real time, oldest first

    def clear(self) -> None:
        self._starts.clear()

    def played_within(self, now_ms: float, gap_ms: float) -> bool:
        """Whether the sound started less than `gap_ms` before `now_ms`."""
        return bool(self._starts) and now_ms - self._starts[-1] < gap_ms

    def play(self, now_ms: float) -> bool:
        """Plays the sound unless it's over the cap at `now_ms`. True if it
        started."""
        if self._play_sfx is None or self._sound is None:
            return False
        starts = self._starts
        while starts and now_ms - starts[0] >= SOUND_WINDOW_MS:
            starts.popleft()
        if starts and now_ms - starts[-1] < SOUND_MIN_GAP_MS:
            return False
        if len(starts) >= SOUNDS_PER_WINDOW:
            return False
        if self._play_sfx(self._sound) is None:  # None: the pool dropped it
            return False
        starts.append(now_ms)
        return True


class ExplosionFrames:
    """The explosion animation -- smoke with the fireball on top -- built
    once per world size from the explosion_* and black_smoke_* images."""

    def __init__(self, assets) -> None:
        self._explosion_images = [
            assets.get_image(f"explosion_{i}") for i in range(EXPLOSION_FRAMES)
        ]
        self._smoke_images = [
            assets.get_image(f"black_smoke_{i}") for i in range(TOTAL_FRAMES)
        ]
        # Built on first use, for one variant at a time (`_reduced`): asking
        # for the other drops these, so the memory doesn't double.
        self._reduced = False
        self._frames_by_size: dict[int, list[pygame.Surface]] = {}

    def frames(self, size: int, reduced: bool = False) -> list[pygame.Surface]:
        """TOTAL_FRAMES frames, `size` px square. `reduced`: the fireball at
        REDUCED_FIREBALL_ALPHA (the smoke unchanged). Only the variant asked
        for last is kept; the bomb impacts and the deaths sharing this object
        always ask with the same flag."""
        if reduced != self._reduced:
            self._frames_by_size.clear()
            self._reduced = reduced
        frames = self._frames_by_size.get(size)
        if frames is None:
            target = (size, size)
            frames = []
            for i in range(TOTAL_FRAMES):
                frame = pygame.Surface(target, pygame.SRCALPHA)
                smoke = pygame.transform.smoothscale(self._smoke_images[i], target)
                frame.blit(smoke, (0, 0))
                if i < EXPLOSION_FRAMES:
                    fire = pygame.transform.smoothscale(
                        self._explosion_images[i], target
                    )
                    if reduced:
                        fire.set_alpha(REDUCED_FIREBALL_ALPHA)
                    frame.blit(fire, (0, 0))
                frames.append(frame)
            self._frames_by_size[size] = frames
        return frames


def draw_explosion(
    surface: pygame.Surface, camera, frame: pygame.Surface, position
) -> None:
    """One explosion frame centered on `position` (world), through the
    camera (follows zoom and scroll)."""
    scaled = camera.scale_image(frame)  # the frame itself at zoom 1.0
    screen = camera.world_to_screen(position)
    surface.blit(scaled, scaled.get_rect(center=(screen.x, screen.y)))


class BombImpactFeedback:
    def __init__(
        self,
        assets,
        play_sfx: Callable[[str], object] | None,
        sound=None,
        *,
        frames: ExplosionFrames,
        reduce_flashing: bool = False,
    ) -> None:
        """assets: the AssetManager (explosion_* and black_smoke_* images).
        play_sfx: plays a sound file at the SFX volume (GameAudio.play_sfx),
        or None for no sound at all (the menu demo). frames: the owner's
        ExplosionFrames, shared with its DeathFeedback. reduce_flashing: the
        fireball is drawn dimmer."""
        self._frames_cache = frames
        self.reduce_flashing = reduce_flashing
        self._sound_cap = SfxRateCap(play_sfx, sound)
        self.explosions: list[_Explosion] = []
        self.now_ms = 0.0  # real time, advanced by update()

    def clear(self) -> None:
        self.explosions.clear()
        self._sound_cap.clear()

    # ── events ────────────────────────────────────────────────────────────────

    def bomb_landed(self, world_pos, radius: float) -> None:
        """A bomb with a splash radius of `radius` landed at `world_pos`."""
        if len(self.explosions) >= MAX_EXPLOSIONS:
            self.explosions.pop(0)
        self.explosions.append(_Explosion(Vector2(world_pos), radius, self.now_ms))
        self._sound_cap.play(self.now_ms)

    # ── update / draw ─────────────────────────────────────────────────────────

    def update(self, frame_ms: float) -> None:
        """frame_ms: real time since the last frame (not scaled by game
        speed, not stopped by pause). Drops the explosions that have played
        out."""
        self.now_ms += frame_ms
        now_ms = self.now_ms
        self.explosions = [e for e in self.explosions if now_ms - e.born_ms < LIFE_MS]

    def frame_index(self, explosion: _Explosion) -> int:
        elapsed = max(0.0, self.now_ms - explosion.born_ms)
        return min(TOTAL_FRAMES - 1, int(elapsed // FRAME_MS))

    @staticmethod
    def world_size(radius: float) -> int:
        """The explosion sprite's side in world px, for a splash radius."""
        return max(1, round(2 * radius * SIZE_FACTOR))

    def draw(self, surface: pygame.Surface, camera) -> None:
        """In the battle, through the camera (follows zoom and scroll)."""
        for explosion in self.explosions:
            frames = self._frames(self.world_size(explosion.radius))
            frame = frames[self.frame_index(explosion)]
            draw_explosion(surface, camera, frame, explosion.position)

    def _frames(self, size: int) -> list[pygame.Surface]:
        return self._frames_cache.frames(size, self.reduce_flashing)
