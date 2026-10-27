"""Grid targeting (gameplay.combat.targeting, issue #40) picks exactly what
the old full scans picked: the same enemy for ground towers and the same
tower for tanks, ties included.

The old algorithms are kept below as reference implementations, copied
from GroundTower.work and Tank._nearest_tower before the grid, and every
test compares the two on seeded random layouts.
"""

import random

import pytest
from pygame.math import Vector2

from gameplay.combat import targeting
from gameplay.combat.tank import Tank
from gameplay.combat.targeting import CELL_SIZE, EnemyGrid, TowerGrid
from gameplay.towers.ground_tower import GroundTower

RANGES = (160, 192, 224, 256, 288)  # every ground tower range in towers.yaml


# ── reference implementations (the pre-grid code) ─────────────────────────────


def reference_enemy(enemies, position, radius, min_radius=0):
    """GroundTower.work's old choice: the index of the enemy it aimed at,
    or None. With a `min_radius` (the heavy cannon's blind spot, #11),
    enemies at that distance or closer are left out of the same scan first;
    with the default 0 this is the old code unchanged."""
    if min_radius > 0:
        visible = [
            i
            for i, enemy in enumerate(enemies)
            if (enemy.position - position).length() > min_radius
        ]
        index = reference_enemy([enemies[i] for i in visible], position, radius)
        return None if index is None else visible[index]
    if not enemies:
        return None
    distances = [enemy.position - position for enemy in enemies]
    lengths = [d.length() for d in distances]
    nearest_dist = min(lengths)
    nearest_idx = lengths.index(nearest_dist)
    if nearest_dist > radius:
        return None
    return nearest_idx


def reference_tower(towers, position):
    """Tank._nearest_tower's old result: (tower, squared distance)."""
    candidates = [t for t in towers if t.maxHP is not None]
    if not candidates:
        return (None, 0)
    best = None
    best_dist = float("inf")
    for t in candidates:
        d = (t.position - position).length_squared()
        if d < best_dist:
            best, best_dist = t, d
    return (best, best_dist)


# ── layouts ──────────────────────────────────────────────────────────────────


class Thing:
    """An enemy or tower: only what targeting reads."""

    def __init__(self, position, maxHP=100):
        self.position = Vector2(position)
        self.maxHP = maxHP


def random_point(rng):
    """Mostly anywhere on (and a bit off) the map, sometimes on whole
    pixels, cell borders or tile centres, where exact ties happen."""
    kind = rng.random()
    if kind < 0.4:
        return (rng.uniform(-200, 3200), rng.uniform(-200, 2400))
    if kind < 0.6:
        return (rng.randint(-50, 3050), rng.randint(-50, 2200))
    if kind < 0.8:
        return (
            rng.randint(-1, 24) * CELL_SIZE + rng.choice((0, -1e-9, 1e-9)),
            rng.randint(-1, 17) * CELL_SIZE + rng.choice((0, -1e-9, 1e-9)),
        )
    return (rng.randint(0, 46) * 64 + 32, rng.randint(0, 33) * 64 + 32)


def mirrored(rng, centre, radius):
    """Points at the same distance from `centre` (exact ties), some right
    on the range boundary, some a hair inside or outside it."""
    r = rng.choice((radius, radius - 1e-9, radius + 1e-9, rng.uniform(0, radius)))
    dx, dy = (r, 0) if rng.random() < 0.5 else (r * 0.6, r * 0.8)
    signs = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
    rng.shuffle(signs)
    return [(centre.x + sx * dx, centre.y + sy * dy) for sx, sy in signs]


def random_layout(rng, centre, radius, count):
    points = [random_point(rng) for _ in range(count)]
    for _ in range(rng.randint(0, 3)):
        points += mirrored(rng, centre, radius)
    if points and rng.random() < 0.3:  # duplicates of one position
        points += [rng.choice(points)] * rng.randint(1, 3)
    rng.shuffle(points)
    return points


def random_centre(rng):
    return Vector2(random_point(rng))


# ── enemies, for ground towers ────────────────────────────────────────────────


@pytest.mark.parametrize("seed", range(40))
def test_enemy_choice_matches_the_full_scan(seed):
    rng = random.Random(seed)
    enemies = []
    grid = EnemyGrid(enemies)
    for _ in range(60):
        centre = random_centre(rng)
        radius = rng.choice(RANGES)
        enemies[:] = [
            Thing(p) for p in random_layout(rng, centre, radius, rng.randint(0, 400))
        ]
        grid = EnemyGrid(enemies)  # a new tick: positions changed

        expected = reference_enemy(enemies, centre, radius)
        enemy, delta = grid.nearest_in_range(centre, radius)

        if expected is None:
            assert enemy is None and delta is None
        else:
            assert enemy is enemies[expected]
            assert delta == enemies[expected].position - centre


