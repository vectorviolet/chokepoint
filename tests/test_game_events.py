"""GameEventsMixin's remaining handlers (test_game_events_start_pause.py
already covers _handle_start_pause specifically). Since most handlers here
call sibling mixin methods directly (self._handle_upgrade_plane_button,
self._cycle_window_size, ...), FakeGame subclasses GameEventsMixin itself
rather than rebinding each cross-call by hand on a bare SimpleNamespace --
every intra-mixin call then just resolves normally through the MRO. Methods
GameEventsMixin expects from Game/GameSaveMixin/Application (_save_game,
cycle_resolution, on_exit_request, ...) are stubbed here and log to
`self.calls` so a test can assert what got invoked without needing a real
Game() (which would load the actual map/panels/assets for no benefit)."""

import pygame

from app.game_events import GameEventsMixin
from domain.game_state import GameState
from util.config_loader import load_tower_config


class FakeButton:
    def __init__(self, clicked=False, focused=False, on_click_sound=None):
        self.clicked = clicked
        self.focused = focused
        self.on_click_sound = on_click_sound
        self.state = "unset"

    def is_clicked(self, event, mouse_pos) -> bool:
        return self.clicked

    def set_state(self, state) -> None:
        self.state = state


class FakeScroller:
    def __init__(self):
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1


class FakeAudio:
    def __init__(self):
        self.played = []
        self.sfx_volume_value = 0.5
        self.music_volume_value = 0.5
        self.is_music_paused = False

    def play_sfx(self, path) -> None:
        self.played.append(path)

    def set_sfx_volume(self, value) -> None:
        self.sfx_volume_value = value

    def set_music_volume(self, value) -> None:
        self.music_volume_value = value

    def toggle_music(self) -> None:
        self.is_music_paused = not self.is_music_paused


class FakeCamera:
    def __init__(self):
        self.events = []

    def handle_event(self, event, mouse_pos) -> None:
        self.events.append(event)


class FakeTowerController:
    def __init__(self):
        self.events = []

    def handle_event(self, event, mouse_pos) -> None:
        self.events.append(event)


