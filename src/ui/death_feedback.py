"""Death effects (#85): a killed enemy or a destroyed tower explodes; a
destroyed tower also leaves a scorched rubble decal that fades away.

- An enemy killed by anything (a shot, a missile, a bomb's splash) shows a
  small explosion: the bomb impacts' smoke puff with a fireball on top
  (ui.bomb_impact_feedback.ExplosionFrames), ENEMY_BLAST_SIZE world px
  across, TANK_BLAST_SIZE for a tank.
- A tower destroyed by tanks shows a bigger one (TOWER_BLAST_SIZE) and a
  decal on its tile: a scorch mark under rubble (Kenney's Particle Pack),
  held for DECAL_HOLD_MS, then fading out over DECAL_FADE_MS.
- A sold tower keeps its coin effect (ui.place_sell_feedback) and an enemy
  that escapes gets nothing: neither is told here.

Sounds go through GameAudio.play_sfx (the SFX pool), rate-capped like the
bomb impacts (SfxRateCap), with one cap each for soldiers, tanks and
towers, so no stream of kills can silence a falling tower. A tank's sound
(the tower's file) is skipped when a tower's started within the minimum
gap, so it never plays on top of itself. A blast over its cap shows
without a sound.

Everything here is cosmetic and runs on real time (frame_ms), like the
bomb impacts: it plays out while the game is paused and x2/x4 speed
doesn't hurry it. An effect keeps only a position, never the dead entity,
so it outlives it and never holds up its removal or payout. At most
MAX_EFFECTS enemy blasts, MAX_TOWER_BLASTS tower blasts and MAX_DECALS
decals play at once; past that the oldest of its kind makes room, so enemy
kills never evict a tower's blast. The menu demo shows them without sound
(play_sfx=None).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame
from pygame.math import Vector2
from pygamine import clamp01

from util.constants import TILE_SIZE

from ui.bomb_impact_feedback import (
    FRAME_MS,
    LIFE_MS,
    SOUND_MIN_GAP_MS,
    TOTAL_FRAMES,
    ExplosionFrames,
    SfxRateCap,
    draw_explosion,
)

# World px across. Enemy sprites are 64 px, the soldier itself about half
# of that; towers stand on a 64 px tile.
ENEMY_BLAST_SIZE = 56
TANK_BLAST_SIZE = 112
TOWER_BLAST_SIZE = 128
MAX_EFFECTS = 32  # enemies' explosions playing at once
MAX_TOWER_BLASTS = 8  # towers' explosions playing at once (their own list)

DECAL_SIZE = 112  # world px: the scorch mark (its art fills the middle)
RUBBLE_SIZE = 80  # world px: the rubble over it
DECAL_HOLD_MS = 1500  # real time at full strength
DECAL_FADE_MS = 2500  # real time fading out after that
DECAL_LIFE_MS = DECAL_HOLD_MS + DECAL_FADE_MS
MAX_DECALS = 16


def rubble_turn(position) -> int:
    """Quarter turns of the decal for a tower at `position` (world): set by
    its tile, so neighbors differ without a random stream (seeded runs stay
    as they were)."""
    x, y = position
    return (int(x) // TILE_SIZE + int(y) // TILE_SIZE) % 4


@dataclass
class _Blast:
    position: Vector2  # world
    size: int  # world px across
    born_ms: float  # on the feedback's own real-time clock


@dataclass
class _Decal:
    position: Vector2  # world: the destroyed tower's center
    turn: int  # quarter turns of the decal, for variety (see rubble_turn)
    born_ms: float


def _born_ms(effect) -> float:
    return effect.born_ms


def _alive(effects: list, now_ms: float, life_ms: float) -> list:
    """The effects that haven't played out `life_ms` after their birth."""
    return [e for e in effects if now_ms - e.born_ms < life_ms]


