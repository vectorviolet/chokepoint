"""The pause panel: opens when the player pauses a running game and closes
when they resume. It holds the music and SFX volume sliders (the same
controls as the settings screen's, kept in step with them by Game) and a
Resume button.

The panel's objects are declared in config/panels.yaml (`pause_*` on the
game panel), so they scale with the rest of the HUD; this module only
toggles them on and off. It isn't part of the HUD slide: Tab hides the HUD
but leaves the pause panel up, since it's how a paused game says so.
"""

from pygamine import PanelManager

PAUSE_PANEL_OBJECTS = (
    "pause_panel_bg",
    "pause_title_text",
    "pause_music_label",
    "pause_music_volume_value_text",
    "pause_music_volume_slider",
    "pause_sfx_label",
    "pause_sfx_volume_value_text",
    "pause_sfx_volume_slider",
    "pause_resume",
    "pause_resume_text",
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