class FakePanelManager(dict):
    """dict for `panel_manager["name"]` subscript access, plus a plain
    settable `.current_panel` attribute -- matches pygamine's real
    PanelManager's own dual interface."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_panel = "main_menu"

    def keys(self):
        return dict.keys(self)


def make_game_panel():
    return {
        "menu_button": FakeButton(),
        "start_pause_button": FakeButton(),
        "start_pause_button_icon": FakeButton(),
        "speed_toggle_button": FakeButton(),
        "upgrade_plane_button": FakeButton(),
        "buy_tower_4": FakeButton(),
        "victory_continue": FakeButton(),
        "victory_play_again": FakeButton(),
        "victory_main_menu": FakeButton(),
        "gameover_play_again": FakeButton(),
        "gameover_main_menu": FakeButton(),
        "music_toggle_button": FakeButton(),
        "music_toggle_icon": FakeButton(),
    }


PLANE_UPGRADE_PRICE = load_tower_config().prices[3][1]


class FakeGame(GameEventsMixin):
    def __init__(self, *, has_saved_game=False, money=10_000):
        self.panel_manager = FakePanelManager(
            {
                "main_menu": {
                    "play": FakeButton(),
                    "credits": FakeButton(),
                    "settings": FakeButton(),
                    "exit": FakeButton(),
                    "music_toggle_icon": FakeButton(),
                },
                "play_menu": {
                    "continue_game": FakeButton(),
                    "new_game": FakeButton(),
                    "back": FakeButton(),
                    "music_toggle_icon": FakeButton(),
                },
                "credits": {
                    "back": FakeButton(),
                    "music_toggle_icon": FakeButton(),
                    "credits_scroller": FakeScroller(),
                },
                "settings": {
                    "back": FakeButton(),
                    "reset": FakeButton(),
                    "window_size_back_button": FakeButton(),
                    "window_size_next_button": FakeButton(),
                    "window_mode_back_button": FakeButton(),
                    "window_mode_next_button": FakeButton(),
                    "music_toggle_icon": FakeButton(),
                },
                "game": make_game_panel(),
            }
        )
        self.mouse = type("M", (), {"position": (0, 0)})()
        self.audio = FakeAudio()
        self.click_sound_path = "assets/sfx/click.ogg"
        self.game_state = GameState(start_money=money, start_lives=10)
        self.tower_config = load_tower_config()
        self.camera = FakeCamera()
        self.tower_controller = FakeTowerController()
        self._victory_popup_open = False
        self._gameover_popup_open = False
        self._has_saved_game_value = has_saved_game
        self.calls: list = []

    # -- stand-ins for GameSaveMixin / Game / Application ---------------------
    def _has_saved_game(self) -> bool:
        return self._has_saved_game_value

    def _start_new_game(self) -> None:
        self.calls.append("_start_new_game")

    def _load_game(self) -> None:
        self.calls.append("_load_game")

    def _save_game(self) -> None:
        self.calls.append("_save_game")

    def _save_settings(self) -> None:
        self.calls.append("_save_settings")

    def _reset_settings(self) -> None:
        self.calls.append("_reset_settings")

    def cycle_resolution(self, step) -> None:
        self.calls.append(("cycle_resolution", step))

    def cycle_window_mode(self, step) -> None:
        self.calls.append(("cycle_window_mode", step))

    def _refresh_window_size_label(self) -> None:
        self.calls.append("_refresh_window_size_label")

    def _refresh_window_mode_label(self) -> None:
        self.calls.append("_refresh_window_mode_label")

    def _refresh_sfx_volume_label(self) -> None:
        self.calls.append("_refresh_sfx_volume_label")

    def _refresh_music_volume_label(self) -> None:
        self.calls.append("_refresh_music_volume_label")

    def on_exit_request(self) -> None:
        self.calls.append("on_exit_request")

    def _close_victory_popup(self) -> None:
        self._victory_popup_open = False
        self.calls.append("_close_victory_popup")

    def _close_gameover_popup(self) -> None:
        self._gameover_popup_open = False
        self.calls.append("_close_gameover_popup")


def click_up():
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=1)


# ── _activate ────────────────────────────────────────────────────────────────


def test_activate_true_on_click_and_plays_the_default_click_sound():
    game = FakeGame()
    button = FakeButton(clicked=True)

    assert game._activate(button, click_up()) is True
    assert game.audio.played == [game.click_sound_path]


def test_activate_true_on_focused_space_keyup():
    game = FakeGame()
    button = FakeButton(focused=True)
    event = pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE)

    assert game._activate(button, event) is True


def test_activate_false_on_space_keyup_when_not_focused():
    game = FakeGame()
    button = FakeButton(focused=False)
    event = pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE)

    assert game._activate(button, event) is False
    assert game.audio.played == []


def test_activate_prefers_the_buttons_own_click_sound():
    game = FakeGame()
    button = FakeButton(clicked=True, on_click_sound="assets/sfx/special.ogg")

    game._activate(button, click_up())

    assert game.audio.played == ["assets/sfx/special.ogg"]


# ── main menu ────────────────────────────────────────────────────────────────


def test_main_menu_play_with_a_saved_game_opens_play_menu():
    game = FakeGame(has_saved_game=True)
    game.panel_manager["main_menu"]["play"].clicked = True

    game._handle_main_menu_event(click_up())

    assert game.panel_manager.current_panel == "play_menu"
    assert "_start_new_game" not in game.calls


def test_main_menu_play_without_a_saved_game_starts_a_new_game():
    game = FakeGame(has_saved_game=False)
    game.panel_manager["main_menu"]["play"].clicked = True

    game._handle_main_menu_event(click_up())

    assert "_start_new_game" in game.calls


def test_main_menu_credits_and_settings_and_exit():
    game = FakeGame()
    game.panel_manager["main_menu"]["credits"].clicked = True
    game._handle_main_menu_event(click_up())
    assert game.panel_manager.current_panel == "credits"

    game2 = FakeGame()
    game2.panel_manager["main_menu"]["settings"].clicked = True
    game2._handle_main_menu_event(click_up())
    assert game2.panel_manager.current_panel == "settings"

    game3 = FakeGame()
    game3.panel_manager["main_menu"]["exit"].clicked = True
    game3._handle_main_menu_event(click_up())
    assert "on_exit_request" in game3.calls


# ── play menu ────────────────────────────────────────────────────────────────


def test_play_menu_continue_loads_the_saved_game():
    game = FakeGame()
    game.panel_manager["play_menu"]["continue_game"].clicked = True

    game._handle_play_menu_event(click_up())

    assert "_load_game" in game.calls


def test_play_menu_new_game_starts_fresh():
    game = FakeGame()
    game.panel_manager["play_menu"]["new_game"].clicked = True

    game._handle_play_menu_event(click_up())

    assert "_start_new_game" in game.calls


def test_play_menu_back_returns_to_main_menu():
    game = FakeGame()
    game.panel_manager["play_menu"]["back"].clicked = True

    game._handle_play_menu_event(click_up())

    assert game.panel_manager.current_panel == "main_menu"


# ── credits ──────────────────────────────────────────────────────────────────


def test_opening_credits_restarts_the_scroll_each_time():
    game = FakeGame()
    scroller = game.panel_manager["credits"]["credits_scroller"]
    game.panel_manager["main_menu"]["credits"].clicked = True

    game._handle_main_menu_event(click_up())
    game.panel_manager.current_panel = "main_menu"
    game._handle_main_menu_event(click_up())

    assert scroller.resets == 2


def test_credits_back_returns_to_main_menu():
    game = FakeGame()
    game.panel_manager["credits"]["back"].clicked = True

    game._handle_credits_event(click_up())

    assert game.panel_manager.current_panel == "main_menu"


# ── settings ─────────────────────────────────────────────────────────────────


def test_settings_back_saves_and_returns_to_main_menu():
    game = FakeGame()
    game.panel_manager["settings"]["back"].clicked = True

    game._handle_settings_event(click_up())

    assert "_save_settings" in game.calls
    assert game.panel_manager.current_panel == "main_menu"


def test_settings_reset():
    game = FakeGame()
    game.panel_manager["settings"]["reset"].clicked = True

    game._handle_settings_event(click_up())

    assert "_reset_settings" in game.calls


def test_settings_window_size_back_and_next():
    game = FakeGame()
    game.panel_manager["settings"]["window_size_back_button"].clicked = True
    game._handle_settings_event(click_up())
    assert ("cycle_resolution", -1) in game.calls
    assert "_refresh_window_size_label" in game.calls

    game2 = FakeGame()
    game2.panel_manager["settings"]["window_size_next_button"].clicked = True
    game2._handle_settings_event(click_up())
    assert ("cycle_resolution", 1) in game2.calls


def test_settings_window_mode_back_and_next():
    game = FakeGame()
    game.panel_manager["settings"]["window_mode_back_button"].clicked = True
    game._handle_settings_event(click_up())
    assert ("cycle_window_mode", -1) in game.calls
    assert "_refresh_window_mode_label" in game.calls
    assert "_refresh_window_size_label" in game.calls

    game2 = FakeGame()
    game2.panel_manager["settings"]["window_mode_next_button"].clicked = True
    game2._handle_settings_event(click_up())
    assert ("cycle_window_mode", 1) in game2.calls


def test_on_sfx_and_music_volume_changed():
    game = FakeGame()

    game._on_sfx_volume_changed(0.75)
    assert game.audio.sfx_volume_value == 0.75
    assert "_refresh_sfx_volume_label" in game.calls

    game._on_music_volume_changed(0.25)
    assert game.audio.music_volume_value == 0.25
    assert "_refresh_music_volume_label" in game.calls


# ── game panel ───────────────────────────────────────────────────────────────


def test_game_event_menu_button_pauses_saves_and_returns_to_menu():
    game = FakeGame()
    game.game_state.is_started = True
    game.panel_manager["game"]["menu_button"].clicked = True

    game._handle_game_event(click_up())

    assert game.game_state.is_started is False
    assert "_save_game" in game.calls
    assert game.panel_manager.current_panel == "main_menu"
    assert game.camera.events == []  # returned early -- rest of the panel never runs


def test_game_event_normal_flow_forwards_to_camera_and_tower_controller():
    game = FakeGame()
    event = click_up()

    game._handle_game_event(event)

    assert game.camera.events == [event]
    assert game.tower_controller.events == [event]


def test_game_event_space_bar_still_starts_the_game():
    game = FakeGame()
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)

    game._handle_game_event(event)

    assert game.game_state.is_started is True


def test_game_event_routes_to_victory_popup_when_open():
    game = FakeGame()
    game._victory_popup_open = True
    game.panel_manager["game"]["victory_play_again"].clicked = True

    game._handle_game_event(click_up())

    assert game._victory_popup_open is False
    assert "_start_new_game" in game.calls
    assert game.camera.events == []  # never reached the normal game-panel path


def test_game_event_routes_to_gameover_popup_when_open():
    game = FakeGame()
    game._gameover_popup_open = True
    game.panel_manager["game"]["gameover_play_again"].clicked = True

    game._handle_game_event(click_up())

    assert game._gameover_popup_open is False
    assert "_start_new_game" in game.calls


# ── victory popup ────────────────────────────────────────────────────────────


def test_victory_continue_resumes_the_game():
    game = FakeGame()
    game._victory_popup_open = True
    game.panel_manager["game"]["victory_continue"].clicked = True

    game._handle_victory_popup_event(click_up())

    assert game._victory_popup_open is False
    assert game.game_state.is_started is True
    assert game.panel_manager["game"]["start_pause_button_icon"].state == "pause"


def test_victory_main_menu_saves_and_exits_to_menu():
    game = FakeGame()
    game._victory_popup_open = True
    game.panel_manager["game"]["victory_main_menu"].clicked = True

    game._handle_victory_popup_event(click_up())

    assert game._victory_popup_open is False
    assert game.game_state.is_started is False
    assert "_save_game" in game.calls
    assert game.panel_manager.current_panel == "main_menu"


# ── game over popup ──────────────────────────────────────────────────────────


def test_gameover_main_menu_returns_to_menu():
    game = FakeGame()
    game._gameover_popup_open = True
    game.panel_manager["game"]["gameover_main_menu"].clicked = True

    game._handle_gameover_popup_event(click_up())

    assert game._gameover_popup_open is False
    assert game.panel_manager.current_panel == "main_menu"


# ── plane upgrade ────────────────────────────────────────────────────────────


def test_upgrade_plane_succeeds_with_enough_money():
    game = FakeGame(money=PLANE_UPGRADE_PRICE)
    game.panel_manager["game"]["upgrade_plane_button"].clicked = True

    game._handle_upgrade_plane_button(click_up())

    assert game.game_state.money == 0
    assert game.game_state.plane_level == 2
    assert game.panel_manager["game"]["buy_tower_4"].state == "lvl2"
    assert game.panel_manager["game"]["upgrade_plane_button"].state == "purchased"


def test_upgrade_plane_fails_with_insufficient_money():
    game = FakeGame(money=PLANE_UPGRADE_PRICE - 1)
    game.panel_manager["game"]["upgrade_plane_button"].clicked = True

    game._handle_upgrade_plane_button(click_up())

    assert game.game_state.money == PLANE_UPGRADE_PRICE - 1
    assert game.game_state.plane_level == 1


def test_upgrade_plane_is_a_one_time_purchase():
    game = FakeGame(money=50_000)
    game.game_state.plane_level = 2
    game.panel_manager["game"]["upgrade_plane_button"].clicked = True

    game._handle_upgrade_plane_button(click_up())

    assert game.game_state.money == 50_000  # unchanged -- already at level 2


def test_upgrade_plane_button_not_clicked_is_a_no_op():
    game = FakeGame(money=50_000)

    game._handle_upgrade_plane_button(click_up())

    assert game.game_state.money == 50_000
    assert game.game_state.plane_level == 1


# ── speed toggle ─────────────────────────────────────────────────────────────


def test_speed_toggle_cycles_1_2_4_and_back_to_1():
    game = FakeGame()
    game.panel_manager["game"]["speed_toggle_button"].clicked = True

    game._handle_speed_toggle(click_up())
    assert game.game_state.speed == 2
    assert game.panel_manager["game"]["speed_toggle_button"].state == "x2_active"

    game._handle_speed_toggle(click_up())
    assert game.game_state.speed == 4
    assert game.panel_manager["game"]["speed_toggle_button"].state == "x4_active"

    game._handle_speed_toggle(click_up())
    assert game.game_state.speed == 1
    assert game.panel_manager["game"]["speed_toggle_button"].state is None


def test_speed_toggle_not_clicked_is_a_no_op():
    game = FakeGame()

    game._handle_speed_toggle(click_up())

    assert game.game_state.speed == 1


# ── music toggle ─────────────────────────────────────────────────────────────


def test_toggle_music_updates_every_panels_icon():
    game = FakeGame()

    game._toggle_music()

    assert game.audio.is_music_paused is True
    for tab in ("main_menu", "play_menu", "credits", "settings", "game"):
        assert game.panel_manager[tab]["music_toggle_icon"].state == "paused"

    game._toggle_music()

    assert game.audio.is_music_paused is False
    for tab in ("main_menu", "play_menu", "credits", "settings", "game"):
        assert game.panel_manager[tab]["music_toggle_icon"].state is None
