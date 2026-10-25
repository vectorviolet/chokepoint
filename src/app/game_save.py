from pygame.math import Vector2

from gameplay.combat.enemy import Enemy
from gameplay.combat.tank import Tank
from gameplay.combat.wave_manager import TANK_TYPES
from towers import TowerFactory


class GameSaveMixin:
    """Mid-game snapshot/restore via the shared SaveStore -- lets a player
    leave the game panel and Continue exactly where they left off: enemy
    positions/HP/path progress, tower positions/levels/HP, wave-in-progress
    state, and the economy (money/lives/level/speed).

    Deliberately excludes in-flight bullets/projectiles/muzzle-flashes: they
    live a fraction of a second, hold direct object references to their
    tower/enemy target (not stable ids), and reconstructing them would need
    an id->object remap for a save that's invisible again one frame after
    load. Towers/enemies just resume firing/aiming fresh next frame.
    """

    def _has_saved_game(self) -> bool:
        return self.save_store.exists()

    # ── save ─────────────────────────────────────────────────────────────────

    def _save_game(self) -> None:
        self.save_store.save({
            "game_state": {
                "money":       self.game_state.money,
                "lives":       self.game_state.lives,
                "level":       self.game_state.level,
                "speed":       self.game_state.speed,
                "is_started":  self.game_state.is_started,
                "plane_level": self.game_state.plane_level,
                "has_won":     self.game_state.has_won,
            },
            "towers": [
                {
                    "tower_type": t.tower_type,
                    "row":        t.row,
                    "col":        t.col,
                    "level":      t.level,
                    "hp":         t.hp,
                    "position":   [t.position.x, t.position.y],  # only ever drifts for planes; harmless to store for all
                }
                for t in self.towers
            ],
            "enemies": [
                {
                    "id":             e.id,
                    "enemy_type":     e.enemy_type,
                    "position":       [e.position.x, e.position.y],
                    "hp":             e.hp,
                    "waypoint_index": e.waypoint_index,
                }
                for e in self.enemies
            ],
            "wave_manager": {
                "current_level":        self.wave_manager._current_level,
                "spawn_queue":          self.wave_manager._spawn_queue,
                "queue_index":          self.wave_manager._queue_index,
                "spawn_interval_ms":    self.wave_manager._spawn_interval_ms,
                "level_finish_pending": self.wave_manager._level_finish_time is not None,
                "count_all_time":       self.wave_manager._count_all_time,
            },
        })

    # ── load ─────────────────────────────────────────────────────────────────

    def _load_game(self) -> None:
        data = self.save_store.load()
        if not data:
            self._start_new_game()
            return

        self._restore_game_state(data.get("game_state", {}))
        self._restore_towers(data.get("towers", []))
        self._restore_enemies(data.get("enemies", []))
        self._restore_wave_manager(data.get("wave_manager", {}))

        self._victory_popup_open  = False
        self._gameover_popup_open = False
        self.tower_controller.buying_tower_type = 0
        self._sync_game_ui()
        self._show_path_entrance()
        self.panel_manager.current_panel = "game"

    def _restore_game_state(self, saved: dict) -> None:
        gs = self.game_state
        gs.money          = saved.get("money", gs.money)
        gs.lives          = saved.get("lives", gs.lives)
        gs.level          = saved.get("level", gs.level)
        gs.speed          = saved.get("speed", gs.speed)
        gs.is_started     = saved.get("is_started", False)
        gs.plane_level    = saved.get("plane_level", 1)
        gs.has_won        = saved.get("has_won", False)
        gs.selected_tower = None

    def _restore_towers(self, saved: list) -> None:
        self.towers.clear()
        for t in saved:
            tower = TowerFactory.create(
                t["tower_type"], t["row"], t["col"],
                self.tower_config, self.assets, self.audio, self.tilemap.map_width,
            )
            tower.level = t["level"]
            if tower.level != 1:
                tower.load(self.assets.image_path(f"tower_{tower.tower_type}_lvl{tower.level}"))
            tower.hp = t["hp"]
            tower.position = Vector2(t["position"])
            tower.rect.center = tower.position
            self.towers.append(tower)

    def _restore_enemies(self, saved: list) -> None:
        self.enemies.clear()
        for e in saved:
            cls = Tank if e["enemy_type"] in TANK_TYPES else Enemy
            enemy = cls(e["id"], e["enemy_type"], self.game_state.level, self.tilemap.waypoints, self.assets)
            enemy.position = Vector2(e["position"])
            enemy.waypoint_index = e["waypoint_index"]
            enemy.hp = e["hp"]
            enemy.rect.center = enemy.position
            if not enemy.reached_end():
                enemy._face_toward(enemy.waypoints[enemy.waypoint_index])
            self.enemies.append(enemy)

    def _restore_wave_manager(self, saved: dict) -> None:
        wm = self.wave_manager
        wm._current_level     = saved.get("current_level", self.game_state.level)
        wm._spawn_queue       = saved.get("spawn_queue", [])
        wm._queue_index       = saved.get("queue_index", 0)
        wm._spawn_interval_ms = saved.get("spawn_interval_ms", wm.SPAWN_INTERVAL_MS)
        wm._count_all_time    = saved.get("count_all_time", 0)
        # Game time restarts from 0 with every process, so any saved timestamp
        # is meaningless after a restart -- rebase both to "now" rather than
        # restoring the literal saved values.
        now = self.game_state.time_ms
        wm._last_spawn_time   = now
        wm._level_finish_time = now if saved.get("level_finish_pending") else None

    # ── new game ─────────────────────────────────────────────────────────────

    def _start_new_game(self) -> None:
        self.towers.clear()
        self.enemies.clear()
        gs = self.game_state
        gs.money          = self._starting_money
        gs.lives          = self._starting_lives
        gs.level          = 1
        gs.speed          = 1
        gs.is_started     = False
        gs.plane_level    = 1
        gs.has_won        = False
        gs.selected_tower = None
        self._init_wave_manager()
        self._victory_popup_open  = False
        self._gameover_popup_open = False
        self.tower_controller.buying_tower_type = 0

        self._sync_game_ui()
        self._show_path_entrance()
        self.panel_manager.current_panel = "game"

    # ── UI sync ──────────────────────────────────────────────────────────────

    def _sync_game_ui(self) -> None:
        """Re-applies button visual states derived from GameState that are
        normally set by the button-click handlers themselves (not via
        GameState listeners) -- needed after directly restoring/resetting
        state rather than clicking through it."""
        panel = self.panel_manager["game"]
        panel["start_pause_button_icon"].set_state("pause" if self.game_state.is_started else None)
        panel["speed_toggle_button"].set_state({1: None, 2: "x2_active", 4: "x4_active"}.get(self.game_state.speed))
        plane_state = "lvl2" if self.game_state.plane_level == 2 else None
        panel["buy_tower_4"].set_state(plane_state)
        panel["upgrade_plane_button"].set_state("purchased" if plane_state else None)
        self._set_victory_popup_active(self._victory_popup_open)
        self._set_gameover_popup_active(self._gameover_popup_open)
        self.hud.refresh()
