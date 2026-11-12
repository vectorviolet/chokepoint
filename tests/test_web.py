"""The web build (pygbag, `sys.platform == "emscripten"`), on a real Game().

The tests pretend to be the browser: `sys.platform` says "emscripten" and
pygbag's `platform.window` is a fake page that records what the game asks of it
(open a tab, enter or leave fullscreen) and keeps a `localStorage`. Desktop
behavior is checked next to it, so the two can't drift apart."""

import platform
import sys
from functools import partial
from pathlib import Path

import pygame
import pytest

import app.game
from app.game import Game
from pygamine import SaveStore
from util import web
from util.constants import FULLSCREEN_POLL_FRAMES
from app.settings_tabs import row_objects
from pygamine import Application
from util.paths import resource_root


class FakeStorage:
    def __init__(self):
        self.items: dict[str, str] = {}

    def getItem(self, key):  # noqa: N802
        return self.items.get(key)

    def setItem(self, key, value):  # noqa: N802
        self.items[key] = value

    def removeItem(self, key):  # noqa: N802
        self.items.pop(key, None)


class BlockedStorage:
    """Storage the browser refuses to touch (private or sandboxed frame)."""

    def getItem(self, key):  # noqa: N802
        raise RuntimeError("SecurityError")

    setItem = removeItem = getItem  # noqa: N815


class FakeDocument:
    def __init__(self):
        self.fullscreenElement = None
        self.enter_calls = 0
        self.exit_calls = 0
        self.documentElement = self

    def requestFullscreen(self):  # noqa: N802
        self.enter_calls += 1
        self.fullscreenElement = object()

    def exitFullscreen(self):  # noqa: N802
        self.exit_calls += 1
        self.fullscreenElement = None


class FakeWindow:
    def __init__(self, local_storage=None):
        self.localStorage = local_storage if local_storage else FakeStorage()
        self.document = FakeDocument()
        self.opened: list[tuple[str, str]] = []

    def open(self, url, target):
        self.opened.append((url, target))


@pytest.fixture
def browser(monkeypatch):
    """The page, with the process pretending to run in it."""
    window = FakeWindow()
    monkeypatch.setattr(platform, "window", window, raising=False)
    monkeypatch.setattr(sys, "platform", "emscripten")
    return window


def make_game(monkeypatch, tmp_path):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return Game()


@pytest.fixture
def desktop_game(monkeypatch, tmp_path, fake_ticks):
    return make_game(monkeypatch, tmp_path)


@pytest.fixture
def web_game(monkeypatch, tmp_path, fake_ticks, browser):
    return make_game(monkeypatch, tmp_path)


def click(game, obj):
    game.mouse.position = obj.rect.center
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=obj.rect.center))


def key(game, code):
    game._handle_core_event(
        pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode="", scancode=0)
    )


def settings(game):
    return game.panel_manager["settings"]


# -- the browser helpers -------------------------------------------------------


def test_is_web_follows_sys_platform(monkeypatch):
    assert not web.is_web()
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert web.is_web()


def test_toggle_fullscreen_enters_then_leaves(browser):
    assert not web.is_fullscreen()
    web.toggle_fullscreen()
    assert web.is_fullscreen()
    assert browser.document.enter_calls == 1
    web.toggle_fullscreen()
    assert not web.is_fullscreen()
    assert browser.document.exit_calls == 1


def test_open_in_new_tab_asks_for_a_blank_target(browser):
    web.open_in_new_tab("https://example.test/")
    assert browser.opened == [("https://example.test/", "_blank")]


# -- splash ---------------------------------------------------------------------


def test_desktop_builds_the_splash(desktop_game):
    assert desktop_game.splash is not None


def test_the_web_build_skips_the_splash(web_game):
    assert web_game.splash is None


# -- Exit -----------------------------------------------------------------------


def test_desktop_exit_button_quits(desktop_game, monkeypatch):
    quits = []
    monkeypatch.setattr(desktop_game, "exit", lambda: quits.append(True))
    click(desktop_game, desktop_game.panel_manager["main_menu"]["exit"])
    assert quits == [True]
    assert desktop_game.panel_manager.current_panel == "main_menu"


def test_web_exit_button_opens_the_thanks_screen_instead_of_quitting(
    web_game, monkeypatch
):
    monkeypatch.setattr(web_game, "exit", lambda: pytest.fail("the web build quit"))
    click(web_game, web_game.panel_manager["main_menu"]["exit"])
    assert web_game.panel_manager.current_panel == "thanks"


def test_web_escape_on_the_main_menu_opens_the_thanks_screen(web_game, monkeypatch):
    monkeypatch.setattr(web_game, "exit", lambda: pytest.fail("the web build quit"))
    key(web_game, pygame.K_ESCAPE)
    assert web_game.panel_manager.current_panel == "thanks"


def test_the_rate_button_opens_the_itch_page_in_a_new_tab(web_game, browser):
    web_game._open_thanks()
    click(web_game, web_game.panel_manager["thanks"]["thanks_rate"])
    assert browser.opened == [(web_game.itch_url, "_blank")]
    assert web_game.itch_url == "https://umutcanekinci.itch.io/chokepoint"
    assert web_game.panel_manager.current_panel == "thanks"  # stays on the screen


