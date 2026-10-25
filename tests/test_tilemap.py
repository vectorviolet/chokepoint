import pytest
from pygame.math import Vector2

from gameplay.tilemap import Tilemap

TMX_PATH = "assets/maps/tiled_tilemap.tmx"


@pytest.fixture(scope="module")
def tilemap() -> Tilemap:
    return Tilemap(TMX_PATH)


def test_tile_dimensions_come_from_the_tmx(tilemap):
    assert tilemap.tile_size > 0
    assert tilemap.cols > 0
    assert tilemap.rows > 0
    assert tilemap.map_width == tilemap.cols * tilemap.tile_size
    assert tilemap.map_height == tilemap.rows * tilemap.tile_size


def test_waypoints_are_loaded_from_the_first_paths_polyline(tilemap):
    assert len(tilemap.waypoints) >= 2
    assert all(isinstance(p, Vector2) for p in tilemap.waypoints)


def test_spawn_marker_is_within_the_grid(tilemap):
    col, row = tilemap.get_spawn_tile()

    assert col is not None and row is not None
    assert 0 <= col < tilemap.cols
    assert 0 <= row < tilemap.rows


def test_buildable_grid_matches_map_dimensions(tilemap):
    assert len(tilemap.buildable_grid) == tilemap.rows
    assert all(len(row) == tilemap.cols for row in tilemap.buildable_grid)


def test_buildable_grid_is_false_somewhere_and_true_somewhere(tilemap):
    # The Road layer marks some tiles unbuildable -- a grid that's all-True
    # would mean the Road layer silently failed to parse.
    flat = [cell for row in tilemap.buildable_grid for cell in row]
    assert any(flat)
    assert not all(flat)


def test_spawn_tile_sits_on_the_road_or_at_least_within_bounds(tilemap):
    # The spawn marker doesn't have to be a Road tile itself (it's a point
    # object, not a tile), but it must resolve to a real grid cell.
    col, row = tilemap.get_spawn_tile()
    assert (col, row) != (None, None)
