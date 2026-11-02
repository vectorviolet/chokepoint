import pytest
from pygame.math import Vector2

from gameplay.combat.enemy import Enemy

WAYPOINTS = [Vector2(0, 0), Vector2(100, 0), Vector2(100, 100)]


def test_spawns_at_first_waypoint_facing_the_second(assets):
    e = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    assert e.position == WAYPOINTS[0]
    assert e.waypoint_index == 1
    assert not e.reached_end()


def test_requires_at_least_one_waypoint(assets):
    with pytest.raises(ValueError):
        Enemy(1, 1, level=1, waypoints=[], assets=assets)


@pytest.mark.parametrize("level,expected_scale", [(1, 1.0), (2, 1.25), (5, 2.0)])
def test_stats_scale_25_percent_per_level(assets, level, expected_scale):
    base = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    scaled = Enemy(1, 1, level=level, waypoints=WAYPOINTS, assets=assets)

    assert scaled.maxHP == int(base.maxHP * expected_scale)
    assert scaled.hp == scaled.maxHP
    assert scaled.killMoney == max(1, int(base.killMoney * expected_scale))
    # Damage and speed are flat stats, not scaled by wave level.
    assert scaled.damage == base.damage
    assert scaled.mov_speed == base.mov_speed


def test_move_advances_toward_next_waypoint_without_overshooting_first(assets):
    e = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    step = e.mov_speed
    e.move(game_speed=1)

    assert e.waypoint_index == 1  # hasn't reached (100, 0) yet
    assert e.position.x == pytest.approx(step)
    assert e.position.y == pytest.approx(0)


def test_move_snaps_to_waypoint_and_advances_index_when_close_enough(assets):
    # A waypoint 0.1px away is closer than any real mov_speed's single-frame
    # step, so one move() should land exactly on it and roll to the next.
    close_waypoints = [Vector2(0, 0), Vector2(0.1, 0), Vector2(100, 100)]
    e = Enemy(1, 1, level=1, waypoints=close_waypoints, assets=assets)

    e.move(game_speed=1)

    assert e.position == close_waypoints[1]
    assert e.waypoint_index == 2


def test_move_does_nothing_once_reached_end(assets):
    e = Enemy(1, 1, level=1, waypoints=[Vector2(0, 0), Vector2(10, 0)], assets=assets)
    e.move(game_speed=100)  # first move should reach/overshoot the only waypoint
    assert e.reached_end()
    pos_before = Vector2(e.position)

    e.move(game_speed=100)

    assert e.position == pos_before


def test_decrease_hp_removes_and_pays_out_on_death(assets, ctx):
    e = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    ctx.enemies.append(e)

    e.decrease_hp(e.maxHP - 1, ctx)
    assert e in ctx.enemies
    assert ctx.money_earned == 0

    e.decrease_hp(1, ctx)
    assert e not in ctx.enemies
    assert ctx.money_earned == e.killMoney


def test_decrease_hp_on_already_dead_enemy_is_a_no_op(assets, ctx):
    e = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    # Not added to ctx.enemies -- simulates a stale reference (e.g. two
    # simultaneous hits resolving in the same frame).
    e.decrease_hp(e.maxHP, ctx)
    assert ctx.money_earned == 0


def test_decrease_hp_credits_the_source_with_the_hp_taken_not_overkill(
    assets, ctx, tower_config
):
    from gameplay.towers import TowerFactory

    tower = TowerFactory.create(1, 0, 0, tower_config, assets, None, 3008)
    e = Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    ctx.enemies.append(e)

    e.decrease_hp(5, ctx, tower)
    assert tower.damage_dealt == 5
    e.decrease_hp(e.maxHP, ctx, tower)  # the killing blow: only what was left
    assert tower.damage_dealt == e.maxHP
    assert (tower.kills, tower.money_earned) == (1, e.killMoney)

    e.decrease_hp(10, ctx, tower)  # already dead: nothing more
    assert tower.damage_dealt == e.maxHP


def test_damage_counter_changes_nothing_else(assets, ctx, tower_config):
    """The counter is statistics only: HP, kills and money come out the same
    with or without a source."""
    from gameplay.towers import TowerFactory

    tower = TowerFactory.create(2, 0, 0, tower_config, assets, None, 3008)
    with_source = Enemy(1, 3, level=4, waypoints=WAYPOINTS, assets=assets)
    without = Enemy(2, 3, level=4, waypoints=WAYPOINTS, assets=assets)
    ctx.enemies.extend([with_source, without])
    for damage in (17, 40, 3):
        with_source.decrease_hp(damage, ctx, tower)
        without.decrease_hp(damage, ctx)
    assert with_source.hp == without.hp
    assert tower.damage_dealt == 60
