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

SOUND_MIN_GAP_MS = 150  # real time between two impact sounds starting
SOUND_WINDOW_MS = 1000
SOUNDS_PER_WINDOW = 3


@dataclass
class _Explosion:
    position: Vector2  # world: where the bomb landed
    radius: float  # world px: the bomb's splash radius
    born_ms: float  # on the feedback's own real-time clock


class BombImpactFeedback:
    def __init__(
        self,
        assets,
        play_sfx: Callable[[str], object] | None,
        sound=None,
    ) -> None:
        """assets: the AssetManager (explosion_* and black_smoke_* images).
        play_sfx: plays a sound file at the SFX volume (GameAudio.play_sfx),
        or None for no sound at all (the menu demo)."""
        self._explosion_images = [
            assets.get_image(f"explosion_{i}") for i in range(EXPLOSION_FRAMES)
        ]
        self._smoke_images = [
            assets.get_image(f"black_smoke_{i}") for i in range(TOTAL_FRAMES)
        ]
        self._frames_by_size: dict[int, list[pygame.Surface]] = {}
        self._play_sfx = play_sfx
        self._sound = str(sound) if sound is not None else None
        self.explosions: list[_Explosion] = []
        self.now_ms = 0.0  # real time, advanced by update()
        self._sound_starts: deque[float] = deque()  # real time, oldest first

    def clear(self) -> None:
        self.explosions.clear()
        self._sound_starts.clear()

    # ── events ────────────────────────────────────────────────────────────────

    def bomb_landed(self, world_pos, radius: float) -> None:
        """A bomb with a splash radius of `radius` landed at `world_pos`."""
        if len(self.explosions) >= MAX_EXPLOSIONS:
            self.explosions.pop(0)
        self.explosions.append(_Explosion(Vector2(world_pos), radius, self.now_ms))
        self._maybe_play_sound()

    def _maybe_play_sound(self) -> None:
        if self._play_sfx is None or self._sound is None:
            return
        now_ms = self.now_ms
        starts = self._sound_starts
        while starts and now_ms - starts[0] >= SOUND_WINDOW_MS:
            starts.popleft()
        if starts and now_ms - starts[-1] < SOUND_MIN_GAP_MS:
            return
        if len(starts) >= SOUNDS_PER_WINDOW:
            return
        if self._play_sfx(self._sound) is not None:  # None: the pool dropped it
            starts.append(now_ms)

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
            size = max(1, round(frame.get_width() * camera.scale))
            scaled = pygame.transform.scale(frame, (size, size))
            screen = camera.world_to_screen(explosion.position)
            surface.blit(scaled, scaled.get_rect(center=(screen.x, screen.y)))

    def _frames(self, size: int) -> list[pygame.Surface]:
        """Smoke with the fireball on top, built once per world size."""
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
                    frame.blit(fire, (0, 0))
                frames.append(frame)
            self._frames_by_size[size] = frames
        return frames
