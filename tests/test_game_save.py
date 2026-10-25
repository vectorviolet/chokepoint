"""GameSaveMixin -- same fake-subclass approach as test_game_events.py:
FakeGame subclasses GameSaveMixin directly so _load_game()/_start_new_game()
(which call _sync_game_ui(), also defined on this mixin) resolve normally,
and only the methods Game/Application/GameEventsMixin would otherwise
provide (_init_wave_manager, _set_*_popup_active, ...) are stubbed."""

from types import SimpleNamespace

from pygame.math import Vector2

from app.game_save import GameSaveMixin
from domain.game_state import GameState
from gameplay.combat.enemy import Enemy
from gameplay.combat.tank import Tank
from gameplay.combat.wave_manager import WaveManager
from gameplay.towers import TowerFactory

MAP_WIDTH = 3008
WAYPOINTS = [Vector2(0, 0), Vector2(100, 0), Vector2(100, 100)]


class FakeSaveStore:
    def __init__(self, data=None):
        self._data = data
        self.saved = None
        self.deleted = False

    def exists(self) -> bool:
        return self._data is not None

    def load(self):
        return self._data

    def save(self, data) -> None:
        self.saved = data
        self._data = data

    def delete(self) -> None:
        self.deleted = True
        self._data = None


class FakeButton:
    def __init__(self):
        self.state = "unset"

    def set_state(self, state) -> None:
        self.state = state


class FakeHud:
    def __init__(self):
        self.refreshed = False

    def refresh(self) -> None:
        self.refreshed = True


