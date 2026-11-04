from dataclasses import dataclass

import yaml

from domain.game_state import TowerConfig, WaveDef
from util.paths import resource_path

# Anchored to the resource root (not this file) so it resolves inside a
# PyInstaller bundle, where module files are relocated but bundled data is not.
_CONFIG_DIR = resource_path("config")


@dataclass
class EnemyStats:
    hp: int
    speed: float
    kill_money: int
    damage: int
    range: int | None = None  # tanks only
    fire_interval_ms: int | None = None  # tanks only
    bullet_damage: int | None = None  # tanks only


def load_settings() -> dict:
    """config/settings.yaml as parsed YAML (window, gameplay, camera, audio)."""
    with open(_CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gameplay_settings(settings: dict | None = None) -> dict:
    """The `gameplay` section of settings.yaml (starting money and lives,
    the default toggles), read from `settings` or loaded when not given."""
    return (load_settings() if settings is None else settings)["gameplay"]


def load_tower_config() -> TowerConfig:
    with open(_CONFIG_DIR / "towers.yaml") as f:
        data = yaml.safe_load(f)

    towers = sorted(data["towers"], key=lambda t: t["type"])
    return TowerConfig(
        prices=[t["prices"] for t in towers],
        max_levels=[t["max_level"] for t in towers],
        ranges=[t["ranges"] for t in towers],
        damages=[t["damages"] for t in towers],
        speeds=[t["speeds"] for t in towers],
        hps=[t.get("hps") for t in towers],
        shoot_sounds=[t.get("shoot_sound") for t in towers],
        min_ranges=[parse_min_ranges(t) for t in towers],
    )


def parse_min_ranges(tower: dict) -> list[int]:
    """A tower's per-level `min_ranges` (its blind spot), or 0 at every
    level when it has none. Raises ValueError naming the tower type unless
    there's one per level, each at least 0 and below that level's range."""
    ranges = tower["ranges"]
    min_ranges = tower.get("min_ranges")
    if min_ranges is None:
        return [0] * len(ranges)
    where = f"config/towers.yaml: tower type {tower['type']}"
    if not isinstance(min_ranges, list) or len(min_ranges) != len(ranges):
        raise ValueError(f"{where} needs one min_ranges entry per level")
    for min_range, max_range in zip(min_ranges, ranges):
        if type(min_range) is not int or not 0 <= min_range < max_range:
            raise ValueError(
                f"{where}: min_ranges must be whole numbers from 0 up to "
                f"(not including) the range, got {min_range} for {max_range}"
            )
    return list(min_ranges)


@dataclass(frozen=True)
class TowerTooltip:
    """A tower's name and one line each for what it's good and bad at (the
    buy button's hover tooltip). They live in the language files
    (`tower_<type>` in config/lang/<code>.yaml), so the game shows them in the
    current language; this reads one language's file, for the stats pages."""

    name: str
    strength: str
    weakness: str


TOWER_TYPES = (1, 2, 3, 4)


def parse_tower_tooltips(data: dict) -> dict[int, TowerTooltip]:
    """Tooltips keyed by tower type, from a parsed language file. Raises
    ValueError naming the tower type if a name or line is missing or blank."""
    tooltips = {}
    for tower_type in TOWER_TYPES:
        tower = data.get(f"tower_{tower_type}") or {}
        for key in ("name", "strength", "weakness"):
            text = tower.get(key)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"language file: tower_{tower_type} needs a non-empty {key}"
                )
        tooltips[tower_type] = TowerTooltip(
            **{k: tower[k].strip() for k in ("name", "strength", "weakness")}
        )
    return tooltips


def load_tower_tooltips(language: str = "en") -> dict[int, TowerTooltip]:
    with open(_CONFIG_DIR / "lang" / f"{language}.yaml", encoding="utf-8") as f:
        return parse_tower_tooltips(yaml.safe_load(f))


def load_enemy_stats() -> dict[int, EnemyStats]:
    with open(_CONFIG_DIR / "enemies.yaml") as f:
        data = yaml.safe_load(f)

    return {
        int(k): EnemyStats(
            hp=v["hp"],
            speed=float(v["speed"]),
            kill_money=v["kill_money"],
            damage=v["damage"],
            range=v.get("range"),
            fire_interval_ms=v.get("fire_interval_ms"),
            bullet_damage=v.get("bullet_damage"),
        )
        for k, v in data["enemies"].items()
    }


def load_wave_compositions() -> dict[int, WaveDef]:
    """Parse waves.yaml.

    Each wave entry may be either:
      - a list of {type, count} groups (default spawn interval), or
      - a dict {spawn_interval: <ms>, groups: [{type, count}, ...]}.
    """
    with open(_CONFIG_DIR / "waves.yaml") as f:
        data = yaml.safe_load(f)

    waves: dict[int, WaveDef] = {}
    for wave, entry in data["waves"].items():
        if isinstance(entry, list):
            groups, interval = entry, None
        else:
            groups, interval = entry["groups"], entry.get("spawn_interval")
        waves[int(wave)] = WaveDef(
            groups=[(e["type"], e["count"]) for e in groups],
            spawn_interval_ms=interval,
        )
    return waves
