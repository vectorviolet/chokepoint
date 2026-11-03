import pygame

from app.settings_tabs import DEFAULT_TAB, SETTINGS_TABS
from util.constants import GAME_SPEEDS

# The speed button's state at each game speed (None: its x1 look).
SPEED_BUTTON_STATES: dict[int, str | None] = {1: None, 2: "x2_active", 4: "x4_active"}
assert set(SPEED_BUTTON_STATES) == set(GAME_SPEEDS)  # one look per speed


class GameEventsMixin:
    """Per-panel input dispatch for Game.

    Game owns a `self.handlers` dict mapping panel name → handler; the base
    `handle_event` looks up the current panel and routes to the matching
    method on this mixin. Each handler reads from `self.panel_manager`
    and mutates game state via the surrounding Game.
    """

    def _activate(self, button, event, *, sound: bool = True) -> bool:
        """True when the button was activated (click or focused-Space/Enter).
        Plays the button's click sound on success, unless `sound` is False
        (the caller then decides, e.g. a refused purchase plays "denied").
        A button that isn't active (hidden with its tab or panel) never is."""
        if not button.active:
            # A press that began while the button was shown must not complete
            # later, when it's shown again: forget it.
            button._pressed = False
            return False
        activated = button.is_clicked(event, self.mouse.position) or (
            event.type == pygame.KEYUP
            and event.key in (pygame.K_SPACE, pygame.K_RETURN)
            and getattr(button, "focused", False)
        )
        if activated and sound:
            self._play_click(button)
        return activated

    def _play_click(self, button) -> None:
        """The button's `on_click_sound`, or the default click."""
        sound = getattr(button, "on_click_sound", None) or self.click_sound_path
        if sound is not None:
            self.audio.play_sfx(str(sound))

    def _handle_main_menu_event(self, event) -> None:
        panel = self.panel_manager["main_menu"]
        if self._activate(panel["play"], event):
            if self._has_saved_game():
                self.panel_manager.current_panel = "play_menu"
            else:
                self._start_new_game()
        elif self._activate(panel["credits"], event):
            self.panel_manager["credits"][
                "credits_scroller"
            ].reset()  # replay from the top
            self.panel_manager.current_panel = "credits"
        elif self._activate(panel["settings"], event):
            self._open_settings("main_menu")
        elif self._activate(panel["exit"], event):
            self.on_exit_request()

    def _handle_play_menu_event(self, event) -> None:
        panel = self.panel_manager["play_menu"]
        if self._activate(panel["continue_game"], event):
            self._load_game()
        elif self._activate(panel["new_game"], event):
            self._start_new_game()
        elif self._activate(panel["back"], event):
            self.panel_manager.current_panel = "main_menu"

    def _handle_credits_event(self, event) -> None:
        panel = self.panel_manager["credits"]
        if self._activate(panel["back"], event):
            self.panel_manager.current_panel = "main_menu"

    def _handle_settings_event(self, event) -> None:
        panel = self.panel_manager["settings"]
        if self._activate(panel["back"], event):
            self._leave_settings()
        elif self._activate(panel["reset"], event):
            self._reset_settings()
        else:
            self._handle_settings_tab_event(panel, event)

    def _handle_settings_tab_event(self, panel, event) -> None:
        """The tab buttons, then the rows' buttons, through SETTINGS_TABS.
        Every tab's buttons are asked, so a hidden one forgets a stale press;
        `_activate` only lets the shown ones through."""
        for tab in SETTINGS_TABS:
            if self._activate(panel[tab.button], event):
                self._show_settings_tab(tab.key)
                return
        for tab in SETTINGS_TABS:
            for row in tab.rows:
                if self._activate(panel[row.button], event):
                    getattr(self, row.handler)(row.arg)
                    return

    def _open_settings(self, return_panel: str) -> None:
        """Opens Settings on its first tab; Back leads to `return_panel`."""
        self._settings_return_panel = return_panel
        self.panel_manager.current_panel = "settings"
        self._show_settings_tab(DEFAULT_TAB, focus_tab=True)

    def _leave_settings(self) -> None:
        """Settings' Back (and Esc there): save, then return to where the
        screen was opened from -- the main menu, or the pause menu."""
        self._save_settings()
        self.panel_manager.current_panel = self._settings_return_panel
        self._settings_return_panel = "main_menu"

    def _cycle_window_size(self, step: int) -> None:
        self.cycle_resolution(step)
        self._refresh_window_size_label()

    def _cycle_window_mode(self, step: int) -> None:
        self.cycle_window_mode(step)
        self._refresh_window_mode_label()
        self._refresh_window_size_label()

    def _on_volume_changed(self, volume, value: float) -> None:
        """A Settings volume slider moved (`volume`: a VolumeSetting row)."""
        getattr(self.audio, volume.setter)(value)
        self._refresh_volume_label(volume)
        # GameAudio keeps its own channels in step; the bell's channel 2 is
        # the game's, so a bell already ringing follows master/SFX here.
        self.life_lost_feedback.apply_volume()

    def _handle_game_event(self, event) -> None:
        if self._victory_popup_open:
            self._handle_victory_popup_event(event)
            return
        if self._gameover_popup_open:
            self._handle_gameover_popup_event(event)
            return
        if self.pause_panel.is_open:
            self._handle_pause_menu_event(event)
            return
        panel = self.panel_manager["game"]
        if self._activate(panel["menu_button"], event):
            self._open_pause_menu()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.hud_slide.toggle()
        self.camera.handle_event(event, self.mouse.position)
        self.tower_controller.handle_event(event, self.mouse.position)
        self._handle_upgrade_plane_button(event)
        self._handle_start_pause(event)
        self._handle_auto_pause_toggle(event)
        self._handle_keep_placing_toggle(event)
        self._handle_speed_toggle(event)

    # ── pause menu ───────────────────────────────────────────────────────────

    def _handle_pause_menu_event(self, event) -> None:
        """While the pause menu is open it takes all of the game panel's
        input: the rest of the HUD, the map and the hotkeys wait."""
        panel = self.panel_manager["game"]
        if self._activate(panel["pause_back"], event):
            self._close_pause_menu()
        elif self._activate(panel["pause_settings"], event):
            self._open_settings("game")
        elif self._activate(panel["pause_music"], event):
            self._toggle_music()
        elif self._activate(panel["pause_main_menu"], event):
            self._leave_game_for_main_menu()

    def _open_pause_menu(self) -> None:
        """Opens the pause menu and pauses the game, remembering whether it
        was running so that closing the menu puts it back as it was."""
        if self.pause_panel.is_open:
            return
        self._resume_on_unpause = self.game_state.is_started
        self._set_started(False)
        self.pause_panel.open()

    def _close_pause_menu(self) -> None:
        if not self.pause_panel.is_open:
            return
        self.pause_panel.close()
        if self._resume_on_unpause:
            self._set_started(True)
        self._resume_on_unpause = False

    def _leave_game_for_main_menu(self) -> None:
        """The pause menu's Main menu: what the HUD menu button did before
        the pause menu -- pause, save the run, go to the main menu."""
        self.pause_panel.close()
        self._resume_on_unpause = False
        self.game_state.is_started = False
        self._save_game()
        self.panel_manager.current_panel = "main_menu"

    def _set_started(self, started: bool) -> None:
        self.game_state.is_started = started
        self.panel_manager["game"]["start_pause_button_icon"].set_state(
            "pause" if started else None
        )

    def _handle_victory_popup_event(self, event) -> None:
        panel = self.panel_manager["game"]
        if self._activate(panel["victory_continue"], event):
            self._close_victory_popup()
            self.game_state.is_started = True
            panel["start_pause_button_icon"].set_state("pause")
        elif self._activate(panel["victory_play_again"], event):
            self._close_victory_popup()
            self._start_new_game()
        elif self._activate(panel["victory_main_menu"], event):
            self._close_victory_popup()
            self.game_state.is_started = False
            self._save_game()
            self.panel_manager.current_panel = "main_menu"

    def _handle_gameover_popup_event(self, event) -> None:
        panel = self.panel_manager["game"]
        if self._activate(panel["gameover_play_again"], event):
            self._close_gameover_popup()
            self._start_new_game()
        elif self._activate(panel["gameover_main_menu"], event):
            self._close_gameover_popup()
            self.panel_manager.current_panel = "main_menu"

    def _handle_upgrade_plane_button(self, event) -> None:
        panel = self.panel_manager["game"]
        button = panel["upgrade_plane_button"]
        if not self._activate(button, event, sound=False):
            return
        if self.game_state.plane_level != 1:
            return  # maxed: grayed, and a click does nothing (not even a sound)
        if not self._buy_plane_upgrade():
            self._deny_purchase()  # the denied sound only, like a refused tower pick
            return
        self._play_click(button)

    def _buy_plane_upgrade(self) -> bool:
        """UPG PLANES: every plane flies at level 2 from now on, for its
        price. False, and nothing changes, if it's already bought or not
        affordable. The HUD button and the balance simulator both buy it
        through here."""
        if self.game_state.plane_level != 1:
            return False
        price = self.tower_config.prices[3][1]
        if self.game_state.money < price:
            return False
        # plane_level first: the money listener then shows the plane's buy
        # button in its lvl2 look and the UPG PLANES button maxed.
        self.game_state.plane_level = 2
        self.game_state.decrease_money(price)
        return True

    def _handle_start_pause(self, event) -> None:
        panel = self.panel_manager["game"]
        button = panel["start_pause_button"]
        # Space is the keyboard shortcut for the same toggle the button does
        # -- there's no keyboard-focus system driving "game"-panel buttons
        # (unlike main_menu/play_menu's MenuController), so this is checked
        # directly rather than routed through _activate()'s focused-Space
        # path, which only fires for a button that already has focus.
        is_hotkey = event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE
        if not (self._activate(button, event) or is_hotkey):
            return
        if is_hotkey:
            self._play_click(button)
        self.game_state.is_started = not self.game_state.is_started
        panel["start_pause_button_icon"].set_state(
            "pause" if self.game_state.is_started else None
        )

    def _handle_auto_pause_toggle(self, event) -> None:
        """The HUD's hourglass: auto-pause between waves on/off, a global
        setting saved at once (like the music toggle)."""
        if not self._activate(self.panel_manager["game"]["auto_pause_button"], event):
            return
        self.auto_pause = not self.auto_pause
        self._refresh_auto_pause_button()
        self._save_settings()

    def _refresh_auto_pause_button(self) -> None:
        self.panel_manager["game"]["auto_pause_button"].set_state(
            "enabled" if self.auto_pause else None
        )

    def _handle_keep_placing_toggle(self, event) -> None:
        """The HUD's keep-placing toggle (or a Shift press): while on,
        placement mode stays on after a placement while another tower of
        the same type is affordable. A global setting saved at once, like
        auto-pause. Holding Shift does nothing more than the press, and only
        a plain Shift press counts: not with Ctrl, Alt or Meta held (Alt+Shift
        switches the keyboard layout on Windows)."""
        button = self.panel_manager["game"]["keep_placing_button"]
        chord = pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META
        is_hotkey = (
            event.type == pygame.KEYDOWN
            and event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT)
            and not getattr(event, "repeat", False)
            and not getattr(event, "mod", 0) & chord
        )
        if not (self._activate(button, event) or is_hotkey):
            return
        if is_hotkey:
            self._play_click(button)
        self.keep_placing = not self.keep_placing
        self._save_settings()

    def _refresh_keep_placing_button(self) -> None:
        self.panel_manager["game"]["keep_placing_button"].set_state(
            "enabled" if self.keep_placing else None
        )

    def _deny_purchase(self, tower_type: int | None = None) -> None:
        """A tower (or the plane upgrade) the player can't afford was
        picked: a short "denied" sound and a red flash of the money counter,
        which peeks back if the HUD is hidden."""
        self.audio.play_sfx(str(self.assets.sound_path("denied")))
        self.hud.flash_money()
        self.hud_slide.peek("money")

    def _handle_speed_toggle(self, event) -> None:
        panel = self.panel_manager["game"]
        button = panel["speed_toggle_button"]
        if not self._activate(button, event):
            return
        # x1 -> x2 -> x4 -> x1; an unknown speed goes back to x1.
        speed = self.game_state.speed
        index = GAME_SPEEDS.index(speed) if speed in GAME_SPEEDS else -1
        next_speed = GAME_SPEEDS[(index + 1) % len(GAME_SPEEDS)]
        self.game_state.speed = next_speed
        button.set_state(SPEED_BUTTON_STATES[next_speed])

    def _toggle_music(self) -> None:
        """The menus' music button and the pause menu's Music: one switch,
        shown the same everywhere and saved with the settings at once."""
        self.audio.toggle_music()
        self._refresh_music_toggles()
        self._save_settings()

    def _refresh_music_toggles(self) -> None:
        paused = self.audio.is_music_paused
        for tab in self.panel_manager.keys():
            panel = self.panel_manager[tab]
            if "music_toggle_icon" in panel:  # the menus' icon buttons
                panel["music_toggle_icon"].set_state("paused" if paused else None)
            if "pause_music_text" in panel:  # the pause menu's Music button
                panel["pause_music_text"].set_text(
                    "MUSIC: OFF" if paused else "MUSIC: ON"
                )
