"""Death effects (#85): every enemy kill and tower destruction explodes (a
tank's and a tower's bigger), a destroyed tower leaves rubble that fades
out, sold towers and escaped enemies show none; sounds rate-capped, all
capped, on real time, cosmetic only. Unit tests drive DeathFeedback
directly; the rest go through a real Game() (saves in a temporary
directory) or the menu demo."""

import random
from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.combat.enemy import Enemy
from gameplay.combat.projectile import Bomb, MuzzleFlash, Projectile
from gameplay.combat.tank import Tank, TankBullet
from gameplay.menu_demo import MenuDemo
from gameplay.tilemap import Tilemap
from gameplay.towers import PLANE_TYPE, TowerFactory
from pygamine import SaveStore
from ui.bomb_impact_feedback import (
    LIFE_MS,
    SOUND_MIN_GAP_MS,
    SOUND_WINDOW_MS,
    SOUNDS_PER_WINDOW,
)
from ui.death_feedback import (
    DECAL_FADE_MS,
    DECAL_HOLD_MS,
    DECAL_LIFE_MS,
    ENEMY_BLAST_SIZE,
    MAX_DECALS,
    MAX_EFFECTS,
    MAX_TOWER_BLASTS,
    TANK_BLAST_SIZE,
    TOWER_BLAST_SIZE,
    DeathFeedback,
    rubble_turn,
)

SMALL, BIG = "sfx/small.ogg", "sfx/big.ogg"
TANK = 5


class SfxSpy:
    """Stands in for GameAudio.play_sfx: records each call and returns a
    channel (any non-None), or None to act as a full pool."""

    def __init__(self):
        self.played = []
        self.pool_full = False

    def __call__(self, path):
        self.played.append(path)
        return None if self.pool_full else object()


class Camera:
    """No offset, a zoom of `scale`."""

    def __init__(self, scale=1.0):
        self.scale = scale

    def world_to_screen(self, pos):
        return Vector2(pos) * self.scale

    def scale_image(self, image):
        if self.scale == 1.0:
            return image
        return pygame.transform.scale_by(image, self.scale)


@pytest.fixture
def sfx():
    return SfxSpy()


@pytest.fixture
def feedback(assets, sfx):
    return DeathFeedback(assets, sfx, SMALL, BIG)


# ── the effects ───────────────────────────────────────────────────────────────


def test_an_enemy_explodes_small_and_a_tank_big(feedback):
    feedback.enemy_died((100, 100), is_tank=False)
    feedback.enemy_died((300, 100), is_tank=True)

    assert [(tuple(b.position), b.size) for b in feedback.blasts] == [
        ((100, 100), ENEMY_BLAST_SIZE),
        ((300, 100), TANK_BLAST_SIZE),
    ]
    assert feedback.decals == []  # enemies leave no rubble
    assert ENEMY_BLAST_SIZE < TANK_BLAST_SIZE


def test_a_destroyed_tower_explodes_and_leaves_rubble(feedback):
    feedback.tower_destroyed((640, 320))

    assert [(tuple(b.position), b.size) for b in feedback.blasts] == [
        ((640, 320), TOWER_BLAST_SIZE)
    ]
    assert [tuple(d.position) for d in feedback.decals] == [(640, 320)]


def test_blasts_play_out_in_life_ms_of_real_time(feedback):
    feedback.enemy_died((0, 0), is_tank=False)

    feedback.update(LIFE_MS - 1)
    assert feedback.blasts
    feedback.update(1)
    assert feedback.blasts == []


def test_the_rubble_holds_then_fades_out(feedback):
    feedback.tower_destroyed((0, 0))
    (decal,) = feedback.decals

    assert feedback.decal_alpha(decal) == 255
    feedback.update(DECAL_HOLD_MS)
    assert feedback.decal_alpha(decal) == 255
    feedback.update(DECAL_FADE_MS / 2)
    assert feedback.decal_alpha(decal) == 128
    feedback.update(DECAL_FADE_MS / 2 - 1)
    assert 0 <= feedback.decal_alpha(decal) <= 1
    assert feedback.decals  # still there, nearly gone
    feedback.update(1)
    assert feedback.decals == []
    assert DECAL_LIFE_MS == DECAL_HOLD_MS + DECAL_FADE_MS


def test_at_most_max_effects_blasts_the_oldest_makes_room(feedback):
    for i in range(MAX_EFFECTS + 3):
        feedback.enemy_died((i, 0), is_tank=False)

    assert len(feedback.blasts) == MAX_EFFECTS
    assert feedback.blasts[0].position.x == 3  # the three oldest went


