from contextlib import contextmanager

from pygamine import PanelManager

from domain.game_state import GameState
from gameplay.combat.tower_placement import SHORTCUT_OFFSET
from ui.tower_info import TOWER_INFO_OBJECTS

SLIDE_MS = 200
PEEK_MS = 1500
BUY_BUTTONS = tuple(f"buy_tower_{i + 1}" for i in range(4))

# name: (objects, the edge it slides out over as (dx, dy), extra margin in px)
GROUPS = {
    "level": (("level_text",), (-1, 0), 0),
    "lives": (("live_text", "live_image"), (-1, 0), 0),
    "money": (("coin_text", "coin_image"), (-1, 0), 0),
    "tower_info": (TOWER_INFO_OBJECTS, (-1, 0), 0),
    "controls": (
        (
            "control_panel_bg",
            "menu_button",
            "start_pause_button",
            "auto_pause_button",
            "speed_toggle_button",
            "upgrade_plane_button",
            "menu_button_icon",
            "start_pause_button_icon",
            "auto_pause_button_icon",
            "speed_toggle_button_text",
            "upgrade_plane_button_text",
        ),
        (1, 0),
        0,
    ),
    "tower_bar": (
        ("tower_panel_bg", *BUY_BUTTONS, *(f"fee_text_{i + 1}" for i in range(4))),
        (0, 1),
        -SHORTCUT_OFFSET[1],  # the 1-4 badges stick out above the buttons
    ),
}


def _ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


class _Group:
    """One part of the HUD, sliding off its nearest screen edge and back."""

    def __init__(self, direction: tuple[int, int], margin: int) -> None:
        self.direction = direction
        self.margin = margin
        self.shown = True
        self.hidden = 0.0  # 0 = resting in place, 1 = fully off-screen
        self._from = self._to = 0.0
        self._elapsed_ms = float(SLIDE_MS)
        self.objects: list = []
        self.canvas = (0, 0)

    def bind(self, objects: list, canvas: tuple[int, int]) -> None:
        self.objects = objects
        self.canvas = canvas
        self._apply_visible()

    @property
    def distance(self) -> int:
        """How far the group moves when fully hidden, measured from the
        objects' resting rects as they are now: text objects re-lay
        themselves out (wider or narrower) whenever their text changes,
        e.g. "Level 9" -> "Level 10", so a distance measured once would
        leave a sliver on screen."""
        dx, dy = self.direction
        if dy > 0:
            edge = self.canvas[1] - min(obj.rect.top for obj in self.objects)
        elif dx > 0:
            edge = self.canvas[0] - min(obj.rect.left for obj in self.objects)
        else:
            edge = max(obj.rect.right for obj in self.objects)
        return edge + self.margin

    @property
    def is_sliding(self) -> bool:
        return self._elapsed_ms < SLIDE_MS

    def slide(self, shown: bool) -> None:
        if shown == self.shown:
            return
        self.shown = shown
        self._apply_visible()
        self._from, self._to = self.hidden, 0.0 if shown else 1.0
        self._elapsed_ms = 0.0

    def update(self, frame_ms: float) -> None:
        if not self.is_sliding:
            return
        self._elapsed_ms = min(SLIDE_MS, self._elapsed_ms + frame_ms)
        t = _ease_out(self._elapsed_ms / SLIDE_MS)
        self.hidden = self._from + (self._to - self._from) * t

    def offset(self) -> tuple[int, int]:
        px = round(self.hidden * self.distance)
        return self.direction[0] * px, self.direction[1] * px

    def _apply_visible(self) -> None:
        # MouseInteractive.visible gates clicks and hover; the placement
        # controller's over-the-UI check reads it too, so a hidden HUD
        # doesn't block clicks on the map beneath its resting place.
        for obj in self.objects:
            obj.visible = self.shown


class HudSlide:
    """Slides the in-game HUD (counters, control buttons, tower bar, tower
    info panel) off the screen edges and back. toggle() is the one entry
    point, for the Tab key now and for an on-screen button later.

    The slide is drawn only: the panel objects keep their resting rects, and
    shifted() offsets them for the duration of a draw. (Text objects re-lay
    themselves out against their resting place whenever their text changes,
    so moving the rects themselves wouldn't stick.) It runs on real time, so
    it works while paused and ignores x2/x4. While the HUD is hidden, a
    change in money or lives brings that counter back for PEEK_MS. Hidden
    buttons take no clicks or hover; hotkeys and a placement in progress
    are untouched. The state lasts for the session only."""

    def __init__(
        self,
        panel_manager: PanelManager,
        canvas: tuple[int, int],
        game_state: GameState,
    ) -> None:
        self.shown = True
        self.groups = {
            name: _Group(direction, margin)
            for name, (_, direction, margin) in GROUPS.items()
        }
        self._peek_ms = {"lives": 0.0, "money": 0.0}
        self.rebind(panel_manager, canvas)
        game_state.add_money_listener(lambda _: self._peek("money"))
        game_state.add_lives_listener(lambda _: self._peek("lives"))

    def rebind(self, panel_manager: PanelManager, canvas: tuple[int, int]) -> None:
        """Pick up the objects of a freshly (re)built game panel."""
        panel = panel_manager["game"]
        for name, (names, _, _) in GROUPS.items():
            self.groups[name].bind([panel[n] for n in names], canvas)

    @property
    def is_sliding(self) -> bool:
        return any(group.is_sliding for group in self.groups.values())

    def toggle(self) -> None:
        self.shown = not self.shown
        for name in self._peek_ms:
            self._peek_ms[name] = 0.0
        for group in self.groups.values():
            group.slide(self.shown)

    def update(self, frame_ms: float) -> None:
        for name, left in self._peek_ms.items():
            if left > 0:
                self._peek_ms[name] = left - frame_ms
                if self._peek_ms[name] <= 0:
                    self.groups[name].slide(False)
        for group in self.groups.values():
            group.update(frame_ms)

    def offset(self, group: str) -> tuple[int, int]:
        return self.groups[group].offset()

    @contextmanager
    def shifted(self):
        """Moves every HUD object to where the slide has got to, for a draw."""
        moved = []
        for group in self.groups.values():
            dx, dy = group.offset()
            if dx or dy:
                for obj in group.objects:
                    obj.rect.move_ip(dx, dy)
                moved.append((group, dx, dy))
        try:
            yield
        finally:
            for group, dx, dy in moved:
                for obj in group.objects:
                    obj.rect.move_ip(-dx, -dy)

    def _peek(self, name: str) -> None:
        if self.shown:
            return
        self._peek_ms[name] = PEEK_MS
        self.groups[name].slide(True)
