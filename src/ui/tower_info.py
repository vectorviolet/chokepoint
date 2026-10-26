"""The tower info panel: a selected tower's record (kills, money earned) and
stats (range, damage, fire rate, HP), each stat that an upgrade changes
shown as "current → next" until the tower is at its max level.

The panel's objects are declared in config/panels.yaml (`tower_info_*` on
the game panel), so they scale with the rest of the HUD; this module fills
in their text, toggles them on and off with the selection, and draws the
HP bar's fill (a ratio of the `tower_info_hp_bar` object's rect, coloured
like the in-world HP bars).
"""

import pygame
from pygamine import PanelManager

from ui import hp_bar
from util.constants import TILE_SIZE

ARROW = "→"  # Anton has this glyph (Comic Neue doesn't): values use Anton

# Stat rows in display order: (key, label object, value object).
ROWS = ("kills", "earned", "range", "damage", "fire_rate", "hp")

TOWER_INFO_OBJECTS = (
    "tower_info_bg",
    "tower_info_title_text",
    *(f"tower_info_{key}_label" for key in ROWS),
    *(f"tower_info_{key}_value" for key in ROWS),
    "tower_info_hp_bar",
)


def fire_rate(reload_ms: int) -> float:
    """Shots per second from a ground tower's `speeds` entry in
    config/towers.yaml, which is the reload time in ms of game time between
    shots: 1000 ms / reload_ms. (A shot actually waits for the first tick
    *past* the reload time, so the true rate is a hair lower -- at most one
    TICK_MS, ~6 ms, per shot.)"""
    return 1000 / reload_ms


def _tiles(px: int) -> str:
    return f"{px / TILE_SIZE:g}"


def _rate(reload_ms: int) -> str:
    return f"{fire_rate(reload_ms):.2f}"


def _preview(current: str, upcoming: str | None, unit: str = "") -> str:
    """ "current" or, when an upgrade changes it, "current → next"."""
    if upcoming is None or upcoming == current:
        return f"{current}{unit}"
    return f"{current} {ARROW} {upcoming}{unit}"


def stat_texts(tower) -> dict[str, str]:
    """The panel's title and value texts for a tower, keyed by row (plus
    "title"). At max level there's no next level, so no previews."""
    now = tower.stats_at(tower.level)
    nxt = None if tower.is_max_level() else tower.stats_at(tower.level + 1)

    def preview(key: str, fmt, unit: str = "") -> str:
        return _preview(fmt(now[key]), fmt(nxt[key]) if nxt else None, unit)

    if now["max_hp"] is None:
        hp = "-"
    else:
        hp = _preview(
            f"{max(0, tower.hp)} / {now['max_hp']}",
            str(nxt["max_hp"]) if nxt else None,
        )
    level = f"Level {tower.level} / {tower.max_level}"
    return {
        "title": level + ("  (max)" if tower.is_max_level() else ""),
        "kills": str(tower.kills),
        "earned": f"{tower.money_earned} $",
        "range": preview("range", _tiles, " tiles"),
        "damage": preview("damage", str),
        "fire_rate": preview("reload_ms", _rate, "/s"),
        "hp": hp,
    }


class TowerInfoPanel:
    """Shows the selected tower's info on the game panel's `tower_info_*`
    objects, or hides them when nothing is selected."""

    def __init__(self, panel_manager: PanelManager) -> None:
        self.tower = None
        self.rebind(panel_manager)

    def rebind(self, panel_manager: PanelManager) -> None:
        """Pick up the objects of a freshly (re)built game panel."""
        panel = panel_manager["game"]
        self._objects = [panel[name] for name in TOWER_INFO_OBJECTS]
        self._title = panel["tower_info_title_text"]
        self._values = {key: panel[f"tower_info_{key}_value"] for key in ROWS}
        self._hp_bar = panel["tower_info_hp_bar"]
        self.show(self.tower)

    @property
    def is_open(self) -> bool:
        return self.tower is not None

    def show(self, tower) -> None:
        """Open the panel on `tower`, refreshing its texts, or close it with
        None. Cheap to call every frame: unchanged texts aren't re-rendered."""
        for obj in self._objects:
            obj.active = tower is not None  # a no-op when unchanged
        self.tower = tower
        if tower is None:
            return
        texts = stat_texts(tower)
        self._title.set_text(texts["title"])
        for key, obj in self._values.items():
            obj.set_text(texts[key])

    def draw_hp_fill(self, surface: pygame.Surface) -> None:
        """The HP bar's fill, over its background object (drawn with the
        panel, so call this after the panel has been drawn)."""
        tower = self.tower
        if tower is None or tower.hp is None or not tower.maxHP:
            return
        ratio = max(0.0, min(1.0, tower.hp / tower.maxHP))
        bar = self._hp_bar.rect
        fill = (bar.x, bar.y, round(bar.width * ratio), bar.height)
        pygame.draw.rect(surface, hp_bar.health_color(ratio), fill)
        pygame.draw.rect(surface, hp_bar.BORDER_COLOR, bar, 1)
