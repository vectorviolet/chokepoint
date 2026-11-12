import random
from functools import partial
from typing import override

import pygame
from pygame import Rect

from app.game_events import GameEventsMixin
from app.game_save import GameSaveMixin
from app.settings_tabs import (
    DEFAULT_TAB,
    TOGGLE_SETTINGS,
    WEB_HIDDEN_ROW_OBJECTS,
    SettingsTabs,
)
from app.volume_settings import VOLUME_SETTINGS, VolumeSetting, saved_volume
from pygamine import ALPHA_BLIT
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
from util.config_loader import (
    LANG_DIR,
    gameplay_settings,
    hud_settings,
    load_settings,
    load_tower_config,
)
from pygamine import Camera
from pygamine.util.localization import DEFAULT_LANGUAGE, localization, tr
from util import web
from util.constants import (
    FULLSCREEN_POLL_FRAMES,
    TILE_SIZE,
    TICK_MS,
    MAX_FRAME_MS,
    WIN_WAVE,
)

# A mouse press this soon after the window regains focus after a focus-loss
# pause is the click that refocused it, and is dropped. Later ones are the
# player's (the focus may have come back without a click at all).
REFOCUS_CLICK_WINDOW_MS = 250
from pygamine import Debug
from pygamine import SplashScreen, standard_splash_media
from pygamine import SaveStore
from pygamine import GameAudio
from gameplay.combat.enemy import Enemy
from ui.game_hud import GameHUD
from ui.hud_slide import HudSlide
from ui.bomb_impact_feedback import BombImpactFeedback, ExplosionFrames
from ui.death_feedback import DeathFeedback
from ui.hit_feedback import HitFeedback
from ui.kill_feedback import KillFeedback
from ui.life_lost_feedback import LifeLostFeedback
from ui.place_sell_feedback import PlaceSellFeedback
from ui.buy_tooltip import BuyTooltip
from ui.enemy_hp_label import EnemyHpLabel
from ui.tower_info import TowerInfoPanel
from ui.pause_panel import PAUSE_PANEL_OBJECTS, PausePanel
from domain.game_state import GameState
from pygamine import Transform
from gameplay.tilemap import Tilemap
from gameplay.combat.tower_placement import TowerPlacementController
from gameplay.towers import BaseTower
from gameplay.combat.wave_manager import WaveManager
from gameplay.battle import BattleSimulation
from gameplay.menu_demo import MenuDemo

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

    def __init__(self, seed: int | None = None):
        # `seed` makes every random choice repeatable (the menu demo's runs,
        # the place/sell and kill effects): the README capture script uses it.
        # None (the game) leaves them unseeded.
        seeds = random.Random(seed) if seed is not None else None

        def rng() -> random.Random | None:
            return random.Random(seeds.getrandbits(64)) if seeds else None

        # Guards on_canvas_resized() firing while Application.__init__ (called
        # below) sets up the very first display mode -- game_area/camera/
        # panel_manager don't exist yet at that point. Flipped True once the
        # rest of this constructor has finished building them.
        self._construction_complete = False

        self.settings = load_settings()
        window = self.settings["window"]
        gameplay = gameplay_settings(self.settings)
        camera = self.settings["camera"]
        audio = self.settings["audio"]
        self._default_audio_settings = dict(audio)  # kept for "reset to defaults"
        self._default_auto_pause = bool(gameplay.get("auto_pause_between_waves", False))
        self._default_keep_placing = bool(gameplay.get("keep_placing", False))
        self._default_toggles = {key: bool(gameplay[key]) for key in TOGGLE_SETTINGS}

        self.settings_store = SaveStore("settings")
        saved_settings = self.settings_store.load()
        # The language tables, and the saved language (English if there is
        # none or it isn't available: a hand-edited file, a removed language).
        localization.load(LANG_DIR)
        saved_language = saved_settings.get("language")
        localization.set_language(
            saved_language
            if isinstance(saved_language, str)
            and saved_language in localization.languages()
            else DEFAULT_LANGUAGE
        )
        # Missing (e.g. master in old settings files) or broken values load
        # at the shipped default; out-of-range ones are clamped to 0-1.
        for volume in VOLUME_SETTINGS:
            audio[volume.key] = saved_volume(
                saved_settings, volume.key, audio[volume.key]
            )

        # Pause the run as each wave is cleared (the HUD's hourglass toggle).
        # A global setting: old settings files without it load as off.
        self.auto_pause: bool = bool(
            saved_settings.get("auto_pause_between_waves", self._default_auto_pause)
        )

        # The ON/OFF settings (TOGGLE_SETTINGS). Old settings files without
        # them load at the shipped default.
        self.toggles: dict[str, bool] = {
            key: bool(saved_settings.get(key, default))
            for key, default in self._default_toggles.items()
        }
        # Window focus (pause on focus loss, no edge scroll while unfocused):
        # `_window_focused` follows pygame.key.get_focused() every update();
        # a focus-lost event only marks `_focus_lost_pending`, acted on in
        # update() if the window is still unfocused (see _sync_focus).
        self._window_focused = True  # read from the real window below
        self._focus_lost_pending = False
        self._paused_by_focus_loss = False
        # Wall-clock ms until which a press is the refocusing click (dropped);
        # None: nothing to drop.
        self._swallow_press_until: int | None = None
        self._swallow_release = False

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
        if not web.is_web():  # the browser has no window modes or sizes to restore
            self.restore_window_settings(saved_settings)
        self._window_focused = pygame.key.get_focused()  # the display exists now

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
        for volume in VOLUME_SETTINGS:
            getattr(self.audio, volume.setter)(audio[volume.key])
        if not saved_settings.get("music_on", True):
            self.audio.pause_music()  # muted last session; kept by show_splash()

        hud = hud_settings(self.settings)
        self.hud = GameHUD(
            self.game_state,
            self.tower_config,
            self.panel_manager,
            money_style=hud["money_style"],
            roll_ms=hud["money_roll_ms"],
        )
        self.place_sell_feedback = PlaceSellFeedback(
            [self.assets.get_image(f"black_smoke_{i}") for i in range(13)],
            self.assets.get_image("coin_sheet"),
            self.audio.play_sfx,
            self.assets.sound_path("tower_placed"),
            self.assets.sound_path("tower_sold"),
            rng=rng(),
        )
        # One explosion animation cache for the bombs and the deaths.
        explosion_frames = ExplosionFrames(self.assets)
        self.bomb_impacts: BombImpactFeedback = BombImpactFeedback(
            self.assets,
            self.audio.play_sfx,
            self.assets.sound_path("bomb_impact"),
            frames=explosion_frames,
            reduce_flashing=self.toggles["reduce_flashing"],
        )
        self.hit_feedback: HitFeedback = HitFeedback(
            rng=rng(), reduce_flashing=self.toggles["reduce_flashing"]
        )
        self.death_feedback: DeathFeedback = DeathFeedback(
            self.assets,
            self.audio.play_sfx,
            self.assets.sound_path("enemy_destroyed"),
            self.assets.sound_path("heavy_destroyed"),
            frames=explosion_frames,
            reduce_flashing=self.toggles["reduce_flashing"],
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
            enemies=self.enemies,
            on_tower_sold=self._tower_sold,
            on_denied=self._deny_purchase,
            keep_selection_while_buying=lambda: self.toggles[
                "keep_selection_while_buying"
            ],
        )
        # Keep placing after a placement (the HUD toggle / a Shift press). A
        # global setting: old settings files without it load as off.
        self.keep_placing = bool(
            saved_settings.get("keep_placing", self._default_keep_placing)
        )
        self.enemy_hp_label = EnemyHpLabel(self.assets.font_path("anton"))
        self.hud_slide = HudSlide(self.panel_manager, self.size, self.game_state)
        self.tower_info = TowerInfoPanel(self.panel_manager)
        self.pause_panel = PausePanel(self.panel_manager)
        self._resume_on_unpause = False  # was the run going when the menu opened?
        self._settings_return_panel = "main_menu"  # where Settings' Back leads
        self._settings_tab = DEFAULT_TAB  # the open Settings tab (kept over resizes)
        self.itch_url = self.settings["links"]["itch_page"]
        self._fullscreen_poll = (
            0  # frames since the Fullscreen row last asked the browser
        )
        self.buy_tooltip = BuyTooltip(self.panel_manager, self.size)
        self.kill_feedback = KillFeedback(
            self.assets.get_image("coin_sheet"),
            self.assets.font_path("fira_sans_bold"),
            rng=rng(),
        )
        self.hud.pending_money = lambda: self.kill_feedback.pending_money
        self.set_reduce_flashing(self.toggles["reduce_flashing"])
        self.life_lost_feedback = LifeLostFeedback(
            self.assets.sound_path("life_lost"), self.audio.effective_sfx_volume
        )

        # Behind the menus: a battle playing itself, in a world of its own.
        self.menu_demo = MenuDemo(
            self.tilemap,
            self.assets,
            self.tower_config,
            self.size,
            rng=rng(),
            reduce_flashing=self.toggles["reduce_flashing"],
        )
        self.menu_overlay = pygame.Surface(self.size, pygame.SRCALPHA)
        self.menu_overlay.fill((0, 0, 0, 120))
        # "Skip intro": no splash is set up, so run() goes straight to the menu.
        # The web build never shows it (its clip plays from a thread and its
        # loop blocks the browser); whether it should is the owner's call, #186.
        self.splash = (
            None
            if self.toggles["skip_intro"] or web.is_web()
            else SplashScreen(standard_splash_media(self.audio), skip_completely=True)
        )
        self._init_wave_manager()

        self.click_sound_path = self.assets.sound_path("click")
        self.handlers = {
            "main_menu": self._handle_main_menu_event,
            "play_menu": self._handle_play_menu_event,
            "credits": self._handle_credits_event,
            "settings": self._handle_settings_event,
            "thanks": self._handle_thanks_event,
            "game": self._handle_game_event,
        }
        self._bind_settings_ui()
        self._refresh_auto_pause_button()
        self._build_menu_controllers()
        self._show_path_entrance()
        self._construction_complete = True

    @override
    def show_splash(self) -> None:
        # Read before the splash: it plays its clip through this same
        # GameAudio, and play_music()/stop_music() clear the paused flag.
        muted = self.audio.is_music_paused
        super().show_splash()
        self.audio.play_music(str(self.assets.sound_path("bg_music")))
        if muted:  # the music toggle was off when the settings were saved
            self.audio.pause_music()
        self._refresh_music_toggles()  # icons and labels follow the audio

    def _bind_settings_ui(self) -> None:
        """(Re-)applies live audio/window state to the settings panel's
        sliders and labels -- needed both at startup and after a canvas
        resize rebuilds those objects from scratch."""
        self._refresh_window_size_label()
        self._refresh_window_mode_label()
        self._apply_web_display_rows()
        self._refresh_language_label()
        settings_panel = self.panel_manager["settings"]
        self.settings_tabs = SettingsTabs(settings_panel, self._settings_tab)
        for volume in VOLUME_SETTINGS:
            slider = settings_panel[volume.slider]
            slider.set_value(getattr(self.audio, volume.getter)())
            slider.on_change = partial(self._on_volume_changed, volume)
            self._refresh_volume_label(volume)
        self._refresh_music_toggles()
        self._refresh_toggle_labels()

    def _menu_controller(self, buttons: list) -> MenuController:
        """Keyboard navigation over `buttons` with the menus' switch sounds."""
        return MenuController(
            buttons,
            self.audio,
            self.assets.sound_path("switch_up"),
            self.assets.sound_path("switch_down"),
        )

    def _build_menu_controllers(self, settings_focus: str | None = None) -> None:
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
        thanks_buttons = [
            self.panel_manager["thanks"][n] for n in ("thanks_rate", "thanks_back")
        ]
        self.menu_controllers = {
            "main_menu": self._menu_controller(main_menu_buttons),
            "play_menu": self._menu_controller(play_menu_buttons),
            "thanks": self._menu_controller(thanks_buttons),
        }
        # `settings_focus`: the Settings button (by name) that had the focus
        # before a rebuild of the panel objects.
        focus = (
            self.panel_manager["settings"][settings_focus] if settings_focus else None
        )
        self._build_settings_controller(focus)

    def _build_settings_controller(self, focus=None) -> None:
        """The Settings keyboard controller over the open tab's focus order
        (tabs, that tab's row buttons, Back, Reset). Rebuilt on every tab
        change; `focus` (a button) keeps the focus where it was."""
        previous = self.menu_controllers.get("settings")
        if previous is not None:
            for button in previous.buttons:
                button.focused = False
        controller = self._menu_controller(self.settings_tabs.focus_order())
        if focus is not None and focus in controller.buttons:
            controller.buttons[0].focused = False
            focus.focused = True
        self.menu_controllers["settings"] = controller

    def _focused_settings_button(self) -> str | None:
        """Name of the Settings button the keyboard focus is on, if any."""
        focused = self.menu_controllers["settings"].focused
        return None if focused is None else self.settings_tabs.name_of(focused)

    def _show_settings_tab(self, key: str, *, focus_tab: bool = False) -> None:
        """Opens Settings tab `key`; the keyboard focus stays on the button it
        was on if that is still in the new order (or moves to the tab button)."""
        controller = self.menu_controllers["settings"]
        focus = controller.focused
        self.settings_tabs.select(key)
        self._settings_tab = key
        if focus_tab:
            focus = self.panel_manager["settings"][self.settings_tabs.tab(key).button]
        self._build_settings_controller(focus)

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
        self.panel_manager["game"]["victory_subtitle_text"].set_params(wave=WIN_WAVE)
        self._bind_popup_objects()

    def _bind_popup_objects(self) -> None:
        """Single source of truth for what draws last on the game panel: the
        pause, victory and game over popups (the panels are rebuilt on every
        canvas resize, so this re-runs from _load_panel_layout). Any new modal
        on the game panel must be added here, or the run's effects draw over it."""
        panel = self.panel_manager["game"]
        names = (
            *PAUSE_PANEL_OBJECTS,
            *_VICTORY_POPUP_OBJECTS,
            *_GAMEOVER_POPUP_OBJECTS,
        )
        self._popup_object_ids = {id(panel[name]) for name in names}

    def _refresh_window_size_label(self) -> None:
        w, h = self.resolution
        self.panel_manager["settings"]["window_size_value_text"].set_text(f"{w}x{h}")

    def _refresh_window_mode_label(self) -> None:
        """The window mode row's value. In the browser that row is the
        Fullscreen toggle and shows ON or OFF."""
        if web.is_web():
            text = tr("settings.on" if web.is_fullscreen() else "settings.off")
        else:
            text = tr(f"settings.window_mode_{self._window_mode}")
        self.panel_manager["settings"]["window_mode_value_text"].set_text(text)

    def _apply_web_display_rows(self) -> None:
        """Settings in the browser: the Window size and Skip intro rows are
        hidden (the canvas has a fixed size; there is no splash), and the
        window mode row becomes the Fullscreen toggle (its caption is set here,
        in code, so it follows the language through _refresh_language_texts).
        Desktop keeps every row as authored."""
        if not web.is_web():
            return
        settings = self.panel_manager["settings"]
        for name in WEB_HIDDEN_ROW_OBJECTS:
            settings[name].active = False
        settings["window_mode_label_text"].set_text(
            tr("settings.window_mode_fullscreen")
        )

    @override
    def cycle_window_mode(self, step: int = 1) -> None:
        """F11 and the window mode row. In the browser there are no window
        modes: both toggle the browser's fullscreen instead (it only works
        from a click or key press, which both are)."""
        if web.is_web():
            web.toggle_fullscreen()
        else:
            super().cycle_window_mode(step)

    def _refresh_toggle_labels(self) -> None:
        settings = self.panel_manager["settings"]
        for key, on in self.toggles.items():
            settings[f"{key}_value_text"].set_text(
                tr("settings.on" if on else "settings.off")
            )

    def _refresh_language_label(self) -> None:
        """The language row shows the current language's own name (its
        `_meta.name`, written in capitals in the language file)."""
        name = localization.languages()[localization.language]
        self.panel_manager["settings"]["language_value_text"].set_text(name)

    def set_language(self, code: str) -> None:
        """Switches the language at once: every key-driven text re-renders
        (pygamine), then the texts the game formats itself are rebuilt. Saved
        with the other settings. Raises KeyError, changing nothing, for an
        unknown code. Always switch through here, not localization alone, so
        the texts built in code follow."""
        localization.set_language(code)
        self._refresh_language_texts()

    def _refresh_language_texts(self) -> None:
        """Re-sets every text the game builds in code, in the current language."""
        self._refresh_window_mode_label()
        self._apply_web_display_rows()
        self._refresh_toggle_labels()
        self._refresh_language_label()
        self._refresh_music_toggles()
        self._refresh_game_language_texts()

    def _refresh_game_language_texts(self) -> None:
        """The in-run texts built in code: HUD, tower panel, open tooltip."""
        self.hud.refresh_language()
        self.tower_info.show(self.tower_info.tower)
        self.buy_tooltip.refresh_language()

    def _refresh_volume_label(self, volume: VolumeSetting) -> None:
        self.panel_manager["settings"][volume.label].set_text(
            f"{round(getattr(self.audio, volume.getter)() * 100)}%"
        )

    # ── settings persistence ─────────────────────────────────────────────────
    #
    # Window mode/resolution persistence itself lives in Application now
    # (restore_window_settings/window_settings/reset_window_settings) --
    # these just merge that with this project's own audio settings.

    @property
    def keep_placing(self) -> bool:
        """The keep-placing toggle, held by the placement controller."""
        return self.tower_controller.keep_placing

    @keep_placing.setter
    def keep_placing(self, on: bool) -> None:
        self.tower_controller.keep_placing = on
        self._refresh_keep_placing_button()

    def set_toggle(self, key: str, on: bool) -> None:
        """Sets the ON/OFF setting `key` (one of TOGGLE_SETTINGS). Reduce
        flashing reaches the game's and the menu demo's feedback at once;
        Skip intro is only read at the next launch."""
        assert key in self.toggles, key
        self.toggles[key] = on
        if key == "reduce_flashing":
            self.set_reduce_flashing(on)
            self.menu_demo.set_reduce_flashing(on)
        self._refresh_toggle_labels()

    def _save_settings(self) -> None:
        self.settings_store.save(
            {
                **({} if web.is_web() else self.window_settings()),
                **{
                    volume.key: getattr(self.audio, volume.getter)()
                    for volume in VOLUME_SETTINGS
                },
                "music_on": not self.audio.is_music_paused,
                "auto_pause_between_waves": self.auto_pause,
                "keep_placing": self.keep_placing,
                "language": localization.language,
                **self.toggles,
            }
        )

    def _reset_settings(self) -> None:
        """Restores window mode/size, the three volumes and the language (English)
        to the shipped defaults (not merely the values from the last save), then
        persists immediately -- Reset is a deliberate action, not a live drag,
        so it shouldn't wait for the player to also press Back."""
        if web.is_web():
            # No window settings to restore; the default is no fullscreen.
            if web.is_fullscreen():
                web.toggle_fullscreen()
        else:
            self.reset_window_settings()
        for volume in VOLUME_SETTINGS:
            getattr(self.audio, volume.setter)(self._default_audio_settings[volume.key])
        self.life_lost_feedback.apply_volume()
        self.auto_pause = self._default_auto_pause
        self._refresh_auto_pause_button()
        self.keep_placing = self._default_keep_placing
        for key, default in self._default_toggles.items():
            self.set_toggle(key, default)
        localization.set_language(DEFAULT_LANGUAGE)

        self._bind_settings_ui()  # sliders, labels (language too) and window labels
        self._refresh_game_language_texts()
        self._save_settings()

    # ── BattleSimulation hooks ───────────────────────────────────────────────

    @override
    def _on_tower_positions(self, positions: set[tuple]) -> None:
        self.tower_controller.tower_positions = positions

    @override
    def set_reduce_flashing(self, on: bool) -> None:
        super().set_reduce_flashing(on)
        self.kill_feedback.reduce_flashing = on
        self.hud.reduce_flashing = on
        if on:  # no animation: the number is the real balance from now on
            self._snap_money()

    def _snap_money(self) -> None:
        """The HUD number is the real balance at once: the coins in flight stop
        holding any of it back."""
        self.kill_feedback.settle()
        self.hud.snap_money()

    @override
    def _on_enemy_killed(self, enemy) -> None:
        self.kill_feedback.add_kill(
            enemy.position,
            enemy.kill_money,
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
        self.wave_manager.on_wave_cleared = self._on_wave_cleared

    def _on_wave_cleared(self) -> None:
        """Clearing round WIN_WAVE wins the run: the victory popup opens
        there, before the next round starts, so the HUD still shows that
        round behind it. Otherwise auto-pause: the run stops as each wave is
        cleared, as if the start/pause button had been pressed. Either way,
        starting again lets the wave manager carry on to the next wave as
        usual."""
        if not self._open_victory_if_won() and self.auto_pause:
            self._set_started(False)

    # ── victory popup ─────────────────────────────────────────────────────────

    def _open_victory_if_won(self) -> bool:
        """Opens the victory popup if round WIN_WAVE has just been cleared
        and the run isn't won yet; says whether it did. Called when a wave
        is cleared, and on load for a run saved with that wave already
        cleared (the hook won't fire again for it)."""
        if self.game_state.level != WIN_WAVE or self.game_state.has_won:
            return False
        self._trigger_victory()
        return True

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
        # The rebuilt objects replace the focused one: keep it by name.
        settings_focus = self._focused_settings_button()
        self._load_panel_layout(Transform((0, 0), new_size))
        self.hud.rebind_panel(self.panel_manager)
        self.tower_info.rebind(self.panel_manager)
        self.pause_panel.rebind(self.panel_manager)
        self.buy_tooltip.rebind(self.panel_manager, new_size)
        self.hud_slide.rebind(self.panel_manager, new_size)
        self._bind_settings_ui()
        self._build_menu_controllers(settings_focus)
        self._sync_game_ui()
        self.menu_demo.resize(new_size)
        self.menu_overlay = pygame.Surface(new_size, pygame.SRCALPHA)
        self.menu_overlay.fill((0, 0, 0, 120))

    # ── update ────────────────────────────────────────────────────────────────

    @override
    def update(self) -> None:
        self._sync_focus()
        frame_ms = self._elapsed_frame_ms()
        self.panel_manager.update()
        if self.panel_manager.current_panel == "game":
            self._update_game(frame_ms)
        else:
            self.menu_demo.update(frame_ms)
        if self.panel_manager.current_panel == "settings":
            # Picks up F11-triggered mode changes. In the browser this asks
            # the page, so it polls (a click refreshes at once; Esc out of
            # fullscreen shows within FULLSCREEN_POLL_FRAMES).
            self._fullscreen_poll = (self._fullscreen_poll + 1) % FULLSCREEN_POLL_FRAMES
            if not web.is_web() or self._fullscreen_poll == 0:
                self._refresh_window_mode_label()

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
        # No scrolling behind the menu, nor while the window is unfocused
        # (whatever "Pause on focus loss" says), so the map can't drift.
        if not self.pause_panel.is_open and self._window_focused:
            self.camera.update_with_mouse(self.mouse.position, frame_ms / TICK_MS)
        self.hud_slide.update(frame_ms)
        self.kill_feedback.update(frame_ms, self.game_state.time_ms)
        # The number shows the whole balance while the pause menu or a popup (victory,
        # game over) is open. The wave pause and the start/pause button don't snap: the
        # coins keep flying on real time then, so the last kill of a wave still animates.
        if self.kill_feedback.pending_money and self._any_popup_open():
            self._snap_money()
        self.hud.update(frame_ms)
        self.place_sell_feedback.update(frame_ms)
        self.bomb_impacts.update(frame_ms)
        self.hit_feedback.update(frame_ms)
        self.death_feedback.update(frame_ms)
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
        if event.type == pygame.WINDOWFOCUSLOST:
            self._window_focused = False
            self._focus_lost_pending = True  # acted on in update(): _sync_focus
            return
        if event.type == pygame.WINDOWFOCUSGAINED:
            # No auto-resume: the pause menu stays open. The click that brings
            # the window back must not land on it, so the first press is dropped.
            self._window_focused = True
            self._focus_lost_pending = False
            self._swallow_press_until = (
                pygame.time.get_ticks() + REFOCUS_CLICK_WINDOW_MS
                if self._paused_by_focus_loss
                else None
            )
            self._paused_by_focus_loss = False
            return
        if self._swallow_input(event):
            return
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

    def _sync_focus(self) -> None:
        """Called each update(). The window's real focus decides, not the
        events alone: SDL sends a focus-lost/-gained pair when the window
        mode changes (F11), and the splash's own event loop takes the focus
        events of the intro. A focus-lost event only counts if the window is
        still unfocused now; then, with "Pause on focus loss" on, a battle
        with no popup open gets the pause menu exactly as with Esc (nothing in
        the menus)."""
        self._window_focused = pygame.key.get_focused()
        pending, self._focus_lost_pending = self._focus_lost_pending, False
        if (
            pending
            and not self._window_focused
            and self.toggles["pause_on_focus_loss"]
            and self.panel_manager.current_panel == "game"
            and not self._any_popup_open()
        ):
            self._open_pause_menu()
            self._paused_by_focus_loss = True

    def _swallow_input(self, event) -> bool:
        """True for a mouse press within REFOCUS_CLICK_WINDOW_MS of a
        focus-loss pause getting its focus back, and for that press's
        release: clicking the window to refocus it must not hit the pause
        menu's buttons. A later press (focus came back without a click) is
        the player's, and disarms this."""
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and self._swallow_press_until is not None
        ):
            until, self._swallow_press_until = self._swallow_press_until, None
            if pygame.time.get_ticks() <= until:
                self._swallow_release = True
                return True
        if event.type == pygame.MOUSEBUTTONUP and self._swallow_release:
            self._swallow_release = False
            return True
        return False

    # ── render pipeline ───────────────────────────────────────────────────────

    @override
    def draw(self):
        canvas = self.window
        canvas.fill((0, 0, 0))
        if self.panel_manager.current_panel == "game":
            self._draw_game()
        else:
            self.menu_demo.draw(canvas)
            canvas.blit(self.menu_overlay, (0, 0), special_flags=ALPHA_BLIT)
        if self.panel_manager.current_panel == "game":
            self._draw_game_panel(canvas)
        else:
            self.panel_manager.draw(canvas)

    def _draw_game_panel(self, canvas: pygame.Surface) -> None:
        """The HUD, then the run's real-time effects drawn over it (the
        kill coins flying to the counter, which pops as they land), then the
        popups last (pause menu, victory, game over): nothing from the run
        is ever drawn over them."""
        objects = [
            obj
            for obj in self.panel_manager["game"].values()
            if hasattr(obj, "draw") and getattr(obj, "active", True)
        ]
        popups = self._popup_object_ids
        with self.hud_slide.shifted():
            for obj in objects:
                if id(obj) not in popups:
                    obj.draw(canvas)
            if not self._any_popup_open():  # not over a popup's overlay
                self.tower_controller.draw_shortcuts(canvas)
                self.tower_info.draw_hp_fill(canvas)
        self._draw_kill_coins()
        for obj in objects:
            if id(obj) in popups:
                obj.draw(canvas)

    def _any_popup_open(self) -> bool:
        return (
            self.pause_panel.is_open
            or self._victory_popup_open
            or self._gameover_popup_open
        )

    def _draw_game(self) -> None:
        canvas = self.window
        old_clip = canvas.get_clip()
        canvas.set_clip(self.game_area)
        self._draw_battle(canvas, self.camera)
        self.place_sell_feedback.draw(canvas, self.camera)
        self.kill_feedback.draw_texts(canvas, self.camera, self.game_state.time_ms)
        self.tower_controller.draw(canvas, self.mouse.position)
        self._draw_selected_tower_ui()
        self.enemy_hp_label.draw(canvas, self.camera, self._selected_enemy())
        self.life_lost_feedback.draw(canvas)  # under the HUD
        canvas.set_clip(old_clip)

    def _draw_kill_coins(self) -> None:
        """Coins fly to the money counter's resting place -- where it shows
        even while the HUD is hidden, since a kill brings it back -- and the
        counter, wherever it's drawn now, pops as they land."""
        canvas = self.window
        panel = self.panel_manager["game"]
        self.kill_feedback.draw_coins(canvas, panel["coin_image"].rect.center)
        offset = self.hud_slide.offset("money")
        self.hud.draw_money_odometer(canvas, offset)
        counter = panel["coin_text"].rect.move(offset)
        self.kill_feedback.draw_pop(canvas, counter)

    def _selected_tower(self) -> BaseTower | None:
        """The selected tower or plane, if it's still there (a tower may have
        been sold or destroyed since, a plane may have left the map)."""
        selected = self.game_state.selected_tower
        return selected if selected in self.towers else None

    def _selected_enemy(self) -> Enemy | None:
        """The enemy clicked for its HP numbers, if it's still on the map
        (the tick clears it once it dies or escapes)."""
        selected = self.game_state.selected_enemy
        return selected if selected in self.enemies else None

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
        Back; elsewhere it goes back to the main menu, or quits from it. The
        web build can't quit (the tab stays open): it shows the thanks screen."""
        panel = self.panel_manager.current_panel
        if panel == "main_menu":
            if web.is_web():
                self._open_thanks()
            else:
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
        elif panel in ("play_menu", "credits", "thanks"):
            self.panel_manager.current_panel = "main_menu"

    @override
    def exit(self) -> None:
        self._save_settings()
        super().exit()
