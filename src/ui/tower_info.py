"""The tower info panel: a selected tower's record (kills, money earned) and
stats (range, minimum range, damage, fire rate, HP), each stat that an upgrade changes
shown as "current → next" until the tower is at its max level.

A selected plane (a flying tower) uses the same panel with some rows
relabeled: "Splash" (its bombs' blast radius) for Range, "Speed" (its
flight speed) for Blind spot, "Bombs" (bombs per second) for Fire rate,
and HP "-" with no bar, since planes have no HP. Its previews are for the
global plane upgrade (the plane-upgrade button), which every plane follows.

The panel's objects are declared in config/panels.yaml (`tower_info_*` on
the game panel), so they scale with the rest of the HUD; this module fills
in their text, toggles them on and off with the selection, and draws the
HP bar's fill (a ratio of the `tower_info_hp_bar` object's rect, colored
like the in-world HP bars).
"""

import pygame
from pygamine import PanelManager, clamp01
from pygamine.util.localization import localization, tr

from ui import hp_bar
from util.constants import TICKS_PER_SECOND, TILE_SIZE
from util.text import decimal, money

ARROW = "→"  # Anton and Fira Sans both have this glyph; the values use Anton

# Stat rows in display order: (key, label object, value object).
ROWS = ("kills", "earned", "range", "min_range", "damage", "fire_rate", "hp")

TOWER_INFO_OBJECTS = (
    "tower_info_bg",
    "tower_info_title_text",
    *(f"tower_info_{key}_label" for key in ROWS),
    *(f"tower_info_{key}_value" for key in ROWS),
    "tower_info_hp_bar",
)

# The label column's text keys (config/lang), for ground towers and planes.
GROUND_LABELS = {key: f"tower_info.{key}" for key in ROWS}
PLANE_LABELS = {
    **GROUND_LABELS,
    "range": "tower_info.plane_range",  # the bombs' splash radius
    "min_range": "tower_info.plane_speed",
    "fire_rate": "tower_info.plane_bombs",  # "Bomb rate" runs into its value
}


def labels(tower) -> dict[str, str]:
    """The label texts for `tower`'s panel, keyed by row, in the current language."""
    keys = PLANE_LABELS if getattr(tower, "is_flying", False) else GROUND_LABELS
    return {row: tr(key) for row, key in keys.items()}


def fire_rate(reload_ms: int) -> float:
    """Shots per second from a ground tower's `speeds` entry in
    config/towers.yaml, which is the reload time in ms of game time between
    shots: 1000 ms / reload_ms. (A shot actually waits for the first tick
    *past* the reload time, so the true rate is a hair lower -- at most one
    TICK_MS, ~6 ms, per shot.)"""
    return 1000 / reload_ms


def bomb_rate(interval_ms: int) -> float:
    """Bombs per second (at x1) from a plane's drop interval (game ms,
    plane_tower.BOMB_DROP_INTERVAL_MS): 1000 / interval_ms. Like
    fire_rate(), the true rate is a hair lower, since a drop waits for the
    first tick past the interval. It doesn't change with the plane's level;
    the upgrade slows the plane down instead (speeds in
    config/towers.yaml), so it drops more bombs over the same stretch."""
    return 1000 / interval_ms


def flight_speed(px_per_tick: int) -> float:
    """A plane's flight speed in tiles per second at x1, from its `speeds`
    entry in config/towers.yaml (world px per tick)."""
    return px_per_tick * TICKS_PER_SECOND / TILE_SIZE


def _tiles(px: int) -> str:
    return decimal(px / TILE_SIZE)


def _rate(reload_ms: int) -> str:
    return decimal(fire_rate(reload_ms), ".2f")


def _preview(current: str, upcoming: str | None, unit: str | None = None) -> str:
    """ "current" or, when an upgrade changes it, "current → next". `unit`
    is a language key whose text wraps the whole preview as `{value}`."""
    if upcoming is None or upcoming == current:
        text = current
    else:
        text = f"{current} {ARROW} {upcoming}"
    return text if unit is None else tr(unit, value=text)


def _title(tower) -> str:
    key = "tower_info.level_max" if tower.is_max_level() else "tower_info.level"
    return tr(key, level=tower.level, max_level=tower.max_level)


