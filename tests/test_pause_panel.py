"""The pause menu in a real Game() (saves and settings in a temporary
directory): Esc or the HUD menu button opening it at any point of a run and
pausing it, closing it restoring the run as it was, its Main menu / Settings
/ Music / Back buttons, the in-game music button being gone (the menus keep
theirs) and the menu fitting on screen at every window size."""

from functools import partial

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore
from pygamine.app.application import COMMON_RESOLUTIONS
from ui.hud_slide import GROUPS
from ui.pause_panel import PAUSE_PANEL_OBJECTS

MENU_PANELS = ("main_menu", "play_menu", "credits", "settings")


@pytest.fixture
def saves(tmp_path):
    return tmp_path


@pytest.fixture
def mouse(monkeypatch):
    state = {"pos": (0, 0)}
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: state["pos"])
    return state


@pytest.fixture
def make_game(monkeypatch, saves, mouse, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=saves))

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


def is_shown(game) -> bool:
    shown = [panel(game)[name].active for name in PAUSE_PANEL_OBJECTS]
    assert all(shown) or not any(shown), "the menu shows only in part"
    return game.pause_panel.is_open and all(shown)


def key(game, k):
    """A key press as the real loop delivers it: pygamine's core handling
    (Esc -> on_exit_request) first, then Game.handle_event."""
    event = pygame.event.Event(pygame.KEYDOWN, key=k)
    if k == pygame.K_ESCAPE:
        game.on_exit_request()
    game.handle_event(event)


def esc(game):
    key(game, pygame.K_ESCAPE)


def click(game, mouse, obj):
    pos = obj.rect.center
    mouse["pos"] = pos
    game.mouse.update()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def resize(game, size):
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)


def run_waves(game):
    key(game, pygame.K_SPACE)
    assert game.game_state.is_started


# ── opening ──────────────────────────────────────────────────────────────────


def test_the_menu_is_hidden_in_a_new_game(game):
    assert not is_shown(game)


def test_esc_opens_it_before_the_first_wave(game):
    esc(game)

    assert is_shown(game)
    assert not game.game_state.is_started
    assert game.panel_manager.current_panel == "game"


def test_esc_opens_it_during_a_wave_and_pauses(game):
    run_waves(game)

    esc(game)

    assert is_shown(game)
    assert not game.game_state.is_started
    assert panel(game)["start_pause_button_icon"].state is None


def test_esc_opens_it_between_waves(game):
    run_waves(game)
    game.enemies.clear()  # the wave is cleared; the next one is on its timer

    esc(game)

    assert is_shown(game)
    assert not game.game_state.is_started


def test_the_hud_menu_button_opens_it(game, mouse):
    run_waves(game)

    click(game, mouse, panel(game)["menu_button"])

    assert is_shown(game)
    assert not game.game_state.is_started
    assert game.panel_manager.current_panel == "game"


def test_space_still_pauses_without_the_menu(game):
    run_waves(game)

    key(game, pygame.K_SPACE)

    assert not game.game_state.is_started
    assert not is_shown(game)


def test_the_game_stands_still_while_it_is_open(game, fake_ticks):
    run_waves(game)
    esc(game)
    before = game.game_state.time_ms

    for t in range(16, 1000, 16):
        fake_ticks["t"] = t
        game.update()

    assert game.game_state.time_ms == before


# ── closing ──────────────────────────────────────────────────────────────────


def test_esc_closes_it_and_a_running_game_resumes(game):
    run_waves(game)
    esc(game)

    esc(game)

    assert not is_shown(game)
    assert game.game_state.is_started
    assert panel(game)["start_pause_button_icon"].state == "pause"


def test_back_closes_it_and_a_running_game_resumes(game, mouse):
    run_waves(game)
    esc(game)

    click(game, mouse, panel(game)["pause_back"])

    assert not is_shown(game)
    assert game.game_state.is_started


def test_a_game_paused_before_stays_paused(game, mouse):
    run_waves(game)
    key(game, pygame.K_SPACE)  # paused with Space
    esc(game)

    click(game, mouse, panel(game)["pause_back"])

    assert not is_shown(game)
    assert not game.game_state.is_started


