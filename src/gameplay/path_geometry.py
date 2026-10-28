"""Geometry of the enemy path on the tilemap: shared by the menu demo, the
play-test save script and the load benchmark."""

from __future__ import annotations

import math

from pygame.math import Vector2

from util.constants import HALF_TILE, TILE_SIZE


def distance_to_path(point: Vector2, path: list[Vector2]) -> float:
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


def tiles_near_path(tilemap, near: float, far: float) -> list[tuple[int, int]]:
    """Build tiles (row, col), row by row, whose centre is `near` to `far`
    world px from the enemy path."""
    path = tilemap.waypoints
    tiles = []
    for row, cells in enumerate(tilemap.buildable_grid):
        for col, buildable in enumerate(cells):
            if not buildable:
                continue
            centre = Vector2(col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE)
            if near <= distance_to_path(centre, path) <= far:
                tiles.append((row, col))
    return tiles
