"""Life lost: a bell and a red vignette pulsing at the screen edges.

Runs on real time (frame_ms), so the pulse reads the same at x1 and x4 and
still plays out if the game is paused straight after. Losing several lives
at once (one big enemy, or a few in the same moment) makes the pulse
stronger, up to MAX_STRENGTH.

The bell has a mixer channel of its own (2, reserved by pygamine and kept
out of its SFX pool), at the SFX volume, so a full pool never drops it.
"""

from __future__ import annotations

import pygame
from pygame import mixer

ATTACK_MS = 80  # up to full strength
FADE_MS = 320  # then back to nothing: ~0.4 s in all
ALPHA_PER_LIFE = 125  # vignette opacity at its edges, per life lost
MAX_STRENGTH = 2.0  # lives' worth: at most ~250 alpha at the edges
EDGE = 0.22  # the vignette's depth, as a share of the shorter canvas side
COLOR = (200, 0, 0)
ALERT_CHANNEL = 2  # pygamine reserves 0-2: 0 is the music, 3+ the SFX pool
_MASK_SIZE = (96, 54)  # built small, then smoothly scaled to the canvas


def _vignette_mask(size: tuple[int, int]) -> pygame.Surface:
    """Red, opaque at the edges and clear inside, as a per-pixel-alpha surface."""
    w, h = _MASK_SIZE
    depth = EDGE * min(w, h)
    small = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            d = min(x + 0.5, y + 0.5, w - x - 0.5, h - y - 0.5)
            if d < depth:
                small.set_at((x, y), (*COLOR, round(255 * (1 - d / depth) ** 2)))
    return pygame.transform.smoothscale(small, size)


class LifeLostFeedback:
    def __init__(self, sound_path, sfx_volume) -> None:
        """sfx_volume: returns the volume SFX play at now (0-1), i.e.
        GameAudio.effective_sfx_volume (master x SFX)."""
        self._sound = mixer.Sound(str(sound_path))
        self._sfx_volume = sfx_volume
        self._mask: pygame.Surface | None = None
        self._from = 0.0
        self._peak = 0.0
        self._elapsed_ms = float(ATTACK_MS + FADE_MS)  # idle

    @property
    def strength(self) -> float:
        """How many lives' worth the vignette shows right now."""
        if self._elapsed_ms < ATTACK_MS:
            t = self._elapsed_ms / ATTACK_MS
            return self._from + (self._peak - self._from) * (1 - (1 - t) ** 2)
        t = min(1.0, (self._elapsed_ms - ATTACK_MS) / FADE_MS)
        return self._peak * (1 - t) ** 2

    @property
    def is_active(self) -> bool:
        return self._elapsed_ms < ATTACK_MS + FADE_MS

    def lives_lost(self, count: int) -> None:
        """Losses stack on what's still showing, up to MAX_STRENGTH."""
        if count <= 0:
            return
        self._from = self.strength
        self._peak = min(MAX_STRENGTH, self._from + count)
        self._elapsed_ms = 0.0
        channel = mixer.Channel(ALERT_CHANNEL)
        channel.set_volume(self._sfx_volume())
        channel.play(self._sound)

    def clear(self) -> None:
        self._from = self._peak = 0.0
        self._elapsed_ms = float(ATTACK_MS + FADE_MS)

    def update(self, frame_ms: float) -> None:
        if self.is_active:
            self._elapsed_ms += frame_ms

    def draw(self, surface: pygame.Surface) -> None:
        strength = self.strength
        if strength <= 0:
            return
        if self._mask is None or self._mask.get_size() != surface.get_size():
            self._mask = _vignette_mask(surface.get_size())
        self._mask.set_alpha(min(255, round(ALPHA_PER_LIFE * strength)))
        surface.blit(self._mask, (0, 0))
