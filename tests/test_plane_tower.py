import pygame
import pytest

from domain.game_state import GameState
from gameplay.combat.projectile import Bomb
from gameplay.towers import TowerFactory
from gameplay.towers.plane_tower import BOMB_DROP_INTERVAL_MS
from gameplay.towers import PLANE_TYPE
from util.constants import GAME_SPEEDS, MAX_GAME_SPEED, TICK_MS

MAP_WIDTH = 3008


def make_plane(tower_config, assets, row=5, col=3):
    return TowerFactory.create(
        PLANE_TYPE, row, col, tower_config, assets, audio=None, map_width=MAP_WIDTH
    )


def running_state(speed=1, time_ms=0.0) -> GameState:
    gs = GameState(start_money=0, start_lives=10)
    gs.is_started = True
    gs.speed = speed
    gs.time_ms = time_ms
    return gs


def test_flies_right_by_its_speed_times_game_speed_each_tick(tower_config, assets):
    plane = make_plane(tower_config, assets)
    x0 = plane.position.x
    gs = running_state(speed=2)

    plane.update(gs, [])

    assert plane.position.x == x0 + plane.speed * 2
    assert plane.rect.centerx == round(plane.position.x)


def test_stays_put_while_the_game_is_paused(tower_config, assets):
    plane = make_plane(tower_config, assets)
    x0 = plane.position.x
    gs = running_state()
    gs.is_started = False

    plane.update(gs, [])

    assert plane.position.x == x0


def test_drops_bombs_every_interval_of_game_time(tower_config, assets):
    plane = make_plane(tower_config, assets)
    gs = running_state(time_ms=1000)

    plane.update(gs, [])  # first update starts the bomb timer
    assert plane.bullets == []

    gs.time_ms += BOMB_DROP_INTERVAL_MS - 1
    plane.update(gs, [])
    assert plane.bullets == []

    gs.time_ms += 1
    plane.update(gs, [])
    assert len(plane.bullets) == 1 and isinstance(plane.bullets[0], Bomb)


def test_takes_the_global_plane_level(tower_config, assets):
    plane = make_plane(tower_config, assets)
    gs = running_state()
    gs.plane_level = 2

    plane.update(gs, [])

    assert plane.level == 2
    assert plane.damage == tower_config.damages[PLANE_TYPE - 1][1]


def test_is_removed_once_its_whole_sprite_is_past_the_right_edge(tower_config, assets):
    # Issue #59: not when its center crosses the edge, but its sprite's left edge.
    plane = make_plane(tower_config, assets)
    half_width = plane.sprite_rect().width / 2
    assert half_width > 0
    assert not plane.should_remove()

    plane.position.x = MAP_WIDTH + 1  # center past the edge, sprite still showing
    assert not plane.should_remove()

    plane.position.x = MAP_WIDTH + half_width  # left edge exactly on the edge
    assert not plane.should_remove()

    plane.position.x = MAP_WIDTH + half_width + 0.5
    assert plane.should_remove()


def test_flies_on_until_its_sprite_has_left_the_map(tower_config, assets):
    plane = make_plane(tower_config, assets)
    plane.position.x = MAP_WIDTH
    gs = running_state()
    ticks = 0
    while not plane.should_remove():
        plane.update(gs, [])
        ticks += 1
        assert ticks < 1000

    assert plane.sprite_rect().left > MAP_WIDTH - 1  # rounded to whole pixels
    assert plane.position.x - plane.speed - plane.sprite_rect().width / 2 <= MAP_WIDTH


class LandingCtx:
    """The bits of IGameContext a falling bomb reads; records where each lands."""

    def __init__(self, game_state: GameState) -> None:
        self._gs = game_state
        self.enemies: list = []
        self.landings: list[float] = []

    @property
    def speed(self) -> int:
        return self._gs.speed

    @property
    def time_ms(self) -> float:
        return self._gs.time_ms

    def bomb_landed(self, position, radius) -> None:
        self.landings.append(position.x)


def fly_to_the_end(plane, gs: GameState) -> list[float]:
    """Ticks like the battle (game time, the plane, then its bombs) until
    the plane has left the map and its last bomb has landed; returns where
    each bomb landed."""
    ctx = LandingCtx(gs)
    for _ in range(100_000):
        if plane.should_remove() and not plane.bullets:
            return ctx.landings
        gs.tick()
        plane.update(gs, [])
        for bomb in list(plane.bullets):
            bomb.update(ctx)
    raise AssertionError("the plane never left")


def plane_at_level(tower_config, assets, level: int, gs: GameState):
    """A plane that has taken `level` from `gs` and started its bomb timer."""
    plane = make_plane(tower_config, assets)
    gs.plane_level = level
    plane.update(gs, [])  # takes the level, starts the bomb timer
    assert plane.level == level
    return plane


def max_drift(plane) -> float:
    """How far before the edge the plane's last bomb may be dropped: its
    drift at the fastest game speed."""
    return Bomb.landing_offset(plane._drop_velocity(), MAX_GAME_SPEED).x


