"""Strategy bots for scripts/balance_sim.py (issue #70).

A bot is a list of steps: an opener played once, then a cycle repeated for
the rest of the run. A bot may switch to another cycle from a given wave
on (`phases`); the new cycle starts from its first step. Each step is one
purchase, and the bot plays them strictly in order: when it can't afford
the next step it waits (saving up) rather than skipping ahead. A step that
can't apply at all (an upgrade with no tower left to upgrade, a placement
with no free tile, UPG PLANES already bought) is skipped.

The steps:

    Place(t, ring)   a new tower of type t on the free build tile of `ring`
                     that covers the most path (see rank_tiles()): "front"
                     is the row of tiles right beside the path, "back" the
                     row behind it. With the ring full, any free tile.
    Upgrade(t)       the lowest-level tower of type t below its max level
                     (the oldest first) goes up one level.
    LaunchPlane()    a plane at the left end of the path's longest
                     straight (see plane_tile()), flying right along it,
                     only while an enemy is on that straight (within the
                     bomb radius of the row); otherwise it waits, or with
                     wait=False skips.
    UpgradePlanes()  the one-time UPG PLANES upgrade.

Every purchase goes through the game's own rules and money (see
balance_sim.Sim): placement through TowerPlacementController, upgrades
through the tower's own upgrade button.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from pygame.math import Vector2

GUN, MISSILE, CANNON, PLANE = 1, 2, 3, 4
TOWER_NAMES = {GUN: "gun", MISSILE: "missile", CANNON: "cannon", PLANE: "plane"}

# Build-tile rings, as distances (in tiles) from the tile centre to the path.
RINGS = {"front": (0.5, 1.6), "back": (1.6, 3.0)}
# Path sample spacing (world px) used to measure how much path a spot covers.
SAMPLE_PX = 8

# Step results.
DONE, WAIT, SKIP = "done", "wait", "skip"


@dataclass(frozen=True)
class Place:
    tower_type: int
    ring: str = "front"


@dataclass(frozen=True)
class Upgrade:
    tower_type: int


@dataclass(frozen=True)
class LaunchPlane:
    wait: bool = True  # False: skipped while no enemy is on the straight


@dataclass(frozen=True)
class UpgradePlanes:
    pass


class Bot:
    """Plays its opener once, then the cycle of the current phase, one
    affordable step at a time."""

    name = ""
    description = ""
    opener: tuple = ()
    # ((from_wave, cycle), ...) in wave order; the first from wave 1.
    phases: tuple = ()

    def __init__(self) -> None:
        self._index = 0  # steps played (or skipped) so far
        self._phase = 0
        self._phase_start = 0  # self._index when the current phase began

    def _next_step(self):
        if self._index < len(self.opener):
            return self.opener[self._index]
        cycle = self.phases[self._phase][1]
        start = max(self._phase_start, len(self.opener))
        return cycle[(self._index - start) % len(cycle)]

    def _enter_phase(self, level: int) -> None:
        phase = self._phase
        while phase + 1 < len(self.phases) and self.phases[phase + 1][0] <= level:
            phase += 1
        if phase != self._phase:
            self._phase, self._phase_start = phase, self._index

    def act(self, sim) -> None:
        """Buys as many steps, in order, as the money allows right now."""
        self._enter_phase(sim.gs.level)
        skipped = 0
        longest = len(self.opener) + max(len(c) for _, c in self.phases)
        while skipped <= longest:  # stop when every step is skipped
            result = sim.apply(self._next_step())
            if result == WAIT:
                return
            self._index += 1
            skipped = skipped + 1 if result == SKIP else 0

    def wave_ended(self, lives_lost: int) -> None:
        """Called after each wave with the lives it cost."""


# Plane builds start flying from this wave: planes cost 600, and the early
# waves pay far too little (under 400 a wave until wave 10) to fund them.
PLANES_FROM_WAVE = 20

# The early waves pay little (wave 1: 24 money in all), and rapid guns are
# the cheapest damage, so every build except gun_spam (all guns anyway) and
# minimal opens with this many guns before its own plan.
OPENING_GUNS = 6
GUN_OPENER = (Place(GUN),) * OPENING_GUNS


class GunSpam(Bot):
    name = "gun_spam"
    description = "rapid guns only, on the best tiles on both sides of the path"
    phases = ((1, (Place(GUN),)),)


GUN_CANNON_CYCLE = (Place(GUN), Place(GUN), Place(CANNON, "back"), Upgrade(CANNON))


class GunCannon(Bot):
    name = "gun_cannon"
    description = (
        "6 rapid guns, then a front line of guns with heavy cannons in the "
        "row behind (2 guns per cannon), cannons upgraded"
    )
    opener = GUN_OPENER
    phases = ((1, GUN_CANNON_CYCLE),)


class Missile(Bot):
    name = "missile"
    description = (
        "6 rapid guns, then homing missiles only, each upgraded to level 3 "
        "before the next"
    )
    opener = GUN_OPENER
    phases = ((1, (Place(MISSILE), Upgrade(MISSILE), Upgrade(MISSILE))),)


class PlaneSpam(Bot):
    name = "plane_spam"
    description = (
        "the gun_cannon build up to wave 19, then from wave 20 only planes: "
        "one along the longest straight whenever affordable while enemies "
        "are on it, UPG PLANES after the 5th"
    )
    opener = GUN_OPENER
    phases = (
        (1, GUN_CANNON_CYCLE),
        (PLANES_FROM_WAVE, (LaunchPlane(),) * 5 + (UpgradePlanes(),)),
    )


MIXED_CYCLE = (
    Place(GUN),
    Place(MISSILE),
    Place(CANNON, "back"),
    Upgrade(MISSILE),
    Upgrade(CANNON),
    Upgrade(MISSILE),
    Place(GUN),
)


class Mixed(Bot):
    name = "mixed"
    description = (
        "6 rapid guns, then all three ground towers with upgrades (gun, "
        "missile, cannon behind, upgrades), plus from wave 20 a plane each "
        "cycle if enemies are on the longest straight"
    )
    opener = GUN_OPENER
    phases = (
        (1, MIXED_CYCLE),
        (PLANES_FROM_WAVE, MIXED_CYCLE + (LaunchPlane(wait=False),)),
    )


class Minimal(Bot):
    """The difficulty floor: it buys rapid guns (the cheapest tower) only
    while its defence has proved too weak -- from a lost life until a
    whole wave passes without one -- and saves otherwise. Towers destroyed
    by tanks are only replaced once that leaks."""

    name = "minimal"
    description = (
        "rapid guns only, bought only after a life is lost and until a wave "
        "passes without a leak"
    )
    phases = ((1, (Place(GUN),)),)

    def __init__(self) -> None:
        super().__init__()
        self._buying = True  # nothing built yet
        self._lives = None

    def act(self, sim) -> None:
        if self._lives is not None and sim.gs.lives < self._lives:
            self._buying = True
        self._lives = sim.gs.lives
        if self._buying:
            super().act(sim)

    def wave_ended(self, lives_lost: int) -> None:
        if lives_lost == 0:
            self._buying = False


STRATEGIES: dict[str, type[Bot]] = {
    bot.name: bot for bot in (GunSpam, GunCannon, Missile, PlaneSpam, Mixed, Minimal)
}


# ── where to build ───────────────────────────────────────────────────────────


def path_samples(waypoints: list[Vector2], spacing: float = SAMPLE_PX) -> list:
    """Points every `spacing` px along the path polyline."""
    points = []
    for a, b in zip(waypoints, waypoints[1:]):
        length = a.distance_to(b)
        steps = max(1, int(length // spacing))
        points.extend(a.lerp(b, i / steps) for i in range(steps))
    points.append(Vector2(waypoints[-1]))
    return points


def rank_tiles(tilemap, tower_config, rng: random.Random) -> dict:
    """{(tower_type, ring): [(row, col), ...]} for the ground towers: the
    build tiles of each ring, best first. Best covers the most path within
    the tower's level-1 range and outside its blind spot; ties are broken
    by `rng` (the run's seed). Ring "any" is every build tile."""
    from gameplay.path_geometry import distance_to_path
    from util.constants import HALF_TILE, TILE_SIZE

    samples = path_samples(tilemap.waypoints)
    tiles = []
    for row, cells in enumerate(tilemap.buildable_grid):
        for col, buildable in enumerate(cells):
            if buildable:
                centre = Vector2(
                    col * TILE_SIZE + HALF_TILE, row * TILE_SIZE + HALF_TILE
                )
                tiles.append((row, col, centre))
    rng.shuffle(tiles)  # the seeded tie-break; sorted() below is stable
    distance = {
        (row, col): distance_to_path(centre, tilemap.waypoints) / TILE_SIZE
        for row, col, centre in tiles
    }
    ranked = {}
    for tower_type in (GUN, MISSILE, CANNON):
        reach = tower_config.ranges[tower_type - 1][0] ** 2
        mins = tower_config.min_ranges
        blind = (mins[tower_type - 1][0] if tower_type <= len(mins) else 0) ** 2
        cover = {}
        for row, col, centre in tiles:
            cover[(row, col)] = sum(
                1 for p in samples if blind < centre.distance_squared_to(p) <= reach
            )
        by_cover = sorted(
            ((row, col) for row, col, _ in tiles if cover[(row, col)] > 0),
            key=lambda rc: -cover[rc],
        )
        for ring, (near, far) in RINGS.items():
            ranked[(tower_type, ring)] = [
                rc for rc in by_cover if near <= distance[rc] < far
            ]
        ranked[(tower_type, "any")] = by_cover
    return ranked


def plane_tile(tilemap) -> tuple[int, int]:
    """Where a plane is placed: the left end of the path's longest
    horizontal straight (consecutive horizontal segments at the same height
    count as one; the first on a tie), so it flies right along the whole
    straight at once."""
    from util.constants import TILE_SIZE

    straights = []  # [y, min x, max x] of each run of horizontal segments
    path = tilemap.waypoints
    for a, b in zip(path, path[1:]):
        if a.y != b.y:
            continue
        if straights and straights[-1][0] == a.y and a.x in straights[-1][1:]:
            run = straights[-1]
            run[1], run[2] = min(run[1], a.x, b.x), max(run[2], a.x, b.x)
        else:
            straights.append([a.y, min(a.x, b.x), max(a.x, b.x)])
    y, left, _ = max(straights, key=lambda run: run[2] - run[1])
    return int(y // TILE_SIZE), int(left // TILE_SIZE)
