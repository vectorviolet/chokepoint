from domain.game_state import GameState, TowerConfig
from pygamine import PanelManager


class GameHUD:
    def __init__(
        self,
        game_state: GameState,
        tower_config: TowerConfig,
        panel_manager: PanelManager,
    ) -> None:
        self._game_state = game_state
        self._tower_config = tower_config

        self.live_text = panel_manager["game"]["live_text"]
        self.live_text.set_text(str(game_state.lives))
        self.coin_text = panel_manager["game"]["coin_text"]
        self.coin_text.set_text(str(game_state.money))
        self.level_text = panel_manager["game"]["level_text"]

        self.fee_texts = [panel_manager["game"][f"fee_text_{i + 1}"] for i in range(4)]
        for i, fee_text in enumerate(self.fee_texts):
            fee_text.set_text(f"{tower_config.prices[i][0]} $")
        self._show_plane_upgrade_price(panel_manager)

        game_state.add_money_listener(self._on_money_changed)
        game_state.add_level_listener(self._on_level_changed)
        game_state.add_lives_listener(self._on_lives_changed)
        self._check_purchasing_power(game_state.money)

    def _show_plane_upgrade_price(self, panel_manager: PanelManager) -> None:
        """The plane-upgrade button shows its price while hovered."""
        price = self._tower_config.prices[3][1]
        label = f"{price / 1000:g}K $" if price >= 1000 else f"{price} $"
        panel_manager["game"]["upgrade_plane_button_text"].set_text(
            label, state="hover"
        )

    def _on_money_changed(self, money: int) -> None:
        self.coin_text.set_text(str(money))
        self._check_purchasing_power(money)

    def _on_level_changed(self, level: int) -> None:
        self.level_text.set_text("Level " + str(level))

    def _on_lives_changed(self, lives: int) -> None:
        self.live_text.set_text(str(lives))

    def _check_purchasing_power(self, money: int) -> None:
        for i, fee_text in enumerate(self.fee_texts):
            fee_text.set_color(
                "green" if money >= self._tower_config.prices[i][0] else "red"
            )
        self.coin_text.set_color("red" if money == 0 else "white")

    def refresh(self) -> None:
        """Re-sync all HUD text/colors from the current GameState -- for when
        fields were set directly (e.g. restoring a save) rather than through
        the mutator methods that normally fire these listeners."""
        self._on_money_changed(self._game_state.money)
        self._on_level_changed(self._game_state.level)
        self._on_lives_changed(self._game_state.lives)

    def rebind_panel(self, panel_manager: PanelManager) -> None:
        """Re-fetch this HUD's text objects from a freshly (re)built
        panel_manager -- e.g. after a canvas resize rebuilds the game panel's
        objects from scratch. Keeps this same GameHUD instance (and its
        already-registered GameState listeners) rather than constructing a
        new one, which would leak the old listeners: GameState has no
        listener-removal mechanism, so a fresh GameHUD per resize would pile
        up duplicate callbacks pointing at orphaned text objects."""
        self.live_text = panel_manager["game"]["live_text"]
        self.coin_text = panel_manager["game"]["coin_text"]
        self.level_text = panel_manager["game"]["level_text"]
        self.fee_texts = [panel_manager["game"][f"fee_text_{i + 1}"] for i in range(4)]
        for i, fee_text in enumerate(self.fee_texts):
            fee_text.set_text(f"{self._tower_config.prices[i][0]} $")
        self._show_plane_upgrade_price(panel_manager)
        self.refresh()
