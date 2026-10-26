"""The pause panel in a real Game() (saves and settings in a temporary
directory): opening when a running game is paused and closing on resume,
its music/SFX sliders changing the volume live and being saved with the
settings, the in-game music toggle being gone (the menus keep theirs), and
the panel fitting on screen at every window size."""

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


def pause_objects(game):
    return [panel(game)[name] for name in PAUSE_PANEL_OBJECTS]


def is_shown(game) -> bool:
    shown = [obj.active for obj in pause_objects(game)]
    assert all(shown) or not any(shown), "the panel shows only in part"
    return game.pause_panel.is_open and all(shown)


def press_space(game):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))


def click(game, mouse, pos):
    mouse["pos"] = pos
    game.mouse.update()
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def slide_to(game, mouse, slider, ratio):
    """Press on the slider and drag to `ratio` of its width, then release."""
    rect = slider.rect
    start = (rect.left + 1, rect.centery)
    end = (round(rect.left + rect.width * ratio), rect.centery)
    for kind, pos in (
        (pygame.MOUSEBUTTONDOWN, start),
        (pygame.MOUSEMOTION, end),
        (pygame.MOUSEBUTTONUP, end),
    ):
        mouse["pos"] = pos
        game.mouse.update()
        extra = {"button": 1} if kind != pygame.MOUSEMOTION else {"rel": (0, 0)}
        game.handle_event(pygame.event.Event(kind, pos=pos, **extra))


def start_and_pause(game):
    game.panel_manager.current_panel = "game"
    press_space(game)  # start the first wave
    press_space(game)  # pause


def resize(game, size):
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)


# ── opening and closing ──────────────────────────────────────────────────────


def test_the_panel_is_hidden_in_a_new_game(game):
    assert not is_shown(game)


def test_starting_the_first_wave_does_not_open_it(game):
    press_space(game)

    assert game.game_state.is_started
    assert not is_shown(game)


def test_pausing_a_running_game_opens_it(game):
    start_and_pause(game)

    assert not game.game_state.is_started
    assert is_shown(game)


def test_the_hud_pause_button_opens_it_too(game, mouse):
    press_space(game)

    click(game, mouse, panel(game)["start_pause_button"].rect.center)

    assert not game.game_state.is_started
    assert is_shown(game)


def test_resuming_with_space_closes_it(game):
    start_and_pause(game)

    press_space(game)

    assert game.game_state.is_started
    assert not is_shown(game)
    assert panel(game)["start_pause_button_icon"].state == "pause"


def test_resuming_with_the_hud_button_closes_it(game, mouse):
    start_and_pause(game)

    click(game, mouse, panel(game)["start_pause_button"].rect.center)

    assert game.game_state.is_started
    assert not is_shown(game)


def test_the_resume_button_closes_it(game, mouse):
    start_and_pause(game)

    click(game, mouse, panel(game)["pause_resume"].rect.center)

    assert game.game_state.is_started
    assert not is_shown(game)
    assert panel(game)["start_pause_button_icon"].state == "pause"


def test_the_panel_does_not_cover_the_hud_resume_button(game):
    start_and_pause(game)

    bg = panel(game)["pause_panel_bg"].rect
    assert not bg.colliderect(panel(game)["start_pause_button"].rect)


def test_clicks_on_the_panel_do_not_reach_the_map(game):
    start_and_pause(game)

    assert game.tower_controller._is_over_ui(panel(game)["pause_panel_bg"].rect.center)


def test_tab_hides_the_hud_but_leaves_the_panel_and_its_resume_button(game, mouse):
    start_and_pause(game)

    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    game.hud_slide.update(1000)

    assert not game.hud_slide.shown
    assert is_shown(game)
    click(game, mouse, panel(game)["pause_resume"].rect.center)
    assert game.game_state.is_started


def test_leaving_for_the_menu_closes_it(game, mouse):
    start_and_pause(game)

    click(game, mouse, panel(game)["menu_button"].rect.center)

    assert game.panel_manager.current_panel == "main_menu"
    assert not is_shown(game)


def test_escape_closes_it(game):
    start_and_pause(game)

    game.on_exit_request()

    assert game.panel_manager.current_panel == "main_menu"
    assert not is_shown(game)


def test_continuing_a_saved_game_does_not_open_it(game, mouse):
    start_and_pause(game)
    game.on_exit_request()  # saves the run

    game._load_game()

    assert game.panel_manager.current_panel == "game"
    assert not is_shown(game)


def test_it_stays_open_through_a_window_resize(game):
    start_and_pause(game)

    resize(game, (1280, 720))

    assert is_shown(game)


def test_drawing_the_open_panel_does_not_raise(game):
    start_and_pause(game)
    game.draw()


