"""The main menu's live background: a battle that plays itself.

A MenuDemo is a world of its own -- its own GameState, towers, enemies and
wave manager -- run by the same BattleSimulation as the real game, so it
always shows the current towers, enemies and effects. Nothing it does
reaches the player's game: it has no save store, its towers are silent and
it never runs out of lives.

Each run is random: towers of every type at random spots along the path,
pre-upgraded, starting at a mid-game wave with planes flying bombing runs.
A camera eases between whatever is happening. After a few waves, or once
the defence has been worn down, it fades to black and starts a new run.
"""

from __future__ import annotations

import math
import random

import pygame
from pygame import Rect
from pygame.math import Vector2

from domain.game_state import GameState, TowerConfig
from gameplay.battle import BattleSimulation
from ui.bomb_impact_feedback import BombImpactFeedback
from gameplay.combat.wave_manager import WaveManager
from pygamine import Camera
from gameplay.towers import TowerFactory
from util.constants import TICK_MS, TILE_SIZE, HALF_TILE

GROUND_TOWER_TYPES = (1, 2, 3)
PLANE_TYPE = 4

START_LEVELS = (8, 16)  # a run starts at a random wave in this range
WAVES_PER_RUN = 3  # ...and is replaced after this many waves
TOWER_COUNT = (16, 22)
MIN_TOWERS_LEFT = 5  # fewer ground towers than this: start over
# Towers go on build tiles whose centre is this far from the path (world px):
# close enough to reach it, never on it.
TOWER_PATH_DISTANCE = (0.9 * TILE_SIZE, 2.6 * TILE_SIZE)
PLANE_INTERVAL_MS = (5000, 11000)  # game time between bombing runs
PREWARM_MS = 9000  # game time simulated before a run is shown
# Denser than the real game's waves, so the screen stays busy: each wave's
# enemies are doubled and spawn twice as fast, and the real game's 5 s
# breather between waves (which would leave the screen empty) is cut short.
WAVE_SIZE_FACTOR = 2
SPAWN_INTERVAL_FACTOR = 0.5
MIN_SPAWN_INTERVAL_MS = 250
WAVE_GAP_MS = 1200

CAMERA_SMOOTHING_S = 1.6  # time constant of the camera's ease
CAMERA_MAX_SPEED = 220  # world px/s
CAMERA_RETARGET_S = (6.0, 10.0)
CLUSTER_RADIUS = 450  # enemies this close to the followed one count as its group
FADE_S = 0.6


class _SilentAudio:
    """Towers play their shot sounds through this: the demo stays quiet
    under the menu music."""

    def play_sfx(self, path) -> None:
        pass


class _DemoWaves(WaveManager):
    """The real waves, packed tighter (see WAVE_SIZE_FACTOR)."""

    LEVEL_END_DELAY_MS = WAVE_GAP_MS

    def _build_queue(self, level: int) -> None:
        super()._build_queue(level)
        self._spawn_queue = self._spawn_queue * WAVE_SIZE_FACTOR
        self._spawn_interval_ms = max(
            MIN_SPAWN_INTERVAL_MS, int(self._spawn_interval_ms * SPAWN_INTERVAL_FACTOR)
        )


