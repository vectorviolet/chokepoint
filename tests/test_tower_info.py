"""The tower info panel: per-tower kill/money tracking, the stat texts and
their upgrade previews, and the panel opening/closing/fitting in a real
Game() (saves in a temporary directory)."""

from functools import partial

import pygame
import pytest
from pygame.math import Vector2

import app.game
from app.game import Game
from gameplay.combat.enemy import Enemy
from gameplay.combat.projectile import Bomb, MuzzleFlash, Projectile
from gameplay.towers import TowerFactory
from gameplay.towers.base_tower import BTN_SIZE, UPGRADE_BTN_OFFSET
from pygamine import SaveStore
from pygamine.app.application import COMMON_RESOLUTIONS
from ui.tower_info import ARROW, TOWER_INFO_OBJECTS, fire_rate, stat_texts

MAP_WIDTH = 3008
WAYPOINTS = [Vector2(0, 0), Vector2(500, 0)]


def make_tower(tower_config, assets, tower_type, *, level=1, row=0, col=0):
    tower = TowerFactory.create(
        tower_type, row, col, tower_config, assets, audio=None, map_width=MAP_WIDTH
    )
    tower.level = level
    tower.hp = tower.maxHP
    return tower


def make_enemy(assets, position, enemy_id=1):
    enemy = Enemy(enemy_id, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    enemy.position = Vector2(position)
    return enemy


# ── kill / money tracking ────────────────────────────────────────────────────


def test_a_new_tower_has_no_kills_or_earnings(tower_config, assets):
    tower = make_tower(tower_config, assets, 2)
    assert (tower.kills, tower.money_earned) == (0, 0)


def test_a_killing_blow_credits_the_source_tower(assets, tower_config, ctx):
    tower = make_tower(tower_config, assets, 2)
    enemy = make_enemy(assets, (100, 100))
    ctx.enemies.append(enemy)

    enemy.decrease_hp(enemy.maxHP - 1, ctx, tower)
    assert tower.kills == 0  # not dead yet
    enemy.decrease_hp(1, ctx, tower)

    assert (tower.kills, tower.money_earned) == (1, enemy.killMoney)
    assert ctx.money_earned == enemy.killMoney  # paid out once, as before


def test_hitting_an_already_dead_enemy_credits_nothing(assets, tower_config, ctx):
    first = make_tower(tower_config, assets, 2)
    second = make_tower(tower_config, assets, 2)
    enemy = make_enemy(assets, (100, 100))
    ctx.enemies.append(enemy)

    enemy.decrease_hp(enemy.maxHP, ctx, first)
    enemy.decrease_hp(enemy.maxHP, ctx, second)

    assert (first.kills, second.kills) == (1, 0)


def test_a_missile_kill_is_credited_to_its_tower(assets, tower_config, ctx):
    tower = make_tower(tower_config, assets, 2)
    tower.position = Vector2(1000, 1000)
    target = make_enemy(assets, (1000 + Projectile.EXPLODE_DISTANCE - 1, 1000))
    target.hp = 1
    ctx.enemies.append(target)
    missile = Projectile(target, tower)
    tower.bullets.append(missile)

    missile.update(ctx)

    assert (tower.kills, tower.money_earned) == (1, target.killMoney)


def test_a_twin_barrel_volley_counts_one_kill(assets, tower_config, ctx):
    tower = make_tower(tower_config, assets, 1)
    target = make_enemy(assets, tower.position + Vector2(50, 0))
    target.hp = 1
    ctx.enemies.append(target)

    MuzzleFlash(target, tower, tower.position, deals_damage=True).update(ctx)
    MuzzleFlash(target, tower, tower.position, deals_damage=False).update(ctx)

    assert tower.kills == 1


def test_a_bomb_kill_is_credited_to_its_plane(assets, tower_config, ctx):
    plane = make_tower(tower_config, assets, 4)
    center = Vector2(1000, 1000)
    enemies = [make_enemy(assets, center, enemy_id=i) for i in range(3)]
    for enemy in enemies:
        enemy.hp = 1
    ctx.enemies.extend(enemies)

    plane.position = Vector2(center)
    bomb = Bomb(plane, Vector2(0, 0))
    plane.bullets = [bomb]
    ctx.time_ms = Bomb.FALL_DURATION_MS
    bomb.update(ctx)

    assert plane.kills == 3
    assert plane.money_earned == sum(e.killMoney for e in enemies)


# ── stat texts and upgrade previews ──────────────────────────────────────────


def test_fire_rate_is_shots_per_second_from_the_reload_time():
    assert fire_rate(1000) == 1.0
    assert fire_rate(500) == 2.0
    assert fire_rate(1200) == pytest.approx(0.833, abs=1e-3)


def test_stat_texts_preview_every_stat_an_upgrade_changes(tower_config, assets):
    tower = make_tower(tower_config, assets, 2)  # missile: 40 dmg -> 70 dmg
    tower.hp = 50
    tower.kills = 7
    tower.money_earned = 120

    texts = stat_texts(tower)

    assert texts["title"] == "Level 1 / 3"
    assert texts["kills"] == "7"
    assert texts["earned"] == "120 $"
    assert texts["damage"] == f"40 {ARROW} 70"
    assert texts["range"] == f"3 {ARROW} 3.5 tiles"  # 192 px -> 224 px
    assert texts["fire_rate"] == f"0.83 {ARROW} 1.00/s"  # 1200 ms -> 1000 ms
    assert texts["hp"] == f"50 / 80 {ARROW} 120"


def test_stat_texts_hide_previews_at_max_level(tower_config, assets):
    tower = make_tower(tower_config, assets, 2, level=3)

    texts = stat_texts(tower)

    assert texts["title"] == "Level 3 / 3  (max)"
    assert texts["damage"] == "120"
    assert texts["range"] == "4 tiles"
    assert texts["fire_rate"] == "1.11/s"
    assert texts["hp"] == "180 / 180"
    assert not any(ARROW in text for text in texts.values())


def test_a_single_level_tower_never_shows_previews(tower_config, assets):
    tower = make_tower(tower_config, assets, 1)  # rapid gun: max level 1

    texts = stat_texts(tower)

    assert texts["damage"] == "12"
    assert not any(ARROW in text for text in texts.values())


def test_a_stat_an_upgrade_leaves_alone_shows_no_preview(tower_config, assets):
    tower = make_tower(tower_config, assets, 3)
    tower._config = type(tower_config)(
        **{**vars(tower_config), "damages": [d[:] for d in tower_config.damages]}
    )
    tower._config.damages[2] = [90, 90]

    assert stat_texts(tower)["damage"] == "90"


def test_stat_texts_never_show_negative_hp(tower_config, assets):
    tower = make_tower(tower_config, assets, 2, level=3)
    tower.hp = -5
    assert stat_texts(tower)["hp"] == "0 / 180"


# ── in a real Game ───────────────────────────────────────────────────────────


@pytest.fixture
def game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    mouse = {"pos": (0, 0)}
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: mouse["pos"])
    g = Game()
    g._start_new_game()
    g.test_mouse = mouse
    return g