class DeathFeedback:
    def __init__(
        self,
        assets,
        play_sfx: Callable[[str], object] | None,
        small_sound=None,
        big_sound=None,
        *,
        frames: ExplosionFrames,
    ) -> None:
        """assets: the AssetManager (the explosion, smoke and decal images).
        play_sfx: plays a sound file at the SFX volume (GameAudio.play_sfx),
        or None for no sound at all (the menu demo). small_sound: a
        soldier's blast; big_sound: a tank's or a tower's. frames: the
        owner's ExplosionFrames, shared with its BombImpactFeedback."""
        self._frames = frames
        self._small_cap = SfxRateCap(play_sfx, small_sound)
        self._tank_cap = SfxRateCap(play_sfx, big_sound)
        self._tower_cap = SfxRateCap(play_sfx, big_sound)
        self._decal_images = self._build_decals(
            assets.get_image("scorch_decal"), assets.get_image("rubble_decal")
        )
        self.enemy_blasts: list[_Blast] = []
        self.tower_blasts: list[_Blast] = []
        self.decals: list[_Decal] = []
        self.now_ms = 0.0  # real time, advanced by update()

    @staticmethod
    def _build_decals(
        scorch: pygame.Surface, rubble: pygame.Surface
    ) -> list[pygame.Surface]:
        """The decal (DECAL_SIZE px world) in its four quarter turns."""
        scorch = pygame.transform.smoothscale(scorch, (DECAL_SIZE, DECAL_SIZE))
        rubble = pygame.transform.smoothscale(rubble, (RUBBLE_SIZE, RUBBLE_SIZE))
        decals = []
        for turn in range(4):
            decal = pygame.Surface((DECAL_SIZE, DECAL_SIZE), pygame.SRCALPHA)
            decal.blit(pygame.transform.rotate(scorch, 90 * turn), (0, 0))
            turned = pygame.transform.rotate(rubble, 90 * turn)
            decal.blit(turned, turned.get_rect(center=decal.get_rect().center))
            decals.append(decal)
        return decals

    def clear(self) -> None:
        self.enemy_blasts.clear()
        self.tower_blasts.clear()
        self.decals.clear()
        self._small_cap.clear()
        self._tank_cap.clear()
        self._tower_cap.clear()

    # ── events ────────────────────────────────────────────────────────────────

    def enemy_died(self, position, is_tank: bool) -> None:
        """An enemy was killed at `position` (world); a tank's blast is
        bigger."""
        size = TANK_BLAST_SIZE if is_tank else ENEMY_BLAST_SIZE
        blast = _Blast(Vector2(position), size, self.now_ms)
        self._add(self.enemy_blasts, MAX_EFFECTS, blast)
        if not is_tank:
            self._small_cap.play(self.now_ms)
        elif not self._tower_cap.played_within(self.now_ms, SOUND_MIN_GAP_MS):
            # The same file as a tower's: never on top of it.
            self._tank_cap.play(self.now_ms)

    def tower_destroyed(self, position) -> None:
        """A tower was destroyed at `position` (world): its blast and the
        rubble left on its tile."""
        now_ms = self.now_ms
        blast = _Blast(Vector2(position), TOWER_BLAST_SIZE, now_ms)
        self._add(self.tower_blasts, MAX_TOWER_BLASTS, blast)
        decal = _Decal(Vector2(position), rubble_turn(position), now_ms)
        self._add(self.decals, MAX_DECALS, decal)
        self._tower_cap.play(now_ms)

    @staticmethod
    def _add(effects: list, cap: int, effect) -> None:
        """Appends `effect`; past `cap`, the oldest makes room."""
        if len(effects) >= cap:
            effects.pop(0)
        effects.append(effect)

    # ── update / draw ─────────────────────────────────────────────────────────

    def update(self, frame_ms: float) -> None:
        """frame_ms: real time since the last frame (not scaled by game
        speed, not stopped by pause). Drops what has played out."""
        self.now_ms += frame_ms
        now_ms = self.now_ms
        self.enemy_blasts = _alive(self.enemy_blasts, now_ms, LIFE_MS)
        self.tower_blasts = _alive(self.tower_blasts, now_ms, LIFE_MS)
        self.decals = _alive(self.decals, now_ms, DECAL_LIFE_MS)

    def frame_index(self, blast: _Blast) -> int:
        elapsed = max(0.0, self.now_ms - blast.born_ms)
        return min(TOTAL_FRAMES - 1, int(elapsed // FRAME_MS))

    def decal_alpha(self, decal: _Decal) -> int:
        """255 while held, then down to 0 over DECAL_FADE_MS."""
        fading = self.now_ms - decal.born_ms - DECAL_HOLD_MS
        return round(255 * (1 - clamp01(fading / DECAL_FADE_MS)))

    def draw_decals(self, surface: pygame.Surface, camera) -> None:
        """Under towers and enemies, through the camera."""
        for decal in self.decals:
            alpha = self.decal_alpha(decal)
            if alpha <= 0:
                continue
            cached = self._decal_images[decal.turn]
            image = camera.scale_image(cached)  # zoomed: already a fresh copy
            if alpha < 255:
                if image is cached:  # zoom 1.0: never fade the cached one
                    image = image.copy()
                image.set_alpha(alpha)
            screen = camera.world_to_screen(decal.position)
            surface.blit(image, image.get_rect(center=(screen.x, screen.y)))

    def draw_blasts(self, surface: pygame.Surface, camera) -> None:
        """With the bomb explosions, through the camera. Oldest first
        across both lists, so a newer blast is on top."""
        both = sorted((*self.enemy_blasts, *self.tower_blasts), key=_born_ms)
        for blast in both:
            frame = self._frames.frames(blast.size)[self.frame_index(blast)]
            draw_explosion(surface, camera, frame, blast.position)