def test_at_most_max_decals_the_oldest_makes_room(feedback):
    for i in range(MAX_DECALS + 2):
        feedback.tower_destroyed((i * 64, 0))

    assert len(feedback.decals) == MAX_DECALS
    assert feedback.decals[0].position.x == 2 * 64


def test_neighbor_tiles_turn_their_rubble_differently():
    assert rubble_turn((32, 32)) != rubble_turn((96, 32))
    assert rubble_turn((32, 32)) == rubble_turn((40, 50))  # same tile


def test_clear_drops_everything(feedback):
    feedback.enemy_died((0, 0), is_tank=False)
    feedback.tower_destroyed((0, 0))
    feedback.clear()

    assert feedback.blasts == [] and feedback.decals == []


# ── sounds ────────────────────────────────────────────────────────────────────


def test_an_enemy_plays_the_small_sound_a_tank_and_a_tower_the_big_one(feedback, sfx):
    feedback.enemy_died((0, 0), is_tank=False)
    feedback.enemy_died((0, 0), is_tank=True)
    feedback.update(SOUND_MIN_GAP_MS)
    feedback.tower_destroyed((0, 0))

    assert sfx.played == [SMALL, BIG, BIG]


def test_enemy_death_sounds_are_rate_capped_like_bomb_impacts(feedback, sfx):
    feedback.enemy_died((0, 0), is_tank=False)
    feedback.update(SOUND_MIN_GAP_MS - 1)
    feedback.enemy_died((0, 0), is_tank=False)  # too soon: silent
    assert sfx.played == [SMALL]
    assert len(feedback.blasts) == 2  # but it still explodes

    # A kill every frame for a second plays SOUNDS_PER_WINDOW sounds.
    feedback.clear()
    sfx.played.clear()
    for _ in range(SOUND_WINDOW_MS // 10):
        feedback.enemy_died((0, 0), is_tank=False)
        feedback.update(10)
    assert len(sfx.played) == SOUNDS_PER_WINDOW


def test_a_stream_of_kills_cannot_silence_a_falling_tower(feedback, sfx):
    """Soldiers and tanks fill their own caps; the tower's has its own."""
    for _ in range(SOUNDS_PER_WINDOW):
        feedback.enemy_died((0, 0), is_tank=False)
        feedback.enemy_died((0, 0), is_tank=True)
        feedback.update(SOUND_MIN_GAP_MS)
    feedback.enemy_died((0, 0), is_tank=False)  # both enemy caps are full
    feedback.enemy_died((0, 0), is_tank=True)
    assert sfx.played == [SMALL, BIG] * SOUNDS_PER_WINDOW

    feedback.tower_destroyed((0, 0))

    assert sfx.played == [SMALL, BIG] * SOUNDS_PER_WINDOW + [BIG]


def test_a_stream_of_kills_cannot_evict_a_towers_blast(feedback):
    feedback.tower_destroyed((640, 320))
    for i in range(MAX_EFFECTS + 5):  # past the enemies' cap
        feedback.enemy_died((i, 0), is_tank=i % 2 == 0)

    assert len(feedback.enemy_blasts) == MAX_EFFECTS
    assert [(tuple(b.position), b.size) for b in feedback.tower_blasts] == [
        ((640, 320), TOWER_BLAST_SIZE)
    ]


def test_at_most_max_tower_blasts_the_oldest_makes_room(feedback):
    for i in range(MAX_TOWER_BLASTS + 2):
        feedback.tower_destroyed((i * 64, 0))

    assert len(feedback.tower_blasts) == MAX_TOWER_BLASTS
    assert feedback.tower_blasts[0].position.x == 2 * 64
    assert feedback.enemy_blasts == []


def test_a_sound_the_pool_dropped_does_not_count(feedback, sfx):
    sfx.pool_full = True
    feedback.enemy_died((0, 0), is_tank=False)
    sfx.pool_full = False
    feedback.enemy_died((0, 0), is_tank=False)

    assert sfx.played == [SMALL, SMALL]


def test_without_play_sfx_deaths_are_silent(assets):
    feedback = DeathFeedback(assets, play_sfx=None)
    feedback.enemy_died((0, 0), is_tank=True)
    feedback.tower_destroyed((0, 0))

    assert len(feedback.blasts) == 2 and len(feedback.decals) == 1


# ── drawing ───────────────────────────────────────────────────────────────────


def lit_pixels(surface):
    mask = pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255))
    mask.invert()
    return mask


