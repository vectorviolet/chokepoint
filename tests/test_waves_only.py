"""BattleSimulation.waves_only() (#64): ticks inside run the waves alone,
for set-up tools such as scripts/make_playtest_save.py."""

from app.game import Game
from gameplay.towers import TowerFactory


def test_waves_only_runs_the_waves_without_defence_or_lives():
    game = Game()
    game._start_new_game()
    tower = TowerFactory.create(
        1,
        5,
        5,
        game.tower_config,
        game.assets,
        game.audio,
        game.tilemap.map_width,
    )
    game.towers.append(tower)
    gs = game.game_state
    gs.is_started = True
    lives = gs.lives

    with game.waves_only() as escaped:
        while game.wave_manager.spawned_count < 2:
            game._tick()
        runner = game.enemies[0]
        runner.waypoint_index = len(runner.waypoints)  # at the end of the path
        game._tick()

    assert escaped == [runner]
    assert runner not in game.enemies
    assert gs.lives == lives  # no lives lost, no game over
    assert not game._gameover_popup_open
    assert tower.now == 0  # the tower never updated

    # Outside it, the game's own rules are back.
    other = game.enemies[0]
    other.waypoint_index = len(other.waypoints)
    game._tick()
    assert gs.lives < lives
    assert escaped == [runner]
