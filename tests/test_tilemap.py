import pygame
import pytest
from pygame.math import Vector2

from gameplay.tilemap import Tilemap
from pygamine import Camera

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


@pytest.fixture
def obstacle_map(tmp_path):
    """Load real TMX objects so pytmx's tile-object anchor conversion is covered."""
    tileset = pygame.Surface((32, 16))
    tileset.fill("green")
    tileset.fill("red", pygame.Rect(16, 0, 16, 16))
    pygame.image.save(tileset, str(tmp_path / "tiles.png"))

    def load(objects, group_attrs=""):
        path = tmp_path / "obstacles.tmx"
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<map version="1.10" orientation="orthogonal" renderorder="right-down" '
            'width="4" height="4" tilewidth="16" tileheight="16" infinite="0">\n'
            ' <tileset firstgid="1" name="tiles" tilewidth="16" tileheight="16" '
            'tilecount="2" columns="2">\n'
            '  <image source="tiles.png" width="32" height="16"/>\n'
            " </tileset>\n"
            ' <layer id="1" name="Base" width="4" height="4">\n'
            '  <data encoding="csv">1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1</data>\n'
            " </layer>\n"
            f' <objectgroup id="2" name="Obstacles"{group_attrs}>{objects}</objectgroup>\n'
            "</map>\n",
            encoding="utf-8",
        )
        return Tilemap(path)

    return load


def blocked_cells(tilemap):
    return {
        (row, col)
        for row, cells in enumerate(tilemap.buildable_grid)
        for col, buildable in enumerate(cells)
        if not buildable
    }


@pytest.mark.parametrize("alpha", [False, True])
@pytest.mark.parametrize(
    "size, top, blocked",
    [(16, 32, {(2, 2)}), (32, 16, {(1, 2), (1, 3), (2, 2), (2, 3)})],
)
def test_tile_obstacle_renders_at_the_blocked_cells(
    obstacle_map, alpha, size, top, blocked
):
    # Tiled stores a tile object's bottom edge; pytmx exposes its top edge.
    tilemap = obstacle_map(
        f'<object id="1" gid="2" x="32" y="48" width="{size}" height="{size}"/>'
    )
    surface = tilemap.pre_render(alpha=alpha)
    expected = pygame.Surface((64, 64))
    expected.fill("green")
    expected.fill("red", pygame.Rect(32, top, size, size))

    assert pygame.image.tobytes(surface, "RGBA") == pygame.image.tobytes(
        expected, "RGBA"
    )
    assert bool(surface.get_flags() & pygame.SRCALPHA) == alpha
    assert blocked_cells(tilemap) == blocked


@pytest.mark.parametrize(
    "bounds, blocked",
    [
        ((16, 16, 16, 16), {(1, 1)}),
        ((15.5, 15.5, 17, 17), {(r, c) for r in range(3) for c in range(3)}),
        ((-8, -8, 16, 16), {(0, 0)}),
        ((56, 56, 16, 16), {(3, 3)}),
        ((-32, -32, 16, 16), set()),
    ],
)
def test_rectangle_obstacle_blocks_its_footprint_without_an_image(
    obstacle_map, bounds, blocked
):
    x, y, width, height = bounds
    tilemap = obstacle_map(
        f'<object id="1" x="{x}" y="{y}" width="{width}" height="{height}"/>'
    )
    expected = pygame.Surface((64, 64))
    expected.fill("green")

    assert blocked_cells(tilemap) == blocked
    assert pygame.image.tobytes(tilemap.pre_render(), "RGBA") == pygame.image.tobytes(
        expected, "RGBA"
    )


def test_repeated_pre_render_keeps_obstacles_in_place(obstacle_map):
    tilemap = obstacle_map(
        '<object id="1" gid="2" x="32" y="48" width="16" height="16"/>'
    )
    first = pygame.image.tobytes(tilemap.pre_render(), "RGBA")

    for _ in range(3):
        assert pygame.image.tobytes(tilemap.pre_render(), "RGBA") == first
    assert blocked_cells(tilemap) == {(2, 2)}