@pytest.fixture
def placed(game):
    """A level-1 missile tower in the middle of the screen."""
    tower = TowerFactory.create(
        2, 8, 6, game.tower_config, game.assets, game.audio, game.tilemap.map_width
    )
    game.towers.insert(0, tower)
    game.camera.center_on(tower.position)
    return tower


def info_objects(game):
    panel = game.panel_manager["game"]
    return [panel[name] for name in TOWER_INFO_OBJECTS]


def frame(game):
    game._update_game(0)


def click(game, pos, button=1):
    game.test_mouse["pos"] = pos
    frame(game)  # the cursor tile follows the mouse
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button))
    frame(game)


def screen_pos(game, tower):
    p = game.camera.world_to_screen(tower.position)
    return (int(p.x), int(p.y))


def test_the_panel_starts_closed(game):
    frame(game)
    assert not game.tower_info.is_open
    assert not any(obj.active for obj in info_objects(game))


def test_clicking_a_tower_opens_its_panel(game, placed):
    click(game, screen_pos(game, placed))

    assert game.tower_info.tower is placed
    assert all(obj.active for obj in info_objects(game))
    value = game.panel_manager["game"]["tower_info_damage_value"]
    assert value.text == f"40 {ARROW} 70"


def test_clicking_elsewhere_closes_the_panel(game, placed):
    click(game, screen_pos(game, placed))
    x, y = screen_pos(game, placed)

    click(game, (x + 300, y + 200))

    assert not game.tower_info.is_open
    assert not any(obj.active for obj in info_objects(game))


