"""The Settings screen's tabs (DISPLAY, AUDIO, GAME, CONTROLS).

Each tab is a button (`tab_<key>_button`) plus a group object (`<key>_tab`)
in config/panels.yaml; the rows of a tab are objects whose `parent:` is that
group, so showing or hiding the group shows or hides the rows (a hidden
object takes no events and isn't drawn). Layout lives in panels.yaml only.

To fill a tab that has no rows yet (CONTROLS): copy a row in
panels.yaml with `parent: <key>_tab`, list the row's `<` / `>` buttons in
that tab's `rows` below (each with the Game method that handles it), and set
`shown=True`. Its tab button then appears and the tab opens like the others.
"""

from dataclasses import dataclass

import pygame

DEFAULT_TAB = "display"


# The ON/OFF settings: one `< ON/OFF >` row each, named `<key>_back_button`,
# `<key>_next_button`, `<key>_value_text` in panels.yaml, with the shipped
# default under `gameplay:` in config/settings.yaml. They are loaded, saved,
# reset and labeled from this one list (Game.toggles); a row's tab lists them
# with toggle_rows().
TOGGLE_SETTINGS = (
    "skip_intro",
    "pause_on_focus_loss",
    "keep_selection_while_buying",
    "reduce_flashing",
)


@dataclass(frozen=True)
class SettingsRow:
    """A keyboard-focusable, clickable button of a tab's row and what it does."""

    button: str  # its object in the settings panel
    handler: str  # name of the Game method called as handler(arg)
    arg: int | str  # the step of a `<` (-1) or `>` (1) button, or a toggle's key


def toggle_rows(*keys: str) -> tuple[SettingsRow, ...]:
    """The `<` and `>` buttons of each toggle in `keys`, top to bottom."""
    assert all(key in TOGGLE_SETTINGS for key in keys)
    return tuple(
        SettingsRow(f"{key}_{side}_button", "_toggle_setting", key)
        for key in keys
        for side in ("back", "next")
    )


@dataclass(frozen=True)
class SettingsTab:
    key: str
    shown: bool  # False: no rows yet, so the tab button stays hidden
    # The tab's buttons, top to bottom (the sliders are mouse-only).
    rows: tuple[SettingsRow, ...] = ()

    @property
    def button(self) -> str:
        return f"tab_{self.key}_button"

    @property
    def group(self) -> str:
        return f"{self.key}_tab"


SETTINGS_TABS = (
    SettingsTab(
        "display",
        shown=True,
        rows=(
            SettingsRow("window_size_back_button", "_cycle_window_size", -1),
            SettingsRow("window_size_next_button", "_cycle_window_size", 1),
            SettingsRow("window_mode_back_button", "_cycle_window_mode", -1),
            SettingsRow("window_mode_next_button", "_cycle_window_mode", 1),
            *toggle_rows("reduce_flashing"),
        ),
    ),
    SettingsTab("audio", shown=True),
    SettingsTab(
        "game",
        shown=True,
        rows=(
            *toggle_rows(
                "skip_intro", "pause_on_focus_loss", "keep_selection_while_buying"
            ),
            SettingsRow("language_back_button", "_cycle_language", -1),
            SettingsRow("language_next_button", "_cycle_language", 1),
        ),
    ),
    SettingsTab("controls", shown=False),
)

# Not part of a tab: always there, last in the keyboard order.
FIXED_BUTTONS = ("back", "reset")

_OFFSCREEN = (-1, -1)


def link_hierarchy(panel) -> None:
    """The panel loader's `parent:` only places an object relative to its
    parent's rectangle; it doesn't make the parent's `active` switch cover
    it. Link each object of the freshly loaded `panel` to its placement
    parent, so hiding a tab's group (or a button) also hides everything inside
    it. Run once per panel load."""
    for obj in panel.values():
        parent = obj.rect.parent
        if parent is not None:
            obj.set_parent(parent.game_object)


class SettingsTabs:
    """Which tab of the settings panel is open, and what that shows."""

    def __init__(self, panel, active: str) -> None:
        self.panel = panel
        self.active = active
        self.select(active)

    def tab(self, key: str) -> SettingsTab:
        return next(t for t in SETTINGS_TABS if t.key == key)

    def select(self, key: str) -> None:
        """Opens tab `key`: shows its rows only, hides the rest, highlights its
        button and hides the buttons of tabs that aren't shown yet."""
        assert self.tab(key).shown, f"settings tab {key!r} is hidden"
        self.active = key
        for tab in SETTINGS_TABS:
            is_open = tab.key == key
            self.panel[tab.group].active = is_open
            button = self.panel[tab.button]
            button.active = tab.shown
            button.set_state("selected" if is_open else None)
            if not is_open:
                for row in tab.rows:
                    self._clear_hover(self.panel[row.button])

    @staticmethod
    def _clear_hover(button) -> None:
        """A hidden button gets no mouse events, so tell it the mouse left;
        otherwise it would still show its hover look when its tab reopens."""
        button.handle_event(
            pygame.event.Event(pygame.MOUSEMOTION, pos=_OFFSCREEN), _OFFSCREEN
        )

    def focus_order(self) -> list:
        """Buttons the keyboard cycles: the shown tab buttons, the open tab's
        row buttons, then Back and Reset (rows of other tabs never)."""
        tabs = [self.panel[t.button] for t in SETTINGS_TABS if t.shown]
        rows = [self.panel[row.button] for row in self.tab(self.active).rows]
        return [*tabs, *rows, *(self.panel[name] for name in FIXED_BUTTONS)]

    def name_of(self, button) -> str:
        """The panel name of one of the buttons in `focus_order()`."""
        names = [t.button for t in SETTINGS_TABS if t.shown]
        names += [row.button for row in self.tab(self.active).rows]
        names += FIXED_BUTTONS
        return next(name for name in names if self.panel[name] is button)
