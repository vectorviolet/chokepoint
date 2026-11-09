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
- Buildable tiles are outside the road, obstacles, and existing towers.
- An object group named `Obstacles` containing unrotated tile objects or
  rectangles (rotation, polygons, polylines, ellipses and points fail an
  assert; zero-area objects are ignored). Their bounds block construction, even
  when they have no image. A hidden group, or a hidden object, is ignored: it
  neither draws nor blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path
from typing import override
from xml.etree import ElementTree

import pygame
from pygame.math import Vector2
import pytmx

from pygamine import TiledMap


_WAY_LAYER = "Road"
_MARKERS_GROUP = "Markers"
_PATHS_GROUP = "Paths"
_OBSTACLES_GROUP = "Obstacles"
_UNSUPPORTED_SHAPE_TAGS = ("polygon", "polyline", "ellipse", "point")


@dataclass(frozen=True)
class Obstacle:
    """A static map obstacle: its art (None for a bare rectangle) and its bounds."""

    image: pygame.Surface | None
    bounds: pygame.FRect


class Tilemap(TiledMap):
    """A Tiled .tmx plus Chokepoint's tower-defense parsing."""

    def __init__(self, tmx_path: str | Path) -> None:
        super().__init__(tmx_path)
        self.waypoints: list[Vector2] = self._load_first_path()
        self._spawn_col, self._spawn_row = self._load_marker("spawn")
        self._unsupported_shape_ids = self._find_unsupported_shape_ids(tmx_path)
        self.obstacles: list[Obstacle] = self._load_obstacles()
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

    def _load_obstacles(self) -> list[Obstacle]:
        obstacles = []
        # Hidden groups and objects are skipped, like hidden tile layers.
        for layer in self.tmx.visible_layers:
            if not (
                isinstance(layer, pytmx.TiledObjectGroup)
                and layer.name == _OBSTACLES_GROUP
            ):
                continue
            for obj in layer:
                if not obj.visible:
                    continue
                assert obj.rotation == 0, (
                    f"Obstacle object {obj.id} is rotated; only unrotated "
                    "tile objects and rectangles are supported"
                )
                assert obj.id not in self._unsupported_shape_ids, (
                    f"Obstacle object {obj.id} is a polygon, polyline, ellipse "
                    "or point; only tile objects and rectangles are supported"
                )
                if obj.width <= 0 or obj.height <= 0:
                    continue  # zero-area objects neither draw nor block
                # pytmx already converts tile-object y from bottom to top.
                bounds = pygame.FRect(obj.x, obj.y, obj.width, obj.height)
                obstacles.append(Obstacle(self._obstacle_image(obj, bounds), bounds))

        return obstacles

    @staticmethod
    def _obstacle_image(
        obj: pytmx.TiledObject, bounds: pygame.FRect
    ) -> pygame.Surface | None:
        """The object's image sized to the whole cells blocking covers."""
        image = obj.image
        if image is None:
            return None
        size = (
            ceil(bounds.right) - floor(bounds.left),
            ceil(bounds.bottom) - floor(bounds.top),
        )
        if image.get_size() != size:
            image = pygame.transform.scale(image, size)
        return image

    @staticmethod
    def _find_unsupported_shape_ids(tmx_path: str | Path) -> set[int]:
        """Ids of Obstacles objects pytmx can't tell from rectangles.

        pytmx drops the `<ellipse/>` and `<point/>` children and gives polygons
        a bounding box, so they would otherwise load as plain rectangles.
        """
        root = ElementTree.parse(tmx_path).getroot()
        return {
            int(obj.get("id", 0))
            for group in root.iter("objectgroup")
            if group.get("name") == _OBSTACLES_GROUP
            for obj in group.iter("object")
            if any(obj.find(tag) is not None for tag in _UNSUPPORTED_SHAPE_TAGS)
        }

    def _compute_buildable(self) -> list[list[bool]]:
        grid = [[True for _ in range(self.cols)] for _ in range(self.rows)]
        for layer in self.tmx.layers:
            if not (
                isinstance(layer, pytmx.TiledTileLayer) and layer.name == _WAY_LAYER
            ):
                continue
            for x, y, gid in layer.iter_data():
                if gid != 0 and 0 <= y < self.rows and 0 <= x < self.cols:
                    grid[y][x] = False

        for obs in self.obstacles:
            bounds = obs.bounds
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
            if obs.image is not None:
                surface.blit(obs.image, (floor(obs.bounds.left), floor(obs.bounds.top)))
        return surface

    # ── public API ────────────────────────────────────────────────────────

    def get_spawn_tile(self) -> list[int | None]:
        return [self._spawn_col, self._spawn_row]
