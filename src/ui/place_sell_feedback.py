"""Tower placed / sold: a sound and a short effect on the tower's tile.

- Placing: a thud and a puff of dust spreading out from the tile.
- Selling: a coin clink and a few coins bursting up from the tile and
  falling back as they fade.

The effects live in the world, so they're drawn through the camera (they
follow scroll and zoom). They're cosmetic, so they run on real time
(frame_ms), like KillFeedback's coin flight and the HUD slide: they play
out even while the game is paused (e.g. building before the first wave),
and x2/x4 speed doesn't hurry them. Sounds go through GameAudio.play_sfx,
the pooled SFX channels, at the SFX volume.

Particles are capped (MAX_EFFECTS) so selling or building in a hurry stays
cheap: when the cap is reached, new effects get fewer particles, then none
(the sound still plays). The menu demo has none of this.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

import pygame
from pygame.math import Vector2

# ── dust (placing) ────────────────────────────────────────────────────────────
DUST_LIFE_MS = 450  # real time
DUST_PUFFS = 6
DUST_COLOR = (150, 128, 96)  # added onto the dark smoke sprites: a dry brown
DUST_ALPHA = 170  # at birth, fading to nothing
DUST_START_SIZE = 22  # world px
DUST_END_SIZE = 46
DUST_SPREAD = (18, 30)  # world px each puff drifts out from the tile centre
DUST_SPRITE_SIZE = 64  # the smoke sprites are downscaled once to this

# ── coins (selling) ───────────────────────────────────────────────────────────
COIN_LIFE_MS = 650  # real time
COINS_PER_SALE = 6
COIN_SIZE = 14  # world px
COIN_SPEED = (90, 150)  # world px/s at launch, upwards in a cone
COIN_CONE = math.radians(70)  # total width of that cone
COIN_GRAVITY = 420  # world px/s^2
COIN_SPIN_MS = 60  # per frame of the coin animation
COIN_FADE_FROM = 0.5  # share of the life after which coins fade out

MAX_EFFECTS = 48  # dust puffs + coins alive at once


@dataclass
class _Dust:
    origin: Vector2  # world: the tile centre
    direction: Vector2  # unit
    spread: float  # world px travelled over the life
    sprite: int
    born_ms: float  # on the feedback's own real-time clock


@dataclass
class _Coin:
    origin: Vector2  # world
    velocity: Vector2  # world px/s at launch
    frame: int  # starting frame of the spin
    born_ms: float  # on the feedback's own real-time clock


def _ease_out(t: float) -> float:
    return 1 - (1 - t) ** 2


def _dust_sprites(smoke_frames) -> list[pygame.Surface]:
    sprites = []
    for frame in smoke_frames:
        small = pygame.transform.smoothscale(
            frame, (DUST_SPRITE_SIZE, DUST_SPRITE_SIZE)
        )
        small.fill(DUST_COLOR, special_flags=pygame.BLEND_RGB_ADD)
        sprites.append(small)
    return sprites


def _coin_frames(coin_sheet: pygame.Surface) -> list[pygame.Surface]:
    size = coin_sheet.get_height()
    return [
        coin_sheet.subsurface((x, 0, size, size)).copy()
        for x in range(0, coin_sheet.get_width() - size + 1, size)
    ]


class PlaceSellFeedback:
    def __init__(
        self,
        smoke_frames,
        coin_sheet: pygame.Surface,
        play_sfx: Callable[[str], object],
        place_sound,
        sell_sound,
        rng=None,
    ) -> None:
        """play_sfx: plays a sound file at the SFX volume (GameAudio.play_sfx)."""
        self._dust_sprites = _dust_sprites(smoke_frames)
        self._coin_frames = _coin_frames(coin_sheet)
        self._play_sfx = play_sfx
        self._place_sound = str(place_sound)
        self._sell_sound = str(sell_sound)
        self._rng = rng or random.Random()
        self.dust: list[_Dust] = []
        self.coins: list[_Coin] = []
        self.now_ms = 0.0  # real time, advanced by update()

    @property
    def live_effects(self) -> int:
        return len(self.dust) + len(self.coins)

    def clear(self) -> None:
        self.dust.clear()
        self.coins.clear()

    # ── events ────────────────────────────────────────────────────────────────

    def tower_placed(self, world_pos) -> None:
        """A tower was built with its centre at `world_pos`."""
        self._play_sfx(self._place_sound)
        origin = Vector2(world_pos)
        offset = self._rng.uniform(0, 2 * math.pi)
        for i in range(min(self._room(), DUST_PUFFS)):
            angle = offset + 2 * math.pi * i / DUST_PUFFS
            self.dust.append(
                _Dust(
                    origin,
                    Vector2(math.cos(angle), math.sin(angle)),
                    self._rng.uniform(*DUST_SPREAD),
                    self._rng.randrange(len(self._dust_sprites)),
                    self.now_ms,
                )
            )

    def tower_sold(self, world_pos) -> None:
        """A tower with its centre at `world_pos` was sold."""
        self._play_sfx(self._sell_sound)
        origin = Vector2(world_pos)
        for _ in range(min(self._room(), COINS_PER_SALE)):
            angle = -math.pi / 2 + self._rng.uniform(-COIN_CONE / 2, COIN_CONE / 2)
            speed = self._rng.uniform(*COIN_SPEED)
            self.coins.append(
                _Coin(
                    origin,
                    Vector2(math.cos(angle), math.sin(angle)) * speed,
                    self._rng.randrange(len(self._coin_frames)),
                    self.now_ms,
                )
            )

    def _room(self) -> int:
        return max(0, MAX_EFFECTS - self.live_effects)

    # ── update / draw ─────────────────────────────────────────────────────────

    def update(self, frame_ms: float) -> None:
        """frame_ms: real time since the last frame (not scaled by game
        speed, not stopped by pause). Drops the effects that have played out."""
        self.now_ms += frame_ms
        now_ms = self.now_ms
        self.dust = [d for d in self.dust if now_ms - d.born_ms < DUST_LIFE_MS]
        self.coins = [c for c in self.coins if now_ms - c.born_ms < COIN_LIFE_MS]

    def dust_position(self, dust: _Dust) -> Vector2:
        t = self._progress(dust.born_ms, DUST_LIFE_MS, self.now_ms)
        return dust.origin + dust.direction * dust.spread * _ease_out(t)

    def coin_position(self, coin: _Coin) -> Vector2:
        s = max(0.0, self.now_ms - coin.born_ms) / 1000
        return coin.origin + coin.velocity * s + Vector2(0, COIN_GRAVITY * s * s / 2)

    def draw(self, surface: pygame.Surface, camera) -> None:
        """Over the battle, through the camera (follows zoom and scroll)."""
        now_ms = self.now_ms
        for dust in self.dust:
            t = self._progress(dust.born_ms, DUST_LIFE_MS, now_ms)
            size = DUST_START_SIZE + (DUST_END_SIZE - DUST_START_SIZE) * _ease_out(t)
            alpha = round(DUST_ALPHA * (1 - t) ** 1.5)
            self._blit(
                surface,
                camera,
                self._dust_sprites[dust.sprite],
                self.dust_position(dust),
                size,
                alpha,
            )
        for coin in self.coins:
            t = self._progress(coin.born_ms, COIN_LIFE_MS, now_ms)
            fade = max(0.0, (t - COIN_FADE_FROM) / (1 - COIN_FADE_FROM))
            elapsed = max(0.0, now_ms - coin.born_ms)
            frame = (coin.frame + int(elapsed // COIN_SPIN_MS)) % len(self._coin_frames)
            self._blit(
                surface,
                camera,
                self._coin_frames[frame],
                self.coin_position(coin),
                COIN_SIZE,
                round(255 * (1 - fade)),
            )

    @staticmethod
    def _progress(born_ms: float, life_ms: float, now_ms: float) -> float:
        return min(1.0, max(0.0, (now_ms - born_ms) / life_ms))

    @staticmethod
    def _blit(surface, camera, sprite, world_pos, world_size, alpha) -> None:
        if alpha <= 0:
            return
        size = max(1, round(world_size * camera.scale))
        scaled = pygame.transform.scale(sprite, (size, size))
        scaled.set_alpha(alpha)
        screen = camera.world_to_screen(world_pos)
        surface.blit(scaled, scaled.get_rect(center=(screen.x, screen.y)))
