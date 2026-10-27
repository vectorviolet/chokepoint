"""Sanity checks against the *real* config/*.yaml -- these catch schema
drift (e.g. a new tower type added without hps, or a wave referencing an
enemy type nothing defines) that a synthetic-fixture test would miss."""

from util.config_loader import (
    load_enemy_stats,
    load_tower_config,
    load_wave_compositions,
)
from gameplay.towers import PLANE_TYPE

TOWER_TYPES = (1, 2, 3, 4)
TANK_ENEMY_TYPES = (5, 6)


def test_tower_config_has_one_entry_per_type_in_type_order():
    cfg = load_tower_config()
    assert len(cfg.prices) == len(TOWER_TYPES)
    assert len(cfg.max_levels) == len(TOWER_TYPES)
    assert len(cfg.ranges) == len(TOWER_TYPES)
    assert len(cfg.damages) == len(TOWER_TYPES)
    assert len(cfg.speeds) == len(TOWER_TYPES)
    assert len(cfg.hps) == len(TOWER_TYPES)


def test_tower_config_per_level_lists_match_max_level():
    cfg = load_tower_config()
    for i, max_level in enumerate(cfg.max_levels):
        assert len(cfg.prices[i]) == max_level
        assert len(cfg.ranges[i]) == max_level
        assert len(cfg.damages[i]) == max_level
        assert len(cfg.speeds[i]) == max_level


def test_tower_prices_strictly_increase_per_level():
    # Upgrade cost should always exceed the tower's current sell value,
    # or upgrading would be free/negative.
    cfg = load_tower_config()
    for prices in cfg.prices:
        assert prices == sorted(prices)
        assert len(set(prices)) == len(prices)


def test_plane_has_no_hp_ground_towers_do():
    cfg = load_tower_config()
    assert cfg.hps[PLANE_TYPE - 1] is None
    for i in range(len(TOWER_TYPES)):
        if i == PLANE_TYPE - 1:
            continue
        assert cfg.hps[i] is not None
        assert len(cfg.hps[i]) == cfg.max_levels[i]


def test_enemy_stats_cover_grunt_through_siege_tank():
    stats = load_enemy_stats()
    assert set(stats.keys()) == {1, 2, 3, 4, 5, 6}
    for enemy_type, s in stats.items():
        assert s.hp > 0
        assert s.speed > 0
        assert s.kill_money > 0
        assert s.damage > 0


def test_only_tank_types_have_combat_stats():
    stats = load_enemy_stats()
    for enemy_type, s in stats.items():
        is_tank = enemy_type in TANK_ENEMY_TYPES
        assert (s.range is not None) == is_tank
        assert (s.fire_interval_ms is not None) == is_tank
        assert (s.bullet_damage is not None) == is_tank


def test_wave_compositions_cover_at_least_the_win_wave():
    waves = load_wave_compositions()
    # WIN_WAVE in src/app/game.py is 25 -- the victory popup fires once this
    # wave clears, so it must exist and be reachable by spawning something.
    assert 25 in waves
    for wave_num, wave_def in waves.items():
        assert wave_num >= 1
        assert wave_def.groups, f"wave {wave_num} spawns nothing"


def test_wave_group_enemy_types_are_all_defined():
    waves = load_wave_compositions()
    enemy_types = set(load_enemy_stats().keys())
    for wave_num, wave_def in waves.items():
        for enemy_type, count in wave_def.groups:
            assert enemy_type in enemy_types, (
                f"wave {wave_num} spawns undefined enemy type {enemy_type}"
            )
            assert count > 0
