"""HudSlide -- Tab slides the in-game HUD off the screen edges and back.

Built on a real Game(), since the slide measures the real panel objects that
panels.yaml lays out for the window size. The slide is drawn only, so these
check where each object is drawn (its resting rect plus its group's offset).
Saves go to a temporary directory.
"""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore
from ui.hud_slide import BUY_BUTTONS, GROUPS, PEEK_MS, SLIDE_MS

MOUSE = {"pos": (400, 300)}
DONE = SLIDE_MS + 50  # long enough for any slide to finish


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    MOUSE["pos"] = (400, 300)  # mid-window, so the camera doesn't edge-scroll
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: MOUSE["pos"])

    def build(window_size=None):
        if window_size is not None:
            SaveStore("settings", directory=tmp_path).save(
                {"window_mode": "windowed", "window_size": list(window_size)}
            )
        game = Game()
        game._start_new_game()
        return game

    return build


def play(game, fake_ticks, ms, fps=60):
    for _ in range(round(ms / (1000 / fps))):
        fake_ticks["t"] += 1000 / fps
        game.update()


def press(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    game.handle_event(pygame.event.Event(pygame.KEYUP, key=key))


def click(game, pos):
    MOUSE["pos"] = pos
    game.mouse.update()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def drawn(game, group):
    """Where each object of a group is drawn right now."""
    panel = game.panel_manager["game"]
    dx, dy = game.hud_slide.offset(group)
    return {n: pygame.Rect(panel[n].rect).move(dx, dy) for n in GROUPS[group][0]}


def drawn_all(game):
    return {g: drawn(game, g) for g in GROUPS}


def assert_hidden(game, group):
    canvas = game.game_area
    for name, rect in drawn(game, group).items():
        assert not rect.colliderect(canvas), (group, name)
    if group == "tower_bar":  # the 1-4 badges over the buttons' corners go too
        for name in BUY_BUTTONS:
            assert drawn(game, group)[name].top - 8 >= canvas.height, name


def assert_shown(game, group):
    panel = game.panel_manager["game"]
    for name, rect in drawn(game, group).items():
        assert rect == panel[name].rect, (group, name)


def hide(game, fake_ticks):
    press(game, pygame.K_TAB)
    play(game, fake_ticks, DONE)


# ── toggling ──────────────────────────────────────────────────────────────────


def test_tab_slides_the_whole_hud_out_and_back(make_game, fake_ticks):
    game = make_game()
    resting = drawn_all(game)

    hide(game, fake_ticks)
    assert not game.hud_slide.shown
    for group in GROUPS:
        assert_hidden(game, group)

    press(game, pygame.K_TAB)
    play(game, fake_ticks, DONE)
    assert game.hud_slide.shown
    assert drawn_all(game) == resting


def test_each_part_leaves_by_its_nearest_edge(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)
    canvas = game.game_area

    assert all(
        r.right <= 0
        for g in ("level", "lives", "money")
        for r in drawn(game, g).values()
    )
    assert all(r.left >= canvas.width for r in drawn(game, "controls").values())
    assert all(r.top >= canvas.height for r in drawn(game, "tower_bar").values())


def test_the_slide_eases_out_over_about_200_ms(make_game, fake_ticks):
    game = make_game()
    distance = game.hud_slide.groups["tower_bar"].distance

    press(game, pygame.K_TAB)
    play(game, fake_ticks, SLIDE_MS / 2)
    assert game.hud_slide.is_sliding
    assert game.hud_slide.offset("tower_bar")[1] > distance / 2  # ease-out

    play(game, fake_ticks, SLIDE_MS / 2 + 50)
    assert not game.hud_slide.is_sliding


def test_the_screen_shows_the_slide(make_game, fake_ticks):
    """Drawn, the bar's resting place shows the map once the HUD is hidden."""
    game = make_game()
    bar = game.panel_manager["game"]["tower_panel_bg"].rect
    probe = (bar.left + 2, bar.bottom - 2)
    game.draw()
    shown = game.window.get_at(probe)

    hide(game, fake_ticks)
    game.draw()

    assert game.window.get_at(probe) != shown
    assert game.panel_manager["game"]["tower_panel_bg"].rect == bar  # rest kept


# ── input while hidden ────────────────────────────────────────────────────────


def test_hidden_buy_buttons_ignore_clicks_and_hover(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)

    button = game.panel_manager["game"]["buy_tower_1"]
    click(game, button.rect.center)

    assert game.tower_controller.buying_tower_type == 0
    assert not button.is_mouse_over(button.rect.center)


def test_hidden_control_buttons_ignore_clicks(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)

    click(game, game.panel_manager["game"]["speed_toggle_button"].rect.center)
    click(game, game.panel_manager["game"]["menu_button"].rect.center)

    assert game.game_state.speed == 1
    assert game.panel_manager.current_panel == "game"


def test_buttons_take_clicks_again_once_shown(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)
    press(game, pygame.K_TAB)
    play(game, fake_ticks, DONE)

    click(game, game.panel_manager["game"]["buy_tower_2"].rect.center)

    assert game.tower_controller.buying_tower_type == 2


def test_a_hidden_hud_does_not_block_the_map_beneath_it(make_game, fake_ticks):
    game = make_game()
    bar = game.panel_manager["game"]["tower_panel_bg"].rect
    assert game.tower_controller._is_over_ui(bar.center)

    hide(game, fake_ticks)

    assert not game.tower_controller._is_over_ui(bar.center)


def test_hotkeys_still_work_while_hidden(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)

    press(game, pygame.K_1)  # the one tower the starting gold affords
    press(game, pygame.K_SPACE)

    assert game.tower_controller.buying_tower_type == 1
    assert game.game_state.is_started


def test_hiding_keeps_a_placement_in_progress(make_game, fake_ticks):
    game = make_game()
    press(game, pygame.K_1)

    hide(game, fake_ticks)

    assert game.tower_controller.buying_tower_type == 1


# ── counters peeking back ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "group, change",
    [
        ("money", lambda gs: gs.increase_money(25)),
        ("lives", lambda gs: gs.decrease_lives(1)),
    ],
)
def test_a_changed_counter_shows_for_a_while_then_hides(
    make_game, fake_ticks, group, change
):
    game = make_game()
    hide(game, fake_ticks)

    change(game.game_state)
    play(game, fake_ticks, DONE)
    assert_shown(game, group)
    others = [g for g in GROUPS if g != group]
    for other in others:
        assert_hidden(game, other)

    play(game, fake_ticks, PEEK_MS - DONE - 100)
    assert_shown(game, group)  # still up, about 1.5 s in

    play(game, fake_ticks, 100 + DONE + 50)
    assert_hidden(game, group)
    assert not game.hud_slide.shown


