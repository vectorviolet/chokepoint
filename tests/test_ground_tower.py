import pytest
from pygame.math import Vector2

from gameplay.combat.projectile import MuzzleFlash, Projectile
from gameplay.towers import TowerFactory
from gameplay.towers.ground_tower import BARREL_FORWARD, BARREL_SPREAD

MAP_WIDTH = 3008


class FakeEnemy:
    def __init__(self, position):
        self.position = Vector2(position)


class FakeAudio:
    def __init__(self):
        self.played = []

    def play_sfx(self, path) -> None:
        self.played.append(path)


def make_tower(tower_config, assets, tower_type=1, row=0, col=0, audio=None):
    return TowerFactory.create(
        tower_type, row, col, tower_config, assets, audio or FakeAudio(), MAP_WIDTH
    )


# ── work() targeting ─────────────────────────────────────────────────────────


def test_work_does_nothing_when_not_started(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(10, 0))

    tower.work([enemy], is_started=False)

    assert tower.is_rotated is False
    assert tower.bullets == []


def test_work_does_nothing_with_no_enemies(tower_config, assets):
    tower = make_tower(tower_config, assets)

    tower.work([], is_started=True)

    assert tower.bullets == []


def test_work_ignores_enemies_out_of_range(tower_config, assets):
    tower = make_tower(tower_config, assets)
    far_enemy = FakeEnemy(tower.position + Vector2(tower.range + 500, 0))

    tower.work([far_enemy], is_started=True)

    assert tower.is_rotated is False
    assert tower.bullets == []


def test_work_rotates_toward_the_nearest_in_range_enemy(tower_config, assets):
    tower = make_tower(tower_config, assets)
    near = FakeEnemy(tower.position + Vector2(20, 0))
    far = FakeEnemy(tower.position + Vector2(tower.range - 5, 0))

    tower.work([far, near], is_started=True)

    assert tower.is_rotated is True


def test_work_shoots_once_the_cooldown_has_elapsed(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2)  # Projectile branch
    enemy = FakeEnemy(tower.position + Vector2(20, 0))
    tower.now = tower.speed + 1

    tower.work([enemy], is_started=True)

    assert len(tower.bullets) == 1
    assert isinstance(tower.bullets[0], Projectile)
    assert tower.last_reload_time == tower.speed + 1


def test_work_does_not_shoot_before_the_cooldown_elapses(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2)
    enemy = FakeEnemy(tower.position + Vector2(20, 0))
    tower.now = tower.speed  # not yet > speed

    tower.work([enemy], is_started=True)

    assert tower.bullets == []


# ── _shoot() branches ────────────────────────────────────────────────────────


def test_shoot_type1_fires_twin_muzzle_flashes_and_plays_its_shoot_sound(
    tower_config, assets
):
    audio = FakeAudio()
    tower = make_tower(tower_config, assets, tower_type=1, audio=audio)
    target = FakeEnemy(tower.position + Vector2(0, -100))

    tower._shoot(target)

    assert len(tower.bullets) == 2
    assert all(isinstance(b, MuzzleFlash) for b in tower.bullets)
    assert len(audio.played) == 1


def test_shoot_type3_level1_fires_a_single_muzzle_flash(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=3)
    target = FakeEnemy(tower.position + Vector2(0, -100))

    tower._shoot(target)

    assert len(tower.bullets) == 1
    assert isinstance(tower.bullets[0], MuzzleFlash)


def test_shoot_type3_level2_fires_twin_muzzle_flashes(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=3)
    tower.level = 2
    target = FakeEnemy(tower.position + Vector2(0, -100))

    tower._shoot(target)

    assert len(tower.bullets) == 2


def test_shoot_type2_fires_a_homing_projectile_instead_of_a_muzzle_flash(
    tower_config, assets
):
    tower = make_tower(tower_config, assets, tower_type=2)
    target = FakeEnemy(tower.position + Vector2(0, -100))

    tower._shoot(target)

    assert len(tower.bullets) == 1
    assert isinstance(tower.bullets[0], Projectile)


def test_shoot_with_no_shoot_sound_configured_plays_nothing(tower_config, assets):
    audio = FakeAudio()
    tower = make_tower(tower_config, assets, tower_type=1, audio=audio)
    target = FakeEnemy(tower.position + Vector2(0, -100))

    # tower_config is a session-scoped fixture shared with other tests --
    # mutate then restore this one entry rather than leaving it corrupted.
    original = tower_config.shoot_sounds[0]
    tower_config.shoot_sounds[0] = None
    try:
        tower._shoot(target)
    finally:
        tower_config.shoot_sounds[0] = original

    assert audio.played == []


# ── _muzzle_positions() geometry ─────────────────────────────────────────────


def test_muzzle_positions_are_offset_forward_and_split_laterally(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=1)
    target = FakeEnemy(tower.position + Vector2(100, 0))  # straight along +x

    (p1, deals1), (p2, deals2) = tower._muzzle_positions(target)

    assert p1.x == pytest.approx(tower.position.x + BARREL_FORWARD)
    assert p2.x == pytest.approx(tower.position.x + BARREL_FORWARD)
    assert p1.y == pytest.approx(tower.position.y + BARREL_SPREAD)
    assert p2.y == pytest.approx(tower.position.y - BARREL_SPREAD)
    assert deals1 is True
    assert deals2 is False


def test_muzzle_positions_single_barrel_for_a_non_twin_tower(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=3)  # level 1 -- not twin
    target = FakeEnemy(tower.position + Vector2(100, 0))

    positions = tower._muzzle_positions(target)

    assert len(positions) == 1
    (pos, deals) = positions[0]
    assert pos.x == pytest.approx(tower.position.x + BARREL_FORWARD)
    assert pos.y == pytest.approx(tower.position.y)
    assert deals is True
