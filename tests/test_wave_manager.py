import pytest
from pygame.math import Vector2

from domain.game_state import GameState
from gameplay.combat.enemy import Enemy
from gameplay.combat.tank import Tank
from gameplay.combat.wave_manager import WAVE_COMPOSITIONS, WaveManager

WAYPOINTS = [Vector2(0, 0), Vector2(500, 0)]


def make_started_state(level=1) -> GameState:
    gs = GameState(start_money=200, start_lives=10)
    gs.is_started = True
    gs.level = level
    return gs


def drain_queue(
    wm: WaveManager, enemies: list, gs: GameState, start_t: float = 0
) -> float:
    """Advances game time until every queued enemy for the current wave has
    spawned. Returns the game time at which the last one spawned."""
    t = start_t
    for _ in range(len(wm._spawn_queue)):
        t += wm._spawn_interval_ms
        gs.time_ms = t
        wm.update(enemies, gs)
    return t


def test_requires_nonempty_waypoints(assets):
    with pytest.raises(ValueError):
        WaveManager([], assets)


def test_does_nothing_when_not_started(assets):
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state()
    gs.is_started = False
    enemies = []

    wm.update(enemies, gs)

    assert enemies == []
    assert wm._spawn_queue == []


def test_builds_spawn_queue_matching_wave_composition_on_level_start(assets):
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=1)

    wm.update([], gs)

    expected = [t for t, count in WAVE_COMPOSITIONS[1].groups for _ in range(count)]
    assert wm._spawn_queue == expected


def test_spawns_nothing_before_the_interval_elapses(assets):
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=1)
    enemies = []

    gs.time_ms = 0
    wm.update(enemies, gs)  # builds the queue; too soon to spawn yet
    assert enemies == []

    gs.time_ms = wm._spawn_interval_ms - 1
    wm.update(enemies, gs)
    assert enemies == []


def test_spawns_first_enemy_once_interval_elapses(assets):
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=1)
    enemies = []

    gs.time_ms = 0
    wm.update(enemies, gs)
    gs.time_ms = wm._spawn_interval_ms
    wm.update(enemies, gs)

    assert len(enemies) == 1
    assert isinstance(enemies[0], Enemy)


def test_wave_25_spawns_the_first_tank_type_as_a_tank_instance(assets):
    # config/waves.yaml wave 25 includes one type-5 (Tank) enemy.
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=25)
    enemies = []

    gs.time_ms = 0
    wm.update(enemies, gs)
    assert 5 in wm._spawn_queue

    drain_queue(wm, enemies, gs)

    tanks = [e for e in enemies if e.enemy_type in (5, 6)]
    non_tanks = [e for e in enemies if e.enemy_type not in (5, 6)]
    assert tanks and all(isinstance(e, Tank) for e in tanks)
    assert non_tanks and all(
        isinstance(e, Enemy) and not isinstance(e, Tank) for e in non_tanks
    )


def test_advances_level_after_queue_drains_and_delay_passes_with_no_enemies(assets):
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=1)
    enemies = []

    gs.time_ms = 0
    wm.update(enemies, gs)
    last_spawn_t = drain_queue(wm, enemies, gs)
    enemies.clear()  # pretend every enemy died

    gs.time_ms = last_spawn_t + WaveManager.LEVEL_END_DELAY_MS
    wm.update(enemies, gs)

    assert gs.level == 2


def test_a_wave_end_pending_at_game_time_0_still_advances(assets):
    """A run continued in a fresh process restores its pending wave end at
    game time 0 (#25); 0 is a time, not "nothing pending"."""
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=2)
    wm._current_level = 2
    wm._spawn_queue = [1, 1]
    wm._queue_index = 2  # fully spawned
    wm._level_finish_time = 0.0

    gs.time_ms = WaveManager.LEVEL_END_DELAY_MS
    wm.update([], gs)

    assert gs.level == 3


def test_does_not_advance_level_while_enemies_are_still_alive(assets):
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=1)
    enemies = []

    gs.time_ms = 0
    wm.update(enemies, gs)
    last_spawn_t = drain_queue(wm, enemies, gs)
    # enemies deliberately left non-empty -- still "alive"

    gs.time_ms = last_spawn_t + WaveManager.LEVEL_END_DELAY_MS
    wm.update(enemies, gs)

    assert gs.level == 1


