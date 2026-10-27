"""The battle itself -- towers, enemies, waves and their bullets -- stepped in
fixed ticks and drawn through a camera.

Shared by the real game (`app.game.Game`) and the main menu's live
background (`gameplay.menu_demo.MenuDemo`), so both run the exact same
simulation. A subclass provides the state it operates on:

    towers, enemies   lists of towers / enemies
    game_state        a GameState (game clock, speed, money, lives, level)
    wave_manager      a WaveManager, or None
    tilemap           the Tilemap (map size, terrain to draw)
    bomb_impacts      a ui.bomb_impact_feedback.BombImpactFeedback, or None:
                      the explosions where bombs land (drawn over towers,
                      under enemies); the owner updates and clears it

and may override the two hooks below for its own rules. It also satisfies
domain.protocols.IGameContext, which projectiles and tanks are updated with.

It keeps its own orphan shots (`orphan_shots`): shots still in flight
whose shooter is gone -- a plane that left the map, a tower sold or
destroyed, a tank killed or escaped. They are adopted where the shooter is
removed, keep flying and hit like any other, credited to their shooter; an
owner that resets the battle (new game, load, a new demo run) calls
`_clear_orphan_shots()`. A tower sold outside the tick is reported with
`_tower_sold()` (the game's placement controller does).
"""

from __future__ import annotations

import pygame

from gameplay.combat.targeting import EnemyGrid, TowerGrid
from ui import hp_bar


class OrphanShot:
    """A shot in flight whose shooter (`source`) is gone. The shot stays in
    its source's `bullets`, which it leaves when it lands, and keeps the
    source as the one credited with its kills and money.

    `after`, for a tower's shot: the live tower it updates right after,
    keeping its source's place in the update order (None: before every
    tower). Tank shells don't use it."""

    __slots__ = ("source", "shot", "after")

    def __init__(self, source, shot, after=None) -> None:
        self.source = source
        self.shot = shot
        self.after = after

    def update(self, ctx) -> bool:
        """Moves the shot on; True once it has landed."""
        self.shot.update(ctx)
        return not any(b is self.shot for b in self.source.bullets)


def _in_flight(source) -> list:
    """`source`'s shots that outlive it: those still in flight. Instant
    hits and cosmetic flashes (no `outlives_source`) go with their source."""
    return [
        b
        for b in getattr(source, "bullets", ())
        if getattr(b, "outlives_source", False)
    ]


def _update_orphans(orphans, ctx, landed: set) -> None:
    for orphan in orphans:
        if orphan.update(ctx):
            landed.add(id(orphan))


