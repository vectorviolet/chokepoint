"""Game itself (app/game.py) -- constructing a real Game() needs the full
YAML-driven panel/asset/tilemap stack for no benefit here (same reasoning
test_game_events_start_pause.py already established for its mixins).
Instead these build a bare Game instance via object.__new__(Game), which
skips __init__ entirely, then attach only the attributes the method under
test actually touches. Because it's a real Game (not a re-implemented
fake), every inherited method -- GameEventsMixin._activate, GameSaveMixin's
_sync_game_ui, Game's own _close_victory_popup, etc. -- resolves normally
through the real MRO with no manual rebinding needed.
"""

from types import SimpleNamespace

import pygame
import pytest
from pygame import Rect

from app.game import Game, WIN_WAVE, _VICTORY_POPUP_OBJECTS, _GAMEOVER_POPUP_OBJECTS
from util.constants import TICK_MS, MAX_FRAME_MS
from domain.game_state import GameState
from pygamine import Application, Camera


class Spy:
    """A zero/one-arg callable that records every call -- assigned directly
    as an instance attribute so `self.name(...)` calls it unbound (the
    closure already has what it needs, so it never needs a `self` param)."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)


class FakeGuiObject:
    def __init__(self):
        self.active = False
        self.state = "unset"

    def set_state(self, state) -> None:
        self.state = state

    def is_clicked(self, event, mouse_pos) -> bool:
        return False


class FakePanel(dict):
    pass


class FakePanelManager(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_panel = "main_menu"

    def keys(self):
        return dict.keys(self)

    def update(self):
        pass

    def handle_event(self, event, pos):
        pass

    def draw(self, surface):
        pass


def make_game_panel():
    panel = FakePanel()
    panel["start_pause_button_icon"] = FakeGuiObject()
    panel["music_toggle_button"] = FakeGuiObject()
    for name in _VICTORY_POPUP_OBJECTS:
        panel[name] = FakeGuiObject()
    for name in _GAMEOVER_POPUP_OBJECTS:
        panel[name] = FakeGuiObject()
    return panel


def make_game(**overrides):
    game = object.__new__(Game)
    game.game_state = GameState(start_money=500, start_lives=10)
    game.panel_manager = FakePanelManager({"game": make_game_panel()})
    game._victory_popup_open = False
    game._gameover_popup_open = False
    game.towers = []
    game.enemies = []
    game.wave_manager = None
    game._construction_complete = True
    game._last_frame_ticks = None
    game._tick_backlog_ms = 0.0
    for key, value in overrides.items():
        setattr(game, key, value)
    return game


# ── IGameContext properties ──────────────────────────────────────────────────


def test_speed_reads_from_game_state():
    game = make_game()
    game.game_state.speed = 3
    assert game.speed == 3


def test_map_dimensions_read_from_the_tilemap():
    game = make_game(tilemap=SimpleNamespace(map_width=3008, map_height=2176))
    assert game.map_width == 3008
    assert game.map_height == 2176


def test_increase_money_delegates_to_game_state():
    game = make_game()
    game.increase_money(50)
    assert game.game_state.money == 550


# ── victory popup ────────────────────────────────────────────────────────────


def test_reaching_the_win_wave_triggers_victory():
    game = make_game()

    game._on_level_changed(WIN_WAVE + 1)

    assert game.game_state.has_won is True
    assert game.game_state.is_started is False
    assert game.panel_manager["game"]["start_pause_button_icon"].state is None
    assert game._victory_popup_open is True
    assert all(game.panel_manager["game"][n].active for n in _VICTORY_POPUP_OBJECTS)


def test_a_normal_level_change_does_not_trigger_victory():
    game = make_game()

    game._on_level_changed(3)

    assert game.game_state.has_won is False
    assert game._victory_popup_open is False


def test_already_won_does_not_retrigger_victory():
    game = make_game()
    game.game_state.has_won = True

    game._on_level_changed(WIN_WAVE + 1)  # should be a no-op, not re-open the popup

    assert game._victory_popup_open is False


def test_close_victory_popup_deactivates_every_victory_object():
    game = make_game()
    game._trigger_victory()

    game._close_victory_popup()

    assert game._victory_popup_open is False
    assert all(not game.panel_manager["game"][n].active for n in _VICTORY_POPUP_OBJECTS)


# ── game over popup ──────────────────────────────────────────────────────────


def test_trigger_game_over_activates_every_gameover_object():
    game = make_game()

    game._trigger_game_over()

    assert game.game_state.is_started is False
    assert game.panel_manager["game"]["start_pause_button_icon"].state is None
    assert game._gameover_popup_open is True
    assert all(game.panel_manager["game"][n].active for n in _GAMEOVER_POPUP_OBJECTS)


def test_close_gameover_popup_deactivates_every_gameover_object():
    game = make_game()
    game._trigger_game_over()

    game._close_gameover_popup()

    assert game._gameover_popup_open is False
    assert all(
        not game.panel_manager["game"][n].active for n in _GAMEOVER_POPUP_OBJECTS
    )


# ── canvas resize ─────────────────────────────────────────────────────────────


def test_on_canvas_resized_is_a_no_op_before_construction_completes():
    game = make_game(_construction_complete=False)
    game._reflow_camera = Spy()
    game._reflow_panels = Spy()

    game.on_canvas_resized((800, 600))

    assert game._reflow_camera.calls == []
    assert game._reflow_panels.calls == []


def test_on_canvas_resized_reflows_camera_and_panels_once_constructed():
    game = make_game(_construction_complete=True)
    game._reflow_camera = Spy()
    game._reflow_panels = Spy()

    game.on_canvas_resized((800, 600))

    assert game._reflow_camera.calls == [((800, 600),)]
    assert game._reflow_panels.calls == [((800, 600),)]


def test_reflow_camera_updates_game_area_and_clamps_the_camera():
    game_area = Rect(0, 0, 1536, 1080)
    camera = Camera(game_area, 3008, 2176, scroll_rect=Rect(0, 0, 1536, 1080))
    game = make_game(game_area=game_area, camera=camera)

    game._reflow_camera((640, 480))

    assert (game.game_area.width, game.game_area.height) == (640, 480)
    assert (game.camera.scroll_rect.width, game.camera.scroll_rect.height) == (640, 480)


# ── update dispatch ──────────────────────────────────────────────────────────


def test_update_on_a_menu_panel_runs_the_menu_demo_by_elapsed_real_time(fake_ticks):
    game = make_game()
    game.panel_manager.current_panel = "main_menu"
    game.menu_demo = SimpleNamespace(update=Spy())

    fake_ticks["t"] = 1000
    game.update()  # first frame: nothing elapsed yet
    fake_ticks["t"] = 1040
    game.update()

    assert game.menu_demo.update.calls == [(0.0,), (40.0,)]


def test_update_on_settings_also_refreshes_the_window_mode_label():
    game = make_game()
    game.panel_manager.current_panel = "settings"
    game.menu_demo = SimpleNamespace(update=Spy())
    game._refresh_window_mode_label = Spy()

    game.update()

    assert len(game._refresh_window_mode_label.calls) == 1


def test_update_on_the_game_panel_calls_update_game_with_the_frame_time(fake_ticks):
    game = make_game()
    game.panel_manager.current_panel = "game"
    game._update_game = Spy()

    fake_ticks["t"] = 500
    game.update()
    fake_ticks["t"] = 520
    game.update()

    assert game._update_game.calls == [(0.0,), (20.0,)]


def test_elapsed_frame_ms_is_capped_so_a_stall_is_not_replayed(fake_ticks):
    game = make_game()
    fake_ticks["t"] = 0
    game._elapsed_frame_ms()

    fake_ticks["t"] = 10_000  # e.g. ten seconds spent dragging the window
    assert game._elapsed_frame_ms() == MAX_FRAME_MS


def make_updating_game():
    game = make_game()
    game.camera = SimpleNamespace(update_with_mouse=Spy())
    game.mouse = SimpleNamespace(position=(1, 2), update=Spy())
    game.tower_controller = SimpleNamespace(update_cursor=Spy())
    game.tower_bar = SimpleNamespace(update=Spy())
    game._tick = Spy()
    return game


def test_update_game_forwards_input_motion_scaled_to_the_frame_time():
    game = make_updating_game()

    game._update_game(2 * TICK_MS)

    assert game.camera.update_with_mouse.calls == [((1, 2), pytest.approx(2.0))]
    assert len(game.mouse.update.calls) == 1
    assert game.tower_controller.update_cursor.calls == [((1, 2),)]
    assert game.tower_bar.update.calls == [(pytest.approx(2 * TICK_MS),)]


def test_update_game_runs_one_tick_per_tick_ms_of_frame_time():
    game = make_updating_game()

    game._update_game(3 * TICK_MS + 1)

    assert len(game._tick.calls) == 3


def test_update_game_carries_leftover_time_into_the_next_frame():
    """At 60 fps a frame is ~2.75 ticks long: the fractional remainder
    must accumulate rather than be dropped, or the game would run slow."""
    game = make_updating_game()

    for _ in range(4):
        game._update_game(TICK_MS * 0.8)  # 3.2 ticks in total

    assert len(game._tick.calls) == 3


def test_simulated_ticks_per_second_do_not_depend_on_the_frame_rate():
    for fps in (30, 60, 144, 240):
        game = make_updating_game()
        for _ in range(fps):
            game._update_game(1000 / fps)
        assert len(game._tick.calls) in (164, 165), fps


def test_tick_advances_game_time_before_updating_towers_and_enemies():
    game = make_game()
    order = []
    game.game_state.is_started = True
    game._update_towers = lambda: order.append(("towers", game.game_state.time_ms))
    game._update_enemies = lambda: order.append(("enemies", game.game_state.time_ms))

    game._tick()

    assert order == [
        ("towers", pytest.approx(TICK_MS)),
        ("enemies", pytest.approx(TICK_MS)),
    ]


def test_time_ms_reads_from_game_state():
    game = make_game()
    game.game_state.time_ms = 1234.5
    assert game.time_ms == 1234.5


def test_show_path_entrance_centres_the_camera_on_the_spawn_point():
    game = make_game()
    game.camera = SimpleNamespace(center_on=Spy())
    spawn = pygame.math.Vector2(2624, 0)
    game.tilemap = SimpleNamespace(waypoints=[spawn, pygame.math.Vector2(2624, 576)])

    game._show_path_entrance()

    assert game.camera.center_on.calls == [(spawn,)]


class FakeBullet:
    def __init__(self):
        self.updated_with = None

    def update(self, ctx):
        self.updated_with = ctx


class FakeTower:
    def __init__(self, *, removed=False, blocking_pos=None):
        self._removed = removed
        self._blocking_pos = blocking_pos
        self.bullets = [FakeBullet()]
        self.update_calls = []

    def should_remove(self):
        return self._removed

    def update(self, game_state, enemies):
        self.update_calls.append((game_state, enemies))

    def get_blocking_position(self):
        return self._blocking_pos


def test_update_towers_drops_removed_towers_and_collects_blocking_positions():
    game = make_game()
    keep = FakeTower(blocking_pos=(1, 2))
    drop = FakeTower(removed=True)
    game.towers = [keep, drop]
    game.tower_controller = SimpleNamespace(tower_positions=None)
    game.game_state.is_started = True

    game._update_towers()

    assert game.towers == [keep]
    assert keep.update_calls == [(game.game_state, game.enemies)]
    assert game.tower_controller.tower_positions == {(1, 2)}
    assert keep.bullets[0].updated_with is game


def test_update_towers_only_advances_bullets_while_the_game_is_started():
    game = make_game()
    tower = FakeTower()
    game.towers = [tower]
    game.tower_controller = SimpleNamespace(tower_positions=None)
    game.game_state.is_started = False

    game._update_towers()

    assert tower.bullets[0].updated_with is None


class FakeEnemy:
    def __init__(self, *, at_end=False, damage=5):
        self._at_end = at_end
        self.damage = damage
        self.moved_with = None

    def reached_end(self):
        return self._at_end

    def move(self, speed):
        self.moved_with = speed


def test_update_enemies_removes_one_that_reached_the_end_and_deducts_a_life():
    game = make_game()
    enemy = FakeEnemy(at_end=True, damage=7)
    game.enemies = [enemy]
    game.game_state.lives = 10

    game._update_enemies()

    assert game.enemies == []
    assert game.game_state.lives == 3


def test_update_enemies_triggers_game_over_when_lives_reach_zero():
    game = make_game()
    game.game_state.lives = 5
    game.enemies = [FakeEnemy(at_end=True, damage=5)]
    game.save_store = SimpleNamespace(delete=Spy())
    game._trigger_game_over = Spy()

    game._update_enemies()

    assert game.game_state.lives == 0
    assert len(game.save_store.delete.calls) == 1
    assert len(game._trigger_game_over.calls) == 1


def test_update_enemies_does_not_move_while_paused():
    game = make_game()
    game.game_state.is_started = False
    enemy = FakeEnemy(at_end=False)
    game.enemies = [enemy]

    game._update_enemies()

    assert enemy.moved_with is None


def test_update_enemies_moves_at_game_speed_while_started():
    game = make_game()
    game.game_state.is_started = True
    game.game_state.speed = 2
    enemy = FakeEnemy(at_end=False)
    game.enemies = [enemy]

    game._update_enemies()

    assert enemy.moved_with == 2


# ── event dispatch ───────────────────────────────────────────────────────────


def test_handle_event_dispatches_to_the_current_panels_handler():
    game = make_game()
    game.panel_manager.current_panel = "game"
    game.mouse = SimpleNamespace(position=(0, 0))
    game.menu_controllers = {}
    handler = Spy()
    game.handlers = {"game": handler}
    event = pygame.event.Event(pygame.MOUSEMOTION, pos=(0, 0))

    game.handle_event(event)

    assert handler.calls == [(event,)]


def test_handle_event_music_toggle_button_click_toggles_music():
    game = make_game()
    game.panel_manager.current_panel = "game"
    game.mouse = SimpleNamespace(position=(5, 5))
    game.menu_controllers = {}
    game.handlers = {}
    game.click_sound_path = "assets/sfx/click.ogg"
    game.audio = SimpleNamespace(play_sfx=Spy())
    game._toggle_music = Spy()
    game.panel_manager["game"][
        "music_toggle_button"
    ].rect = None  # is_clicked stubbed below
    game.panel_manager["game"]["music_toggle_button"].is_clicked = lambda event, pos: (
        True
    )

    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1))

    assert len(game._toggle_music.calls) == 1


# ── draw dispatch ────────────────────────────────────────────────────────────


def test_draw_on_the_game_panel_calls_draw_game_and_shortcuts():
    game = make_game()
    game.panel_manager.current_panel = "game"
    game.window = pygame.Surface((100, 100))
    game._draw_game = Spy()
    game.tower_controller = SimpleNamespace(draw_shortcuts=Spy())

    game.draw()

    assert len(game._draw_game.calls) == 1
    assert len(game.tower_controller.draw_shortcuts.calls) == 1


def test_draw_on_a_menu_panel_draws_the_menu_demo_and_overlay():
    game = make_game()
    game.panel_manager.current_panel = "main_menu"
    game.window = pygame.Surface((100, 100))
    game.menu_demo = SimpleNamespace(draw=Spy())
    game.menu_overlay = pygame.Surface((100, 100), pygame.SRCALPHA)

    game.draw()

    assert len(game.menu_demo.draw.calls) == 1


def test_draw_selected_tower_ui_is_a_no_op_with_nothing_selected():
    game = make_game()
    game.game_state.selected_tower = None
    game._draw_selected_tower_ui()  # must not raise


def test_draw_selected_tower_ui_is_a_no_op_when_selected_tower_was_already_sold():
    game = make_game()
    tower = object()
    game.game_state.selected_tower = tower
    game.towers = []  # sold -- no longer in the list

    game._draw_selected_tower_ui()  # must not raise


# ── exit flow ────────────────────────────────────────────────────────────────


def test_on_exit_request_from_main_menu_exits():
    game = make_game()
    game.panel_manager.current_panel = "main_menu"
    game.exit = Spy()

    game.on_exit_request()

    assert len(game.exit.calls) == 1


def test_on_exit_request_from_settings_saves_and_returns_to_menu():
    game = make_game()
    game.panel_manager.current_panel = "settings"
    game._save_settings = Spy()

    game.on_exit_request()

    assert len(game._save_settings.calls) == 1
    assert game.panel_manager.current_panel == "main_menu"


def test_on_exit_request_from_game_pauses_and_saves():
    game = make_game()
    game.panel_manager.current_panel = "game"
    game.game_state.is_started = True
    game._save_game = Spy()

    game.on_exit_request()

    assert game.game_state.is_started is False
    assert len(game._save_game.calls) == 1
    assert game.panel_manager.current_panel == "main_menu"


def test_on_exit_request_from_game_skips_saving_after_a_lost_run():
    game = make_game()
    game.panel_manager.current_panel = "game"
    game._gameover_popup_open = True
    game._save_game = Spy()

    game.on_exit_request()

    assert game._save_game.calls == []
    assert game.panel_manager.current_panel == "main_menu"


def test_exit_saves_settings_before_delegating_to_the_base_application(monkeypatch):
    game = make_game()
    game._save_settings = Spy()
    base_exit = Spy()
    monkeypatch.setattr(Application, "exit", lambda self: base_exit())

    game.exit()

    assert len(game._save_settings.calls) == 1
    assert len(base_exit.calls) == 1


# ── wave manager init ────────────────────────────────────────────────────────


def test_init_wave_manager_raises_without_any_waypoints():
    game = make_game(tilemap=SimpleNamespace(waypoints=[]))

    with pytest.raises(RuntimeError):
        game._init_wave_manager()


def test_init_wave_manager_builds_a_real_wave_manager(assets):
    from pygame.math import Vector2

    game = make_game(
        tilemap=SimpleNamespace(waypoints=[Vector2(0, 0), Vector2(1, 1)]), assets=assets
    )

    game._init_wave_manager()

    assert game.wave_manager is not None