# ── volume ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind, volume", [("music", "music_volume"), ("sfx", "sfx_volume")]
)
def test_a_slider_changes_the_volume_live(game, mouse, kind, volume):
    start_and_pause(game)

    slide_to(game, mouse, panel(game)[f"pause_{kind}_volume_slider"], 0.25)

    level = getattr(game.audio, volume)()
    assert level == pytest.approx(0.25, abs=0.01)
    label = panel(game)[f"pause_{kind}_volume_value_text"].text
    assert label == f"{round(level * 100)}%"


@pytest.mark.parametrize("kind", ["music", "sfx"])
def test_the_settings_screen_shows_the_same_volume(game, mouse, kind):
    start_and_pause(game)

    slide_to(game, mouse, panel(game)[f"pause_{kind}_volume_slider"], 0.4)

    pause_slider = panel(game)[f"pause_{kind}_volume_slider"]
    settings = game.panel_manager["settings"]
    assert settings[f"{kind}_volume_slider"].value == pause_slider.value
    assert (
        settings[f"{kind}_volume_value_text"].text
        == panel(game)[f"pause_{kind}_volume_value_text"].text
    )


def test_a_settings_screen_change_shows_on_the_pause_panel(game):
    game._on_music_volume_changed(0.3)

    level = game.audio.music_volume()  # the mixer rounds to its own steps
    assert level == pytest.approx(0.3, abs=0.01)
    assert panel(game)["pause_music_volume_slider"].value == pytest.approx(level)
    assert panel(game)["pause_music_volume_value_text"].text == "30%"


def test_the_volumes_are_saved_with_the_settings_on_resume(game, mouse, make_game):
    start_and_pause(game)
    slide_to(game, mouse, panel(game)["pause_music_volume_slider"], 0.25)
    slide_to(game, mouse, panel(game)["pause_sfx_volume_slider"], 0.6)
    music, sfx = game.audio.music_volume(), game.audio.sfx_volume()

    press_space(game)  # resume

    saved = SaveStore("settings", directory=game.settings_store.directory).load()
    assert saved["music_volume"] == pytest.approx(music)
    assert saved["sfx_volume"] == pytest.approx(sfx)
    restarted = make_game()
    assert restarted.audio.music_volume() == pytest.approx(music)
    assert restarted.audio.sfx_volume() == pytest.approx(sfx)
    assert restarted.panel_manager["game"]["pause_music_volume_slider"].value == (
        pytest.approx(music)
    )


def test_the_volumes_are_saved_when_leaving_for_the_menu(game, mouse):
    start_and_pause(game)
    slide_to(game, mouse, panel(game)["pause_music_volume_slider"], 0.5)

    game.on_exit_request()

    saved = game.settings_store.load()
    assert saved["music_volume"] == pytest.approx(game.audio.music_volume())


def test_the_settings_store_is_in_the_temporary_folder(game, saves):
    assert game.settings_store.path.parent == saves


# ── music toggle ─────────────────────────────────────────────────────────────


def test_the_game_has_no_music_toggle(game):
    assert "music_toggle_button" not in panel(game)
    assert "music_toggle_icon" not in panel(game)
    controls = GROUPS["controls"][0]
    assert not any(name.startswith("music_toggle") for name in controls)


@pytest.mark.parametrize("tab", MENU_PANELS)
def test_the_menus_keep_their_music_toggle(game, tab):
    assert "music_toggle_button" in game.panel_manager[tab]
    assert "music_toggle_icon" in game.panel_manager[tab]


def test_the_main_menu_toggle_still_works(game, mouse):
    game.panel_manager.current_panel = "main_menu"

    click(
        game, mouse, game.panel_manager["main_menu"]["music_toggle_button"].rect.center
    )

    assert game.audio.is_music_paused
    assert game.panel_manager["main_menu"]["music_toggle_icon"].state == "paused"


# ── fitting on screen ────────────────────────────────────────────────────────


@pytest.mark.parametrize("size", [*COMMON_RESOLUTIONS, (800, 600), (1024, 768)])
def test_the_panel_fits_at_every_window_size(game, size):
    resize(game, size)
    start_and_pause(game)

    p = panel(game)
    screen = pygame.Rect(0, 0, *size)
    bg = p["pause_panel_bg"].rect
    assert screen.contains(bg)
    for name in PAUSE_PANEL_OBJECTS[1:]:
        assert bg.contains(p[name].rect), name
    # Clear of the HUD: the counters, the control buttons and the tower bar.
    hud = (
        "level_text",
        "live_text",
        "coin_text",
        "control_panel_bg",
        "menu_button",
        "start_pause_button",
        "speed_toggle_button",
        "upgrade_plane_button",
        "tower_panel_bg",
    )
    for name in hud:
        assert not bg.colliderect(p[name].rect), name