def test_right_click_closes_the_panel(game, placed):
    click(game, screen_pos(game, placed))

    click(game, screen_pos(game, placed), button=3)

    assert not game.tower_info.is_open


def test_clicking_inside_the_panel_keeps_it_open(game, placed):
    click(game, screen_pos(game, placed))
    bg = game.panel_manager["game"]["tower_info_bg"]

    click(game, bg.rect.center)

    assert game.tower_info.tower is placed


def test_upgrading_keeps_the_panel_open_and_updates_the_previews(game, placed):
    game.game_state.money = 10_000
    click(game, screen_pos(game, placed))
    x, y = screen_pos(game, placed)
    upgrade = (
        x + UPGRADE_BTN_OFFSET.x + BTN_SIZE[0] // 2,
        y + UPGRADE_BTN_OFFSET.y + BTN_SIZE[1] // 2,
    )

    click(game, upgrade)

    assert placed.level == 2
    assert game.tower_info.tower is placed
    value = game.panel_manager["game"]["tower_info_damage_value"]
    assert value.text == f"70 {ARROW} 120"


def test_the_panel_closes_when_its_tower_is_destroyed(game, placed):
    click(game, screen_pos(game, placed))
    game.towers.remove(placed)

    frame(game)

    assert not game.tower_info.is_open


def test_the_panel_follows_kills_as_they_happen(game, placed):
    click(game, screen_pos(game, placed))
    enemy = Enemy(1, 1, level=1, waypoints=game.tilemap.waypoints, assets=game.assets)
    game.enemies.append(enemy)

    enemy.decrease_hp(enemy.maxHP, game, placed)
    frame(game)

    panel = game.panel_manager["game"]
    assert panel["tower_info_kills_value"].text == "1"
    assert panel["tower_info_earned_value"].text == f"{enemy.killMoney} $"


def test_the_panel_hides_with_the_hud(game, placed):
    click(game, screen_pos(game, placed))

    game.hud_slide.toggle()
    game.hud_slide.update(1000)

    bg = game.panel_manager["game"]["tower_info_bg"]
    with game.hud_slide.shifted():
        assert bg.rect.right <= 0
    assert not bg.visible  # and takes no clicks while away


def test_drawing_the_open_panel_does_not_raise(game, placed):
    click(game, screen_pos(game, placed))
    placed.hp = placed.maxHP // 2
    game.draw()


@pytest.mark.parametrize("size", COMMON_RESOLUTIONS)
def test_the_panel_fits_on_screen_at_every_window_size(game, placed, size):
    placed.level = 2  # the longest texts: previews on every row
    placed.hp = placed.maxHP
    placed.kills = 9999
    placed.money_earned = 999_999
    game.game_state.selected_tower = placed
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)
    frame(game)

    panel = game.panel_manager["game"]
    bg = panel["tower_info_bg"].rect
    assert pygame.Rect(0, 0, *size).contains(bg)
    for obj in info_objects(game):
        assert bg.contains(obj.rect), obj
    for other in ("coin_text", "tower_panel_bg", "control_panel_bg"):
        assert not bg.colliderect(panel[other].rect), other
