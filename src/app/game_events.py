import pygame


class GameEventsMixin:
    """Per-panel input dispatch for Game.

    Game owns a `self.handlers` dict mapping panel name → handler; the base
    `handle_event` looks up the current panel and routes to the matching
    method on this mixin. Each handler reads from `self.panel_manager`
    and mutates game state via the surrounding Game.
    """

    def _activate(self, button, event) -> bool:
        """True when the button was activated (click or focused-Space/Enter).
        Plays the button's `on_click_sound` (or the default click) on success."""
        activated = button.is_clicked(event, self.mouse.position) or (
            event.type == pygame.KEYUP
            and event.key in (pygame.K_SPACE, pygame.K_RETURN)
            and getattr(button, "focused", False)
        )
        if activated:
            sound = getattr(button, "on_click_sound", None) or self.click_sound_path
            if sound is not None:
                self.audio.play_sfx(str(sound))
        return activated

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
            self.panel_manager.current_panel = "settings"
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
            self._save_settings()
            self.panel_manager.current_panel = "main_menu"
        elif self._activate(panel["reset"], event):
            self._reset_settings()
        elif self._activate(panel["window_size_back_button"], event):
            self._cycle_window_size(-1)
        elif self._activate(panel["window_size_next_button"], event):
            self._cycle_window_size(1)
        elif self._activate(panel["window_mode_back_button"], event):
            self._cycle_window_mode(-1)
        elif self._activate(panel["window_mode_next_button"], event):
            self._cycle_window_mode(1)

    def _cycle_window_size(self, step: int) -> None:
        self.cycle_resolution(step)
        self._refresh_window_size_label()

    def _cycle_window_mode(self, step: int) -> None:
        self.cycle_window_mode(step)
        self._refresh_window_mode_label()
        self._refresh_window_size_label()

    def _on_sfx_volume_changed(self, value: float) -> None:
        self.audio.set_sfx_volume(value)
        self._refresh_sfx_volume_label()

    def _on_music_volume_changed(self, value: float) -> None:
        self.audio.set_music_volume(value)
        self._refresh_music_volume_label()

    def _handle_game_event(self, event) -> None:
        if self._victory_popup_open:
            self._handle_victory_popup_event(event)
            return
        if self._gameover_popup_open:
            self._handle_gameover_popup_event(event)
            return
        panel = self.panel_manager["game"]
        if self._activate(panel["menu_button"], event):
            self.game_state.is_started = False
            self._close_pause_panel()
            self._save_game()
            self.panel_manager.current_panel = "main_menu"
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.hud_slide.toggle()
        self.camera.handle_event(event, self.mouse.position)
        self.tower_controller.handle_event(event, self.mouse.position)
        self._handle_upgrade_plane_button(event)
        self._handle_start_pause(event)
        self._handle_pause_resume_button(event)
        self._handle_speed_toggle(event)

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
        if not self._activate(panel["upgrade_plane_button"], event):
            return
        price = self.tower_config.prices[3][1]
        if self.game_state.money >= price and self.game_state.plane_level == 1:
            self.game_state.decrease_money(price)
            panel["buy_tower_4"].set_state("lvl2")
            panel["upgrade_plane_button"].set_state("purchased")
            self.game_state.plane_level = 2

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
            sound = getattr(button, "on_click_sound", None) or self.click_sound_path
            if sound is not None:
                self.audio.play_sfx(str(sound))
        self._set_running(not self.game_state.is_started)

    def _handle_pause_resume_button(self, event) -> None:
        if self.pause_panel.is_open and self._activate(
            self.panel_manager["game"]["pause_resume"], event
        ):
            self._set_running(True)

    def _set_running(self, running: bool) -> None:
        """Start/resume or pause the game. Pausing a running game opens the
        pause panel and resuming closes it; the first start of a run (from
        "not started yet") has no panel to close."""
        self.game_state.is_started = running
        self.panel_manager["game"]["start_pause_button_icon"].set_state(
            "pause" if running else None
        )
        if running:
            self._close_pause_panel()
        else:
            self.pause_panel.open()

    def _close_pause_panel(self) -> None:
        """Close the pause panel, saving the settings if it was open -- its
        volume sliders change them live, like the settings screen's, and
        are saved when it closes, like that screen's are on Back."""
        if self.pause_panel.is_open:
            self.pause_panel.close()
            self._save_settings()

    def _handle_speed_toggle(self, event) -> None:
        panel = self.panel_manager["game"]
        button = panel["speed_toggle_button"]
        if not self._activate(button, event):
            return
        next_speed, next_state = {1: (2, "x2_active"), 2: (4, "x4_active")}.get(
            self.game_state.speed, (1, None)
        )
        self.game_state.speed = next_speed
        button.set_state(next_state)

    def _toggle_music(self) -> None:
        self.audio.toggle_music()
        state = "paused" if self.audio.is_music_paused else None
        for tab in self.panel_manager.keys():
            panel = self.panel_manager[tab]
            if "music_toggle_icon" in panel:  # the game panel has none
                panel["music_toggle_icon"].set_state(state)