class FakePanelManager(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_panel = None


def make_game_panel():
    return {
        "start_pause_button_icon": FakeButton(),
        "speed_toggle_button": FakeButton(),
        "buy_tower_4": FakeButton(),
        "upgrade_plane_button": FakeButton(),
    }


class FakeGame(GameSaveMixin):
    def __init__(self, tower_config, assets, *, saved_data=None, money=500, lives=10):
        self.save_store = FakeSaveStore(saved_data)
        self.game_state = GameState(start_money=money, start_lives=lives)
        self.towers: list = []
        self.enemies: list = []
        self.tower_config = tower_config
        self.assets = assets
        self.audio = None
        self.tilemap = SimpleNamespace(map_width=MAP_WIDTH, waypoints=WAYPOINTS)
        self.wave_manager = WaveManager(WAYPOINTS, assets)
        self._starting_money = money
        self._starting_lives = lives
        self._victory_popup_open = True  # deliberately "dirty" so tests can
        self._gameover_popup_open = True  # observe these actually reset to False
        self.tower_controller = SimpleNamespace(buying_tower_type=1)
        self.panel_manager = FakePanelManager({"game": make_game_panel()})
        self.hud = FakeHud()
        self.calls: list = []

    def _init_wave_manager(self) -> None:
        self.calls.append("_init_wave_manager")

    def _set_victory_popup_active(self, active) -> None:
        self.calls.append(("_set_victory_popup_active", active))

    def _set_gameover_popup_active(self, active) -> None:
        self.calls.append(("_set_gameover_popup_active", active))

    def _show_path_entrance(self) -> None:
        self.calls.append("_show_path_entrance")


def make_tower(
    tower_config,
    assets,
    *,
    tower_type=1,
    row=0,
    col=0,
    level=1,
    hp=None,
    position=(64.0, 64.0),
):
    tower = TowerFactory.create(
        tower_type, row, col, tower_config, assets, audio=None, map_width=MAP_WIDTH
    )
    tower.level = level
    if hp is not None:
        tower.hp = hp
    tower.position = Vector2(position)
    return tower


# ── has_saved_game ───────────────────────────────────────────────────────────


def test_has_saved_game_reflects_the_save_store(tower_config, assets):
    assert FakeGame(tower_config, assets, saved_data=None)._has_saved_game() is False
    assert (
        FakeGame(tower_config, assets, saved_data={"game_state": {}})._has_saved_game()
        is True
    )


# ── save ─────────────────────────────────────────────────────────────────────


def test_save_game_captures_state_towers_and_enemies(tower_config, assets):
    game = FakeGame(tower_config, assets)
    game.game_state.money = 777
    game.game_state.level = 3
    tower = make_tower(tower_config, assets, tower_type=1, row=2, col=3, hp=40)
    game.towers.append(tower)
    enemy = Enemy(9, 1, level=1, waypoints=WAYPOINTS, assets=assets)
    game.enemies.append(enemy)

    game._save_game()

    saved = game.save_store.saved
    assert saved["game_state"]["money"] == 777
    assert saved["game_state"]["level"] == 3
    assert saved["towers"] == [
        {
            "tower_type": tower.tower_type,
            "row": 2,
            "col": 3,
            "level": 1,
            "hp": 40,
            "position": [tower.position.x, tower.position.y],
        }
    ]
    assert saved["enemies"][0]["id"] == 9
    assert saved["enemies"][0]["enemy_type"] == 1
    assert saved["enemies"][0]["hp"] == enemy.hp
    assert saved["wave_manager"]["current_level"] == game.wave_manager._current_level


# ── load: no saved data falls back to a new game ────────────────────────────


def test_load_game_with_no_saved_data_starts_a_new_game(tower_config, assets):
    game = FakeGame(tower_config, assets, saved_data=None, money=250, lives=5)
    game.towers.append(make_tower(tower_config, assets))

    game._load_game()

    assert "_init_wave_manager" in game.calls
    assert game.towers == []
    assert game.game_state.money == 250
    assert game.panel_manager.current_panel == "game"


# ── load: restoring a real save ──────────────────────────────────────────────


def make_saved_blob(tower_config, assets):
    tower = make_tower(tower_config, assets, tower_type=2, row=1, col=1, level=2, hp=77)
    return {
        "game_state": {
            "money": 999,
            "lives": 3,
            "level": 4,
            "speed": 2,
            "is_started": True,
            "plane_level": 2,
            "has_won": False,
        },
        "towers": [
            {
                "tower_type": tower.tower_type,
                "row": tower.row,
                "col": tower.col,
                "level": 2,
                "hp": 77,
                "position": [200.0, 300.0],
            }
        ],
        "enemies": [
            {
                "id": 1,
                "enemy_type": 1,
                "position": [50.0, 0.0],
                "hp": 30,
                "waypoint_index": 1,
            },
            {
                "id": 2,
                "enemy_type": 5,
                "position": [100.0, 50.0],
                "hp": 60,
                "waypoint_index": 2,
            },  # 5 -> Tank
        ],
        "wave_manager": {
            "current_level": 4,
            "spawn_queue": [1, 1, 2],
            "queue_index": 1,
            "spawn_interval_ms": 500,
            "level_finish_pending": True,
            "count_all_time": 12,
        },
    }


def test_load_game_restores_full_state(tower_config, assets):
    saved = make_saved_blob(tower_config, assets)
    game = FakeGame(tower_config, assets, saved_data=saved)

    game._load_game()

    gs = game.game_state
    assert (gs.money, gs.lives, gs.level, gs.speed) == (999, 3, 4, 2)
    assert gs.is_started is True
    assert gs.plane_level == 2
    assert gs.selected_tower is None

    assert len(game.towers) == 1
    restored_tower = game.towers[0]
    assert restored_tower.level == 2
    assert restored_tower.hp == 77
    assert restored_tower.position == Vector2(200.0, 300.0)
    assert restored_tower.rect.center == (200, 300)

    assert len(game.enemies) == 2
    assert isinstance(game.enemies[0], Enemy) and not isinstance(game.enemies[0], Tank)
    assert isinstance(game.enemies[1], Tank)
    assert game.enemies[0].hp == 30
    assert game.enemies[1].waypoint_index == 2

    assert game.wave_manager._current_level == 4
    assert game.wave_manager._spawn_queue == [1, 1, 2]
    assert game.wave_manager._queue_index == 1
    assert (
        game.wave_manager._level_finish_time is not None
    )  # pending -> rebased to "now"

    assert game._victory_popup_open is False
    assert game._gameover_popup_open is False
    assert game.tower_controller.buying_tower_type == 0
    assert game.panel_manager.current_panel == "game"
    assert game.hud.refreshed is True


def test_restore_towers_only_reloads_the_image_above_level_one(tower_config, assets):
    game = FakeGame(tower_config, assets)
    level1 = {
        "tower_type": 1,
        "row": 0,
        "col": 0,
        "level": 1,
        "hp": 50,
        "position": [0.0, 0.0],
    }
    level2 = {
        "tower_type": 2,
        "row": 1,
        "col": 1,
        "level": 2,
        "hp": 100,
        "position": [64.0, 64.0],
    }

    game._restore_towers([level1, level2])

    assert len(game.towers) == 2
    assert game.towers[0].level == 1
    assert game.towers[1].level == 2  # .load() ran without raising


def test_restore_enemies_handles_an_enemy_already_at_the_end(tower_config, assets):
    game = FakeGame(tower_config, assets)
    past_end_index = len(WAYPOINTS)  # reached_end() is waypoint_index >= len(waypoints)
    saved = [
        {
            "id": 1,
            "enemy_type": 1,
            "position": [100.0, 100.0],
            "hp": 1,
            "waypoint_index": past_end_index,
        }
    ]

    game._restore_enemies(saved)

    assert len(game.enemies) == 1
    assert game.enemies[0].reached_end()  # no _face_toward() crash on an at-end enemy


def test_restore_wave_manager_rebases_timestamps_to_now(tower_config, assets):
    game = FakeGame(tower_config, assets)
    game.game_state.time_ms = 5000

    game._restore_wave_manager(
        {
            "current_level": 2,
            "spawn_queue": [],
            "queue_index": 0,
            "spawn_interval_ms": 800,
            "level_finish_pending": False,
            "count_all_time": 7,
        }
    )

    assert game.wave_manager._last_spawn_time == 5000
    assert game.wave_manager._level_finish_time is None
    assert game.wave_manager._count_all_time == 7


# ── start new game ───────────────────────────────────────────────────────────


def test_start_new_game_resets_everything_to_starting_values(tower_config, assets):
    game = FakeGame(tower_config, assets, money=300, lives=4)
    game.game_state.money = 0
    game.game_state.lives = 0
    game.game_state.level = 9
    game.game_state.has_won = True
    game.towers.append(make_tower(tower_config, assets))
    game.enemies.append(Enemy(1, 1, level=1, waypoints=WAYPOINTS, assets=assets))

    game._start_new_game()

    gs = game.game_state
    assert (gs.money, gs.lives, gs.level, gs.speed) == (300, 4, 1, 1)
    assert gs.is_started is False
    assert gs.has_won is False
    assert game.towers == []
    assert game.enemies == []
    assert "_init_wave_manager" in game.calls
    assert game._victory_popup_open is False
    assert game._gameover_popup_open is False
    assert game.tower_controller.buying_tower_type == 0
    assert game.panel_manager.current_panel == "game"
    assert game.hud.refreshed is True


# ── sync UI ──────────────────────────────────────────────────────────────────


def test_sync_game_ui_reflects_started_and_speed_and_plane_state(tower_config, assets):
    game = FakeGame(tower_config, assets)
    game.game_state.is_started = True
    game.game_state.speed = 4
    game.game_state.plane_level = 2

    game._sync_game_ui()

    panel = game.panel_manager["game"]
    assert panel["start_pause_button_icon"].state == "pause"
    assert panel["speed_toggle_button"].state == "x4_active"
    assert panel["buy_tower_4"].state == "lvl2"
    assert panel["upgrade_plane_button"].state == "purchased"
    assert ("_set_victory_popup_active", True) in game.calls
    assert ("_set_gameover_popup_active", True) in game.calls
    assert game.hud.refreshed is True


def test_sync_game_ui_reflects_paused_speed_1_and_no_plane_upgrade(
    tower_config, assets
):
    game = FakeGame(tower_config, assets)
    game._victory_popup_open = False
    game._gameover_popup_open = False
    game.game_state.is_started = False
    game.game_state.speed = 1
    game.game_state.plane_level = 1

    game._sync_game_ui()

    panel = game.panel_manager["game"]
    assert panel["start_pause_button_icon"].state is None
    assert panel["speed_toggle_button"].state is None
    assert panel["buy_tower_4"].state is None
    assert panel["upgrade_plane_button"].state is None
    assert ("_set_victory_popup_active", False) in game.calls
    assert ("_set_gameover_popup_active", False) in game.calls


# ── test isolation ──────────────────────────────────────────────────────────


def test_tests_never_save_into_the_real_saves_folder(tmp_path):
    """conftest's saves_in_tmp: a SaveStore built with no directory, as
    Game() builds its own, lands in this test's temporary folder."""
    from pygamine import SaveStore

    store = SaveStore("save")
    store.save({"probe": 1})

    assert store.path.parent == tmp_path / "saves"
    assert store.path.is_file()
