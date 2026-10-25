from pygame.math import Vector2

from util.config_loader import load_wave_compositions
from gameplay.combat.enemy import Enemy
from gameplay.combat.tank import Tank
from domain.game_state import GameState, WaveDef

TANK_TYPES = (5, 6)

WAVE_COMPOSITIONS: dict[int, WaveDef] = load_wave_compositions()


class WaveManager:
    """Handles enemy spawning and wave-transition timing."""

    SPAWN_INTERVAL_MS = 1000
    LEVEL_END_DELAY_MS = 5000
    MIN_ENDLESS_INTERVAL_MS = 400

    def __init__(self, waypoints: list[Vector2], assets) -> None:
        if not waypoints:
            raise ValueError("WaveManager needs a non-empty waypoints list")
        self._waypoints = waypoints
        self._assets = assets
        self._count_all_time: int = 0
        self._last_spawn_time: int = 0
        self._level_finish_time: int | None = None
        self._current_level: int = -1
        self._spawn_queue: list[int] = []  # flattened list of enemy types
        self._queue_index: int = 0
        self._spawn_interval_ms: int = self.SPAWN_INTERVAL_MS

    def _build_queue(self, level: int) -> None:
        wave = WAVE_COMPOSITIONS.get(level) or self._wave_for(level)
        self._spawn_queue = [
            enemy_type for enemy_type, count in wave.groups for _ in range(count)
        ]
        self._spawn_interval_ms = wave.spawn_interval_ms or self.SPAWN_INTERVAL_MS
        self._queue_index = 0
        self._level_finish_time = None

    def _wave_for(self, level: int) -> WaveDef:
        """Endless-mode waves past the last authored one: keep its mix and
        grow every group a little per wave, tanks half as fast, while the
        spawn interval tightens down to a floor. HP/reward keep scaling
        per level in Enemy, as for every wave."""
        last = max(WAVE_COMPOSITIONS)
        base = WAVE_COMPOSITIONS[last]
        extra = level - last
        groups = [
            (enemy_type, count + (extra // 2 if enemy_type in TANK_TYPES else extra))
            for enemy_type, count in base.groups
        ]
        interval = base.spawn_interval_ms or self.SPAWN_INTERVAL_MS
        return WaveDef(
            groups=groups,
            spawn_interval_ms=max(self.MIN_ENDLESS_INTERVAL_MS, interval - 10 * extra),
        )

    def update(self, enemies: list, game_state: GameState) -> None:
        if not game_state.is_started:
            return

        if game_state.level != self._current_level:
            self._current_level = game_state.level
            self._build_queue(game_state.level)

        now = game_state.time_ms

        if self._queue_index < len(self._spawn_queue):
            if now - self._last_spawn_time >= self._spawn_interval_ms:
                enemy_type = self._spawn_queue[self._queue_index]
                self._queue_index += 1
                self._count_all_time += 1
                cls = Tank if enemy_type in TANK_TYPES else Enemy
                enemies.append(
                    cls(
                        self._count_all_time,
                        enemy_type,
                        game_state.level,
                        self._waypoints,
                        self._assets,
                    )
                )
                self._last_spawn_time = now
                if self._queue_index == len(self._spawn_queue):
                    self._level_finish_time = now

        elif (
            self._level_finish_time
            and now - self._level_finish_time >= self.LEVEL_END_DELAY_MS
            and not enemies
        ):
            game_state.advance_level()