def test_a_game_not_started_yet_stays_waiting(game):
    esc(game)
    esc(game)

    assert not is_shown(game)
    assert not game.game_state.is_started


def test_while_open_it_takes_the_game_input(game, mouse):
    esc(game)

    key(game, pygame.K_SPACE)
    key(game, pygame.K_TAB)
    click(game, mouse, panel(game)["buy_tower_1"])

    assert is_shown(game)
    assert not game.game_state.is_started
    assert game.hud_slide.shown
    assert game.tower_controller.buying_tower_type == 0


def test_it_stays_open_through_a_window_resize(game):
    esc(game)

    resize(game, (1280, 720))

    assert is_shown(game)


# ── main menu ────────────────────────────────────────────────────────────────


def test_main_menu_saves_the_run_and_leaves(game, mouse):
    run_waves(game)
    game.game_state.money = 345
    esc(game)

    click(game, mouse, panel(game)["pause_main_menu"])

    assert game.panel_manager.current_panel == "main_menu"
    assert not is_shown(game)
    assert game._has_saved_game()
    saved = game.save_store.load()["game_state"]
    assert saved["money"] == 345
    assert saved["is_started"] is False


def test_continue_after_main_menu_has_no_menu_open(game, mouse):
    esc(game)
    click(game, mouse, panel(game)["pause_main_menu"])

    game._load_game()

    assert game.panel_manager.current_panel == "game"
    assert not is_shown(game)


# ── settings ─────────────────────────────────────────────────────────────────


def test_settings_opens_the_settings_screen(game, mouse):
    esc(game)

    click(game, mouse, panel(game)["pause_settings"])

    assert game.panel_manager.current_panel == "settings"


def test_settings_back_returns_to_the_pause_menu(game, mouse):
    run_waves(game)
    esc(game)
    click(game, mouse, panel(game)["pause_settings"])

    click(game, mouse, game.panel_manager["settings"]["back"])

    assert game.panel_manager.current_panel == "game"
    assert is_shown(game)
    assert not game.game_state.is_started  # still paused under the menu


def test_esc_on_settings_returns_to_the_pause_menu(game, mouse):
    esc(game)
    click(game, mouse, panel(game)["pause_settings"])

    esc(game)

    assert game.panel_manager.current_panel == "game"
    assert is_shown(game)


def test_settings_from_the_main_menu_still_goes_back_there(game, mouse):
    esc(game)
    click(game, mouse, panel(game)["pause_settings"])
    esc(game)  # back to the pause menu
    click(game, mouse, panel(game)["pause_main_menu"])

    click(game, mouse, game.panel_manager["main_menu"]["settings"])
    click(game, mouse, game.panel_manager["settings"]["back"])

    assert game.panel_manager.current_panel == "main_menu"


def test_the_run_stays_paused_while_on_settings(game, mouse, fake_ticks):
    run_waves(game)
    esc(game)
    click(game, mouse, panel(game)["pause_settings"])
    before = game.game_state.time_ms

    for t in range(16, 500, 16):
        fake_ticks["t"] = t
        game.update()

    assert game.game_state.time_ms == before


# ── music ────────────────────────────────────────────────────────────────────


def test_music_toggles_the_music_and_every_toggle_follows(game, mouse):
    esc(game)

    click(game, mouse, panel(game)["pause_music"])

    assert game.audio.is_music_paused
    assert panel(game)["pause_music_text"].text == "MUSIC: OFF"
    for tab in MENU_PANELS:
        assert game.panel_manager[tab]["music_toggle_icon"].state == "paused"

    click(game, mouse, panel(game)["pause_music"])

    assert not game.audio.is_music_paused
    assert panel(game)["pause_music_text"].text == "MUSIC: ON"
    for tab in MENU_PANELS:
        assert game.panel_manager[tab]["music_toggle_icon"].state is None


