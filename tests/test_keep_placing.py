"""Keep placing and unaffordable picks (#69) in a real Game() (saves and
settings in a temporary directory): the HUD's keep-placing toggle and the
Shift press that flips it, the setting being saved, restored and reset, the
button sliding away with the HUD; an unaffordable tower's buy button looking
disabled, and picking it (click or number key) being refused with the denied
sound and a red flash of the money counter."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore
from ui.game_hud import FLASH_MS, FLASH_STEP_MS
from ui.hud_slide import GROUPS, SLIDE_MS
from util.constants import TILE_SIZE


@pytest.fixture
def mouse(monkeypatch):
    state = {"pos": (400, 300)}  # mid-window: no edge scrolling
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: state["pos"])
    return state


@pytest.fixture
def make_game(monkeypatch, tmp_path, mouse, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))

    def make() -> Game:
        g = Game()
        g._start_new_game()
        g.played = []
        monkeypatch.setattr(g.audio, "play_sfx", g.played.append)
        return g

    return make


@pytest.fixture
def game(make_game):
    return make_game()


def panel(game):
    return game.panel_manager["game"]


def click_at(game, mouse, pos):
    mouse["pos"] = pos
    game.mouse.update()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))
    mouse["pos"] = (400, 300)
    game.mouse.update()


def click(game, mouse, obj):
    click_at(game, mouse, obj.rect.center)


def key(game, k, kind=pygame.KEYDOWN, **extra):
    game.handle_event(pygame.event.Event(kind, key=k, **extra))


def toggle(game, mouse):
    click(game, mouse, panel(game)["keep_placing_button"])


def denied_sound(game):
    return str(game.assets.sound_path("denied"))


def price(game, tower_type):
    return game.tower_config.prices[tower_type - 1][0]


def set_money(game, money):
    gs = game.game_state
    gs.decrease_money(gs.money - money) if gs.money > money else gs.increase_money(
        money - gs.money
    )
    assert gs.money == money


def free_tile_pos(game):
    """The screen position of a buildable, free tile in view."""
    grid = game.tilemap.buildable_grid
    for row in range(len(grid)):
        for col in range(len(grid[0])):
            if (
                not grid[row][col]
                or (row, col) in game.tower_controller.tower_positions
            ):
                continue
            world = (col * TILE_SIZE + TILE_SIZE // 2, row * TILE_SIZE + TILE_SIZE // 2)
            pos = game.camera.world_to_screen(world)
            pos = (int(pos.x), int(pos.y))
            if game.game_area.inflate(-200, -300).collidepoint(pos):
                return pos
    raise AssertionError("no free tile in view")


def place(game, mouse):
    pos = free_tile_pos(game)
    mouse["pos"] = pos
    game.mouse.update()
    game.tower_controller.update_cursor(pos)
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))
    mouse["pos"] = (400, 300)
    game.mouse.update()


# ── the toggle ───────────────────────────────────────────────────────────────


def test_keep_placing_is_off_by_default(game):
    assert game.keep_placing is False
    assert game.tower_controller.keep_placing is False
    assert panel(game)["keep_placing_button"].state is None


def test_the_button_toggles_it_and_shows_it(game, mouse):
    toggle(game, mouse)
    assert game.keep_placing is True
    assert game.tower_controller.keep_placing is True
    button = panel(game)["keep_placing_button"]
    assert button.state == "enabled"
    assert button.images["enabled"] is not button.images[None]  # yellow, not grey

    toggle(game, mouse)
    assert game.keep_placing is False
    assert panel(game)["keep_placing_button"].state is None


@pytest.mark.parametrize("shift", [pygame.K_LSHIFT, pygame.K_RSHIFT])
def test_a_shift_press_toggles_it(game, shift):
    key(game, shift)
    assert game.keep_placing is True
    assert panel(game)["keep_placing_button"].state == "enabled"
    assert game.played == [str(game.click_sound_path)]

    key(game, shift, pygame.KEYUP)  # releasing does nothing
    assert game.keep_placing is True

    key(game, shift)
    assert game.keep_placing is False


@pytest.mark.parametrize(
    "mod",
    [pygame.KMOD_LALT, pygame.KMOD_RALT, pygame.KMOD_LCTRL, pygame.KMOD_LMETA],
    ids=["alt", "right-alt", "ctrl", "meta"],
)
@pytest.mark.parametrize("shift", [pygame.K_LSHIFT, pygame.K_RSHIFT])
def test_shift_with_ctrl_alt_or_meta_does_not_toggle(game, shift, mod):
    # Alt+Shift switches the keyboard layout on Windows; Ctrl+Shift starts
    # shortcuts. Only a plain Shift press flips the toggle.
    key(game, shift, mod=mod | pygame.KMOD_LSHIFT)

    assert game.keep_placing is False
    assert game.played == []
    assert "keep_placing" not in game.settings_store.load()


def test_a_plain_shift_press_with_its_own_mod_toggles(game):
    key(game, pygame.K_LSHIFT, mod=pygame.KMOD_LSHIFT)  # as SDL sends it
    assert game.keep_placing is True


def test_holding_shift_does_nothing_more(game, mouse):
    key(game, pygame.K_LSHIFT)
    key(game, pygame.K_LSHIFT, repeat=True)  # a key repeat, if enabled
    assert game.keep_placing is True

    key(game, pygame.K_1)
    place(game, mouse)  # Shift still held, toggle on: keeps placing
    assert game.tower_controller.buying_tower_type == 1


def test_with_it_on_placement_continues_until_gold_runs_out(game, mouse):
    toggle(game, mouse)
    set_money(game, price(game, 1) * 2)
    key(game, pygame.K_1)

    place(game, mouse)
    assert game.tower_controller.buying_tower_type == 1
    place(game, mouse)

    assert game.game_state.money == 0
    assert game.tower_controller.buying_tower_type == 0  # placement ended
    assert game.keep_placing is True  # the toggle stays on


def test_with_it_off_placement_ends_after_one_tower(game, mouse):
    key(game, pygame.K_1)
    place(game, mouse)
    assert game.tower_controller.buying_tower_type == 0


def test_the_toggle_does_not_start_or_pause_the_run(game, mouse):
    toggle(game, mouse)
    key(game, pygame.K_LSHIFT)
    assert not game.game_state.is_started


# ── the setting ──────────────────────────────────────────────────────────────


def test_the_setting_is_saved_and_restored(game, mouse, make_game):
    toggle(game, mouse)

    assert game.settings_store.load()["keep_placing"] is True
    restarted = make_game()
    assert restarted.keep_placing is True
    assert restarted.tower_controller.keep_placing is True
    assert panel(restarted)["keep_placing_button"].state == "enabled"


def test_a_shift_press_saves_it_too(game, make_game):
    key(game, pygame.K_LSHIFT)
    assert game.settings_store.load()["keep_placing"] is True


def test_old_settings_without_it_load_as_off(game, make_game):
    game.settings_store.save({"music_on": True, "sfx_volume": 0.5})

    restarted = make_game()

    assert restarted.keep_placing is False
    assert panel(restarted)["keep_placing_button"].state is None


def test_reset_to_defaults_turns_it_off(game, mouse):
    toggle(game, mouse)

    game._reset_settings()

    assert game.keep_placing is False
    assert panel(game)["keep_placing_button"].state is None
    assert game.settings_store.load()["keep_placing"] is False


def test_the_state_survives_a_window_resize(game, mouse):
    toggle(game, mouse)
    game.window = pygame.Surface((1280, 720))
    game.set_size((1280, 720))
    game.on_canvas_resized((1280, 720))

    assert panel(game)["keep_placing_button"].state == "enabled"
    assert game.keep_placing is True


# ── the button in the HUD ────────────────────────────────────────────────────


def test_the_button_slides_away_with_the_hud(game, mouse):
    assert "keep_placing_button" in GROUPS["controls"][0]
    assert "keep_placing_button_icon" in GROUPS["controls"][0]
    p = panel(game)
    assert p["keep_placing_button"].rect.contains(p["keep_placing_button_icon"].rect)
    rest = p["keep_placing_button"].rect.center
    key(game, pygame.K_TAB)
    game.hud_slide.update(SLIDE_MS + 50)

    dx, _ = game.hud_slide.offset("controls")
    assert p["keep_placing_button"].rect.move(dx, 0).left >= game.size[0]
    click_at(game, mouse, rest)
    assert game.keep_placing is False  # takes no clicks while away
    key(game, pygame.K_LSHIFT)
    assert game.keep_placing is True  # the key still works


def test_drawing_the_hud_with_the_button_does_not_raise(game, mouse):
    game.draw()
    toggle(game, mouse)
    game.draw()


# ── unaffordable towers ──────────────────────────────────────────────────────


def test_an_unaffordable_tower_looks_disabled(game):
    set_money(game, price(game, 1))  # tower 1 only
    buttons = [panel(game)[f"buy_tower_{i + 1}"] for i in range(4)]

    assert buttons[0].state is None
    for button in buttons[1:]:
        assert button.state == "disabled"
        assert button.images["disabled"] is not button.images[None]


def test_the_look_follows_the_money(game):
    button = panel(game)["buy_tower_3"]
    set_money(game, price(game, 3) - 1)
    assert button.state == "disabled"
    game.game_state.increase_money(1)
    assert button.state is None


def test_a_greyed_look_is_grey(game):
    button = panel(game)["buy_tower_2"]
    image = button.images["disabled"]
    w, h = image.get_size()
    for x, y in ((w // 2, h // 2), (w // 3, h // 2), (w // 2, h // 3)):
        c = image.get_at((x, y))
        if c.a:
            assert c.r == c.g == c.b


def test_the_upgraded_plane_has_a_disabled_look_too(game, mouse):
    set_money(game, game.tower_config.prices[3][1])
    click(game, mouse, panel(game)["upgrade_plane_button"])
    assert game.game_state.plane_level == 2

    assert game.game_state.money == 0
    assert panel(game)["buy_tower_4"].state == "lvl2_disabled"
    game.game_state.increase_money(price(game, 4))
    assert panel(game)["buy_tower_4"].state == "lvl2"


def test_clicking_an_unaffordable_tower_is_denied(game, mouse):
    set_money(game, price(game, 3) - 1)

    click(game, mouse, panel(game)["buy_tower_3"])

    assert game.tower_controller.buying_tower_type == 0
    assert game.played == [denied_sound(game)]
    assert game.hud.is_flashing
    assert panel(game)["coin_text"].color == pygame.Color("red")


@pytest.mark.parametrize("k", [pygame.K_4, pygame.K_KP4])
def test_its_number_key_is_denied_too(game, k):
    set_money(game, price(game, 4) - 1)

    key(game, k)

    assert game.tower_controller.buying_tower_type == 0
    assert game.played == [denied_sound(game)]
    assert game.hud.is_flashing


def test_the_flash_blinks_and_ends(game, fake_ticks):
    set_money(game, 50)  # white counter
    key(game, pygame.K_1)
    coin = panel(game)["coin_text"]
    assert coin.color == pygame.Color("red")

    game.hud.update(FLASH_STEP_MS)
    assert coin.color == pygame.Color("white")
    game.hud.update(FLASH_STEP_MS)
    assert coin.color == pygame.Color("red")
    game.hud.update(FLASH_MS)
    assert not game.hud.is_flashing
    assert coin.color == pygame.Color("white")


def test_the_flash_shows_at_zero_gold_too(game):
    set_money(game, 0)  # the counter is red already
    key(game, pygame.K_1)
    game.hud.update(FLASH_STEP_MS)
    assert panel(game)["coin_text"].color == pygame.Color("white")
    game.hud.update(FLASH_MS)
    assert panel(game)["coin_text"].color == pygame.Color("red")


def test_a_denied_key_brings_the_hidden_money_counter_back(game):
    key(game, pygame.K_TAB)
    game.hud_slide.update(SLIDE_MS + 50)
    set_money(game, 0)
    game.hud_slide.update(5000)  # the money change's own peek is over
    assert not game.hud_slide.groups["money"].shown

    key(game, pygame.K_1)

    assert game.hud_slide.groups["money"].shown


def test_the_unaffordable_plane_upgrade_is_denied_the_same_way(game, mouse):
    set_money(game, game.tower_config.prices[3][1] - 1)

    click(game, mouse, panel(game)["upgrade_plane_button"])

    assert game.game_state.plane_level == 1
    assert game.played == [denied_sound(game)]  # no click on top
    assert game.hud.is_flashing


def test_an_affordable_plane_upgrade_clicks_as_before(game, mouse):
    set_money(game, game.tower_config.prices[3][1])

    click(game, mouse, panel(game)["upgrade_plane_button"])

    assert game.game_state.plane_level == 2
    assert game.played == [str(game.click_sound_path)]


def test_an_affordable_pick_plays_no_denied_sound(game):
    key(game, pygame.K_1)
    assert game.tower_controller.buying_tower_type == 1
    assert denied_sound(game) not in game.played
    assert not game.hud.is_flashing


# ── the maxed plane upgrade ──────────────────────────────────────────────────


def buy_plane_upgrade(game, mouse):
    set_money(game, game.tower_config.prices[3][1] + 1000)
    click(game, mouse, panel(game)["upgrade_plane_button"])
    assert game.game_state.plane_level == 2
    game.played.clear()


def assert_maxed(game):
    button = panel(game)["upgrade_plane_button"]
    assert button.state == "maxed"
    image = button.images["maxed"]
    w, h = image.get_size()
    c = image.get_at((w // 2, h // 2))
    assert c.r == c.g == c.b  # the greyscale look of an unaffordable buy button
    assert panel(game)["upgrade_plane_button_text"].states["hover"] == "MAX"


def test_before_the_upgrade_it_shows_its_price(game):
    button = panel(game)["upgrade_plane_button"]
    assert button.state is None
    price = game.tower_config.prices[3][1]
    label = panel(game)["upgrade_plane_button_text"].states["hover"]
    assert label == (f"{price / 1000:g}K $" if price >= 1000 else f"{price} $")


def test_the_bought_upgrade_is_greyed_and_shows_max(game, mouse):
    rest = panel(game)["upgrade_plane_button"].rect.copy()

    buy_plane_upgrade(game, mouse)

    assert_maxed(game)
    assert panel(game)["upgrade_plane_button"].rect == rest  # the column stays put


def test_the_maxed_look_stays_while_hovered(game, mouse):
    buy_plane_upgrade(game, mouse)
    button = panel(game)["upgrade_plane_button"]
    pos = button.rect.center
    mouse["pos"] = pos
    game.mouse.update()
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0)))
    game.update()
    game.draw()

    assert button._active_surface is button.images["maxed"]
    assert panel(game)["upgrade_plane_button_text"].text == "MAX"


def test_a_click_on_the_maxed_upgrade_does_nothing(game, mouse):
    buy_plane_upgrade(game, mouse)
    money = game.game_state.money

    click(game, mouse, panel(game)["upgrade_plane_button"])
    set_money(game, 0)
    game.played.clear()
    click(game, mouse, panel(game)["upgrade_plane_button"])  # broke, still no denial

    assert game.game_state.plane_level == 2
    assert money > 0
    assert game.played == []  # no click, no denied sound
    assert not game.hud.is_flashing
    assert_maxed(game)


def test_the_maxed_upgrade_is_restored_from_a_save(game, mouse, make_game):
    buy_plane_upgrade(game, mouse)
    game._leave_game_for_main_menu()

    restarted = make_game()
    assert panel(restarted)["upgrade_plane_button"].state is None  # a new game
    restarted._load_game()

    assert restarted.game_state.plane_level == 2
    assert_maxed(restarted)


def test_a_new_game_brings_the_upgrade_back(game, mouse):
    buy_plane_upgrade(game, mouse)

    game._start_new_game()

    assert panel(game)["upgrade_plane_button"].state is None
    assert panel(game)["upgrade_plane_button_text"].states["hover"] != "MAX"


def test_the_maxed_upgrade_survives_a_window_resize(game, mouse):
    buy_plane_upgrade(game, mouse)
    game.window = pygame.Surface((1280, 720))
    game.set_size((1280, 720))
    game.on_canvas_resized((1280, 720))

    assert_maxed(game)


def test_the_label_goes_back_to_upg_planes_when_not_hovered(game, mouse):
    buy_plane_upgrade(game, mouse)  # bought while hovered
    away = (400, 300)
    mouse["pos"] = away
    game.mouse.update()
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=away, rel=(0, 0)))
    game.update()

    assert panel(game)["upgrade_plane_button_text"].text == "UPG PLANES"
