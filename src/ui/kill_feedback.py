"""Kill reward feedback: a floating "+$N" over each kill, and a few coins
flying from it to the money counter, which pops as they land.

Two clocks, on purpose:

- The "+$N" text lives in the world, over the battle, so it runs on game
  time (GameState.time_ms): pausing freezes it with everything around it,
  and x2/x4 speed it up in step with the enemies.
- The coins fly to the HUD, so they run on real time (frame_ms), like the
  HUD slide: a flight always takes the same ~0.5 s, and a pause straight
  after a kill doesn't leave coins hanging over the UI.

The money itself is paid on the kill, as before; all of this is visual. Only the
HUD's number lags: each coin carries a share of its kill's reward (`value`), and
`pending_money` -- the shares still in flight -- is what the HUD holds back from
the number it shows (GameHUD). It's derived from the live coins, so it can't
drift from them: a coin that lands, `clear()` and `settle()` all just remove it.
Effects are capped (MAX_EFFECTS) so mass kills at x4 stay cheap: when the
cap is reached, new kills show fewer coins, then no effect at all.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pygame
from pygame.math import Vector2
from pygamine import clamp01

from util.text import reward

TEXT_LIFE_MS = 800  # game time
TEXT_RISE = 48  # world px over the text's life
TEXT_COLOR = (255, 159, 0)  # the coin sprite's gold
TEXT_OUTLINE = (24, 14, 14)  # and its dark outline
TEXT_SIZE = 26
COIN_FLIGHT_MS = 500  # real time
COIN_SIZE = 12
COINS_PER_KILL = (3, 5)
COIN_STAGGER_MS = 40  # coins of one kill leave one after another
COIN_SCATTER = 14  # screen px around the enemy that the coins start from
POP_MS = 160
POP_SCALE = 0.25  # the counter grows by up to 25%
MAX_EFFECTS = 60  # texts + coins alive at once


def _ease_in(t: float) -> float:
    return t * t * t


@dataclass
class _Text:
    position: Vector2  # world
    amount: int
    label: pygame.Surface
    born_ms: float  # game time


@dataclass
class _Coin:
    start: Vector2  # screen
    delay_ms: float
    value: int = 0  # the share of the kill's reward the HUD shows once it lands
    elapsed_ms: float = 0.0


class KillFeedback:
    def __init__(self, coin_sheet: pygame.Surface, font_path, rng=None) -> None:
        frame = coin_sheet.subsurface(
            (0, 0, coin_sheet.get_height(), coin_sheet.get_height())
        )
        self._coin = pygame.transform.smoothscale(frame, (COIN_SIZE, COIN_SIZE))
        self._font = pygame.font.Font(font_path, TEXT_SIZE)
        self._rng = rng or random.Random()
        self.texts: list[_Text] = []
        self.coins: list[_Coin] = []
        self._pop_ms = float(POP_MS)  # no pop running
        # With Reduce flashing on there is no animation: coins carry no value (the
        # HUD number follows the real balance) and the counter doesn't pop.
        self.reduce_flashing = False

    @property
    def pending_money(self) -> int:
        """The reward shares of the coins still in flight."""
        return sum(coin.value for coin in self.coins)

    def settle(self) -> None:
        """The HUD shows the real balance at once (pause, popups): the coins in
        flight stay as pictures, but their shares are already counted."""
        for coin in self.coins:
            coin.value = 0

    @property
    def live_effects(self) -> int:
        return len(self.texts) + len(self.coins)

    def clear(self) -> None:
        self.texts.clear()
        self.coins.clear()
        self._pop_ms = float(POP_MS)

    def add_kill(self, world_pos, amount: int, screen_pos, now_ms: float) -> None:
        """A kill paying `amount` at `world_pos` (seen at `screen_pos`)."""
        if self.live_effects >= MAX_EFFECTS:
            return
        self.texts.append(
            _Text(Vector2(world_pos), amount, self._render_label(amount), now_ms)
        )
        room = MAX_EFFECTS - self.live_effects
        count = min(room, self._rng.randint(*COINS_PER_KILL))
        shares = self._split(amount, count)
        for i in range(count):
            jitter = Vector2(
                self._rng.uniform(-COIN_SCATTER, COIN_SCATTER),
                self._rng.uniform(-COIN_SCATTER, COIN_SCATTER),
            )
            self.coins.append(
                _Coin(Vector2(screen_pos) + jitter, i * COIN_STAGGER_MS, shares[i])
            )

    def _split(self, amount: int, count: int) -> list[int]:
        """The reward shared out over `count` coins (as even as whole coins allow, the first coins get the extra).
        With no coins (the cap) or Reduce flashing on, nothing is held back."""
        if count == 0 or self.reduce_flashing:
            return [0] * count
        base, extra = divmod(amount, count)
        return [base + (1 if i < extra else 0) for i in range(count)]

    def update(self, frame_ms: float, now_ms: float) -> None:
        """frame_ms: real time since the last frame. now_ms: game time."""
        self.texts = [t for t in self.texts if now_ms - t.born_ms < TEXT_LIFE_MS]
        landed = False
        for coin in self.coins:
            coin.elapsed_ms += frame_ms
        flying = []
        for coin in self.coins:
            if coin.elapsed_ms - coin.delay_ms >= COIN_FLIGHT_MS:
                landed = True
            else:
                flying.append(coin)
        self.coins = flying
        if landed:
            self._pop_ms = 0.0
        elif self._pop_ms < POP_MS:
            self._pop_ms = min(POP_MS, self._pop_ms + frame_ms)

    # ── drawing ───────────────────────────────────────────────────────────────

    def draw_texts(self, surface: pygame.Surface, camera, now_ms: float) -> None:
        """Over the battle, through the camera (follows zoom and scroll)."""
        for text in self.texts:
            t = clamp01((now_ms - text.born_ms) / TEXT_LIFE_MS)
            world = text.position - Vector2(0, TEXT_RISE * (1 - (1 - t) ** 2))
            screen = camera.world_to_screen(world)
            text.label.set_alpha(round(255 * (1 - t * t)))
            surface.blit(
                text.label, text.label.get_rect(midbottom=(screen.x, screen.y))
            )

    def draw_coins(self, surface: pygame.Surface, target) -> None:
        """Over the HUD: each coin on its way to `target` (screen)."""
        target = Vector2(target)
        for coin in self.coins:
            t = (coin.elapsed_ms - coin.delay_ms) / COIN_FLIGHT_MS
            if t < 0:
                pos = coin.start
            else:
                pos = coin.start.lerp(target, _ease_in(clamp01(t)))
            surface.blit(self._coin, self._coin.get_rect(center=(pos.x, pos.y)))

    def draw_pop(self, surface: pygame.Surface, counter: pygame.Rect) -> None:
        """Scales the drawn money counter up and back as coins land."""
        if self._pop_ms >= POP_MS or self.reduce_flashing:
            return
        counter = counter.clip(surface.get_rect())
        if not counter.w or not counter.h:
            return
        t = self._pop_ms / POP_MS
        scale = 1 + POP_SCALE * (1 - abs(2 * t - 1))  # up, then back down
        grabbed = surface.subsurface(counter).copy()
        size = (round(counter.w * scale), round(counter.h * scale))
        popped = pygame.transform.smoothscale(grabbed, size)
        surface.blit(popped, popped.get_rect(center=counter.center))

    @property
    def is_popping(self) -> bool:
        return self._pop_ms < POP_MS

    def _render_label(self, amount: int) -> pygame.Surface:
        text = reward(amount)
        fill = self._font.render(text, True, TEXT_COLOR)
        outline = self._font.render(text, True, TEXT_OUTLINE)
        label = pygame.Surface(
            (fill.get_width() + 4, fill.get_height() + 4), pygame.SRCALPHA
        )
        for dx, dy in ((0, 2), (4, 2), (2, 0), (2, 4), (0, 0), (4, 4), (0, 4), (4, 0)):
            label.blit(outline, (dx, dy))
        label.blit(fill, (2, 2))
        return label