@pytest.mark.parametrize("seed", range(20))
def test_one_grid_per_tick_follows_kills(seed):
    """Towers share a tick's grid while kills remove enemies from the list
    between them: each tower still picks what the full scan would."""
    rng = random.Random(1000 + seed)
    centre = Vector2(1500, 1000)
    enemies = [
        Thing(p) for p in random_layout(rng, centre, 256, 300)
    ]  # enemies spread around a crowded spot
    enemies += [
        Thing((centre.x + rng.uniform(-300, 300), centre.y + rng.uniform(-300, 300)))
        for _ in range(150)
    ]
    grid = EnemyGrid(enemies)
    for _ in range(80):
        position = centre + Vector2(rng.uniform(-400, 400), rng.uniform(-400, 400))
        radius = rng.choice(RANGES)
        expected = reference_enemy(enemies, position, radius)
        enemy, _ = grid.nearest_in_range(position, radius)
        assert enemy is (None if expected is None else enemies[expected])
        for _ in range(rng.randint(0, 3)):  # this tower's shots kill some
            if enemies:
                enemies.remove(rng.choice(enemies))


def test_equal_distances_pick_the_first_enemy_in_the_list():
    centre = Vector2(640, 640)
    enemies = [Thing(centre + offset) for offset in ((0, 100), (100, 0), (0, -100))]

    enemy, _ = EnemyGrid(enemies).nearest_in_range(centre, 160)

    assert enemy is enemies[0]


def test_an_enemy_exactly_at_range_is_in_range():
    centre = Vector2(640, 640)
    enemies = [Thing(centre + Vector2(160, 0))]

    enemy, delta = EnemyGrid(enemies).nearest_in_range(centre, 160)

    assert enemy is enemies[0]
    assert delta == Vector2(160, 0)


def test_the_nearest_enemy_out_of_range_means_no_target():
    centre = Vector2(640, 640)
    enemies = [Thing(centre + Vector2(161, 0))]

    assert EnemyGrid(enemies).nearest_in_range(centre, 160) == (None, None)


# ── the heavy cannon's blind spot (issue #11) ────────────────────────────────

MIN_RANGE = 96  # the heavy cannon's, in towers.yaml


@pytest.mark.parametrize("seed", range(40))
def test_enemy_choice_with_a_blind_spot_matches_the_full_scan(seed):
    rng = random.Random(5000 + seed)
    for _ in range(60):
        centre = random_centre(rng)
        radius = rng.choice((256, 288))
        min_radius = rng.choice((MIN_RANGE, rng.uniform(1, radius - 1)))
        points = random_layout(rng, centre, radius, rng.randint(0, 400))
        for _ in range(rng.randint(0, 3)):  # ties on the blind spot's edge
            points += mirrored(rng, centre, min_radius)
        rng.shuffle(points)
        enemies = [Thing(p) for p in points]

        expected = reference_enemy(enemies, centre, radius, min_radius)
        enemy, delta = EnemyGrid(enemies).nearest_in_range(centre, radius, min_radius)

        if expected is None:
            assert enemy is None and delta is None
        else:
            assert enemy is enemies[expected]
            assert delta == enemies[expected].position - centre


@pytest.mark.parametrize(
    ("distance", "targetable"),
    [
        (MIN_RANGE - 1, False),  # just inside the blind spot
        (MIN_RANGE - 1e-9, False),
        (MIN_RANGE, False),  # on its edge: still blind (exclusive)
        (MIN_RANGE + 1e-9, True),
        (MIN_RANGE + 1, True),  # just outside it
        (256, True),  # the outer edge stays inclusive
        (256 + 1e-9, False),
    ],
)
def test_the_blind_spot_edges(distance, targetable):
    centre = Vector2(640, 640)
    enemies = [Thing(centre + Vector2(distance, 0))]

    enemy, _ = EnemyGrid(enemies).nearest_in_range(centre, 256, MIN_RANGE)

    assert (enemy is enemies[0]) is targetable


def test_the_nearest_enemy_outside_the_blind_spot_is_picked():
    centre = Vector2(640, 640)
    enemies = [
        Thing(centre + Vector2(0, 50)),  # nearest, but in the blind spot
        Thing(centre + Vector2(200, 0)),
        Thing(centre + Vector2(0, -120)),
    ]

    enemy, delta = EnemyGrid(enemies).nearest_in_range(centre, 256, MIN_RANGE)

    assert enemy is enemies[2]
    assert delta == Vector2(0, -120)


def test_only_enemies_in_the_blind_spot_means_no_target():
    centre = Vector2(640, 640)
    enemies = [Thing(centre), Thing(centre + Vector2(MIN_RANGE, 0))]

    assert EnemyGrid(enemies).nearest_in_range(centre, 256, MIN_RANGE) == (
        None,
        None,
    )