class BattleSimulation:
    bomb_impacts = None
    # This tick's grid of the towers while enemies update, for tanks
    # (IGameContext is free to lack it); None the rest of the time.
    tower_grid: TowerGrid | None = None
    # OrphanShots whose shooter was removed: towers' shots in update order
    # (see _tower_removed), and tanks' shells. Always replaced, never
    # mutated in place, so the empty class defaults are safe to share.
    _orphan_tower_shots: tuple | list = ()
    _orphan_tank_shells: tuple | list = ()

    # ── IGameContext interface ────────────────────────────────────────────────

    @property
    def speed(self) -> int:
        return self.game_state.speed

    @property
    def time_ms(self) -> float:
        return self.game_state.time_ms

    @property
    def map_width(self) -> int:
        return self.tilemap.map_width

    @property
    def map_height(self) -> int:
        return self.tilemap.map_height

    def increase_money(self, amount: int) -> None:
        self.game_state.increase_money(amount)

    def enemy_killed(self, enemy) -> None:
        self._tank_removed(enemy)
        self.increase_money(enemy.killMoney)
        self._on_enemy_killed(enemy)

    def bomb_landed(self, position, radius: float) -> None:
        """A bomb landed (its damage is already dealt): show its explosion."""
        if self.bomb_impacts is not None:
            self.bomb_impacts.bomb_landed(position, radius)

    # ── hooks ─────────────────────────────────────────────────────────────────

    def _on_tower_positions(self, positions: set[tuple]) -> None:
        """The build tiles towers occupy, refreshed every tick."""

    def _on_enemy_killed(self, enemy) -> None:
        """An enemy was killed and its reward paid (it's already removed)."""

    def _on_enemy_escaped(self, enemy) -> None:
        """An enemy reached the end of the path (it's already removed)."""
        self.game_state.decrease_lives(enemy.damage)

    # ── simulation ────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        """One fixed simulation step: game time first, then everything
        that reads it."""
        self.game_state.tick()
        self._update_towers()
        self._update_enemies()

    def _update_towers(self) -> None:
        kept = []
        for tower in self.towers:
            if tower.should_remove():
                self._tower_removed(tower, kept[-1] if kept else None)
                if self.game_state.selected_tower is tower:
                    # A plane that left the map or a destroyed tower: its
                    # info panel closes.
                    self.game_state.selected_tower = None
            else:
                kept.append(tower)
        self.towers[:] = kept
        started = self.game_state.is_started
        # Orphan shots update where their tower was in the order, so the
        # same shot as before lands first and takes the kill.
        groups: dict = {}
        if started:
            for orphan in self._orphan_tower_shots:
                key = None if orphan.after is None else id(orphan.after)
                groups.setdefault(key, []).append(orphan)
        landed: set = set()
        if groups:
            _update_orphans(groups.pop(None, ()), self, landed)
        positions: set[tuple] = set()
        # Enemies don't move while towers update, and kills only remove
        # them, which the grid notices: one grid serves the whole loop.
        enemy_grid = EnemyGrid(self.enemies)
        for tower in self.towers:
            tower.update(self.game_state, self.enemies, enemy_grid)
            pos = tower.get_blocking_position()
            if pos:
                positions.add(pos)
            if started:
                for bullet in list(tower.bullets):  # copy: a landing bomb leaves
                    bullet.update(self)
            if groups:
                _update_orphans(groups.pop(id(tower), ()), self, landed)
        for rest in groups.values():  # their tower left unannounced
            _update_orphans(rest, self, landed)
        if landed:
            self._orphan_tower_shots = [
                o for o in self._orphan_tower_shots if id(o) not in landed
            ]
        self._on_tower_positions(positions)

    # ── orphan shots ──────────────────────────────────────────────────────────

    @property
    def orphan_shots(self) -> list:
        """Every OrphanShot in flight: towers' shots, then tanks' shells."""
        return [*self._orphan_tower_shots, *self._orphan_tank_shells]

    def _tower_sold(self, tower, index: int) -> None:
        """`tower`, at `index` in `towers`, was sold and removed between
        ticks: its shots in flight carry on."""
        self._tower_removed(tower, self.towers[index - 1] if index > 0 else None)

    def _tower_removed(self, tower, after) -> None:
        """`tower` leaves the battle; `after` is the live tower that came
        before it in `towers` (None: it was first). Its shots in flight
        carry on in its place in the update order: right after `after`'s
        shots and orphans, ahead of the orphans that updated after it."""
        shots = _in_flight(tower)
        orphans = self._orphan_tower_shots
        followers = [o for o in orphans if o.after is tower]
        if not shots and not followers:
            return
        rank = {id(t): i for i, t in enumerate(self.towers)}
        after_rank = -1 if after is None else rank.get(id(after), len(rank))

        def later(o) -> bool:
            if o.after is tower:
                return True
            return o.after is not None and rank.get(id(o.after), len(rank)) > after_rank

        at = next((i for i, o in enumerate(orphans) if later(o)), len(orphans))
        for o in followers:
            o.after = after
        new = [OrphanShot(tower, shot, after) for shot in shots]
        self._orphan_tower_shots = [*orphans[:at], *new, *orphans[at:]]

    def _tank_removed(self, enemy) -> None:
        """`enemy` died or escaped: a tank's shells in flight carry on."""
        shells = _in_flight(enemy)
        if shells:
            new = [OrphanShot(enemy, shell) for shell in shells]
            self._orphan_tank_shells = [*self._orphan_tank_shells, *new]

    def _clear_orphan_shots(self) -> None:
        """The battle is reset (new game, load, a new demo run): shots in
        flight aren't saved."""
        self._orphan_tower_shots = ()
        self._orphan_tank_shells = ()

    def _update_enemies(self) -> None:
        # Shells of tanks killed this tick fly on first, before the wave
        # can be cleared and auto-pause the run: every shell moves on the
        # tick its tank died, as its live shells would.
        if self._orphan_tank_shells and self.game_state.is_started:
            landed: set = set()
            _update_orphans(self._orphan_tank_shells, self, landed)
            if landed:
                self._orphan_tank_shells = [
                    o for o in self._orphan_tank_shells if id(o) not in landed
                ]
        if self.wave_manager:
            self.wave_manager.update(self.enemies, self.game_state)
        # Towers don't move or get removed while enemies update.
        self.tower_grid = TowerGrid(self.towers)
        try:
            for enemy in list(self.enemies):  # copy: reaching the end removes it
                if enemy.reached_end():
                    self.enemies.remove(enemy)
                    self._tank_removed(enemy)
                    self._on_enemy_escaped(enemy)
                    continue
                if not self.game_state.is_started:
                    continue
                enemy.move(self.game_state.speed)
                if hasattr(enemy, "update_combat"):
                    enemy.update_combat(self)
                    for bullet in list(enemy.bullets):
                        bullet.update(self)
        finally:
            self.tower_grid = None
        if self.game_state.selected_enemy not in self.enemies:
            self.game_state.selected_enemy = None  # it died or escaped

    # ── rendering ─────────────────────────────────────────────────────────────

    def _draw_tower(self, tower, surface: pygame.Surface, camera) -> None:
        tower.draw(self.game_state, camera, surface)
        if not tower.draws_own_bullets:
            for bullet in tower.bullets:
                camera.draw(surface, bullet)

    def _draw_battle(self, surface: pygame.Surface, camera) -> None:
        """Terrain, then ground towers and their bullets, then enemies and
        theirs, then bomb explosions, then planes over all of them (they
        fly), then every HP bar on top so neither fire nor a plane hides one."""
        self.tilemap.draw(surface, camera)

        for tower in self.towers:
            if not tower.is_flying:  # planes come after the explosions
                self._draw_tower(tower, surface, camera)

        # Shots whose tower is gone: drawn where its shots would be.
        self._draw_orphans(surface, camera, self._orphan_tower_shots)

        for enemy in self.enemies:
            camera.draw(surface, enemy)
            if hasattr(enemy, "draw_muzzle"):
                enemy.draw_muzzle(surface, camera)
                for bullet in enemy.bullets:
                    camera.draw(surface, bullet)
        self._draw_orphans(surface, camera, self._orphan_tank_shells)

        if self.bomb_impacts is not None:
            self.bomb_impacts.draw(surface, camera)

        # Planes fly: each with its shadow, its falling bombs under it and,
        # if selected, its splash ring.
        for tower in self.towers:
            if tower.is_flying:
                self._draw_tower(tower, surface, camera)

        for tower in self.towers:
            hp_bar.draw(
                surface,
                camera,
                tower.position,
                tower.hp,
                tower.maxHP,
                force=tower is self.game_state.selected_tower,
            )
        for enemy in self.enemies:
            hp_bar.draw(
                surface,
                camera,
                enemy.position,
                enemy.hp,
                enemy.maxHP,
                force=enemy is self.game_state.selected_enemy,
            )

    def _draw_orphans(self, surface, camera, orphans) -> None:
        for orphan in orphans:
            camera.draw(surface, orphan.shot)