@pytest.mark.parametrize("level", [1, 2])
@pytest.mark.parametrize("speed", GAME_SPEEDS)
def test_the_last_bomb_lands_at_or_before_the_edge(tower_config, assets, level, speed):
    # Issue #94: a bomb drifts on after its release; the plane drops only
    # bombs that will land on the map.
    gs = running_state(speed=speed, time_ms=1000)
    plane = plane_at_level(tower_config, assets, level, gs)
    plane.position.x = MAP_WIDTH - 1000

    landings = fly_to_the_end(plane, gs)

    assert len(landings) >= 3
    assert max(landings) <= MAP_WIDTH
    # It drops right up to the cut-off: the next bomb, one drop interval
    # of flight later, could have landed past the edge at the fastest speed.
    interval_flight = plane.speed * BOMB_DROP_INTERVAL_MS / TICK_MS  # any speed
    drift = Bomb.landing_offset(plane._drop_velocity(), speed).x
    margin = interval_flight + plane.speed * speed + max_drift(plane) - drift
    assert landings[-1] > MAP_WIDTH - margin - 0.1


@pytest.mark.parametrize("level", [1, 2])
@pytest.mark.parametrize("speed", GAME_SPEEDS)
def test_drops_a_bomb_that_may_land_on_the_edge_but_none_past_it(
    tower_config, assets, level, speed
):
    gs = running_state(speed=speed, time_ms=1000)
    plane = plane_at_level(tower_config, assets, level, gs)
    step = plane.speed * speed
    cut_off = MAP_WIDTH - max_drift(plane) - step  # the drop tick starts here

    plane.position.x = cut_off - 0.01  # next tick: lands just inside the edge
    gs.time_ms += BOMB_DROP_INTERVAL_MS
    plane.update(gs, [])
    assert len(plane.bullets) == 1

    plane.bullets.clear()
    plane.position.x = cut_off + 0.01  # next tick: could land just past it
    gs.time_ms += BOMB_DROP_INTERVAL_MS
    plane.update(gs, [])
    assert plane.bullets == []
    # Nor while its sprite slides off.
    while not plane.should_remove():
        gs.time_ms += BOMB_DROP_INTERVAL_MS
        plane.update(gs, [])
    assert plane.bullets == []


@pytest.mark.parametrize("level", [1, 2])
def test_speeding_up_mid_fall_still_lands_the_last_bomb_on_the_map(
    tower_config, assets, level
):
    gs = running_state(speed=1, time_ms=1000)
    plane = plane_at_level(tower_config, assets, level, gs)
    plane.position.x = MAP_WIDTH - max_drift(plane) - plane.speed - 0.01
    gs.time_ms += BOMB_DROP_INTERVAL_MS
    plane.update(gs, [])  # drops the last bomb at x1, as far right as it may
    (bomb,) = plane.bullets
    ctx = LandingCtx(gs)
    bomb.update(ctx)  # its first x1 tick, as in the battle

    gs.speed = MAX_GAME_SPEED  # the player speeds up while it falls
    landings = ctx.landings + fly_to_the_end(plane, gs)

    assert len(landings) == 1
    assert MAP_WIDTH - 1 < landings[0] <= MAP_WIDTH


@pytest.mark.parametrize(
    ("level", "game_speed", "expected"),
    [
        (1, 1, 33.3),
        (2, 1, 16.7),
        (1, 2, 34.4),
        (2, 2, 17.2),
        (1, 4, 36.5),
        (2, 4, 18.2),
    ],
)
def test_landing_offset_is_the_drift_a_falling_bomb_covers(
    tower_config, assets, level, game_speed, expected
):
    gs = running_state(speed=game_speed)
    plane = plane_at_level(tower_config, assets, level, gs)
    offset = Bomb.landing_offset(plane._drop_velocity(), game_speed)
    assert offset.y == 0
    assert offset.x == pytest.approx(expected, abs=0.05)

    # A real bomb drifts that far, to within a tenth of a pixel, and no further.
    plane.now = gs.time_ms
    bomb = Bomb(plane, plane._drop_velocity())
    start = bomb.position.x
    ctx = LandingCtx(gs)
    while not ctx.landings:
        bomb.update(ctx)
        gs.tick()
    assert offset.x - 0.1 <= ctx.landings[0] - start <= offset.x


def test_never_blocks_a_build_tile_and_is_untargetable(tower_config, assets):
    plane = make_plane(tower_config, assets)

    assert plane.get_blocking_position() is None
    assert plane.max_hp is None and plane.hp is None


def test_draw_renders_shadow_plane_and_range_when_selected(tower_config, assets):
    from pygamine import Camera

    plane = make_plane(tower_config, assets)
    gs = running_state()
    gs.selected_tower = plane
    camera = Camera(pygame.Rect(0, 0, 800, 600), MAP_WIDTH, 2176)
    surface = pygame.Surface((800, 600))

    plane.draw(gs, camera, surface)  # must not raise

    plane.work([], True)  # planes attack only through their bombs