def test_no_blind_spot_still_targets_an_enemy_on_the_tower():
    centre = Vector2(640, 640)
    enemies = [Thing(centre)]

    enemy, _ = EnemyGrid(enemies).nearest_in_range(centre, 160)

    assert enemy is enemies[0]


# ── towers, for tanks ─────────────────────────────────────────────────────────


def random_towers(rng, centre):
    towers = []
    for p in random_layout(rng, centre, rng.choice(RANGES), rng.randint(0, 120)):
        towers.append(Thing(p, maxHP=None if rng.random() < 0.1 else 100))
    return towers


@pytest.mark.parametrize("seed", range(40))
def test_tower_choice_matches_the_full_scan(seed):
    rng = random.Random(2000 + seed)
    for _ in range(60):
        centre = random_centre(rng)
        towers = random_towers(rng, centre)

        expected = reference_tower(towers, centre)
        result = TowerGrid(towers).nearest(centre)

        assert result[0] is expected[0]
        assert result[1] == expected[1]


def test_the_tower_grid_follows_its_list():
    near, far = Thing((100, 100)), Thing((2000, 1500))
    towers = [near, far]
    grid = TowerGrid(towers)
    assert grid.nearest(Vector2(0, 0))[0] is near

    towers.remove(near)

    assert grid.nearest(Vector2(0, 0))[0] is far


def test_planes_alone_are_no_target():
    towers = [Thing((100, 100), maxHP=None)]

    assert TowerGrid(towers).nearest(Vector2(0, 0)) == (None, 0)


# ── the whole battle ──────────────────────────────────────────────────────────


def _reference_work(self, enemies, is_started, enemy_grid=None):
    if not is_started or not enemies:
        return
    index = reference_enemy(enemies, self.position, self.range, self.min_range)
    if index is None:
        return
    self.rotate_to_delta(enemies[index].position - self.position)
    if self._is_attack_ready():
        self._shoot(enemies[index])


def _reference_nearest_tower(self, ctx):
    return reference_tower(ctx.towers, self.position)


def _target_id(bullet):
    """Enemies by id, towers by tile: the same in both runs."""
    enemy = getattr(bullet, "target", None)
    if enemy is not None:
        return ("enemy", enemy.id)
    tower = getattr(bullet, "target_tower", None)
    if tower is not None:
        return ("tower", tower.row, tower.col)
    return None


def _snapshot(demo):
    """Everything targeting decides: who each tower and tank aims at (their
    sprite's rotated size, the tank's muzzle angle) and shoots at (their
    bullets' targets), and what came of it (HP, kills, positions)."""
    return (
        demo.game_state.level,
        [
            (
                e.id,
                e.hp,
                tuple(e.position),
                getattr(e, "_muzzle_angle", None),
                [_target_id(b) for b in getattr(e, "bullets", ())],
            )
            for e in demo.enemies
        ],
        [
            (
                t.tower_type,
                t.row,
                t.col,
                t.hp,
                t.kills,
                tuple(t.rect),
                [_target_id(b) for b in t.bullets],
            )
            for t in demo.towers
        ],
    )


def _run_demo(tilemap, assets, tower_config, seed, ticks):
    from gameplay.menu_demo import MenuDemo

    random.seed(seed)  # in case anything in a run draws from the global rng
    demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(seed))
    snapshots = []
    for tick in range(ticks):
        if tick % 60 == 0:  # the demo's waves have no tanks: send some in
            enemy_type = 5 + (tick // 60) % 2
            demo.enemies.append(
                Tank(10_000 + tick, enemy_type, 10, tilemap.waypoints, assets)
            )
        demo._tick()
        snapshots.append(_snapshot(demo))
    return snapshots


@pytest.mark.parametrize("seed", (3, 7))
def test_a_whole_battle_plays_out_exactly_as_before(
    seed, assets, tower_config, monkeypatch
):
    """The menu demo's battle (towers of every type, tanks, planes, kills)
    run tick by tick, once with the grid and once with the old scans: every
    enemy's HP and position and every tower's HP, kills, shots and aim are
    the same on every tick."""
    from gameplay.tilemap import Tilemap

    tilemap = Tilemap("assets/maps/tiled_tilemap.tmx")
    with_grid = _run_demo(tilemap, assets, tower_config, seed, 1500)

    monkeypatch.setattr(GroundTower, "work", _reference_work)
    monkeypatch.setattr(Tank, "_nearest_tower", _reference_nearest_tower)
    monkeypatch.setattr(targeting.EnemyGrid, "nearest_in_range", None)
    monkeypatch.setattr(targeting.TowerGrid, "nearest", None)
    before = _run_demo(tilemap, assets, tower_config, seed, 1500)

    # The battle did exercise both: towers and tanks shot at something.
    assert any(t[6] for s in before for t in s[2])
    assert any(e[4] for s in before for e in s[1])
    assert with_grid == before
