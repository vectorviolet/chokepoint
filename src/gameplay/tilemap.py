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
  Buildable tiles are anywhere outside the `Road` layer (and outside towers).
"""

from __future__ import annotations

from pathlib import Path

import pytmx
from pygame.math import Vector2

from pygamine import TiledMap


_WAY_LAYER = "Road"
_MARKERS_GROUP = "Markers"
_PATHS_GROUP = "Paths"


class Tilemap(TiledMap):
    """A Tiled .tmx plus Chokepoint's tower-defense parsing."""

    def __init__(self, tmx_path: str | Path) -> None:
        super().__init__(tmx_path)
        self.waypoints: list[Vector2] = self._load_first_path()
        self._spawn_col, self._spawn_row = self._load_marker("spawn")
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

    def _compute_buildable(self) -> list[list[bool]]:
        grid = [[True for _ in range(self.cols)] for _ in range(self.rows)]
        for layer in self.tmx.layers:
            if not isinstance(layer, pytmx.TiledTileLayer) or layer.name != _WAY_LAYER:
                continue
            for x, y, gid in layer.iter_data():
                if gid != 0 and 0 <= y < self.rows and 0 <= x < self.cols:
                    grid[y][x] = False
        return grid

    # ── public API ────────────────────────────────────────────────────────

    def get_spawn_tile(self) -> list[int | None]:
        return [self._spawn_col, self._spawn_row]
