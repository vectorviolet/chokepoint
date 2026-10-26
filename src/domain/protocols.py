from typing import Protocol


class IGameContext(Protocol):
    """Minimal interface required by enemies and projectiles during gameplay.

    Any object that has these members can be passed as a context — the full
    Game class satisfies this protocol, but so can lightweight test stubs.
    """

    enemies: list
    towers: list
    speed: int
    time_ms: float
    map_width: int
    map_height: int

    def enemy_killed(self, enemy) -> None:
        """Pays out a kill (the enemy is already removed)."""
        ...
