"""Hit feedback: a hit enemy or tower flashes white, with a spark where it
was hit.

- The flash is a white silhouette of the target's sprite (every part of
  it: a ground tower's platform and turret, a tank's hull and turret)
  drawn right over it for FLASH_MS. Each silhouette is made from the very
  surface drawn (rotation included), so it matches the sprite exactly, and
  kept in this feedback's own LRU cache (MAX_CACHED_SILHOUETTES) keyed on
  that surface: a sprite that keeps its drawn surface builds it once.
- The spark is a few short rays bursting from the impact point: the edge
  of the target facing the shot or bomb (IMPACT_REACH from its center, or
  less if the shot is closer; its center if the bomb landed right on it).
  Drawn procedurally, no asset.

Both are cosmetic and run on real time (frame_ms), like PlaceSellFeedback
and BombImpactFeedback: they play out while the game is paused and x2/x4
speed doesn't hurry them. Nothing here touches gameplay: the battle tells
it about a hit after the damage is decided.

Rate cap: a target shows at most one hit per HIT_MIN_INTERVAL_MS of real
time; hits on it in between show nothing. So several towers -- or one at
x4 -- pouring fire into one enemy read as a steady pulse of hits, never a
strobe. At most MAX_EFFECTS hits play at once; past that a new hit shows
nothing. No sound (the issue's decision has none); the menu demo has the
same flash and sparks.

A hit holds its target only until its effects end, so a target that dies
or is sold on the hit's tick is safe: it simply isn't drawn any more, and
the spark plays out on its own.
"""

from __future__ import annotations

import math
import random
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

import pygame
from pygame.math import Vector2
from pygamine import clamp01

FLASH_MS = 80  # real time the sprite shows white
FLASH_ALPHA = 220  # the silhouette's opacity over the sprite (255: solid)

SPARK_LIFE_MS = 150  # real time
SPARK_RAYS = 5
SPARK_REACH = 14  # world px the rays reach out from the impact point
SPARK_WIDTH = 2  # world px, at birth; thins as it fades
SPARK_COLOR = (255, 232, 150)  # warm white-yellow
SPARK_CORE_COLOR = (255, 255, 255)
IMPACT_REACH = 16  # world px from the target's center toward the shot

HIT_MIN_INTERVAL_MS = 250  # real time between two hits shown on one target
MAX_EFFECTS = 64  # hits (flash + spark) playing at once
MAX_CACHED_SILHOUETTES = 256

# A target has one hit record at a time, kept for HIT_MIN_INTERVAL_MS: its
# flash and spark must be over by then.
assert FLASH_MS <= HIT_MIN_INTERVAL_MS and SPARK_LIFE_MS <= HIT_MIN_INTERVAL_MS


class Flashable(Protocol):
    """A hit target: an enemy or a tower (gameplay.rotatable_object)."""

    position: Vector2

    def flash_parts(self) -> list[tuple[pygame.Surface, Vector2]]: ...


@dataclass
class _Hit:
    target: object  # held only while the hit plays (its id keys _hits)
    impact: Vector2  # world: where the spark bursts
    angle: float  # radians: the spark's first ray
    born_ms: float  # on the feedback's own real-time clock


def silhouette(image: pygame.Surface) -> pygame.Surface:
    """`image` in white at FLASH_ALPHA, keeping its shape (per-pixel alpha)."""
    white = pygame.Surface(image.get_size(), pygame.SRCALPHA)
    white.blit(image, (0, 0))
    white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
    white.fill((255, 255, 255, FLASH_ALPHA), special_flags=pygame.BLEND_RGBA_MULT)
    return white


def impact_point(target_pos, hit_from) -> Vector2:
    """Where a hit from `hit_from` (a shot's or bomb's position) lands on a
    target centered at `target_pos`: IMPACT_REACH toward the shot, or less
    if the shot is closer; the center if the shot is right on it."""
    center = Vector2(target_pos)
    delta = Vector2(hit_from) - center
    distance = delta.length()
    if distance == 0:
        return center
    return center + delta * (min(distance, IMPACT_REACH) / distance)


