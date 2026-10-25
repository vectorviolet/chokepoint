from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from util.constants import TICK_MS

if TYPE_CHECKING:
    from towers.base_tower import BaseTower


@dataclass
class WaveDef:
    """Composition + spawn timing for a single wave.

    `spawn_interval_ms` is `None` when the wave defers to WaveManager's default.
    """

    groups: list[tuple[int, int]]  # [(enemy_type, count), ...]
    spawn_interval_ms: int | None = None


@dataclass
class TowerConfig:
    """All per-type, per-level tower data.

    prices[type-1][level-1] is the buy/upgrade cost to *reach* that level
    (same index scheme used by the original code throughout). For planes,
    whose level is a global upgrade, prices[3][1] is that upgrade's cost.
    """

    prices: list[list[int]]
    max_levels: list[int]
    ranges: list[list[int]]
    damages: list[list[int]]
    speeds: list[list[int]]
    hps: list[list[int] | None]  # None = invulnerable (e.g. planes)
    shoot_sounds: list[str | None]  # asset key per tower type; None = silent


class GameState:
    """Pure game state — no pygame, no rendering, no game-object lists."""

    def __init__(self, start_money: int, start_lives: int) -> None:
        self.money: int = start_money
        self.lives: int = start_lives
        self.level: int = 1
        self.speed: int = 1
        self.is_started: bool = False
        self.selected_tower: "BaseTower | None" = None
        self.plane_level: int = 1
        self.has_won: bool = False
        # Game time in ms: advances one TICK_MS * speed per tick while the
        # game runs, and stands still while it's paused. Every gameplay
        # timer (spawn intervals, reloads, fuses, ...) reads this rather
        # than the wall clock, so pausing freezes them and x2/x4 speed
        # runs them faster along with movement.
        self.time_ms: float = 0.0

        self._money_cbs: list[Callable[[int], None]] = []
        self._lives_cbs: list[Callable[[int], None]] = []
        self._level_cbs: list[Callable[[int], None]] = []

    # ── listeners ────────────────────────────────────────────────────────────

    def add_money_listener(self, cb: Callable[[int], None]) -> None:
        self._money_cbs.append(cb)

    def add_lives_listener(self, cb: Callable[[int], None]) -> None:
        self._lives_cbs.append(cb)

    def add_level_listener(self, cb: Callable[[int], None]) -> None:
        self._level_cbs.append(cb)

    # ── mutations ─────────────────────────────────────────────────────────────

    def increase_money(self, amount: int) -> None:
        self.money += amount
        for cb in self._money_cbs:
            cb(self.money)

    def decrease_money(self, amount: int) -> None:
        self.money -= amount
        for cb in self._money_cbs:
            cb(self.money)

    def decrease_lives(self, amount: int) -> None:
        self.lives = max(0, self.lives - amount)
        for cb in self._lives_cbs:
            cb(self.lives)

    def tick(self) -> None:
        if self.is_started:
            self.time_ms += TICK_MS * self.speed

    def advance_level(self) -> None:
        self.level += 1
        for cb in self._level_cbs:
            cb(self.level)
