"""The pause menu: Esc or the HUD menu button opens it at any time in a run,
pausing the game; Back (or Esc again) closes it. It offers Back, Settings,
a Music toggle and Main menu -- Game handles those buttons and the pausing.

The menu's objects are declared in config/panels.yaml (`pause_*` on the
game panel), so they scale with the rest of the UI; this module only
toggles them on and off. It isn't part of the HUD slide (Tab), and while
it's open its full-screen overlay sits over the HUD.
"""

from pygamine import PanelManager

PAUSE_PANEL_OBJECTS = (
    "pause_overlay",
    "pause_panel_bg",
    "pause_title_text",
    "pause_back",
    "pause_back_text",
    "pause_settings",
    "pause_settings_text",
    "pause_music",
    "pause_music_text",
    "pause_main_menu",
    "pause_main_menu_text",
)


class PausePanel:
    """Shows or hides the game panel's `pause_*` objects."""

    def __init__(self, panel_manager: PanelManager) -> None:
        self.is_open = False
        self.rebind(panel_manager)

    def rebind(self, panel_manager: PanelManager) -> None:
        """Pick up the objects of a freshly (re)built game panel."""
        panel = panel_manager["game"]
        self._objects = [panel[name] for name in PAUSE_PANEL_OBJECTS]
        self._apply()

    def open(self) -> None:
        self.is_open = True
        self._apply()

    def close(self) -> None:
        self.is_open = False
        self._apply()

    def _apply(self) -> None:
        for obj in self._objects:
            obj.active = self.is_open  # a no-op when unchanged
