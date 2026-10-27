"""Auto-pause between waves (#34) in a real Game() (saves and settings in a
temporary directory): the HUD's hourglass toggle, the run pausing as each
wave is cleared while it's on and carrying on as before while it's off, the
setting being saved, restored and reset, the button sliding away with the
HUD and fitting at every window size, and the menu demo being unaffected."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore
from pygamine.app.application import COMMON_RESOLUTIONS
from ui.hud_slide import GROUPS, SLIDE_MS

COLUMN = (
    "menu_button",
    "start_pause_button",
    "auto_pause_button",
    "speed_toggle_button",
    "upgrade_plane_button",
)
MAX_TICKS = 20_000


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
        return g

    return make


@pytest.fixture
def game(make_game):
    return make_game()


def panel(game):
    return game.panel_manager["game"]


def click(game, mouse, obj):
    pos = obj.rect.center
    mouse["pos"] = pos
    game.mouse.update()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))
    mouse["pos"] = (400, 300)
    game.mouse.update()


def space(game):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))


def toggle(game, mouse):
    click(game, mouse, panel(game)["auto_pause_button"])


def play_until_cleared_or_next(game) -> None:
    """Ticks the started run, killing every enemy as it spawns, until it
    pauses or the next wave begins."""
    level = game.game_state.level
    for _ in range(MAX_TICKS):
        game._tick()
        game.enemies.clear()
        if not game.game_state.is_started or game.game_state.level != level:
            return
    raise AssertionError("the wave never ended")


def play_until_next_wave(game) -> int:
    """Ticks until the level changes; returns how many ticks that took."""
    level = game.game_state.level
    for n in range(MAX_TICKS):
        if game.game_state.level != level:
            return n
        game._tick()
        game.enemies.clear()
    raise AssertionError("the next wave never came")


def start(game):
    space(game)
    assert game.game_state.is_started


# ── off (the default) ────────────────────────────────────────────────────────


def test_auto_pause_is_off_by_default(game):
    assert game.auto_pause is False
    assert panel(game)["auto_pause_button"].state is None


def test_off_the_next_wave_comes_on_its_own_as_before(game):
    start(game)

    play_until_cleared_or_next(game)

    assert game.game_state.level == 2
    assert game.game_state.is_started


# ── on ───────────────────────────────────────────────────────────────────────


def test_the_button_toggles_auto_pause_and_shows_it(game, mouse):
    toggle(game, mouse)
    assert game.auto_pause is True
    assert panel(game)["auto_pause_button"].state == "enabled"
    button = panel(game)["auto_pause_button"]
    assert "enabled" in button.images  # a real highlighted look, not a no-op
    assert button.images["enabled"] is not button.images[None]

    toggle(game, mouse)
    assert game.auto_pause is False
    assert panel(game)["auto_pause_button"].state is None


def test_the_toggle_does_not_start_or_pause_the_run(game, mouse):
    toggle(game, mouse)
    assert not game.game_state.is_started
    start(game)
    toggle(game, mouse)
    assert game.game_state.is_started


def test_on_the_run_pauses_once_the_wave_is_cleared(game, mouse):
    toggle(game, mouse)
    start(game)

    play_until_cleared_or_next(game)

    wm = game.wave_manager
    assert not game.game_state.is_started
    assert panel(game)["start_pause_button_icon"].state is None  # shows "play"
    assert game.game_state.level == 1  # the counter hasn't moved yet
    assert wm._queue_index == len(wm._spawn_queue)
    assert not game.enemies


def test_start_brings_the_next_wave_and_the_level_advances_once(game, mouse):
    toggle(game, mouse)
    start(game)
    play_until_cleared_or_next(game)

    start(game)
    play_until_next_wave(game)

    assert game.game_state.level == 2
    assert game.game_state.is_started
    assert "2" in panel(game)["level_text"].text


def test_it_pauses_again_after_the_next_wave(game, mouse):
    toggle(game, mouse)
    start(game)
    play_until_cleared_or_next(game)
    start(game)
    play_until_next_wave(game)

    play_until_cleared_or_next(game)

    assert not game.game_state.is_started
    assert game.game_state.level == 2


def test_turning_it_off_while_paused_lets_waves_run_on(game, mouse):
    toggle(game, mouse)
    start(game)
    play_until_cleared_or_next(game)
    toggle(game, mouse)
    start(game)
    play_until_next_wave(game)

    play_until_cleared_or_next(game)

    assert game.game_state.level == 3
    assert game.game_state.is_started


def test_a_run_continued_at_a_cleared_wave_does_not_pause_again(game, mouse, make_game):
    toggle(game, mouse)
    start(game)
    play_until_cleared_or_next(game)
    game._leave_game_for_main_menu()

    restarted = make_game()
    restarted._load_game()
    assert restarted.auto_pause
    start(restarted)
    play_until_cleared_or_next(restarted)

    assert restarted.game_state.level == 2
    assert restarted.game_state.is_started


# ── the setting ──────────────────────────────────────────────────────────────


def test_the_setting_is_saved_and_restored(game, mouse, make_game):
    toggle(game, mouse)

    assert game.settings_store.load()["auto_pause_between_waves"] is True
    restarted = make_game()
    assert restarted.auto_pause is True
    assert panel(restarted)["auto_pause_button"].state == "enabled"


def test_old_settings_without_it_load_as_off(game, make_game):
    game.settings_store.save({"music_on": True, "sfx_volume": 0.5})

    restarted = make_game()

    assert restarted.auto_pause is False
    assert panel(restarted)["auto_pause_button"].state is None


def test_reset_to_defaults_turns_it_off(game, mouse):
    toggle(game, mouse)

    game._reset_settings()

    assert game.auto_pause is False
    assert panel(game)["auto_pause_button"].state is None
    assert game.settings_store.load()["auto_pause_between_waves"] is False


def test_the_state_survives_a_window_resize(game, mouse):
    toggle(game, mouse)
    game.window = pygame.Surface((1280, 720))
    game.set_size((1280, 720))
    game.on_canvas_resized((1280, 720))

    assert panel(game)["auto_pause_button"].state == "enabled"


# ── the button in the HUD ────────────────────────────────────────────────────


def test_the_button_slides_away_with_the_hud(game, mouse, fake_ticks):
    assert "auto_pause_button" in GROUPS["controls"][0]
    assert "auto_pause_button_icon" in GROUPS["controls"][0]
    rest = panel(game)["auto_pause_button"].rect.center
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    game.hud_slide.update(SLIDE_MS + 50)

    dx, _ = game.hud_slide.offset("controls")
    assert panel(game)["auto_pause_button"].rect.move(dx, 0).left >= game.size[0]
    mouse["pos"] = rest
    game.mouse.update()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=rest))
    assert game.auto_pause is False  # takes no clicks while away


@pytest.mark.parametrize("size", [*COMMON_RESOLUTIONS, (800, 600), (1024, 768)])
def test_the_control_column_fits_at_every_window_size(game, size):
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)

    p = panel(game)
    screen = pygame.Rect(0, 0, *size)
    rects = [p[name].rect for name in COLUMN]
    for name, rect in zip(COLUMN, rects):
        assert screen.contains(rect), name
    for upper, lower in zip(rects, rects[1:]):
        assert upper.bottom <= lower.top  # stacked in order, no overlap
    assert p["auto_pause_button"].rect.contains(p["auto_pause_button_icon"].rect)
    for other in ("tower_panel_bg", "coin_text", "level_text"):
        assert not rects[-1].colliderect(p[other].rect), other
        assert not p["auto_pause_button"].rect.colliderect(p[other].rect), other


def test_drawing_the_hud_with_the_button_does_not_raise(game, mouse):
    game.draw()
    toggle(game, mouse)
    game.draw()


# ── the menu demo ────────────────────────────────────────────────────────────


def test_the_menu_demo_never_auto_pauses(game, mouse):
    toggle(game, mouse)
    demo = game.menu_demo
    assert demo.wave_manager.on_wave_cleared is None
    level = demo.game_state.level

    for _ in range(MAX_TICKS):
        demo._tick()
        demo.enemies.clear()
        if demo.game_state.level != level:
            break

    assert demo.game_state.level == level + 1
    assert demo.game_state.is_started
