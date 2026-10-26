"""GameEventsMixin._handle_start_pause -- the Space-bar shortcut added
alongside the existing start_pause_button mouse-click path. Calls the real
unbound method against a lightweight fake (same pattern used elsewhere in
this codebase's sibling projects for Game-level methods), since constructing
a real Game() would load the actual map/panels/assets for no benefit here.
"""

from types import SimpleNamespace

import pygame

from app.game_events import GameEventsMixin


class FakeButton:
    def __init__(self):
        self.state = "unset"
        self.clicked = False

    def is_clicked(self, event, mouse_pos) -> bool:
        return self.clicked

    def set_state(self, state) -> None:
        self.state = state


class FakeAudio:
    def __init__(self):
        self.played = []

    def play_sfx(self, path) -> None:
        self.played.append(path)


class FakePausePanel:
    def __init__(self):
        self.is_open = False

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False


def make_game(*, is_started=False):
    button = FakeButton()
    panel = {"start_pause_button": button, "start_pause_button_icon": button}
    game = SimpleNamespace(
        panel_manager={"game": panel},
        mouse=SimpleNamespace(position=(0, 0)),
        audio=FakeAudio(),
        click_sound_path="assets/sfx/click.ogg",
        game_state=SimpleNamespace(is_started=is_started),
        pause_panel=FakePausePanel(),
        _save_settings=lambda: None,
    )
    # _handle_start_pause calls self._activate(...), another mixin method --
    # a bare SimpleNamespace has no class relationship to GameEventsMixin,
    # so bind the real implementation directly rather than reimplementing it.
    game._activate = lambda button, event: GameEventsMixin._activate(
        game, button, event
    )
    game._set_running = lambda running: GameEventsMixin._set_running(game, running)
    game._close_pause_panel = lambda: GameEventsMixin._close_pause_panel(game)
    return game, button


def space_keydown():
    return pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)


def test_space_bar_starts_the_game_when_not_yet_started():
    game, button = make_game(is_started=False)

    GameEventsMixin._handle_start_pause(game, space_keydown())

    assert game.game_state.is_started is True
    assert button.state == "pause"


def test_space_bar_pauses_the_game_when_already_started():
    game, button = make_game(is_started=True)

    GameEventsMixin._handle_start_pause(game, space_keydown())

    assert game.game_state.is_started is False
    assert button.state is None


def test_space_bar_toggles_back_and_forth():
    game, button = make_game(is_started=False)

    GameEventsMixin._handle_start_pause(game, space_keydown())
    assert game.game_state.is_started is True

    GameEventsMixin._handle_start_pause(game, space_keydown())
    assert game.game_state.is_started is False

    GameEventsMixin._handle_start_pause(game, space_keydown())
    assert game.game_state.is_started is True


def test_space_bar_plays_the_click_sound():
    game, _ = make_game(is_started=False)

    GameEventsMixin._handle_start_pause(game, space_keydown())

    assert game.audio.played == [game.click_sound_path]


def test_other_keys_do_not_trigger_the_shortcut():
    game, _ = make_game(is_started=False)

    GameEventsMixin._handle_start_pause(
        game, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a)
    )

    assert game.game_state.is_started is False
    assert game.audio.played == []


def test_space_key_up_does_not_trigger_the_shortcut():
    """Only KEYDOWN fires it -- matches _TOWER_HOTKEYS' convention
    (tower_placement.py) rather than _activate()'s KEYUP-based
    focused-button convention, which doesn't apply here (no keyboard-focus
    system drives "game"-panel buttons)."""
    game, _ = make_game(is_started=False)

    GameEventsMixin._handle_start_pause(
        game, pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE)
    )

    assert game.game_state.is_started is False


def test_mouse_click_on_the_button_still_works():
    game, button = make_game(is_started=False)
    button.clicked = True

    GameEventsMixin._handle_start_pause(
        game, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
    )

    assert game.game_state.is_started is True
    assert button.state == "pause"
    assert game.audio.played == [game.click_sound_path]


def test_unrelated_mouse_event_does_not_trigger_anything():
    game, button = make_game(is_started=False)
    button.clicked = False

    GameEventsMixin._handle_start_pause(
        game, pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1))
    )

    assert game.game_state.is_started is False
    assert game.audio.played == []