def test_the_main_menu_toggle_shows_on_the_pause_menu(game, mouse):
    game.panel_manager.current_panel = "main_menu"

    click(game, mouse, game.panel_manager["main_menu"]["music_toggle_button"])

    assert game.audio.is_music_paused
    assert panel(game)["pause_music_text"].text == "MUSIC: OFF"


def test_the_music_setting_is_saved_and_restored(game, mouse, make_game):
    esc(game)
    click(game, mouse, panel(game)["pause_music"])

    assert game.settings_store.load()["music_on"] is False
    restarted = make_game()
    assert restarted.audio.is_music_paused
    assert restarted.panel_manager["game"]["pause_music_text"].text == "MUSIC: OFF"
    assert restarted.panel_manager["main_menu"]["music_toggle_icon"].state == "paused"


def test_a_muted_game_stays_muted_through_the_splash_music(game, mouse, make_game):
    esc(game)
    click(game, mouse, panel(game)["pause_music"])
    restarted = make_game()
    restarted.splash = type("NoSplash", (), {"run": lambda self, *args: None})()

    restarted.show_splash()

    assert restarted.audio.is_music_paused


def test_music_on_is_the_default(game):
    assert not game.audio.is_music_paused
    assert panel(game)["pause_music_text"].text == "MUSIC: ON"


def test_the_settings_store_is_in_the_temporary_folder(game, saves):
    assert game.settings_store.path.parent == saves


def test_the_game_has_no_music_button_of_its_own(game):
    assert "music_toggle_button" not in panel(game)
    assert "music_toggle_icon" not in panel(game)
    controls = GROUPS["controls"][0]
    assert not any(name.startswith("music_toggle") for name in controls)


@pytest.mark.parametrize("tab", MENU_PANELS)
def test_the_menus_keep_their_music_toggle(game, tab):
    assert "music_toggle_button" in game.panel_manager[tab]
    assert "music_toggle_icon" in game.panel_manager[tab]


# ── popups ───────────────────────────────────────────────────────────────────


def test_esc_with_the_game_over_popup_leaves_as_before(game):
    game._trigger_game_over()

    esc(game)

    assert game.panel_manager.current_panel == "main_menu"
    assert not is_shown(game)


def test_esc_with_the_victory_popup_saves_and_leaves_as_before(game):
    game._trigger_victory()

    esc(game)

    assert game.panel_manager.current_panel == "main_menu"
    assert not is_shown(game)
    assert game._has_saved_game()


# ── drawing and fitting ──────────────────────────────────────────────────────


def test_drawing_the_open_menu_does_not_raise(game):
    esc(game)
    game.draw()


@pytest.mark.parametrize("size", [*COMMON_RESOLUTIONS, (800, 600), (1024, 768)])
def test_the_menu_fits_at_every_window_size(game, size):
    resize(game, size)
    esc(game)

    p = panel(game)
    screen = pygame.Rect(0, 0, *size)
    assert p["pause_overlay"].rect == screen
    bg = p["pause_panel_bg"].rect
    assert screen.contains(bg)
    for name in PAUSE_PANEL_OBJECTS[2:]:
        assert bg.contains(p[name].rect), name
    texts = [n for n in PAUSE_PANEL_OBJECTS if n.endswith("_text")]
    for name in texts[1:]:  # button labels inside their buttons
        button = p[name.removesuffix("_text")]
        assert button.rect.contains(p[name].rect), name
    buttons = [p[n] for n in ("pause_back", "pause_settings", "pause_music")]
    for upper, lower in zip(buttons, [*buttons[1:], p["pause_main_menu"]]):
        assert upper.rect.bottom <= lower.rect.top


def test_hud_extras_are_not_drawn_over_the_open_menu(game, monkeypatch):
    calls = []
    monkeypatch.setattr(
        game.tower_controller, "draw_shortcuts", lambda s: calls.append("badges")
    )
    monkeypatch.setattr(game.tower_info, "draw_hp_fill", lambda s: calls.append("hp"))

    game.draw()
    assert calls == ["badges", "hp"]

    esc(game)
    calls.clear()
    game.draw()
    assert calls == []