def test_draw_keeps_obstacles_aligned_when_zoom_changes(obstacle_map):
    tilemap = obstacle_map(
        '<object id="1" gid="2" x="32" y="48" width="16" height="16"/>'
    )
    camera = Camera(pygame.Rect(0, 0, 128, 128), map_width=64, map_height=64)
    surface = pygame.Surface((128, 128))

    for scale in (1.0, 2.0, 0.5, 1.0):
        camera.scale = scale
        surface.fill("black")
        tilemap.draw(surface, camera)
        left, top, size = int(32 * scale), int(32 * scale), int(16 * scale)
        assert surface.get_at((left, top)) == pygame.Color("red")
        assert surface.get_at((left + size - 1, top + size - 1)) == pygame.Color("red")
        assert surface.get_at((left - 1, top)) == pygame.Color("green")
        assert surface.get_at((left, top - 1)) == pygame.Color("green")


def test_fractional_obstacle_image_covers_the_blocked_cells(obstacle_map):
    # Bounds 15.5..32.5 block cells 0..2, so the art spans pixels 15..33 too.
    tilemap = obstacle_map(
        '<object id="1" gid="2" x="15.5" y="32.5" width="17" height="17"/>'
    )
    surface = tilemap.pre_render()

    assert surface.get_at((15, 15)) == pygame.Color("red")
    assert surface.get_at((32, 32)) == pygame.Color("red")
    assert surface.get_at((14, 15)) == pygame.Color("green")
    assert surface.get_at((33, 32)) == pygame.Color("green")
    assert surface.get_at((15, 14)) == pygame.Color("green")
    assert surface.get_at((32, 33)) == pygame.Color("green")


def test_negative_fractional_obstacle_image_starts_at_the_floor(obstacle_map):
    tilemap = obstacle_map(
        '<object id="1" gid="2" x="-8.5" y="7.5" width="16" height="16"/>'
    )
    surface = tilemap.pre_render()

    assert surface.get_at((0, 0)) == pygame.Color("red")
    assert blocked_cells(tilemap) == {(0, 0)}


def test_obstacles_are_typed_records(obstacle_map):
    tilemap = obstacle_map(
        '<object id="1" gid="2" x="32" y="48" width="16" height="16"/>'
        '<object id="2" x="0" y="0" width="16" height="16"/>'
    )

    with_image, bare = tilemap.obstacles
    assert with_image.image is not None
    assert with_image.bounds == pygame.FRect(32, 32, 16, 16)
    assert bare.image is None
    with pytest.raises(AttributeError):
        bare.image = None  # type: ignore[misc]


def test_hidden_obstacle_group_neither_draws_nor_blocks(obstacle_map):
    tilemap = obstacle_map(
        '<object id="1" gid="2" x="32" y="48" width="16" height="16"/>',
        group_attrs=' visible="0"',
    )

    assert tilemap.obstacles == []
    assert blocked_cells(tilemap) == set()
    assert tilemap.pre_render().get_at((32, 32)) == pygame.Color("green")


def test_hidden_obstacle_object_neither_draws_nor_blocks(obstacle_map):
    tilemap = obstacle_map(
        '<object id="1" gid="2" x="32" y="48" width="16" height="16" visible="0"/>'
        '<object id="2" x="0" y="0" width="16" height="16"/>'
    )

    assert len(tilemap.obstacles) == 1
    assert blocked_cells(tilemap) == {(0, 0)}
    assert tilemap.pre_render().get_at((32, 32)) == pygame.Color("green")


@pytest.mark.parametrize(
    "obj, message",
    [
        (
            '<object id="7" x="0" y="0" width="16" height="16" rotation="90"/>',
            "rotated",
        ),
        (
            '<object id="7" x="0" y="0"><polygon points="0,0 16,0 16,16"/></object>',
            "polygon",
        ),
        (
            '<object id="7" x="0" y="0"><polyline points="0,0 16,16"/></object>',
            "polygon",
        ),
        (
            '<object id="7" x="0" y="0" width="16" height="16"><ellipse/></object>',
            "ellipse",
        ),
        ('<object id="7" x="0" y="0"><point/></object>', "point"),
        ('<object id="7" x="15.5" y="15.5" width="0" height="16"/>', "no area"),
        ('<object id="7" x="15.5" y="15.5" width="16" height="0"/>', "no area"),
    ],
)
def test_unsupported_obstacle_shapes_fail_loudly(obstacle_map, obj, message):
    with pytest.raises(AssertionError, match=message):
        obstacle_map(obj)


def test_unsupported_shapes_in_a_hidden_group_are_ignored(obstacle_map):
    tilemap = obstacle_map(
        '<object id="7" x="0" y="0" width="16" height="16" rotation="90"/>',
        group_attrs=' visible="0"',
    )

    assert tilemap.obstacles == []