def stat_texts(tower) -> dict[str, str]:
    """The panel's title and value texts for a tower, keyed by row (plus
    "title"). At max level there's no next level, so no previews."""
    now = tower.stats_at(tower.level)
    nxt = None if tower.is_max_level() else tower.stats_at(tower.level + 1)

    def preview(key: str, fmt, unit: str | None = None) -> str:
        return _preview(fmt(now[key]), fmt(nxt[key]) if nxt else None, unit)

    if getattr(tower, "is_flying", False):
        return _plane_texts(tower, now, nxt, preview)
    if now["max_hp"] is None:
        hp = "-"
    else:
        hp = _preview(
            f"{max(0, tower.hp)} / {now['max_hp']}",
            str(nxt["max_hp"]) if nxt else None,
        )
    if now["min_range"] or (nxt and nxt["min_range"]):
        min_range = preview("min_range", _tiles, "tower_info.tiles")
    else:
        min_range = "-"  # no blind spot (every tower but the heavy cannon)
    return {
        "title": _title(tower),
        "kills": str(tower.kills),
        "earned": money(tower.money_earned),
        "range": preview("range", _tiles, "tower_info.tiles"),
        "min_range": min_range,
        "damage": preview("damage", str),
        "fire_rate": preview("reload_ms", _rate, "tower_info.per_second"),
        "hp": hp,
    }


def _plane_texts(tower, now, nxt, preview) -> dict[str, str]:
    """stat_texts() for a plane: splash radius, flight speed and bomb rate
    in the range / blind spot / fire rate rows, and no HP."""
    return {
        "title": _title(tower),
        "kills": str(tower.kills),
        "earned": money(tower.money_earned),
        "range": preview("range", _tiles, "tower_info.tiles"),
        "min_range": preview(
            "reload_ms",
            lambda v: decimal(flight_speed(v), ".1f"),
            "tower_info.tiles_per_second",
        ),
        "damage": preview("damage", str),
        "fire_rate": tr(
            "tower_info.per_second",
            value=decimal(bomb_rate(tower.bomb_interval_ms), ".2f"),
        ),
        "hp": "-",
    }


class TowerInfoPanel:
    """Shows the selected tower's info on the game panel's `tower_info_*`
    objects, or hides them when nothing is selected."""

    def __init__(self, panel_manager: PanelManager) -> None:
        self.tower = None
        self._label_set: tuple[str, bool] | None = None
        self.rebind(panel_manager)

    def rebind(self, panel_manager: PanelManager) -> None:
        """Pick up the objects of a freshly (re)built game panel."""
        panel = panel_manager["game"]
        self._objects = [panel[name] for name in TOWER_INFO_OBJECTS]
        self._title = panel["tower_info_title_text"]
        self._values = {key: panel[f"tower_info_{key}_value"] for key in ROWS}
        self._labels = {key: panel[f"tower_info_{key}_label"] for key in ROWS}
        self._hp_bar = panel["tower_info_hp_bar"]
        self._label_set = None  # new label objects
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
        self._hp_bar.active = tower.max_hp is not None  # planes have no HP
        texts = stat_texts(tower)
        self._title.set_text(texts["title"])
        for key, obj in self._values.items():
            obj.set_text(texts[key])
        label_set = (localization.language, getattr(tower, "is_flying", False))
        if label_set != self._label_set:  # not every frame: they only change then
            self._label_set = label_set
            for key, text in labels(tower).items():
                self._labels[key].set_text(text)

    def draw_hp_fill(self, surface: pygame.Surface) -> None:
        """The HP bar's fill, over its background object (drawn with the
        panel, so call this after the panel has been drawn)."""
        tower = self.tower
        if tower is None or tower.hp is None or not tower.max_hp:
            return
        ratio = clamp01(tower.hp / tower.max_hp)
        bar = self._hp_bar.rect
        fill = (bar.x, bar.y, round(bar.width * ratio), bar.height)
        pygame.draw.rect(surface, hp_bar.health_color(ratio), fill)
        pygame.draw.rect(surface, hp_bar.BORDER_COLOR, bar, 1)
