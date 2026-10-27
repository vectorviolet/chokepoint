from domain.game_state import TowerConfig
from gameplay.towers.base_tower import BaseTower
from gameplay.towers.ground_tower import GroundTower
from gameplay.towers.plane_tower import PlaneTower

PLANE_TYPE = 4
GROUND_TOWER_TYPES = (1, 2, 3)


class TowerFactory:
    """Creates the correct BaseTower subclass for a given tower type (OCP).

    Adding a new tower type only requires a new subclass and an entry here —
    no changes to callers.
    """

    _PLANE_TYPE = PLANE_TYPE

    @staticmethod
    def create(
        tower_type: int,
        row: int,
        col: int,
        config: TowerConfig,
        assets,
        audio,
        map_width: int,
        level: int = 1,
    ) -> BaseTower:
        """A new tower at `level`: its sprite for that level and full HP."""
        if tower_type == TowerFactory._PLANE_TYPE:
            tower = PlaneTower(tower_type, row, col, config, assets, audio, map_width)
        else:
            tower = GroundTower(tower_type, row, col, config, assets, audio)
        if level != 1:
            tower.level = level
            tower.load(assets.image_path(f"tower_{tower_type}_lvl{level}"))
            tower.hp = tower.maxHP
        return tower