def test_waves_beyond_the_last_authored_entry_are_generated_dynamically(assets):
    wm = WaveManager(WAYPOINTS, assets)
    beyond_max_defined = max(WAVE_COMPOSITIONS) + 5
    gs = make_started_state(level=beyond_max_defined)

    wm.update([], gs)

    assert wm._spawn_queue  # non-empty: a wave got generated, not skipped


# ── endless waves ────────────────────────────────────────────────────────────


def test_endless_waves_continue_from_the_last_authored_wave(assets):
    """Past the last wave in config/waves.yaml, each wave keeps that wave's
    mix and grows every group by one per wave (tanks by one per two waves),
    rather than jumping to an unrelated composition."""
    wm = WaveManager(WAYPOINTS, assets)
    last = max(WAVE_COMPOSITIONS)
    base = dict(WAVE_COMPOSITIONS[last].groups)

    one = dict(wm._wave_for(last + 1).groups)
    two = dict(wm._wave_for(last + 2).groups)

    assert set(one) == set(base)
    for enemy_type, count in base.items():
        if enemy_type in (5, 6):
            assert (one[enemy_type], two[enemy_type]) == (count, count + 1)
        else:
            assert (one[enemy_type], two[enemy_type]) == (count + 1, count + 2)


def test_endless_wave_spawn_interval_tightens_to_a_floor(assets):
    wm = WaveManager(WAYPOINTS, assets)
    last = max(WAVE_COMPOSITIONS)
    base_interval = (
        WAVE_COMPOSITIONS[last].spawn_interval_ms or WaveManager.SPAWN_INTERVAL_MS
    )

    assert wm._wave_for(last + 1).spawn_interval_ms == base_interval - 10
    assert (
        wm._wave_for(last + 1000).spawn_interval_ms
        == WaveManager.MIN_ENDLESS_INTERVAL_MS
    )


def test_the_wave_after_the_last_authored_one_is_not_a_difficulty_spike(assets):
    wm = WaveManager(WAYPOINTS, assets)
    last = max(WAVE_COMPOSITIONS)

    total_last = sum(count for _, count in WAVE_COMPOSITIONS[last].groups)
    total_next = sum(count for _, count in wm._wave_for(last + 1).groups)

    assert total_last < total_next <= total_last + len(WAVE_COMPOSITIONS[last].groups)


# ── spawn interval from waves.yaml (Refs #25) ─────────────────────────────────


@pytest.mark.parametrize("interval, expected", [(None, 1000), (0, 0), (650, 650)])
def test_a_waves_spawn_interval_keeps_an_explicit_zero(
    assets, monkeypatch, interval, expected
):
    from domain.game_state import WaveDef
    import gameplay.combat.wave_manager as wm_module

    monkeypatch.setitem(
        wm_module.WAVE_COMPOSITIONS,
        3,
        WaveDef(groups=[(1, 4)], spawn_interval_ms=interval),
    )
    wm = WaveManager(WAYPOINTS, assets)

    wm._build_queue(3)

    assert wm._spawn_interval_ms == expected


def test_a_zero_interval_wave_spawns_one_enemy_per_tick(assets, monkeypatch):
    from domain.game_state import WaveDef
    import gameplay.combat.wave_manager as wm_module

    monkeypatch.setitem(
        wm_module.WAVE_COMPOSITIONS, 3, WaveDef(groups=[(1, 4)], spawn_interval_ms=0)
    )
    wm = WaveManager(WAYPOINTS, assets)
    gs = make_started_state(level=3)
    enemies = []

    for tick in range(4):
        gs.time_ms = tick
        wm.update(enemies, gs)

    assert len(enemies) == 4


def test_endless_waves_after_a_zero_interval_wave_use_the_floor(assets, monkeypatch):
    from domain.game_state import WaveDef
    import gameplay.combat.wave_manager as wm_module

    last = max(WAVE_COMPOSITIONS)
    monkeypatch.setitem(
        wm_module.WAVE_COMPOSITIONS, last, WaveDef(groups=[(1, 4)], spawn_interval_ms=0)
    )
    wm = WaveManager(WAYPOINTS, assets)

    assert (
        wm._wave_for(last + 1).spawn_interval_ms == WaveManager.MIN_ENDLESS_INTERVAL_MS
    )