class HitFeedback:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._hits: dict[int, _Hit] = {}  # id(target) -> its latest hit
        self._silhouettes: OrderedDict[pygame.Surface, pygame.Surface] = OrderedDict()
        self.now_ms = 0.0  # real time, advanced by update()

    @property
    def live_effects(self) -> int:
        return len(self._hits)

    def clear(self) -> None:
        self._hits.clear()

    # ── events ────────────────────────────────────────────────────────────────

    def target_hit(self, target: Flashable, hit_from) -> bool:
        """`target` took a hit from a shot or bomb at `hit_from` (world).
        Shows it unless the target showed one less than HIT_MIN_INTERVAL_MS
        ago or MAX_EFFECTS hits are playing. True if shown."""
        key = id(target)
        last = self._hits.get(key)
        if last is not None and self.now_ms - last.born_ms < HIT_MIN_INTERVAL_MS:
            return False
        if last is None and len(self._hits) >= MAX_EFFECTS:
            return False
        self._hits[key] = _Hit(
            target,
            impact_point(target.position, hit_from),
            self._rng.uniform(0, 2 * math.pi),
            self.now_ms,
        )
        return True

    # ── update / draw ─────────────────────────────────────────────────────────

    def update(self, frame_ms: float) -> None:
        """frame_ms: real time since the last frame (not scaled by game
        speed, not stopped by pause). Forgets the hits whose rate-cap window
        is over (their flash and spark ended before)."""
        self.now_ms += frame_ms
        if not self._hits:
            return
        now_ms = self.now_ms
        expired = [
            key
            for key, hit in self._hits.items()
            if now_ms - hit.born_ms >= HIT_MIN_INTERVAL_MS
        ]
        for key in expired:
            del self._hits[key]

    def is_flashing(self, target) -> bool:
        hit = self._hits.get(id(target))
        return (
            hit is not None
            and hit.target is target
            and self.now_ms - hit.born_ms < FLASH_MS
        )

    def draw_flash(self, surface: pygame.Surface, camera, target: Flashable) -> None:
        """Right after `target` is drawn: its white silhouette while it's
        flashing, through the camera (follows zoom and scroll)."""
        if not self.is_flashing(target):
            return
        for drawn, center in target.flash_parts():
            white = self._silhouette(drawn)
            scaled = camera.scale_image(white)
            screen = camera.world_to_screen(center)
            surface.blit(scaled, scaled.get_rect(center=(int(screen.x), int(screen.y))))

    def draw_sparks(self, surface: pygame.Surface, camera) -> None:
        """Every spark still playing, through the camera."""
        now_ms = self.now_ms
        for hit in self._hits.values():
            t = clamp01((now_ms - hit.born_ms) / SPARK_LIFE_MS)
            if t >= 1:
                continue
            reach = SPARK_REACH * (1 - (1 - t) ** 2)  # eases out
            inner = reach * t  # the rays' tails catch up as they fade
            width = max(1, round(SPARK_WIDTH * (1 - t) * camera.scale))
            center = camera.world_to_screen(hit.impact)
            for i in range(SPARK_RAYS):
                angle = hit.angle + 2 * math.pi * i / SPARK_RAYS
                direction = Vector2(math.cos(angle), math.sin(angle)) * camera.scale
                pygame.draw.line(
                    surface,
                    SPARK_COLOR,
                    center + direction * inner,
                    center + direction * reach,
                    width,
                )
            if t < 0.5:
                core = max(1, round(SPARK_WIDTH * (1 - 2 * t) * camera.scale))
                pygame.draw.circle(surface, SPARK_CORE_COLOR, center, core)

    def _silhouette(self, drawn: pygame.Surface) -> pygame.Surface:
        """The silhouette of `drawn` (a surface as it is drawn), from the
        LRU cache. Keyed on the surface itself: an enemy keeps its rotated
        surface between turns, a turret's comes from the rotation cache, so
        they hit the cache; a surface rebuilt every tick (a tank's turret)
        builds a small one per frame while it flashes, and the bound keeps
        those from piling up."""
        cache = self._silhouettes
        white = cache.get(drawn)
        if white is None:
            white = silhouette(drawn)
            cache[drawn] = white
            if len(cache) > MAX_CACHED_SILHOUETTES:
                cache.popitem(last=False)
        else:
            cache.move_to_end(drawn)
        return white
