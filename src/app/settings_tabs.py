"""The Settings screen's tabs (DISPLAY, AUDIO, GAME, CONTROLS).

Each tab is a button (`tab_<key>_button`) plus a group object (`<key>_tab`)
in config/panels.yaml; the rows of a tab are objects whose `parent:` is that
group, so showing or hiding the group shows or hides the rows (a hidden
object takes no events and isn't drawn). Layout lives in panels.yaml only.

To fill a tab that has no rows yet (GAME, CONTROLS): copy a row in
panels.yaml with `parent: <key>_tab`, list the row's `<` / `>` buttons in
that tab's `buttons` below (so the keyboard can focus them), and set
`shown=True`. Its tab button then appears and the tab opens like the others.
"""

from dataclasses import dataclass

DEFAULT_TAB = "display"


@dataclass(frozen=True)
class SettingsTab:
    key: str
    shown: bool  # False: no rows yet, so the tab button stays hidden
    # The tab's keyboard-focusable buttons, top to bottom (sliders are mouse-only).
    buttons: tuple[str, ...] = ()

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
        buttons=(
            "window_size_back_button",
            "window_size_next_button",
            "window_mode_back_button",
            "window_mode_next_button",
        ),
    ),
    SettingsTab("audio", shown=True),
    SettingsTab("game", shown=False),
    SettingsTab("controls", shown=False),
)


class SettingsTabs:
    """Which tab of the settings panel is open, and what that shows."""

    def __init__(self, panel, active: str = DEFAULT_TAB) -> None:
        self.panel = panel
        self.active = active
        self._link_hierarchy()
        self.select(active)

    def _link_hierarchy(self) -> None:
        """The panel loader's `parent:` only places an object relative to its
        parent's rectangle; it doesn't make the parent's `active` switch cover
        it. Link each object to its placement parent, so hiding a tab's group
        (or a button) also hides everything inside it."""
        for obj in self.panel.values():
            parent = obj.rect.parent
            if parent is not None:
                obj.set_parent(parent.game_object)

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

    def focus_order(self) -> list:
        """Buttons the keyboard cycles: the shown tab buttons, the open tab's
        row buttons, then Back and Reset (rows of other tabs never)."""
        tabs = [self.panel[t.button] for t in SETTINGS_TABS if t.shown]
        rows = [self.panel[name] for name in self.tab(self.active).buttons]
        return [*tabs, *rows, self.panel["back"], self.panel["reset"]]