def test_a_blast_draws_on_its_spot(feedback):
    feedback.enemy_died((100, 100), is_tank=False)
    surface = pygame.Surface((200, 200))
    surface.fill((0, 0, 0))

    feedback.draw_blasts(surface, Camera())

    box = lit_pixels(surface).get_bounding_rects()
    assert box and box[0].unionall(box[1:]).collidepoint(100, 100)


def test_the_rubble_draws_fainter_as_it_fades(feedback):
    feedback.tower_destroyed((100, 100))
    surface = pygame.Surface((200, 200))

    def strength():
        surface.fill((255, 255, 255))
        feedback.draw_decals(surface, Camera())
        return sum(255 - surface.get_at((x, y)).r for x in range(200) for y in (100,))

    full = strength()
    feedback.update(DECAL_HOLD_MS + DECAL_FADE_MS / 2)
    half = strength()
    assert 0 < half < full
    feedback.update(DECAL_FADE_MS / 2)
    assert strength() == 0


def test_the_rubble_follows_the_zoom(feedback):
    feedback.tower_destroyed((50, 50))

    def width(scale):
        surface = pygame.Surface((400, 400))
        surface.fill((255, 255, 255))
        feedback.draw_decals(surface, Camera(scale))
        dark = pygame.mask.from_threshold(surface, (255, 255, 255), (1, 1, 1, 255))
        dark.invert()
        return dark.get_bounding_rects()[0].width

    assert width(2.0) > 1.5 * width(1.0)


# ── through the battle ────────────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (400, 300))
    g = Game()
    g._start_new_game()
    g.wave_manager = None  # no spawns: only the enemies a test places
    g.game_state.is_started = True
    g.towers.clear()
    g.enemies.clear()
    return g


def add_enemy(game, pos, hp=None, enemy_type=1):
    if enemy_type == TANK:
        enemy = Tank(len(game.enemies) + 1, TANK, 1, [Vector2(pos)], game.assets)
    else:
        enemy = Enemy(len(game.enemies) + 1, enemy_type, 1, [Vector2(pos)], game.assets)
    if hp is not None:
        enemy.hp = hp
    game.enemies.append(enemy)
    return enemy


def ground_tower(game, tower_type=2, row=10, col=10):
    tower = TowerFactory.create(
        tower_type, row, col, game.tower_config, game.assets, None, map_width=3008
    )
    tower.now = game.game_state.time_ms
    game.towers.append(tower)
    return tower


def blasts(battle):
    return [(tuple(b.position), b.size) for b in battle.death_feedback.blasts]


def test_a_missile_kill_explodes_where_the_enemy_died(game):
    tower = ground_tower(game)
    enemy = add_enemy(game, tower.position + Vector2(100, 0), hp=1)
    missile = Projectile(enemy, tower)
    missile.position = Vector2(enemy.position)

    missile.update(game)

    assert enemy not in game.enemies
    assert blasts(game) == [(tuple(enemy.position), ENEMY_BLAST_SIZE)]


def test_an_instant_hit_kill_explodes(game):
    tower = ground_tower(game, tower_type=1)
    enemy = add_enemy(game, tower.position + Vector2(100, 0), hp=1)

    MuzzleFlash(enemy, tower, tower.position).update(game)

    assert blasts(game) == [(tuple(enemy.position), ENEMY_BLAST_SIZE)]


def test_every_enemy_a_bomb_kills_explodes(game):
    plane = TowerFactory.create(
        PLANE_TYPE, 0, 0, game.tower_config, game.assets, None, map_width=3008
    )
    plane.position = Vector2(700, 700)
    plane.now = game.game_state.time_ms
    a = add_enemy(game, (700, 700), hp=1)
    b = add_enemy(game, (730, 700), hp=1)
    tough = add_enemy(game, (710, 700), hp=100_000)  # survives the blast
    bomb = Bomb(plane, Vector2(0, 0))
    plane.bullets.append(bomb)

    bomb._detonate(game)

    assert tough in game.enemies
    assert blasts(game) == [
        (tuple(a.position), ENEMY_BLAST_SIZE),
        (tuple(b.position), ENEMY_BLAST_SIZE),
    ]


def test_a_dead_tank_explodes_big_with_the_big_sound(game, monkeypatch):
    played = []
    monkeypatch.setattr(
        game.death_feedback._tank_cap, "_play_sfx", lambda p: played.append(p) or 1
    )
    tower = ground_tower(game)
    tank = add_enemy(game, tower.position + Vector2(100, 0), hp=1, enemy_type=TANK)
    missile = Projectile(tank, tower)
    missile.position = Vector2(tank.position)

    missile.update(game)

    assert blasts(game) == [(tuple(tank.position), TANK_BLAST_SIZE)]
    assert played == [str(game.assets.sound_path("heavy_destroyed"))]