def test_another_change_keeps_the_counter_up(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)

    game.game_state.increase_money(5)
    play(game, fake_ticks, PEEK_MS - 300)
    game.game_state.increase_money(5)
    play(game, fake_ticks, 600)

    assert_shown(game, "money")


def test_counters_do_not_peek_while_the_hud_is_shown(make_game, fake_ticks):
    game = make_game()
    game.game_state.increase_money(25)
    play(game, fake_ticks, PEEK_MS + DONE)

    for group in GROUPS:
        assert_shown(game, group)


def test_tab_during_a_peek_hides_or_shows_everything(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)
    game.game_state.increase_money(5)
    play(game, fake_ticks, DONE)

    press(game, pygame.K_TAB)  # show the HUD
    play(game, fake_ticks, PEEK_MS + DONE)

    for group in GROUPS:
        assert_shown(game, group)  # the peek's timer didn't hide money again


# ── counters whose text grows ────────────────────────────────────────────────


def widen_counters(game):
    """Longer level, lives and money texts, which lay themselves out wider."""
    panel = game.panel_manager["game"]
    before = {n: panel[n].rect.right for n in ("level_text", "live_text", "coin_text")}
    gs = game.game_state
    for _ in range(11):  # "Round 1" -> "Round 12", as in issue #43
        gs.advance_level()
    gs.increase_money(1_000_000)
    gs.lives = 100_000
    gs.decrease_lives(1)
    for name, right in before.items():
        assert panel[name].rect.right > right, name  # really wider now


def test_counters_widened_before_hiding_leave_the_screen(make_game, fake_ticks):
    game = make_game()
    widen_counters(game)

    hide(game, fake_ticks)

    for group in GROUPS:
        assert_hidden(game, group)


def test_counters_widened_while_hidden_stay_off_the_screen(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)

    widen_counters(game)  # the level stays hidden; money and lives peek back
    for group in ("level", "tower_info", "controls", "tower_bar"):
        assert_hidden(game, group)
    play(game, fake_ticks, PEEK_MS + DONE)

    assert not game.hud_slide.shown
    for group in GROUPS:
        assert_hidden(game, group)


def test_no_sliver_of_a_two_digit_level_is_drawn(make_game, fake_ticks):
    """Drawn, the strip just left of the screen edge shows the same with the
    level at 12 as at 1 (the map, not the counter's background)."""
    game = make_game()
    level = game.panel_manager["game"]["level_text"].rect
    probes = [(x, level.centery) for x in range(0, 12)]
    hide(game, fake_ticks)
    game.draw()
    clean = [game.window.get_at(p) for p in probes]

    for _ in range(11):
        game.game_state.advance_level()
    game.draw()

    assert [game.window.get_at(p) for p in probes] == clean


# ── window size, pause, speed ─────────────────────────────────────────────────


@pytest.mark.parametrize("window_size", [(1280, 720), (800, 600)])
def test_it_slides_relative_to_the_scaled_layout(make_game, fake_ticks, window_size):
    game = make_game(window_size)
    assert game.game_area.size == window_size
    resting = drawn_all(game)

    hide(game, fake_ticks)
    for group in GROUPS:
        assert_hidden(game, group)

    press(game, pygame.K_TAB)
    play(game, fake_ticks, DONE)
    assert drawn_all(game) == resting


def test_a_resize_while_hidden_keeps_it_hidden(make_game, fake_ticks):
    game = make_game()
    hide(game, fake_ticks)

    game.on_canvas_resized((800, 600))  # rebuilds the panels at their resting places
    assert game.game_area.size == (800, 600)

    for group in GROUPS:
        assert_hidden(game, group)
    press(game, pygame.K_TAB)
    play(game, fake_ticks, DONE)
    for group in GROUPS:
        assert_shown(game, group)


def test_it_slides_while_paused(make_game, fake_ticks):
    game = make_game()
    game.game_state.is_started = False

    hide(game, fake_ticks)

    for group in GROUPS:
        assert_hidden(game, group)
    assert game.game_state.time_ms == 0  # the game itself stayed paused


def test_game_speed_does_not_change_the_slide(make_game, fake_ticks):
    offsets = []
    for speed in (1, 4):
        game = make_game()
        game.game_state.is_started = True
        game.game_state.speed = speed
        press(game, pygame.K_TAB)
        play(game, fake_ticks, SLIDE_MS / 2)
        offsets.append(game.hud_slide.offset("tower_bar"))

    assert offsets[0] == offsets[1]
