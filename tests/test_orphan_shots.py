"""Shots already in flight outlive their shooter (issue #62): a tank's shell
keeps flying and hits its tower after the tank dies or escapes, and a
tower's missile keeps flying and hits after the tower is sold or destroyed,
credited to that tower. Plane bombs, the first case, are in
test_orphan_bombs.py. Runs a real Game() with saves in a temporary
directory, and the menu demo."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.combat.projectile import MuzzleFlash, Projectile
from gameplay.combat.tank import Tank, TankBullet
from gameplay.menu_demo import MenuDemo
from gameplay.towers import TowerFactory
from pygamine import SaveStore

MISSILE, RAPID = 2, 1
TANK = 5
ENOUGH_TICKS = 400  # far more than any shot here needs to land


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    g.wave_manager = None  # no spawns: only the enemies a test places
    g.game_state.is_started = True
    return g


def orphans(battle) -> list:
    return [o.shot for o in battle.orphan_shots]


def place_tower(battle, tower_type, tower_config, audio=None, row=10, col=20):
    if audio is None:
        audio = battle.audio
    tower = TowerFactory.create(
        tower_type, row, col, tower_config, battle.assets, audio, battle.map_width
    )
    tower.last_reload_time = battle.game_state.time_ms - 10**6  # loaded
    battle.towers.append(tower)
    return tower


def stand(enemy, battle, position, hp):
    enemy.position = Vector2(position)
    enemy.rect.center = enemy.position
    enemy.move = lambda game_speed: None
    enemy.hp = enemy.maxHP = hp
    battle.enemies.append(enemy)
    return enemy


def standing_tank(battle, tower, hp=10**9):
    """A tank 200 px from `tower` (in range), ready to fire on its next tick."""
    tank = Tank(1, TANK, 1, battle.tilemap.waypoints, battle.assets)
    stand(tank, battle, tower.position + Vector2(200, 0), hp)
    tank._last_fire_time = battle.game_state.time_ms - tank.fire_interval_ms
    return tank


def tank_fires(battle, tank):
    """Tick until the tank has a shell in flight; returns the shell."""
    battle._tick()
    (shell,) = [b for b in tank.bullets if isinstance(b, TankBullet)]
    return shell


def missile_fired(battle, tower, tower_config, hp):
    """A missile tower with a standing enemy in range: tick once so it
    fires; returns (missile, enemy)."""
    from gameplay.combat.enemy import Enemy

    enemy = Enemy(1, 1, 1, battle.tilemap.waypoints, battle.assets)
    stand(enemy, battle, tower.position + Vector2(tower.range * 0.8, 0), hp)
    battle._tick()
    (missile,) = tower.bullets
    assert isinstance(missile, Projectile)
    return missile, enemy


def tick_until_landed(battle):
    for _ in range(ENOUGH_TICKS):
        battle._tick()
        if not battle.orphan_shots:
            return
    raise AssertionError("an orphan shot never landed")


# ── tank shells ───────────────────────────────────────────────────────────────


def test_a_tanks_shell_hits_its_tower_after_the_tank_dies(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    tank = standing_tank(game, tower)
    shell = tank_fires(game, tank)

    tank.decrease_hp(tank.hp, game)  # killed while its shell is in flight
    assert tank not in game.enemies
    game._tick()
    assert orphans(game) == [shell]
    game.draw()  # a flying orphan shell is drawn

    tick_until_landed(game)
    assert tower.hp == tower.maxHP - tank.bullet_damage
    assert not any(isinstance(b, TankBullet) for b in tank.bullets)


def test_a_tanks_shell_hits_its_tower_after_the_tank_escapes(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    tank = standing_tank(game, tower)
    shell = tank_fires(game, tank)
    lives = game.game_state.lives

    tank.waypoint_index = len(tank.waypoints)  # reaches the end
    game._tick()
    assert tank not in game.enemies
    assert game.game_state.lives == lives - tank.damage
    assert orphans(game) == [shell]

    tick_until_landed(game)
    assert tower.hp == tower.maxHP - tank.bullet_damage


def test_an_orphan_shell_lands_on_the_same_tick_as_with_its_tank(game, tower_config):
    def landing_tick(kill_tank: bool) -> int:
        game._start_new_game()
        game.game_state.is_started = True
        tower = place_tower(game, MISSILE, tower_config)
        tower.update = lambda *args: None  # holds fire: the tank lives
        tank = standing_tank(game, tower)
        tank_fires(game, tank)
        tank.update_combat = lambda ctx: None  # fires no second shell
        if kill_tank:
            tank.decrease_hp(tank.hp, game)
        for tick in range(ENOUGH_TICKS):
            game._tick()
            if tower.hp < tower.maxHP:
                return tick
        raise AssertionError("the shell never landed")

    assert landing_tick(kill_tank=True) == landing_tick(kill_tank=False)


def test_a_tanks_muzzle_flash_goes_with_it(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    tank = standing_tank(game, tower)
    tank_fires(game, tank)
    assert len(tank.bullets) == 2  # the shell and its muzzle flash

    tank.decrease_hp(tank.hp, game)
    game._tick()
    assert all(isinstance(s, TankBullet) for s in orphans(game))


def test_an_orphan_shell_waits_while_the_game_is_paused(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    tank = standing_tank(game, tower)
    shell = tank_fires(game, tank)
    tank.decrease_hp(tank.hp, game)
    game._tick()
    position = Vector2(shell.position)

    game.game_state.is_started = False
    for _ in range(ENOUGH_TICKS):
        game._tick()

    assert orphans(game) == [shell]
    assert shell.position == position
    assert tower.hp == tower.maxHP


# ── tower missiles ────────────────────────────────────────────────────────────


def sell(game, tower):
    game.game_state.selected_tower = tower
    mouse = game.tower_controller  # sold through the real controller
    assert mouse._handle_tower_actions(tower._sell_hit_rect(game.camera).center)
    assert tower not in game.towers


def test_a_sold_towers_missile_hits_and_is_credited_to_it(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    missile, enemy = missile_fired(game, tower, tower_config, hp=tower.damage)
    money = game.game_state.money

    sell(game, tower)
    assert game.game_state.money == money + tower.sell_price
    game._tick()
    assert orphans(game) == [missile]
    game.draw()  # a flying orphan missile is drawn

    tick_until_landed(game)
    assert enemy not in game.enemies
    assert tower.kills == 1
    assert tower.money_earned == enemy.killMoney
    assert game.game_state.money == money + tower.sell_price + enemy.killMoney
    assert tower.bullets == []


def test_a_destroyed_towers_missile_hits_and_is_credited_to_it(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    missile, enemy = missile_fired(game, tower, tower_config, hp=tower.damage + 1)

    tower.hp = 0  # destroyed by a tank
    game._tick()
    assert tower not in game.towers
    assert orphans(game) == [missile]

    tick_until_landed(game)
    assert enemy.hp == 1  # it took the hit
    assert tower.kills == 0


def test_an_orphan_missile_lands_on_the_same_tick_as_with_its_tower(game, tower_config):
    def landing_tick(sell_it: bool) -> int:
        game._start_new_game()
        game.game_state.is_started = True
        tower = place_tower(game, MISSILE, tower_config)
        _, enemy = missile_fired(game, tower, tower_config, hp=10**6)
        tower.update = lambda *args: None  # fires no second missile
        if sell_it:
            sell(game, tower)
        for tick in range(ENOUGH_TICKS):
            game._tick()
            if enemy.hp < enemy.maxHP:
                return tick
        raise AssertionError("the missile never landed")

    assert landing_tick(sell_it=True) == landing_tick(sell_it=False)


def test_an_orphan_missile_whose_target_died_lands_harmlessly(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    missile, enemy = missile_fired(game, tower, tower_config, hp=10**6)
    sell(game, tower)
    game.enemies.remove(enemy)  # its target is gone, as when it dies

    tick_until_landed(game)
    assert enemy.hp == enemy.maxHP
    assert tower.bullets == []


def test_a_sold_towers_muzzle_flash_goes_with_it(game, tower_config):
    tower = place_tower(game, RAPID, tower_config)
    from gameplay.combat.enemy import Enemy

    enemy = Enemy(1, 1, 1, game.tilemap.waypoints, game.assets)
    stand(enemy, game, tower.position + Vector2(tower.range * 0.5, 0), hp=10**6)
    game._tick()
    assert tower.bullets and all(isinstance(b, MuzzleFlash) for b in tower.bullets)
    hp = enemy.hp

    sell(game, tower)
    game._tick()
    assert not game.orphan_shots
    assert enemy.hp == hp  # the instant hit landed once, before the sale


# ── resets ────────────────────────────────────────────────────────────────────


def test_starting_a_new_game_or_loading_drops_orphan_shots(game, tower_config):
    tower = place_tower(game, MISSILE, tower_config)
    tank = standing_tank(game, tower)
    tank_fires(game, tank)
    tank.decrease_hp(tank.hp, game)
    game._tick()
    assert game.orphan_shots
    game._init_wave_manager()  # the save needs one
    game._save_game()  # shots in flight aren't saved

    game._load_game()
    assert not game.orphan_shots
    game.game_state.is_started = True
    game._tick()
    assert not game.orphan_shots  # the old battle's shooters are forgotten

    tower = place_tower(game, MISSILE, tower_config)
    missile_fired(game, tower, tower_config, hp=10**6)
    sell(game, tower)
    game._tick()
    assert game.orphan_shots
    game._start_new_game()
    assert not game.orphan_shots
    game.game_state.is_started = True
    game._tick()
    assert not game.orphan_shots


def test_the_menu_demos_orphan_shots_land_too(assets, tower_config):
    from gameplay.tilemap import Tilemap

    tilemap = Tilemap("assets/maps/tiled_tilemap.tmx")
    demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))
    demo.wave_manager = None
    demo.enemies.clear()
    demo.towers.clear()
    demo._next_plane_at = float("inf")
    demo.assets = assets
    tower = place_tower(demo, MISSILE, tower_config, demo._audio)
    tank = standing_tank(demo, tower)
    tank_fires(demo, tank)

    tank.decrease_hp(tank.hp, demo)
    demo._tick()
    assert demo.orphan_shots
    demo.draw(pygame.Surface((1280, 720)))
    tick_until_landed(demo)
    assert tower.hp == tower.maxHP - tank.bullet_damage

    demo._start_run()
    assert not demo.orphan_shots
