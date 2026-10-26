from pygamine import PanelManager

from gameplay.combat.tower_placement import SHORTCUT_OFFSET

SLIDE_MS = 200
BUY_BUTTONS = tuple(f"buy_tower_{i + 1}" for i in range(4))
OBJECT_NAMES = (
    "tower_panel_bg",
    *BUY_BUTTONS,
    *(f"fee_text_{i + 1}" for i in range(4)),
)


def _ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


class TowerBar:
    """The bottom tower bar (background, buy buttons, price labels), which
    slides down off-screen and back up. toggle() is the one entry point, for
    the Tab key now and for an on-screen button later.

    The slide runs on real time (update() takes wall-clock ms), so it works
    while the game is paused and ignores x2/x4. Panel objects hold absolute
    positions, so the bar moves each object by the change in offset; the
    price labels re-lay themselves out against the (already moved) background
    and so stay in step. Hidden buy buttons take no clicks or hover; the
    1-4 hotkeys and any placement in progress are untouched."""

    def __init__(self, panel_manager: PanelManager, canvas_height: int) -> None:
        self.shown = True
        self._hidden = 0.0  # 0 = resting in place, 1 = fully off-screen
        self._from = self._to = 0.0
        self._elapsed_ms = float(SLIDE_MS)
        self.rebind(panel_manager, canvas_height)

    def rebind(self, panel_manager: PanelManager, canvas_height: int) -> None:
        """Pick up the objects of a freshly (re)built game panel, which sit at
        their resting positions, and put them where the slide has got to."""
        panel = panel_manager["game"]
        self._objects = [panel[name] for name in OBJECT_NAMES]
        self._buttons = [panel[name] for name in BUY_BUTTONS]
        top = min(
            min(obj.rect.top for obj in self._objects),
            min(btn.rect.top for btn in self._buttons) + SHORTCUT_OFFSET[1],
        )
        self._distance = canvas_height - top
        self._applied_px = 0
        for btn in self._buttons:
            btn.visible = self.shown
        self._apply()

    @property
    def is_sliding(self) -> bool:
        return self._elapsed_ms < SLIDE_MS

    def toggle(self) -> None:
        self.shown = not self.shown
        for btn in self._buttons:
            btn.visible = self.shown
        self._from, self._to = self._hidden, 0.0 if self.shown else 1.0
        self._elapsed_ms = 0.0

    def update(self, frame_ms: float) -> None:
        if not self.is_sliding:
            return
        self._elapsed_ms = min(SLIDE_MS, self._elapsed_ms + frame_ms)
        t = _ease_out(self._elapsed_ms / SLIDE_MS)
        self._hidden = self._from + (self._to - self._from) * t
        self._apply()

    def _apply(self) -> None:
        offset = round(self._hidden * self._distance)
        delta, self._applied_px = offset - self._applied_px, offset
        if delta:
            for obj in self._objects:
                obj.rect.y += delta
