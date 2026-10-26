from pathlib import Path
from typing import override

import pygame
import yaml
from pygame import Rect

from app.game_events import GameEventsMixin
from app.game_save import GameSaveMixin
from pygamine import Application
from pygamine import AssetManager
from pygamine import MenuController
from pygamine import Mouse
from pygamine import PanelManager
from pygamine import PanelLoaderExt

from pygamine import (
    make_factory,
    make_text_factory,
    make_animated_factory,
    make_slider_factory,
    make_scrolling_panel_factory,
)
from util.config_loader import load_tower_config, load_tower_tooltips
from pygamine import Camera
from util.constants import TILE_SIZE, TICK_MS, MAX_FRAME_MS
from pygamine import Debug
from pygamine import SplashScreen, standard_splash_media
from pygamine import SaveStore
from pygamine import GameAudio
from gameplay.combat.enemy import Enemy
from ui.game_hud import GameHUD
from ui.hud_slide import HudSlide
from ui.kill_feedback import KillFeedback
from ui.life_lost_feedback import LifeLostFeedback
from ui.place_sell_feedback import PlaceSellFeedback
from ui.buy_tooltip import BuyTooltip
from ui.tower_info import TowerInfoPanel
from ui.pause_panel import PausePanel
from domain.game_state import GameState
from pygamine import Transform
from gameplay.tilemap import Tilemap
from gameplay.combat.tower_placement import TowerPlacementController
from gameplay.towers import BaseTower, GroundTower
from gameplay.combat.wave_manager import WaveManager
from gameplay.battle import BattleSimulation
from gameplay.menu_demo import MenuDemo

WINDOW_MODE_LABELS = {
    "fullscreen": "FULLSCREEN",
    "borderless": "BORDERLESS",
    "windowed": "WINDOWED",
}

# Clearing this wave triggers the victory popup once per run (config/waves.yaml
# keeps generating waves past it -- "Continue" just keeps playing those).
WIN_WAVE = 25

# Toggled together via _set_victory_popup_active() -- the panel/GuiObject
# system has no group-visibility concept, so each object's .active is set
# individually (see config/panels.yaml's victory_* objects).
_VICTORY_POPUP_OBJECTS = (
    "victory_overlay",
    "victory_panel_bg",
    "victory_title_text",
    "victory_subtitle_text",
    "victory_continue",
    "victory_continue_text",
    "victory_play_again",
    "victory_play_again_text",
    "victory_main_menu",
    "victory_main_menu_text",
)

_GAMEOVER_POPUP_OBJECTS = (
    "gameover_overlay",
    "gameover_panel_bg",
    "gameover_title_text",
    "gameover_subtitle_text",
    "gameover_play_again",
    "gameover_play_again_text",
    "gameover_main_menu",
    "gameover_main_menu_text",
)


