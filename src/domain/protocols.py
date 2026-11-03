from typing import Protocol, runtime_checkable


class IGameContext(Protocol):
    """Minimal interface required by enemies and projectiles during gameplay.

    Any object that has these members can be passed as a context — the full
    Game class satisfies this protocol, but so can lightweight test stubs.
    """

    enemies: list
    towers: list

    # Read-only: a context may compute them (BattleSimulation does) or
    # store them as plain attributes (test stubs do).
    @property
    def speed(self) -> int: ...

    @property
    def time_ms(self) -> float: ...

    @property
    def map_width(self) -> int: ...

    @property
    def map_height(self) -> int: ...

    def enemy_killed(self, enemy) -> None:
        """Pays out a kill (the enemy is already removed)."""
        ...

    def bomb_landed(self, position, radius: float) -> None:
        """A bomb landed at `position` (its splash damage already dealt);
        shows its explosion and plays its sound."""
        ...

    def target_hit(self, target, hit_from) -> None:
        """`target` (an enemy or a tower) took a hit from a shot or bomb at
        `hit_from` (world); shows the hit. Cosmetic only."""
        ...


@runtime_checkable
class ArmedEnemy(Protocol):
    """An enemy that fights back (a tank): the battle updates its combat and
    shots, and draws its turret. Checked by what it has, not by its class."""

    bullets: list

    def update_combat(self, ctx: IGameContext) -> None: ...

    def draw_muzzle(self, surface, camera) -> None: ...
