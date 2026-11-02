"""Smooth turret turning (issue #83): the drawn barrel eases toward its
target at TURN_RATE_DEG_PER_S of game time, while aim, firing and damage
stay exactly as before (the turn is cosmetic)."""

import pytest
from pygame.math import Vector2

from domain.game_state import GameState
from gameplay.combat.projectile import MuzzleFlash
from gameplay import rotatable_object
from gameplay.rotatable_object import (
    cached_rotation,
    quantise_angle,
    turn_toward,
    wrap_angle,
)
from gameplay.towers import TowerFactory
from gameplay.towers.ground_tower import BARREL_FORWARD, TURN_RATE_DEG_PER_S
from util.constants import TICK_MS

MAP_WIDTH = 3008


class FakeEnemy:
    _next_id = 0

    def __init__(self, position, hp=10**9):
        FakeEnemy._next_id += 1
        self.id = FakeEnemy._next_id
        self.position = Vector2(position)
        self.hp = hp
        self.hits: list[int] = []

    def decrease_hp(self, damage, ctx=None, source=None) -> None:
        self.hp -= damage
        self.hits.append(damage)


class FakeAudio:
    def play_sfx(self, path) -> None:
        pass


class FakeCtx:
    def __init__(self, enemies):
        self.enemies = enemies
        self.time_ms = 0.0


def make_tower(tower_config, assets, tower_type=1):
    return TowerFactory.create(
        tower_type, 5, 5, tower_config, assets, FakeAudio(), MAP_WIDTH
    )


def make_state(speed=1) -> GameState:
    gs = GameState(start_money=0, start_lives=10)
    gs.is_started = True
    gs.speed = speed
    return gs


def tick(tower, gs, enemies) -> None:
    """One fixed tick, as BattleSimulation runs it."""
    if gs.is_started:
        gs.time_ms += TICK_MS * gs.speed
    tower.update(gs, enemies)


# ── turn_toward() ────────────────────────────────────────────────────────────


def test_turn_toward_steps_by_at_most_the_max_step():
    assert turn_toward(0, 90, 10) == pytest.approx(10)
    assert turn_toward(0, -90, 10) == pytest.approx(-10)


def test_turn_toward_lands_on_the_target_once_within_reach():
    assert turn_toward(85, 90, 10) == pytest.approx(90)
    assert turn_toward(90, 90, 0) == pytest.approx(90)


def test_turn_toward_goes_the_short_way_across_the_seam():
    # 170 -> -170 is 20 degrees through 180, not 340 back through 0.
    assert turn_toward(170, -170, 5) == pytest.approx(175)
    assert turn_toward(175, -170, 10) == pytest.approx(-175)
    assert turn_toward(-170, 170, 5) == pytest.approx(-175)


def test_turn_toward_stays_wrapped():
    for current, target in ((179, -179), (-179, 179), (0, 180), (350, 10)):
        assert -180 <= turn_toward(current, target, 1) < 180


def test_turn_toward_hand_computed_values():
    # Worked by hand: the signed shortest difference, then one capped step.
    assert turn_toward(-170, 170, 30) == pytest.approx(170)  # 20 apart: lands
    assert turn_toward(-170, 170, 15) == pytest.approx(175)  # -185 wraps to 175
    assert turn_toward(10, -10, 4) == pytest.approx(6)  # down through 0
    # Exactly opposite: the difference wraps to -180, so it turns negative.
    assert turn_toward(-90, 90, 45) == pytest.approx(-135)
    assert turn_toward(135, -135, 100) == pytest.approx(-135)  # 90 apart: lands
    assert turn_toward(0, 0, 0) == pytest.approx(0)


def test_wrap_angle_hand_computed_values():
    assert wrap_angle(190) == pytest.approx(-170)
    assert wrap_angle(-190) == pytest.approx(170)
    assert wrap_angle(180) == pytest.approx(-180)
    assert wrap_angle(540) == pytest.approx(-180)
    assert wrap_angle(-180) == pytest.approx(-180)
    assert wrap_angle(359) == pytest.approx(-1)


