"""Tower-defense Tiled map for Chokepoint.

Extends `pygamine.assets.tilemap.TiledMap` with the TD-specific parsing this game
needs on top of the generic loader: the enemy path, the spawn marker, and the
buildable grid. Generic concerns (tile dimensions, object iteration, the
offscreen pre-render, and the camera-aware draw) live in the base class.

TMX conventions this loader expects:

- `infinite="0"` in the map header. pytmx 3.32 does not load infinite maps;
  run `python scripts/convert_tmx_to_finite.py <map.tmx>` once after exporting
  from Tiled in infinite mode.
- An object group named `Markers` containing point objects named `"spawn"`
  and `"end"`.
- An object group named `Paths` containing polyline objects, one per path.
- A tile layer named `Road` whose tiles describe the enemy path geometry.
- An object group named `Obstacles` containing unrotated tile objects or
  rectangles. Their bounds block construction, even when they have no image.
  Buildable tiles are outside the road, obstacles, and existing towers.
"""

from __future__ import annotations

from math import ceil, floor
from pathlib import Path
from typing import override

import pygame
from pygame.math import Vector2
import pytmx

from pygamine import TiledMap


_WAY_LAYER = "Road"
_MARKERS_GROUP = "Markers"
_PATHS_GROUP = "Paths"
_OBSTACLES_GROUP = "Obstacles"


class Tilemap(TiledMap):
    """A Tiled .tmx plus Chokepoint's tower-defense parsing."""

    def __init__(self, tmx_path: str | Path) -> None:
        super().__init__(tmx_path)
        self.waypoints: list[Vector2] = self._load_first_path()
        self._spawn_col, self._spawn_row = self._load_marker("spawn")
        self.obstacles: list[dict] = self._load_obstacles()
        self.buildable_grid: list[list[bool]] = self._compute_buildable()

    # ── loaders ───────────────────────────────────────────────────────────

    def _load_first_path(self) -> list[Vector2]:
        for obj in self.iter_objects(_PATHS_GROUP):
            points: list | None = getattr(obj, "points", None)
            if points:
                return [Vector2(p.x, p.y) for p in points]
        return []

    def _load_marker(self, name: str) -> tuple[int | None, int | None]:
        for obj in self.iter_objects(_MARKERS_GROUP):
            if (obj.name or "").lower() == name.lower():
                col = int(obj.x // self.tile_size)
                row = int(obj.y // self.tile_size)
                return col, row
        return None, None

    def _load_obstacles(self) -> list[dict]:
        obstacles_list = []
        for obj in self.iter_objects(_OBSTACLES_GROUP):
            # pytmx already converts tile-object y from bottom to top.
            bounds = pygame.FRect(obj.x, obj.y, obj.width, obj.height)
            if bounds.width <= 0 or bounds.height <= 0:
                continue
            image = getattr(obj, "image", None)
            if image is not None:
                size = (max(1, round(bounds.width)), max(1, round(bounds.height)))
                if image.get_size() != size:
                    image = pygame.transform.scale(image, size)
            obstacles_list.append(
                {
                    "image": image,
                    "pos": Vector2(bounds.topleft),
                    "col": floor(bounds.left / self.tile_size),
                    "row": floor(bounds.top / self.tile_size),
                    "bounds": bounds,
                    "properties": getattr(obj, "properties", {}),
                }
            )

        return obstacles_list

    def _compute_buildable(self) -> list[list[bool]]:
        grid = [[True for _ in range(self.cols)] for _ in range(self.rows)]
        for layer in self.tmx.layers:
            if not isinstance(layer, pytmx.TiledTileLayer) or layer.name != _WAY_LAYER:
                continue
            for x, y, gid in layer.iter_data():
                if gid != 0 and 0 <= y < self.rows and 0 <= x < self.cols:
                    grid[y][x] = False

        for obs in self.obstacles:
            bounds = obs["bounds"]
            first_col = max(0, floor(bounds.left / self.tile_size))
            first_row = max(0, floor(bounds.top / self.tile_size))
            end_col = min(self.cols, ceil(bounds.right / self.tile_size))
            end_row = min(self.rows, ceil(bounds.bottom / self.tile_size))
            for row in range(first_row, end_row):
                for col in range(first_col, end_col):
                    grid[row][col] = False

        return grid

    @override
    def pre_render(self, alpha: bool = False) -> pygame.Surface:
        """Bake static obstacle images into the map before the base class caches it."""
        surface = super().pre_render(alpha=alpha)
        for obs in self.obstacles:
            if obs["image"] is not None:
                surface.blit(obs["image"], obs["pos"])
        return surface

    # ── public API ────────────────────────────────────────────────────────

    def get_spawn_tile(self) -> list[int | None]:
        return [self._spawn_col, self._spawn_row]
