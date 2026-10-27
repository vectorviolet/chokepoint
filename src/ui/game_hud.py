import pygame

from domain.game_state import GameState, TowerConfig
from pygamine import PanelManager

BUY_BUTTONS = tuple(f"buy_tower_{i + 1}" for i in range(4))
# The money counter's flash when an unaffordable tower is picked: red and
# white in turn, FLASH_STEP_MS each, for FLASH_MS (real time).
FLASH_MS = 450
FLASH_STEP_MS = 150
# Multiplied into a buy button's (greyed) image while its tower is unaffordable.
DISABLED_SHADE = (150, 150, 150)


def disabled_state(state):
    """The key of a buy button's greyed look for its look `state`."""
    return "disabled" if state is None else f"{state}_disabled"


def _greyed(image: pygame.Surface) -> pygame.Surface:
    grey = pygame.transform.grayscale(image)
    grey.fill(DISABLED_SHADE, special_flags=pygame.BLEND_RGB_MULT)
    return grey


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
        self._flash_left_ms = 0.0
        self._bind_buy_buttons(panel_manager)

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

    def _bind_buy_buttons(self, panel_manager: PanelManager) -> None:
        """Gives each buy button a greyed copy of each of its looks, shown
        while its tower is unaffordable."""
        self.buy_buttons = [panel_manager["game"][name] for name in BUY_BUTTONS]
        for button in self.buy_buttons:
            for state, image in list(button.images.items()):
                if isinstance(state, str) and state.endswith("disabled"):
                    continue
                button.add_surface(disabled_state(state), _greyed(image))

    def refresh_buy_buttons(self) -> None:
        """Shows each buy button greyed while its tower is unaffordable; the
        plane's in its level-2 look once planes are upgraded."""
        money = self._game_state.money
        for i, button in enumerate(self.buy_buttons):
            look = "lvl2" if i == 3 and self._game_state.plane_level == 2 else None
            affordable = money >= self._tower_config.prices[i][0]
            button.set_state(look if affordable else disabled_state(look))

    def flash_money(self) -> None:
        """A brief red flash of the money counter (a refused purchase)."""
        self._flash_left_ms = FLASH_MS
        self._color_coin_text()

    @property
    def is_flashing(self) -> bool:
        return self._flash_left_ms > 0

    def update(self, frame_ms: float) -> None:
        """Runs the money flash on real time."""
        if not self.is_flashing:
            return
        self._flash_left_ms = max(0.0, self._flash_left_ms - frame_ms)
        self._color_coin_text()

    def _color_coin_text(self) -> None:
        if self.is_flashing:
            step = int((FLASH_MS - self._flash_left_ms) // FLASH_STEP_MS)
            self.coin_text.set_color("red" if step % 2 == 0 else "white")
        else:
            self.coin_text.set_color("red" if self._game_state.money == 0 else "white")

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
        self._color_coin_text()
        self.refresh_buy_buttons()

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
        self._bind_buy_buttons(panel_manager)
        self.fee_texts = [panel_manager["game"][f"fee_text_{i + 1}"] for i in range(4)]
        for i, fee_text in enumerate(self.fee_texts):
            fee_text.set_text(f"{self._tower_config.prices[i][0]} $")
        self._show_plane_upgrade_price(panel_manager)
        self.refresh()