def test_quantise_angle_hand_computed_values():
    # 2 degree steps, halves rounding up, wrapped to [-180, 180).
    assert quantise_angle(0.0) == 0
    assert quantise_angle(0.9) == 0
    assert quantise_angle(1.0) == 2
    assert quantise_angle(3.0) == 4
    assert quantise_angle(5.0) == 6
    assert quantise_angle(6.4) == 6
    assert quantise_angle(-0.9) == 0
    assert quantise_angle(-1.1) == -2
    assert quantise_angle(-3.0) == -2
    assert quantise_angle(179.0) == -180
    assert quantise_angle(-179.2) == -180
    assert quantise_angle(270.0) == -90


# ── the barrel in the game loop ──────────────────────────────────────────────


def test_barrel_turns_at_the_turn_rate_per_second_of_game_time(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(0, 50))  # straight down: 90
    gs = make_state()
    tick(tower, gs, [enemy])
    start = tower.barrel_angle
    assert 0 < start < 90  # one tick of turning

    ticks = 10
    for _ in range(ticks):
        tick(tower, gs, [enemy])

    expected = TURN_RATE_DEG_PER_S * ticks * TICK_MS / 1000
    assert tower.barrel_angle - start == pytest.approx(expected)


def test_barrel_reaches_the_target_and_holds(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(0, 50))
    gs = make_state()
    for _ in range(200):
        tick(tower, gs, [enemy])
    assert tower.barrel_angle == pytest.approx(90)


def test_pause_freezes_the_barrel(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(0, 50))
    gs = make_state()
    tick(tower, gs, [enemy])
    frozen = tower.barrel_angle

    gs.is_started = False
    for _ in range(50):
        tick(tower, gs, [enemy])

    assert tower.barrel_angle == frozen


def test_speed_x4_turns_four_times_as_far_per_tick(tower_config, assets):
    turned = {}
    for speed in (1, 4):
        tower = make_tower(tower_config, assets)
        enemy = FakeEnemy(tower.position + Vector2(0, -50))  # up: -90
        gs = make_state(speed)
        tick(tower, gs, [enemy])
        turned[speed] = abs(tower.barrel_angle)
    assert turned[4] == pytest.approx(4 * turned[1])


def test_barrel_takes_the_short_way_across_the_seam(tower_config, assets):
    tower = make_tower(tower_config, assets)
    tower.barrel_angle = 170.0
    enemy = FakeEnemy(tower.position + Vector2(-50, -9))  # about -170
    gs = make_state()
    for _ in range(3):
        tick(tower, gs, [enemy])
        # Through 180, never back down through 0.
        assert abs(tower.barrel_angle) > 165


def test_barrel_keeps_turning_to_the_last_aim_without_a_target(tower_config, assets):
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(0, 50))
    gs = make_state()
    tick(tower, gs, [enemy])
    for _ in range(200):
        tick(tower, gs, [])  # it died: nothing in range
    assert tower.barrel_angle == pytest.approx(90)


def test_a_tower_that_never_aimed_keeps_its_sprite(tower_config, assets):
    tower = make_tower(tower_config, assets)
    gs = make_state()
    for _ in range(5):
        tick(tower, gs, [])
    assert tower.is_rotated is False


def test_the_drawn_sprite_keeps_its_centre(tower_config, assets):
    tower = make_tower(tower_config, assets)
    for angle in range(-180, 180, 7):
        tower.rotate_to_angle_cached(angle)
        assert tower.rect.center == (int(tower.position.x), int(tower.position.y))
        assert tower.rect.size == tower.image.get_size()


def test_rotated_images_are_cached(tower_config, assets):
    tower = make_tower(tower_config, assets)
    tower.rotate_to_angle_cached(32)
    first = tower.image
    tower.rotate_to_angle_cached(32.4)  # same step
    assert tower.image is first
    source = tower.images[None]
    assert cached_rotation(source, 10) is cached_rotation(source, 10)