class MenuDemo(BattleSimulation):
    def __init__(
        self,
        tilemap,
        assets,
        tower_config: TowerConfig,
        size: tuple[int, int],
        rng: random.Random | None = None,
    ) -> None:
        self.tilemap = tilemap
        self._assets = assets
        self._tower_config = tower_config
        self._audio = _SilentAudio()
        # Explosions where the bombs land, silent like the rest of the demo.
        self.bomb_impacts = BombImpactFeedback(assets, play_sfx=None)
        self._rng = rng or random.Random()

        self.view = Rect(0, 0, *size)
        self.camera = Camera(self.view, tilemap.map_width, tilemap.map_height)
        self._candidate_tiles = self._tiles_along_path()

        self._tick_backlog_ms = 0.0
        self._fade = 1.0  # black overlay opacity, 0..1
        self._fading_out = False
        self._start_run()

    # ── public ───────────────────────────────────────────────────────────────

    def resize(self, size: tuple[int, int]) -> None:
        self.view.update(0, 0, *size)
        self.camera.center_on(self._camera_pos)

    def update(self, frame_ms: float) -> None:
        """Advance by `frame_ms` of real time."""
        dt = frame_ms / 1000
        self.bomb_impacts.update(frame_ms)
        if self._fading_out:
            self._fade = min(1.0, self._fade + dt / FADE_S)
            if self._fade >= 1.0:
                self._fading_out = False
                self._start_run()
            return
        self._fade = max(0.0, self._fade - dt / FADE_S)

        self._tick_backlog_ms += frame_ms
        while self._tick_backlog_ms >= TICK_MS:
            self._tick_backlog_ms -= TICK_MS
            self._tick()
        self._update_camera(dt)

        if self._run_is_over():
            self._fading_out = True

    def draw(self, surface: pygame.Surface) -> None:
        old_clip = surface.get_clip()
        surface.set_clip(self.view)
        self._draw_battle(surface, self.camera)
        surface.set_clip(old_clip)
        if self._fade > 0:
            veil = pygame.Surface(self.view.size)
            veil.set_alpha(round(255 * self._fade))
            surface.blit(veil, self.view.topleft)

    # ── simulation ────────────────────────────────────────────────────────────

    def _on_enemy_escaped(self, enemy) -> None:
        pass  # endless lives: the show goes on

    def _tick(self) -> None:
        super()._tick()
        if self.game_state.time_ms >= self._next_plane_at:
            self._launch_plane()

    def _run_is_over(self) -> bool:
        ground = sum(1 for t in self.towers if t.tower_type in GROUND_TOWER_TYPES)
        return self.game_state.level >= self._last_level or ground < MIN_TOWERS_LEFT

    # ── a new run ─────────────────────────────────────────────────────────────

    def _start_run(self) -> None:
        rng = self._rng
        self.game_state = GameState(start_money=0, start_lives=1)
        self.game_state.level = rng.randint(*START_LEVELS)
        self.game_state.plane_level = rng.choice((1, 2))
        self.game_state.is_started = True
        self._last_level = self.game_state.level + WAVES_PER_RUN
        self.towers = []
        self.enemies = []
        self._clear_orphan_shots()
        self.wave_manager = _DemoWaves(self.tilemap.waypoints, self._assets)
        self._place_towers()
        self._next_plane_at = rng.uniform(*PLANE_INTERVAL_MS) / 2

        # Open on a battle already under way, rather than on enemies
        # trickling in from the edge of the map.
        for _ in range(int(PREWARM_MS / TICK_MS)):
            self._tick()
        self.bomb_impacts.clear()  # bombs that landed while pre-warming

        self._camera_target = self._pick_camera_target()
        self._camera_pos = Vector2(self._target_position())
        self._retarget_in = rng.uniform(*CAMERA_RETARGET_S)
        self.camera.center_on(self._camera_pos)

    def _tiles_along_path(self) -> list[tuple[int, int]]:
        """Build tiles within reach of the enemy path."""
        near, far = TOWER_PATH_DISTANCE
        grid = self.tilemap.buildable_grid
        path = self.tilemap.waypoints
        tiles = []
        for row, cells in enumerate(grid):
            for col, buildable in enumerate(cells):
                if not buildable:
                    continue
                centre = Vector2(
                    col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE
                )
                if near <= _distance_to_path(centre, path) <= far:
                    tiles.append((row, col))
        return tiles

    def _place_towers(self) -> None:
        rng = self._rng
        count = min(rng.randint(*TOWER_COUNT), len(self._candidate_tiles))
        for row, col in rng.sample(self._candidate_tiles, count):
            tower_type = rng.choice(GROUND_TOWER_TYPES)
            tower = self._create_tower(tower_type, row, col)
            # Upgraded more often than not: a run is set mid-game.
            tower.level = rng.choices(
                range(1, tower.max_level + 1), weights=range(1, tower.max_level + 1)
            )[0]
            if tower.level > 1:
                tower.load(
                    self._assets.image_path(f"tower_{tower_type}_lvl{tower.level}")
                )
                tower.hp = tower.maxHP
            self.towers.append(tower)

    def _launch_plane(self) -> None:
        rng = self._rng
        self._next_plane_at = self.game_state.time_ms + rng.uniform(*PLANE_INTERVAL_MS)
        # Fly over the action: the row of an enemy (or of the path).
        if self.enemies:
            y = rng.choice(self.enemies).position.y
        else:
            y = rng.choice(self.tilemap.waypoints).y
        row = max(0, min(len(self.tilemap.buildable_grid) - 1, int(y // TILE_SIZE)))
        self.towers.append(self._create_tower(PLANE_TYPE, row, 0))

    def _create_tower(self, tower_type: int, row: int, col: int):
        return TowerFactory.create(
            tower_type,
            row,
            col,
            self._tower_config,
            self._assets,
            self._audio,
            self.tilemap.map_width,
        )

    # ── camera ────────────────────────────────────────────────────────────────

    def _pick_camera_target(self):
        """Something to look at: an enemy (the camera then frames its whole
        group), or a tower while no enemy is around."""
        rng = self._rng
        if self.enemies:
            return rng.choice(self.enemies)
        ground = [t for t in self.towers if t.tower_type in GROUND_TOWER_TYPES]
        if ground:
            return rng.choice(ground)
        return rng.choice(self.tilemap.waypoints)

    def _target_position(self) -> Vector2:
        target = self._camera_target
        if target in self.enemies:
            # The middle of its group, so the whole fight is in frame.
            group = [
                e.position
                for e in self.enemies
                if e.position.distance_to(target.position) <= CLUSTER_RADIUS
            ]
            return sum(group, Vector2()) / len(group)
        return target.position if hasattr(target, "position") else target

    def _update_camera(self, dt: float) -> None:
        self._retarget_in -= dt
        target_gone = (
            self._camera_target not in self.enemies
            and self._camera_target not in self.towers
            and not isinstance(self._camera_target, Vector2)
        )
        if self._retarget_in <= 0 or target_gone:
            self._camera_target = self._pick_camera_target()
            self._retarget_in = self._rng.uniform(*CAMERA_RETARGET_S)

        # Ease toward the target, never faster than CAMERA_MAX_SPEED.
        to_target = Vector2(self._target_position()) - self._camera_pos
        step = to_target * (1 - math.exp(-dt / CAMERA_SMOOTHING_S))
        max_step = CAMERA_MAX_SPEED * dt
        if step.length() > max_step:
            step.scale_to_length(max_step)
        self._camera_pos += step
        self.camera.center_on(self._camera_pos)


def _distance_to_path(point: Vector2, path: list[Vector2]) -> float:
    """Shortest distance from `point` to the polyline `path`."""
    best = math.inf
    for a, b in zip(path, path[1:]):
        ab = b - a
        length_sq = ab.length_squared()
        t = (
            0.0
            if length_sq == 0
            else max(0.0, min(1.0, (point - a).dot(ab) / length_sq))
        )
        best = min(best, point.distance_to(a + ab * t))
    return best