def test_back_and_escape_leave_the_thanks_screen_for_the_main_menu(web_game):
    web_game._open_thanks()
    click(web_game, web_game.panel_manager["thanks"]["thanks_back"])
    assert web_game.panel_manager.current_panel == "main_menu"

    web_game._open_thanks()
    key(web_game, pygame.K_ESCAPE)
    assert web_game.panel_manager.current_panel == "main_menu"


def test_the_thanks_screen_has_its_own_keyboard_focus(web_game):
    controller = web_game.menu_controllers["thanks"]
    panel = web_game.panel_manager["thanks"]
    assert controller.buttons == [panel["thanks_rate"], panel["thanks_back"]]


def test_the_thanks_screen_uses_the_pause_menus_green_panel(web_game):
    thanks = web_game.panel_manager["thanks"]["thanks_panel_bg"]
    pause = web_game.panel_manager["game"]["pause_panel_bg"]
    corner = pygame.Rect(0, 0, 10, 10)  # the nine-slice's pixel-exact corner
    assert pygame.image.tobytes(
        thanks.require_image().subsurface(corner), "RGBA"
    ) == pygame.image.tobytes(pause.require_image().subsurface(corner), "RGBA")
    assert abs(thanks.rect.centerx - pause.rect.centerx) <= 1  # centered like it
    assert abs(thanks.rect.centery - pause.rect.centery) <= 1


# -- DISPLAY settings -------------------------------------------------------------


def test_desktop_display_tab_is_unchanged(desktop_game):
    desktop_game._open_settings("main_menu")
    p = settings(desktop_game)
    assert all(p[n].active for n in row_objects("window_size"))
    assert p["window_mode_label_text"].text == "WINDOW MODE"
    names = {desktop_game.settings_tabs.name_of(b) for b in _focus(desktop_game)}
    assert "window_size_back_button" in names
    assert "window_mode_back_button" in names


def _focus(game):
    return game.settings_tabs.focus_order()


def test_web_display_tab_hides_the_size_row_and_shows_a_fullscreen_toggle(web_game):
    web_game._open_settings("main_menu")
    p = settings(web_game)
    assert not any(p[n].active for n in row_objects("window_size"))
    assert p["window_mode_label_text"].text == "FULLSCREEN"
    assert p["window_mode_value_text"].text == "OFF"
    assert p["reduce_flashing_back_button"].active  # the rest is unchanged
    names = {web_game.settings_tabs.name_of(b) for b in _focus(web_game)}
    assert "window_size_back_button" not in names
    assert {"window_mode_back_button", "window_mode_next_button"} <= names


def test_clicking_the_fullscreen_toggle_asks_the_browser_and_follows_it(
    web_game, browser
):
    web_game._open_settings("main_menu")
    p = settings(web_game)
    click(web_game, p["window_mode_next_button"])
    assert browser.document.enter_calls == 1
    web_game.update()  # the label follows the browser, which answers later
    assert p["window_mode_value_text"].text == "ON"

    click(web_game, p["window_mode_back_button"])
    assert browser.document.exit_calls == 1
    web_game.update()
    assert p["window_mode_value_text"].text == "OFF"


def test_the_label_follows_a_fullscreen_left_with_the_browsers_own_key(
    web_game, browser
):
    web_game._open_settings("main_menu")
    web.toggle_fullscreen()
    for _ in range(FULLSCREEN_POLL_FRAMES):
        web_game.update()
    assert settings(web_game)["window_mode_value_text"].text == "ON"
    browser.document.fullscreenElement = None  # Esc in the browser
    for _ in range(FULLSCREEN_POLL_FRAMES):
        web_game.update()
    assert settings(web_game)["window_mode_value_text"].text == "OFF"


def test_f11_toggles_the_browsers_fullscreen_not_the_window_mode(web_game, browser):
    mode = web_game.window_mode
    key(web_game, pygame.K_F11)
    assert browser.document.enter_calls == 1
    key(web_game, pygame.K_F11)
    assert browser.document.exit_calls == 1
    assert web_game.window_mode == mode


def test_f11_on_desktop_still_cycles_the_window_mode(desktop_game, monkeypatch):
    steps = []
    monkeypatch.setattr(
        Application, "cycle_window_mode", lambda self, step=1: steps.append(step)
    )
    key(desktop_game, pygame.K_F11)
    assert steps == [1]


def test_the_fullscreen_caption_follows_the_language(web_game):
    web_game._open_settings("main_menu")
    web_game.set_language("tr")
    assert settings(web_game)["window_mode_label_text"].text == "TAM EKRAN"
    assert settings(web_game)["window_mode_value_text"].text == "KAPALI"


def test_reset_leaves_the_browsers_fullscreen(web_game, browser):
    web_game._open_settings("main_menu")
    web.toggle_fullscreen()
    web_game._reset_settings()
    assert not web.is_fullscreen()
    assert settings(web_game)["window_mode_value_text"].text == "OFF"