def test_a_tower_destroyed_by_a_tank_explodes_and_leaves_rubble(game):
    tower = ground_tower(game)
    tower.hp = 1
    tank = Tank(1, TANK, 1, [tower.position + Vector2(200, 0)], game.assets)
    shell = TankBullet(tank, tower, tower.position + Vector2(10, 0))
    tank.bullets.append(shell)

    shell.update(game)

    # Shown on the hit that takes its HP to 0, before its removal.
    assert tower in game.towers
    assert blasts(game) == [(tuple(tower.position), TOWER_BLAST_SIZE)]
    assert [tuple(d.position) for d in game.death_feedback.decals] == [
        tuple(tower.position)
    ]
    game._tick()
    assert tower not in game.towers
    assert len(blasts(game)) == 1  # not again when it's removed


def test_a_tower_explodes_once_however_many_shells_hit_it(game):
    tower = ground_tower(game)
    tower.hp = 1
    tank = Tank(1, TANK, 1, [tower.position + Vector2(200, 0)], game.assets)

    for _ in range(3):  # the killing shell, then two more on the wreck
        tower.decrease_hp(tank.bullet_damage, game, tower.position)

    assert len(game.death_feedback.tower_blasts) == 1
    assert len(game.death_feedback.decals) == 1


def test_a_tower_sold_before_its_removal_still_explodes(game):
    """Its HP runs out and the player sells it in the same frame, before
    the tick that would remove it: its blast and rubble already show."""
    tower = ground_tower(game)
    tower.hp = 1
    tank = Tank(1, TANK, 1, [tower.position + Vector2(200, 0)], game.assets)
    TankBullet(tank, tower, tower.position).update(game)
    game.game_state.selected_tower = tower
    controller = game.tower_controller
    assert controller._handle_tower_actions(tower._sell_hit_rect(game.camera).center)

    assert tower not in game.towers
    assert blasts(game) == [(tuple(tower.position), TOWER_BLAST_SIZE)]
    assert len(game.death_feedback.decals) == 1


def test_a_tank_is_the_enemy_with_the_big_blast(assets):
    tank = Tank(1, TANK, 1, [Vector2(0, 0)], assets)
    soldier = Enemy(2, 1, 1, [Vector2(0, 0)], assets)

    assert tank.big_death_blast is True
    assert soldier.big_death_blast is False


def test_a_plane_leaving_the_map_does_not_explode(game):
    plane = TowerFactory.create(
        PLANE_TYPE, 0, 0, game.tower_config, game.assets, None, map_width=3008
    )
    plane.position = Vector2(3008 + 5000, 700)  # past the right edge
    plane.rect.center = plane.position
    game.towers.append(plane)
    assert plane.should_remove()

    game._tick()

    assert plane not in game.towers
    assert blasts(game) == [] and game.death_feedback.decals == []


def test_a_sold_tower_keeps_its_coins_and_does_not_explode(game):
    tower = ground_tower(game)
    game.game_state.selected_tower = tower
    controller = game.tower_controller
    assert controller._handle_tower_actions(tower._sell_hit_rect(game.camera).center)
    game._tick()

    assert tower not in game.towers
    assert blasts(game) == [] and game.death_feedback.decals == []
    assert game.place_sell_feedback.coins  # the coin burst


def test_an_escaped_enemy_does_not_explode(game):
    enemy = add_enemy(game, (500, 500))
    enemy.waypoint_index = len(enemy.waypoints)  # at the end

    game._tick()

    assert enemy not in game.enemies
    assert blasts(game) == []


def test_the_blast_outlives_the_enemy_and_does_not_hold_up_its_payout(game):
    tower = ground_tower(game)
    enemy = add_enemy(game, tower.position + Vector2(100, 0), hp=1)
    money = game.game_state.money
    missile = Projectile(enemy, tower)
    missile.position = Vector2(enemy.position)

    missile.update(game)

    assert enemy not in game.enemies
    assert game.game_state.money == money + enemy.kill_money
    assert tower.kills == 1
    assert not any(
        vars(b).get(k) is enemy for b in game.death_feedback.blasts for k in vars(b)
    )  # it holds a position, never the enemy
    game._draw_battle(pygame.Surface((1280, 720)), game.camera)


