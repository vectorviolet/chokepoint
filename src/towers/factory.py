from domain.game_state import TowerConfig
from towers.base_tower import BaseTower
from towers.ground_tower import GroundTower
from towers.plane_tower import PlaneTower


class TowerFactory:
    """Creates the correct BaseTower subclass for a given tower type (OCP).

    Adding a new tower type only requires a new subclass and an entry here —
    no changes to callers.
    """

    _PLANE_TYPE = 4

    @staticmethod
    def create(
        tower_type: int,
        row: int,
        col: int,
        config: TowerConfig,
        assets,
        audio,
        map_width: int,
    ) -> BaseTower:
        if tower_type == TowerFactory._PLANE_TYPE:
            return PlaneTower(tower_type, row, col, config, assets, audio, map_width)
        return GroundTower(tower_type, row, col, config, assets, audio)