def test_an_unchanged_step_is_not_redrawn(tower_config, assets, monkeypatch):
    tower = make_tower(tower_config, assets)
    tower.rotate_to_angle_cached(40)
    calls = []
    monkeypatch.setattr(
        rotatable_object,
        "cached_rotation",
        lambda source, rotation: calls.append(rotation) or source,
    )
    tower.rotate_to_angle_cached(40.3)  # same step: nothing to do
    assert calls == []
    tower.rotate_to_angle_cached(44)  # next step
    assert calls == [-44]


def test_the_rotation_cache_is_bounded(monkeypatch):
    import pygame

    monkeypatch.setattr(rotatable_object, "MAX_CACHED_ROTATIONS", 5)
    monkeypatch.setattr(
        rotatable_object, "_rotation_cache", type(rotatable_object._rotation_cache)()
    )
    source = pygame.Surface((8, 8), pygame.SRCALPHA)
    others = [pygame.Surface((8, 8), pygame.SRCALPHA) for _ in range(20)]
    kept = cached_rotation(source, 0)
    for i, other in enumerate(others):
        cached_rotation(other, 2 * i)
        cached_rotation(source, 0)  # used every time: stays cached
    assert len(rotatable_object._rotation_cache) == 5
    assert cached_rotation(source, 0) is kept
    assert (others[0], 0) not in rotatable_object._rotation_cache


def test_a_tower_built_mid_run_turns_rather_than_snaps(tower_config, assets):
    """A new tower's clock starts at 0; its first update must not count the
    whole run so far as turning time."""
    tower = make_tower(tower_config, assets)
    enemy = FakeEnemy(tower.position + Vector2(0, 50))  # 90 degrees away
    gs = make_state()
    gs.time_ms = 400_000.0
    tick(tower, gs, [enemy])
    one_tick = TURN_RATE_DEG_PER_S * TICK_MS / 1000
    assert tower.barrel_angle == pytest.approx(one_tick)


def test_upgrade_keeps_the_barrel_angle(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2)
    enemy = FakeEnemy(tower.position + Vector2(0, 50))
    gs = make_state()
    for _ in range(200):
        tick(tower, gs, [enemy])
    tower.level = 2
    tower.load(assets.image_path("tower_2_lvl2"))  # as upgrade() does
    assert tower.is_rotated is False
    tick(tower, gs, [enemy])
    assert tower.is_rotated is True
    assert tower.barrel_angle == pytest.approx(90)


# ── muzzle flashes and damage ────────────────────────────────────────────────


def test_muzzle_flash_sits_at_the_drawn_barrel_tip(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=3)  # single barrel
    tower.barrel_angle = 0.0
    target = FakeEnemy(tower.position + Vector2(0, 100))  # below, not along +x
    tower._shoot(target)
    flash = tower.bullets[0]
    assert flash.position.x == pytest.approx(tower.position.x + BARREL_FORWARD)
    assert flash.position.y == pytest.approx(tower.position.y)
    assert flash.target is target


def test_firing_does_not_wait_for_the_barrel(tower_config, assets):
    """The shot and damage sequence is the same whichever way the barrel is
    drawn: a tower facing away fires on the same ticks, at the same
    targets, for the same damage as one already facing its target."""
    records = []
    for start in (90.0, -90.0, 180.0):
        tower = make_tower(tower_config, assets, tower_type=1)
        tower.barrel_angle = start
        a = FakeEnemy(tower.position + Vector2(0, 60))
        b = FakeEnemy(tower.position + Vector2(-80, 0))
        gs = make_state()
        ctx = FakeCtx([a, b])
        shots = []
        for n in range(600):
            if n == 300:
                a.position = tower.position + Vector2(0, 150)  # b is now nearest
            tick(tower, gs, [a, b])
            ctx.time_ms = gs.time_ms
            for flash in list(tower.bullets):
                if isinstance(flash, MuzzleFlash) and not flash._damage_dealt:
                    shots.append((n, flash.target is a))
                flash.update(ctx)
        records.append((shots, a.hits, b.hits))
    assert records[0][0], "the tower fired"
    assert {target for _, target in records[0][0]} == {True, False}
    assert records[0] == records[1] == records[2]