class Game(GameEventsMixin, GameSaveMixin, BattleSimulation, Application):
    """Top-level orchestrator.

    Responsibilities: wiring subsystems, routing input per panel,
    and running the update/draw pipeline. The battle itself (ticking towers,
    enemies and waves, and drawing them) is BattleSimulation's, shared with
    the main menu's live background.
    """

    # ── construction ──────────────────────────────────────────────────────────

    def __init__(self):
        # Guards on_canvas_resized() firing while Application.__init__ (called
        # below) sets up the very first display mode -- game_area/camera/
        # panel_manager don't exist yet at that point. Flipped True once the
        # rest of this constructor has finished building them.
        self._construction_complete = False

        self.settings = yaml.safe_load(Path("config/settings.yaml").read_text())
        window = self.settings["window"]
        gameplay = self.settings["gameplay"]
        camera = self.settings["camera"]
        audio = self.settings["audio"]
        self._default_audio_settings = dict(audio)  # kept for "reset to defaults"

        self.settings_store = SaveStore("settings")
        saved_settings = self.settings_store.load()
        audio["music_volume"] = saved_settings.get(
            "music_volume", audio["music_volume"]
        )
        audio["sfx_volume"] = saved_settings.get("sfx_volume", audio["sfx_volume"])

        self.save_store = SaveStore("save")
        self._starting_money = gameplay["starting_money"]
        self._starting_lives = gameplay["starting_lives"]
        # panels.yaml's positions/sizes/font sizes are authored for this
        # resolution; _load_panel_layout() shrinks (never grows) UI chrome
        # by the same factor the canvas falls short of it, so buttons/panels
        # stay fully on-screen at smaller windows instead of overflowing.
        self._authored_ui_size = tuple(window["size"])

        super().__init__(
            tuple(window["size"]), window["title"], window["fps"], Mouse(TILE_SIZE)
        )
        self.restore_window_settings(saved_settings)

        window_transform = Transform((0, 0), self.size)
        self.towers: list[BaseTower] = []
        self.enemies: list[Enemy] = []
        self.wave_manager: WaveManager | None = None

        # The map viewport is the whole canvas. self.size is the canvas as
        # restored from the saved window settings above -- on_canvas_resized()
        # is skipped during construction, so this is the only place a saved
        # non-default size reaches the viewport at startup.
        self.game_area = Rect(0, 0, *self.size)
        self.game_state = GameState(
            start_money=gameplay["starting_money"],
            start_lives=gameplay["starting_lives"],
        )
        self.game_state.add_level_listener(self._on_level_changed)
        self._victory_popup_open = False
        self._gameover_popup_open = False
        self._last_frame_ticks: int | None = None  # wall clock of the previous update()
        self._tick_backlog_ms = 0.0  # real time not yet simulated as whole ticks
        self.assets = AssetManager()
        self.tower_config = load_tower_config()
        self.tilemap = Tilemap("assets/maps/tiled_tilemap.tmx")
        self.camera = Camera(
            self.game_area,
            self.tilemap.map_width,
            self.tilemap.map_height,
            scroll_rect=Rect(0, 0, *self.size),
            edge_scroll_zone=camera["edge_scroll_zone"],
            speed=camera["speed"],
            zoom_step=camera["zoom_step"],
            zoom_min=camera["zoom_min"],
            zoom_max=camera["zoom_max"],
        )
        self.panel_manager = PanelManager(starting_tab="main_menu")

        self.load_panels(window_transform)

        self.audio = GameAudio(str(self.assets.sound_path("bg_music")), autoplay=False)
        self.audio.set_music_volume(audio["music_volume"])
        self.audio.set_sfx_volume(audio["sfx_volume"])
        if not saved_settings.get("music_on", True):
            self.audio.pause_music()  # muted last session; kept by show_splash()

        self.hud = GameHUD(self.game_state, self.tower_config, self.panel_manager)
        self.place_sell_feedback = PlaceSellFeedback(
            [self.assets.get_image(f"black_smoke_{i}") for i in range(13)],
            self.assets.get_image("coin_sheet"),
            self.audio.play_sfx,
            self.assets.sound_path("tower_placed"),
            self.assets.sound_path("tower_sold"),
        )
        self.tower_controller = TowerPlacementController(
            self.towers,
            self.tower_config,
            self.assets,
            self.audio,
            self.game_state,
            self.camera,
            self.panel_manager,
            self.tilemap.buildable_grid,
            self.tilemap.map_width,
            self.game_area,
            feedback=self.place_sell_feedback,
        )
        self.hud_slide = HudSlide(self.panel_manager, self.size, self.game_state)
        self.tower_info = TowerInfoPanel(self.panel_manager)
        self.pause_panel = PausePanel(self.panel_manager)
        self._resume_on_unpause = False  # was the run going when the menu opened?
        self._settings_return_panel = "main_menu"  # where Settings' Back leads
        self.buy_tooltip = BuyTooltip(
            self.panel_manager, self.size, load_tower_tooltips()
        )
        self.kill_feedback = KillFeedback(
            self.assets.get_image("coin_sheet"),
            self.assets.font_path("comic_neue_bold"),
        )
        self.life_lost_feedback = LifeLostFeedback(
            self.assets.sound_path("life_lost"), self.audio.sfx_volume
        )

        # Behind the menus: a battle playing itself, in a world of its own.
        self.menu_demo = MenuDemo(
            self.tilemap, self.assets, self.tower_config, self.size
        )
        self.menu_overlay = pygame.Surface(self.size, pygame.SRCALPHA)
        self.menu_overlay.fill((0, 0, 0, 120))
        self.splash = SplashScreen(
            standard_splash_media(self.audio), skip_completely=True
        )
        self._init_wave_manager()

        self.click_sound_path = self.assets.sound_path("click")
        self.handlers = {
            "main_menu": self._handle_main_menu_event,
            "play_menu": self._handle_play_menu_event,
            "credits": self._handle_credits_event,
            "settings": self._handle_settings_event,
            "game": self._handle_game_event,
        }
        self._bind_settings_ui()
        self._build_menu_controllers()
        self._show_path_entrance()
        self._construction_complete = True

    @override
    def show_splash(self) -> None:
        super().show_splash()
        muted = self.audio.is_music_paused
        self.audio.play_music(str(self.assets.sound_path("bg_music")))
        if muted:  # the music toggle was off when the settings were saved
            self.audio.pause_music()

    def _bind_settings_ui(self) -> None:
        """(Re-)applies live audio/window state to the settings panel's
        sliders and labels -- needed both at startup and after a canvas
        resize rebuilds those objects from scratch."""
        self._refresh_window_size_label()
        self._refresh_window_mode_label()
        settings_panel = self.panel_manager["settings"]
        settings_panel["sfx_volume_slider"].set_value(self.audio.sfx_volume())
        settings_panel["sfx_volume_slider"].on_change = self._on_sfx_volume_changed
        settings_panel["music_volume_slider"].set_value(self.audio.music_volume())
        settings_panel["music_volume_slider"].on_change = self._on_music_volume_changed
        self._refresh_sfx_volume_label()
        self._refresh_music_volume_label()
        self._refresh_music_toggles()

    def _build_menu_controllers(self) -> None:
        """(Re-)builds the keyboard-nav controllers from the current panel
        objects -- they hold direct button references, so a canvas resize
        (which rebuilds those objects) must rebuild these too."""
        main_menu_buttons = [
            self.panel_manager["main_menu"][n]
            for n in ("play", "credits", "settings", "exit")
        ]
        play_menu_buttons = [
            self.panel_manager["play_menu"][n]
            for n in ("continue_game", "new_game", "back")
        ]
        self.menu_controllers = {
            "main_menu": MenuController(
                main_menu_buttons,
                self.audio,
                self.assets.sound_path("switch_up"),
                self.assets.sound_path("switch_down"),
            ),
            "play_menu": MenuController(
                play_menu_buttons,
                self.audio,
                self.assets.sound_path("switch_up"),
                self.assets.sound_path("switch_down"),
            ),
        }

    def load_panels(self, window_transform) -> None:
        self.assets.load_manifest("config/assets.yaml")
        missing = self.assets.validate()
        if missing:
            raise RuntimeError("Missing assets:\n" + "\n".join(missing))
        self._load_panel_layout(window_transform)

    def _load_panel_layout(self, window_transform) -> None:
        """The YAML-parsing half of load_panels(), split out so a canvas
        resize can re-run just this part (positions/sizes depend on the
        window_transform passed in) without re-parsing config/assets.yaml."""
        loader = PanelLoaderExt(self.panel_manager, window_transform, self.assets)
        loader.authored_size = self._authored_ui_size
        loader.scale = min(
            1.0,
            window_transform.width / self._authored_ui_size[0],
            window_transform.height / self._authored_ui_size[1],
        )
        loader.register("object", make_factory(self.assets), default=True)
        loader.register("text", make_text_factory(self.assets))
        loader.register("animated", make_animated_factory(self.assets))
        loader.register("slider", make_slider_factory(self.assets))
        loader.register("scrolling_panel", make_scrolling_panel_factory(self.assets))

        loader.load("config/panels.yaml")

    def _refresh_window_size_label(self) -> None:
        w, h = self.resolution
        self.panel_manager["settings"]["window_size_value_text"].set_text(f"{w}x{h}")

    def _refresh_window_mode_label(self) -> None:
        self.panel_manager["settings"]["window_mode_value_text"].set_text(
            WINDOW_MODE_LABELS[self._window_mode]
        )

    def _refresh_sfx_volume_label(self) -> None:
        self.panel_manager["settings"]["sfx_volume_value_text"].set_text(
            f"{round(self.audio.sfx_volume() * 100)}%"
        )

    def _refresh_music_volume_label(self) -> None:
        self.panel_manager["settings"]["music_volume_value_text"].set_text(
            f"{round(self.audio.music_volume() * 100)}%"
        )

    # ── settings persistence ─────────────────────────────────────────────────
    #
    # Window mode/resolution persistence itself lives in Application now
    # (restore_window_settings/window_settings/reset_window_settings) --
    # these just merge that with this project's own audio settings.

    def _save_settings(self) -> None:
        self.settings_store.save(
            {
                **self.window_settings(),
                "sfx_volume": self.audio.sfx_volume(),
                "music_volume": self.audio.music_volume(),
                "music_on": not self.audio.is_music_paused,
            }
        )

    def _reset_settings(self) -> None:
        """Restores window mode/size and both volumes to config/settings.yaml's
        shipped defaults (not merely the values from the last save), then
        persists immediately -- Reset is a deliberate action, not a live drag,
        so it shouldn't wait for the player to also press Back."""
        self.reset_window_settings()
        self.audio.set_sfx_volume(self._default_audio_settings["sfx_volume"])
        self.audio.set_music_volume(self._default_audio_settings["music_volume"])

        settings_panel = self.panel_manager["settings"]
        settings_panel["sfx_volume_slider"].set_value(self.audio.sfx_volume())
        settings_panel["music_volume_slider"].set_value(self.audio.music_volume())
        self._refresh_window_size_label()
        self._refresh_window_mode_label()
        self._refresh_sfx_volume_label()
        self._refresh_music_volume_label()
        self._save_settings()

    # ── BattleSimulation hooks ───────────────────────────────────────────────

    @override
    def _on_tower_positions(self, positions: set[tuple]) -> None:
        self.tower_controller.tower_positions = positions

    @override
    def _on_enemy_killed(self, enemy) -> None:
        self.kill_feedback.add_kill(
            enemy.position,
            enemy.killMoney,
            self.camera.world_to_screen(enemy.position),
            self.game_state.time_ms,
        )

    @override
    def _on_enemy_escaped(self, enemy) -> None:
        lives_before = self.game_state.lives
        super()._on_enemy_escaped(enemy)
        if self.game_state.lives == 0:
            # The last life: the game-over screen takes over, no pulse.
            if not self._gameover_popup_open:
                self.save_store.delete()  # a lost run isn't continuable
                self._trigger_game_over()
            return
        self.life_lost_feedback.lives_lost(lives_before - self.game_state.lives)

    def _show_path_entrance(self) -> None:
        """Point the camera at where enemies spawn -- the map's top-left
        corner it would otherwise open on is empty grass."""
        self.camera.center_on(self.tilemap.waypoints[0])

    def _init_wave_manager(self) -> None:
        if not self.tilemap.waypoints:
            raise RuntimeError("TMX has no Paths/polyline; enemies have nowhere to go")
        self.wave_manager = WaveManager(self.tilemap.waypoints, self.assets)

    # ── victory popup ─────────────────────────────────────────────────────────

    def _on_level_changed(self, level: int) -> None:
        if level == WIN_WAVE + 1 and not self.game_state.has_won:
            self._trigger_victory()

    def _trigger_victory(self) -> None:
        self.game_state.has_won = True
        self.game_state.is_started = False
        self.panel_manager["game"]["start_pause_button_icon"].set_state(None)
        self._victory_popup_open = True
        self._set_victory_popup_active(True)

    def _close_victory_popup(self) -> None:
        self._victory_popup_open = False
        self._set_victory_popup_active(False)

    def _set_victory_popup_active(self, active: bool) -> None:
        panel = self.panel_manager["game"]
        for name in _VICTORY_POPUP_OBJECTS:
            panel[name].active = active

    # ── game over popup ──────────────────────────────────────────────────────

    def _trigger_game_over(self) -> None:
        self.game_state.is_started = False
        self.panel_manager["game"]["start_pause_button_icon"].set_state(None)
        self._gameover_popup_open = True
        self._set_gameover_popup_active(True)

    def _close_gameover_popup(self) -> None:
        self._gameover_popup_open = False
        self._set_gameover_popup_active(False)

    def _set_gameover_popup_active(self, active: bool) -> None:
        panel = self.panel_manager["game"]
        for name in _GAMEOVER_POPUP_OBJECTS:
            panel[name].active = active

    # ── canvas resize ────────────────────────────────────────────────────────

    @override
    def on_canvas_resized(self, new_size: tuple[int, int]) -> None:
        if not self._construction_complete:
            return  # Application.__init__ is still setting up the first display mode
        self._reflow_camera(new_size)
        self._reflow_panels(new_size)

    def _reflow_camera(self, new_size: tuple[int, int]) -> None:
        """game_area IS camera.rect (same Rect object, shared by reference
        with TowerPlacementController too) -- mutating it in place propagates
        everywhere it's already shared, no reassignment needed."""
        w, h = new_size
        self.game_area.update(0, 0, w, h)
        self.camera.scroll_rect.update(0, 0, w, h)
        self.camera._clamp_offset()

    def _reflow_panels(self, new_size: tuple[int, int]) -> None:
        """Rebuilds every panel object against the new canvas size, reusing
        the existing panel_manager (add_object() overwrites by name, so
        stale objects are simply replaced) rather than replacing it -- that
        keeps TowerPlacementController's stored panel_manager reference
        valid. GameHUD is re-bound rather than reconstructed so its
        already-registered GameState listeners aren't duplicated (GameState
        has no listener-removal mechanism)."""
        self._load_panel_layout(Transform((0, 0), new_size))
        self.hud.rebind_panel(self.panel_manager)
        self.tower_info.rebind(self.panel_manager)
        self.pause_panel.rebind(self.panel_manager)
        self.buy_tooltip.rebind(self.panel_manager, new_size)
        self.hud_slide.rebind(self.panel_manager, new_size)
        self._bind_settings_ui()
        self._build_menu_controllers()
        self._sync_game_ui()
        self.menu_demo.resize(new_size)
        self.menu_overlay = pygame.Surface(new_size, pygame.SRCALPHA)
        self.menu_overlay.fill((0, 0, 0, 120))

    # ── update ────────────────────────────────────────────────────────────────

    @override
    def update(self) -> None:
        frame_ms = self._elapsed_frame_ms()
        self.panel_manager.update()
        if self.panel_manager.current_panel == "game":
            self._update_game(frame_ms)
        else:
            self.menu_demo.update(frame_ms)
        if self.panel_manager.current_panel == "settings":
            self._refresh_window_mode_label()  # picks up F11-triggered mode changes

    def _elapsed_frame_ms(self) -> float:
        """Wall-clock ms since the previous update(), capped at MAX_FRAME_MS."""
        now = pygame.time.get_ticks()
        last, self._last_frame_ticks = self._last_frame_ticks, now
        if last is None:
            return 0.0
        return float(min(MAX_FRAME_MS, max(0, now - last)))

    def _update_game(self, frame_ms: float) -> None:
        # Input-driven motion follows real time; the simulation runs in fixed
        # ticks so the same game plays out at any frame rate.
        if not self.pause_panel.is_open:  # no scrolling behind the menu
            self.camera.update_with_mouse(self.mouse.position, frame_ms / TICK_MS)
        self.hud_slide.update(frame_ms)
        self.kill_feedback.update(frame_ms, self.game_state.time_ms)
        self.place_sell_feedback.update(frame_ms)
        self.life_lost_feedback.update(frame_ms)
        self.mouse.update()
        self.tower_controller.update_cursor(self.mouse.position)
        self._tick_backlog_ms += frame_ms
        while self._tick_backlog_ms >= TICK_MS:
            self._tick_backlog_ms -= TICK_MS
            self._tick()
        self.tower_info.show(self._selected_tower())
        self.buy_tooltip.update(
            self.mouse.position,
            self.hud_slide.shown
            and not self.hud_slide.is_sliding
            and not self.pause_panel.is_open,
        )

    # ── event handling ────────────────────────────────────────────────────────

    @override
    def handle_event(self, event):
        self.panel_manager.handle_event(event, self.mouse.position)
        if controller := self.menu_controllers.get(self.panel_manager.current_panel):
            controller.handle_event(event, self.mouse.position)
        if handler := self.handlers.get(self.panel_manager.current_panel):
            handler(event)
        # The menus' music toggle (the game's is on the pause menu instead).
        panel = self.panel_manager[self.panel_manager.current_panel]
        if "music_toggle_button" in panel and self._activate(
            panel["music_toggle_button"], event
        ):
            self._toggle_music()

    # ── render pipeline ───────────────────────────────────────────────────────

    @override
    def draw(self):
        self.window.fill((0, 0, 0))
        if self.panel_manager.current_panel == "game":
            self._draw_game()
        else:
            self.menu_demo.draw(self.window)
            self.window.blit(self.menu_overlay, (0, 0))
        if self.panel_manager.current_panel == "game":
            with self.hud_slide.shifted():
                self.panel_manager.draw(self.window)
                if not self.pause_panel.is_open:  # not over the menu's overlay
                    self.tower_controller.draw_shortcuts(self.window)
                    self.tower_info.draw_hp_fill(self.window)
            self._draw_kill_coins()
        else:
            self.panel_manager.draw(self.window)

    def _draw_game(self) -> None:
        old_clip = self.window.get_clip()
        self.window.set_clip(self.game_area)
        self._draw_battle(self.window, self.camera)
        self.place_sell_feedback.draw(self.window, self.camera)
        self.kill_feedback.draw_texts(self.window, self.camera, self.game_state.time_ms)
        self.tower_controller.draw(self.window, self.mouse.position)
        self._draw_selected_tower_ui()
        self.life_lost_feedback.draw(self.window)  # under the HUD
        self.window.set_clip(old_clip)

    def _draw_kill_coins(self) -> None:
        """Coins fly to the money counter's resting place -- where it shows
        even while the HUD is hidden, since a kill brings it back -- and the
        counter, wherever it's drawn now, pops as they land."""
        panel = self.panel_manager["game"]
        self.kill_feedback.draw_coins(self.window, panel["coin_image"].rect.center)
        counter = panel["coin_text"].rect.move(self.hud_slide.offset("money"))
        self.kill_feedback.draw_pop(self.window, counter)

    def _selected_tower(self) -> GroundTower | None:
        """The selected tower, if it's still standing (it may have been sold
        or destroyed since). Only ground towers can be selected: a plane
        leaves its tile at once."""
        selected = self.game_state.selected_tower
        if selected is None or selected not in self.towers:
            return None
        return selected if isinstance(selected, GroundTower) else None

    def _draw_selected_tower_ui(self) -> None:
        if selected := self._selected_tower():
            selected.draw_selected_ui(self.window, self.game_state, self.camera)

    # ── debug ─────────────────────────────────────────────────────────────────

    @override
    def draw_debug(self):
        if not self._is_in_debug_mode:
            return

        debug_info = [
            self.mouse.info(),
            self.camera.info(),
            self.panel_manager["main_menu"]["play"].info(),
        ]
        Debug.draw(self.window, pygame.font.SysFont("Consolas", 20), debug_info)

    # ── exit ──────────────────────────────────────────────────────────────────

    @override
    def on_exit_request(self):
        """Esc (and the window's close button -- pygamine routes both here).
        In a run it opens or closes the pause menu; on Settings it acts as
        Back; elsewhere it goes back to the main menu, or quits from it."""
        panel = self.panel_manager.current_panel
        if panel == "main_menu":
            self.exit()
        elif panel == "settings":
            self._leave_settings()
        elif panel == "game":
            if self._victory_popup_open or self._gameover_popup_open:
                # As before the pause menu: the popup's run ends here.
                self.game_state.is_started = False
                if not self._gameover_popup_open:
                    self._save_game()  # a lost run isn't continuable -- nothing to save
                self.panel_manager.current_panel = "main_menu"
            elif self.pause_panel.is_open:
                self._close_pause_menu()
            else:
                self._open_pause_menu()
        elif panel in ("play_menu", "credits"):
            self.panel_manager.current_panel = "main_menu"

    @override
    def exit(self) -> None:
        self._save_settings()
        super().exit()