def test_death_effects_play_out_on_real_time_while_paused(game):
    game.death_feedback.enemy_died((500, 500), is_tank=False)
    game.death_feedback.tower_destroyed((640, 640))
    game.game_state.is_started = False

    game._update_game(LIFE_MS)
    assert game.death_feedback.blasts == []
    game._update_game(DECAL_LIFE_MS - LIFE_MS)
    assert game.death_feedback.decals == []


@pytest.mark.parametrize("reset", ["_start_new_game", "load"])
def test_new_game_and_load_drop_the_effects(game, reset):
    game._start_new_game()  # a real wave manager, to save with
    game.death_feedback.tower_destroyed((640, 640))
    if reset == "load":
        game._save_game()
        game._load_game()
    else:
        game._start_new_game()

    assert game.death_feedback.blasts == [] and game.death_feedback.decals == []


# ── the menu demo, and no gameplay change ────────────────────────────────────


@pytest.fixture(scope="module")
def tilemap():
    return Tilemap("assets/maps/tiled_tilemap.tmx")


def test_the_menu_demo_explodes_silently(tilemap, assets, tower_config):
    demo = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(1))
    assert demo.death_feedback.blasts == []  # the pre-warm's are cleared
    assert demo.death_feedback._small_cap._play_sfx is None
    assert demo.death_feedback._tank_cap._play_sfx is None
    assert demo.death_feedback._tower_cap._play_sfx is None

    for _ in range(600):
        demo._tick()

    assert demo.death_feedback.blasts
    demo.draw(pygame.Surface((1280, 720)))


def battle_outcome(demo):
    gs = demo.game_state
    return (
        gs.money,
        gs.lives,
        gs.level,
        [(e.id, e.hp, tuple(e.position)) for e in demo.enemies],
        [
            (t.tower_type, t.row, t.col, t.hp, t.kills, t.damage_dealt)
            for t in demo.towers
        ],
    )


def test_the_battle_plays_out_the_same_without_it(
    tilemap, assets, tower_config, monkeypatch
):
    """The menu demo's battle, seeded, ticked with and without the death
    effects: money, lives, level, every enemy's and tower's HP, kills and
    damage end up identical. Towers are made frail and a tank drives past
    them, so some fall too."""

    def frail(demo):
        for tower in demo.towers:
            if tower.hp is not None:
                tower.hp = 40
        start = demo.towers[0].position + Vector2(-150, 0)
        tank = Tank(999, TANK, 10, [start, start + Vector2(2000, 0)], assets)
        demo.enemies.append(tank)

    with_it = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(3))
    without = MenuDemo(tilemap, assets, tower_config, (1280, 720), random.Random(3))
    without.death_feedback = None
    frail(with_it)
    frail(without)
    destroyed = []
    real = with_it.death_feedback.tower_destroyed
    monkeypatch.setattr(
        with_it.death_feedback,
        "tower_destroyed",
        lambda pos: destroyed.append(pos) or real(pos),
    )
    for _ in range(3000):
        with_it._tick()
        without._tick()

    assert with_it.death_feedback is not None
    assert with_it.death_feedback.blasts  # it was killing
    assert destroyed  # and towers fell
    assert battle_outcome(with_it) == battle_outcome(without)


def test_fading_never_touches_the_cached_decal(feedback):
    feedback.tower_destroyed((100, 100))
    feedback.update(DECAL_HOLD_MS + DECAL_FADE_MS / 2)
    surface = pygame.Surface((200, 200))

    feedback.draw_decals(surface, Camera())  # zoom 1.0: the cached image

    cached = feedback._decal_images[feedback.decals[0].turn]
    assert cached.get_alpha() in (None, 255)


def test_a_blast_at_zoom_one_draws_its_frame_unscaled(feedback, monkeypatch):
    scaled = []
    monkeypatch.setattr(
        pygame.transform, "scale", lambda *a, **k: scaled.append(a) or a[0]
    )
    feedback.enemy_died((100, 100), is_tank=False)

    feedback.draw_blasts(pygame.Surface((200, 200)), Camera())

    assert scaled == []


@pytest.mark.parametrize("owner", ["game", "demo"])
def test_bombs_and_deaths_share_one_explosion_cache(owner, request):
    if owner == "game":
        battle = request.getfixturevalue("game")
    else:
        battle = MenuDemo(
            request.getfixturevalue("tilemap"),
            request.getfixturevalue("assets"),
            request.getfixturevalue("tower_config"),
            (1280, 720),
            random.Random(1),
        )

    assert battle.bomb_impacts._frames_cache is battle.death_feedback._frames
