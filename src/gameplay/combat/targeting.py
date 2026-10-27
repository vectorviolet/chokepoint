"""Spatial grids for targeting: ground towers looking for the nearest enemy,
and tanks looking for the nearest tower.

Comparing every tower with every enemy on every tick is O(towers x enemies)
(see docs/PERFORMANCE.md). Instead, the battle buckets the enemies (and the
towers) into square cells once per tick, and each query looks only at the
cells that can hold an answer.

The answers are exactly the ones the old full scans gave, ties included:

- ``EnemyGrid.nearest_in_range`` returns the enemy with the smallest
  ``(enemy.position - position).length()``, the first one in list order on
  a tie, or None if that smallest length is greater than the range.
  With a minimum range (the heavy cannon's blind spot, issue #11), enemies
  at that length or closer are left out first: the answer is the nearest
  enemy with ``min_radius < length <= radius``. A minimum range of 0 leaves
  nothing out, so the answer is exactly the one above.
- ``TowerGrid.nearest`` returns the targetable tower (``maxHP`` not None)
  with the smallest ``(tower.position - position).length_squared()``, the
  first one in list order on a tie, at any distance.

The cell search uses plain float arithmetic with a safety margin only to
skip what can't be an answer; every remaining candidate is compared with the
same Vector2 call the old scan used, so rounding can't change the choice.

A grid reads its list again when the list's length changes, so enemies
killed (and removed) earlier in the same tick are never picked. It assumes
nothing moves between its building and its queries, so build it once per
tick, before the phase that queries it, and don't keep it past that phase.
"""

from __future__ import annotations

from math import floor

from pygame.math import Vector2

CELL_SIZE = 128  # px; two tiles

# Relative slack on squared distances for the float pre-filters: far larger
# than any rounding difference between two ways of computing the same
# distance, far smaller than anything that matters in world pixels.
_SLACK = 1e-9


def _cell(x: float, y: float) -> tuple[int, int]:
    return floor(x / CELL_SIZE), floor(y / CELL_SIZE)


class EnemyGrid:
    """The enemies of one tick, bucketed by position, for ground towers."""

    def __init__(self, enemies: list) -> None:
        self.enemies = enemies
        self._count = -1  # built on the first query
        self._cells: dict[tuple[int, int], list] = {}

    def _sync(self) -> None:
        if len(self.enemies) == self._count:
            return
        cells: dict[tuple[int, int], list] = {}
        for i, enemy in enumerate(self.enemies):
            x, y = enemy.position
            cells.setdefault(_cell(x, y), []).append((i, enemy, x, y))
        self._cells = cells
        self._count = len(self.enemies)

    def nearest_in_range(self, position: Vector2, radius: float, min_radius: float = 0):
        """(enemy, enemy.position - position) for the nearest enemy that is
        within `radius` (inclusive) and outside `min_radius` (exclusive: an
        enemy exactly at `min_radius` is in the blind spot); (None, None)
        if there is none. `min_radius` 0 means no blind spot."""
        self._sync()
        px, py = position
        reach = radius + 1  # +1 px: covers rounding at the cell borders
        cx0, cy0 = _cell(px - reach, py - reach)
        cx1, cy1 = _cell(px + reach, py + reach)
        limit_sq = radius * radius * (1 + _SLACK)
        # Squared distances below this are surely inside the blind spot.
        # -1 when there is none, so nothing is skipped (not even distance 0).
        inner_sq = min_radius * min_radius * (1 - _SLACK) if min_radius > 0 else -1

        cells = self._cells
        best = best_delta = None
        best_len = best_i = 0
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                bucket = cells.get((cx, cy))
                if bucket is None:
                    continue
                for i, enemy, x, y in bucket:
                    dx = x - px
                    dy = y - py
                    dist_sq = dx * dx + dy * dy
                    if dist_sq > limit_sq or dist_sq < inner_sq:
                        continue
                    delta = enemy.position - position
                    length = delta.length()
                    if length > radius or (min_radius > 0 and length <= min_radius):
                        continue
                    if (
                        best is None
                        or length < best_len
                        or (length == best_len and i < best_i)
                    ):
                        best, best_delta, best_len, best_i = enemy, delta, length, i
        return best, best_delta


class TowerGrid:
    """The targetable towers of one tick, bucketed by position, for tanks.
    Towers without HP (planes: ``maxHP`` is None) are left out."""

    def __init__(self, towers: list) -> None:
        self.towers = towers
        self._count = -1  # built on the first query
        self._cells: dict[tuple[int, int], list] = {}
        self._bounds = (0, 0, -1, -1)

    def _sync(self) -> None:
        if len(self.towers) == self._count:
            return
        cells: dict[tuple[int, int], list] = {}
        index = 0
        for tower in self.towers:
            if tower.maxHP is None:
                continue
            x, y = tower.position
            cells.setdefault(_cell(x, y), []).append((index, tower))
            index += 1
        self._cells = cells
        self._count = len(self.towers)
        if cells:
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            self._bounds = (min(xs), min(ys), max(xs), max(ys))

    def nearest(self, position: Vector2) -> tuple:
        """(tower, squared distance) for the nearest targetable tower at any
        distance, or (None, 0) if there is none."""
        self._sync()
        cells = self._cells
        if not cells:
            return (None, 0)
        cx, cy = _cell(*position)
        min_x, min_y, max_x, max_y = self._bounds
        last_ring = max(cx - min_x, max_x - cx, cy - min_y, max_y - cy)

        best = None
        best_sq = best_i = 0
        for ring in range(last_ring + 1):
            for key in _ring_cells(cx, cy, ring):
                bucket = cells.get(key)
                if bucket is None:
                    continue
                for i, tower in bucket:
                    dist_sq = (tower.position - position).length_squared()
                    if (
                        best is None
                        or dist_sq < best_sq
                        or (dist_sq == best_sq and i < best_i)
                    ):
                        best, best_sq, best_i = tower, dist_sq, i
            # Every cell not searched yet is more than `ring` whole cells
            # away, so nothing in it can be as close as `best`.
            gap = ring * CELL_SIZE
            if best is not None and best_sq < gap * gap * (1 - _SLACK):
                break
        return (best, best_sq)


def _ring_cells(cx: int, cy: int, ring: int):
    """The cells exactly `ring` cells away (Chebyshev) from (cx, cy)."""
    if ring == 0:
        yield (cx, cy)
        return
    for x in range(cx - ring, cx + ring + 1):
        yield (x, cy - ring)
        yield (x, cy + ring)
    for y in range(cy - ring + 1, cy + ring):
        yield (cx - ring, y)
        yield (cx + ring, y)
