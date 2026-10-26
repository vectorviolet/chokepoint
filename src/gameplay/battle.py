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
"""

from __future__ import annotations

import pygame

from gameplay.combat.targeting import EnemyGrid, TowerGrid
from ui import hp_bar


class BattleSimulation:
    bomb_impacts = None
    # This tick's grid of the towers while enemies update, for tanks
    # (IGameContext is free to lack it); None the rest of the time.
    tower_grid: TowerGrid | None = None

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
        self.towers[:] = [t for t in self.towers if not t.should_remove()]
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
        self._on_tower_positions(positions)

    def _update_enemies(self) -> None:
        if self.wave_manager:
            self.wave_manager.update(self.enemies, self.game_state)
        # Towers don't move or get removed while enemies update.
        self.tower_grid = TowerGrid(self.towers)
        try:
            for enemy in list(self.enemies):  # copy: reaching the end removes it
                if enemy.reached_end():
                    self.enemies.remove(enemy)
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

    # ── rendering ─────────────────────────────────────────────────────────────

    def _draw_battle(self, surface: pygame.Surface, camera) -> None:
        """Terrain, then towers and their bullets, then enemies and theirs."""
        self.tilemap.draw(surface, camera)

        for tower in self.towers:
            tower.draw(self.game_state, camera, surface)
            for bullet in tower.bullets:
                camera.draw(surface, bullet)
            hp_bar.draw(
                surface,
                camera,
                tower.position,
                tower.hp,
                tower.maxHP,
                force=tower is self.game_state.selected_tower,
            )

        if self.bomb_impacts is not None:
            self.bomb_impacts.draw(surface, camera)

        for enemy in self.enemies:
            camera.draw(surface, enemy)
            if hasattr(enemy, "draw_muzzle"):
                enemy.draw_muzzle(surface, camera)
                for bullet in enemy.bullets:
                    camera.draw(surface, bullet)
            hp_bar.draw(surface, camera, enemy.position, enemy.hp, enemy.maxHP)
