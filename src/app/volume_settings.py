"""The Settings screen's volume sliders, top to bottom. One row per volume
drives loading, the slider and its percentage label, the change handler,
saving and "reset to default", so a new volume is one more row here (plus
its objects in config/panels.yaml and its default in config/settings.yaml)."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VolumeSetting:
    key: str  # in config/settings.yaml's audio section and the saved settings
    slider: str  # the settings panel's slider object
    label: str  # the settings panel's percentage text
    getter: str  # GameAudio method returning the volume set (0-1)
    setter: str  # GameAudio method setting it


VOLUME_SETTINGS = tuple(
    VolumeSetting(
        key=f"{name}_volume",
        slider=f"{name}_volume_slider",
        label=f"{name}_volume_value_text",
        getter=f"{name}_volume",
        setter=f"set_{name}_volume",
    )
    for name in ("master", "sfx", "music")
)


def saved_volume(saved: dict, key: str, default: float) -> float:
    """The volume saved under `key`, clamped to 0-1. A missing key, or a value
    that isn't a number (null, a string, true/false, NaN), gives `default`,
    so a hand-edited or old settings file still loads."""
    value = saved.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if math.isnan(value):
        return default
    return max(0.0, min(1.0, float(value)))