# -- saves ----------------------------------------------------------------------


def test_blocked_storage_loads_the_defaults(monkeypatch, tmp_path, fake_ticks):
    window = FakeWindow(local_storage=BlockedStorage())
    monkeypatch.setattr(platform, "window", window, raising=False)
    monkeypatch.setattr(sys, "platform", "emscripten")
    game = make_game(monkeypatch, tmp_path)
    assert game.toggles == game._default_toggles
    assert game.audio.master_volume() == game._default_audio_settings["master_volume"]
    assert not game._has_saved_game()
    game._save_settings()  # a refused write must not crash either


def test_settings_persist_in_local_storage(monkeypatch, tmp_path, fake_ticks, browser):
    game = make_game(monkeypatch, tmp_path)
    game.set_toggle("reduce_flashing", True)
    game._save_settings()
    assert any(browser.localStorage.items), "nothing reached localStorage"
    again = make_game(monkeypatch, tmp_path)
    assert again.toggles["reduce_flashing"]


# -- music ----------------------------------------------------------------------


def test_the_music_is_ogg_and_no_mp3_ships(assets):
    path = Path(assets.sound_path("bg_music"))
    assert path.suffix == ".ogg"
    assert path.exists()
    assert list((Path(resource_root()) / "assets").rglob("*.mp3")) == []


# -- review follow-ups ----------------------------------------------------------


def test_the_itch_page_comes_from_settings_yaml():
    from util.config_loader import itch_page_url

    assert itch_page_url() == "https://umutcanekinci.itch.io/chokepoint"


def test_the_web_build_has_no_window_settings_to_restore_or_save(
    monkeypatch, tmp_path, fake_ticks, browser
):
    restored = []
    monkeypatch.setattr(
        Application, "restore_window_settings", lambda self, saved: restored.append(1)
    )
    game = make_game(monkeypatch, tmp_path)
    assert restored == []
    game._save_settings()
    saved = game.settings_store.load()
    assert "window_mode" not in saved and "window_size" not in saved


def test_desktop_restores_and_saves_the_window_settings(
    monkeypatch, tmp_path, fake_ticks
):
    restored = []
    monkeypatch.setattr(
        Application, "restore_window_settings", lambda self, saved: restored.append(1)
    )
    game = make_game(monkeypatch, tmp_path)
    assert restored == [1]
    game._save_settings()
    saved = game.settings_store.load()
    assert "window_mode" in saved and "window_size" in saved


def test_the_web_fullscreen_label_polls_the_browser_every_few_frames(
    web_game, browser, monkeypatch
):
    web_game._open_settings("main_menu")
    asked = []
    real = web.is_fullscreen
    monkeypatch.setattr(web, "is_fullscreen", lambda: asked.append(1) or real())
    frames = 2 * FULLSCREEN_POLL_FRAMES
    for _ in range(frames):
        web_game.update()
    assert len(asked) == 2  # not one JS call per frame


def test_clicking_the_toggle_refreshes_the_label_at_once(web_game, browser):
    web_game._open_settings("main_menu")
    p = settings(web_game)
    click(web_game, p["window_mode_next_button"])
    assert p["window_mode_value_text"].text == "ON"  # no update() in between


def test_desktop_refreshes_the_window_mode_label_every_frame(desktop_game, monkeypatch):
    desktop_game._open_settings("main_menu")
    calls = []
    monkeypatch.setattr(
        desktop_game, "_refresh_window_mode_label", lambda: calls.append(1)
    )
    for _ in range(5):
        desktop_game.update()
    assert len(calls) == 5


def test_desktop_leaves_every_row_as_authored(desktop_game):
    desktop_game._open_settings("main_menu")
    p = settings(desktop_game)
    assert all(p[n].active for n in row_objects("window_size"))
    desktop_game._show_settings_tab("game")
    assert all(p[n].active for n in row_objects("skip_intro"))
    names = {desktop_game.settings_tabs.name_of(b) for b in _focus(desktop_game)}
    assert "skip_intro_back_button" in names


def test_the_web_game_tab_hides_skip_intro(web_game):
    web_game._open_settings("main_menu")
    web_game._show_settings_tab("game")
    p = settings(web_game)
    assert not any(p[n].active for n in row_objects("skip_intro"))
    assert p["pause_on_focus_loss_back_button"].active
    names = {web_game.settings_tabs.name_of(b) for b in _focus(web_game)}
    assert "skip_intro_back_button" not in names
    assert "pause_on_focus_loss_back_button" in names
    before = web_game.toggles["skip_intro"]
    click(web_game, p["skip_intro_next_button"])  # hidden: takes no click
    assert web_game.toggles["skip_intro"] == before


def test_keyboard_focus_and_click_dispatch_share_the_visible_rows(web_game):
    web_game._open_settings("main_menu")
    tab = web_game.settings_tabs.tab("display")
    focus = {web_game.settings_tabs.name_of(b) for b in _focus(web_game)}
    assert {row.button for row in tab.visible_rows} <= focus
    assert "window_size_next_button" not in {row.button for row in tab.visible_rows}
