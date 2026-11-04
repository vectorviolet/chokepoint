"""Money texts shared by the HUD, the tower info panel and the in-world prices,
formatted through the language files (`format.*` in config/lang)."""

from pygamine.util.localization import tr


def decimal(value: float, spec: str = "g") -> str:
    """`value` formatted with `spec` (a format spec such as ".2f" or "g"), using
    the language's decimal separator (`format.decimal_separator`: "." in English,
    "," in Turkish). Every decimal number the player sees goes through here."""
    return format(value, spec).replace(".", tr("format.decimal_separator"))


def money(amount: int) -> str:
    """A price or balance: "100 $"."""
    return tr("format.money", amount=amount)


def money_short(amount: int) -> str:
    """A price, with thousands shortened from 1000 up: "100 $", "5K $"."""
    if amount >= 1000:
        return tr("format.money_thousands", amount=decimal(amount / 1000))
    return money(amount)


def reward(amount: int) -> str:
    """A kill's floating reward: "+$12"."""
    return tr("format.reward", amount=amount)
