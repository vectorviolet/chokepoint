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

It keeps one list of its own, `orphan_shots`: shots still in flight whose
shooter is gone -- a plane that left the map, a tower sold or destroyed, a
tank killed or escaped. They keep flying and hit like any other, credited
to their shooter; an owner that resets the battle (new game, load, a new
demo run) calls `_clear_orphan_shots()`.
"""

from __future__ import annotations

from typing import NamedTuple

import pygame

from gameplay.combat.targeting import EnemyGrid, TowerGrid
from ui import hp_bar


class OrphanShot(NamedTuple):
    """A shot in flight whose shooter (`source`) is gone. The shot stays in
    its source's `bullets`, which it leaves when it lands, and keeps the
    source as the one credited with its kills and money. `from_tower`: it
    updates and draws with the towers' bullets, else with the enemies'."""

    source: object
    shot: object
    from_tower: bool


def _adoptable(source) -> list:
    """`source`'s shots that outlive it: those still in flight. Instant
    hits and cosmetic flashes (no `outlives_source`) go with their source."""
    return [b for b in source.bullets if getattr(b, "outlives_source", False)]


def _gone(previous, current) -> list:
    """The members of `previous` no longer in `current` (by identity)."""
    still = {id(x) for x in current}
    return [x for x in previous if id(x) not in still]


class BattleSimulation:
    bomb_impacts = None
    # This tick's grid of the towers while enemies update, for tanks
    # (IGameContext is free to lack it); None the rest of the time.
    tower_grid: TowerGrid | None = None
    # OrphanShots: shots in flight whose shooter was removed (see
    # _adopt_orphan_shots). Always replaced, never mutated in place, so the
    # empty class defaults are safe to share.
    orphan_shots: tuple | list = ()
    # The towers / enemies as the last tick left them, to notice shooters
    # removed between ticks (a sold tower) or by other shooters (a tank
    # killed by a tower's shot).
    _last_towers: tuple = ()
    _last_enemies: tuple = ()

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
        # Towers removed since the last tick (sold): their shots fly on.
        for tower in _gone(self._last_towers, self.towers):
            self._adopt_orphan_shots(tower, from_tower=True)
        kept = []
        for tower in self.towers:
            if tower.should_remove():
                self._adopt_orphan_shots(tower, from_tower=True)
                if self.game_state.selected_tower is tower:
                    # A plane that left the map or a destroyed tower: its
                    # info panel closes.
                    self.game_state.selected_tower = None
            else:
                kept.append(tower)
        self.towers[:] = kept
        self._last_towers = tuple(kept)
        positions: set[tuple] = set()
        # Enemies don't move while towers update, and kills only remove
        # them, which the grid notices: one grid serves the whole loop.
        enemy_grid = EnemyGrid(self.enemies)
        for tower in self.towers:
            tower.update(self.game_state, self.enemies, enemy_grid)
            pos = tower.get_blocking_position()
            if pos:
                positions.add(pos)
            for bullet in list(tower.bullets):  # copy: a landing bomb removes itself
                if self.game_state.is_started:
                    bullet.update(self)
        self._update_orphan_shots(from_tower=True)
        self._on_tower_positions(positions)

    def _adopt_orphan_shots(self, source, from_tower: bool) -> None:
        """`source` (a tower or a tank) is gone or going: its shots still in
        flight carry on without it, updated and drawn where its own would be."""
        shots = [OrphanShot(source, b, from_tower) for b in _adoptable(source)]
        if shots:
            self.orphan_shots = [*self.orphan_shots, *shots]

    def _update_orphan_shots(self, from_tower: bool) -> None:
        if not self.orphan_shots:
            return
        if self.game_state.is_started:
            for orphan in list(self.orphan_shots):
                if orphan.from_tower == from_tower:
                    orphan.shot.update(self)
        # A shot that landed has left its source's bullets: forget it.
        self.orphan_shots = [
            o for o in self.orphan_shots if any(x is o.shot for x in o.source.bullets)
        ]

    def _clear_orphan_shots(self) -> None:
        """The battle is reset (new game, load, a new demo run): shots in
        flight aren't saved, and the old towers and enemies are forgotten."""
        self.orphan_shots = ()
        self._last_towers = ()
        self._last_enemies = ()

    def _update_enemies(self) -> None:
        if self.wave_manager:
            self.wave_manager.update(self.enemies, self.game_state)
        # Towers don't move or get removed while enemies update.
        # Tanks killed since the last tick: their shells fly on.
        for enemy in _gone(self._last_enemies, self.enemies):
            if hasattr(enemy, "bullets"):
                self._adopt_orphan_shots(enemy, from_tower=False)
        self.tower_grid = TowerGrid(self.towers)
        try:
            for enemy in list(self.enemies):  # copy: reaching the end removes it
                if enemy.reached_end():
                    self.enemies.remove(enemy)
                    if hasattr(enemy, "bullets"):
                        self._adopt_orphan_shots(enemy, from_tower=False)
                    self._on_enemy_escaped(enemy)
                    continue
                if not self.game_state.is_started:
                    continue
                enemy.move(self.game_state.speed)
                if hasattr(enemy, "update_combat"):
                    enemy.update_combat(self)
                    for bullet in list(enemy.bullets):
                        bullet.update(self)
            self._update_orphan_shots(from_tower=False)
        finally:
            self.tower_grid = None
        self._last_enemies = tuple(self.enemies)
        if self.game_state.selected_enemy not in self.enemies:
            self.game_state.selected_enemy = None  # it died or escaped

    # ── rendering ─────────────────────────────────────────────────────────────

    def _draw_battle(self, surface: pygame.Surface, camera) -> None:
        """Terrain, then towers and their bullets, then enemies and theirs,
        then bomb explosions over all of them, then every HP bar on top so
        fire never hides one."""
        self.tilemap.draw(surface, camera)

        for tower in self.towers:
            tower.draw(self.game_state, camera, surface)
            if not tower.draws_own_bullets:
                for bullet in tower.bullets:
                    camera.draw(surface, bullet)

        # Shots whose tower is gone: drawn where its shots would be.
        self._draw_orphan_shots(surface, camera, from_tower=True)

        for enemy in self.enemies:
            camera.draw(surface, enemy)
            if hasattr(enemy, "draw_muzzle"):
                enemy.draw_muzzle(surface, camera)
                for bullet in enemy.bullets:
                    camera.draw(surface, bullet)
        self._draw_orphan_shots(surface, camera, from_tower=False)

        if self.bomb_impacts is not None:
            self.bomb_impacts.draw(surface, camera)

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

    def _draw_orphan_shots(self, surface, camera, from_tower: bool) -> None:
        for orphan in self.orphan_shots:
            if orphan.from_tower == from_tower:
                camera.draw(surface, orphan.shot)
