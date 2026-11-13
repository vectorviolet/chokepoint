from collections.abc import Callable

import pygame

from domain.game_state import GameState, TowerConfig
from pygamine import PanelManager
from ui.odometer import Odometer
from util.text import money

BUY_BUTTONS = tuple(f"buy_tower_{i + 1}" for i in range(4))
PLANE_UPGRADE = "upgrade_plane_button"
MAXED = "maxed"  # the plane upgrade's state once bought
# The money counter's flash when an unaffordable tower is picked: red and
# white in turn, FLASH_STEP_MS each, for FLASH_MS (real time).
FLASH_MS = 450
FLASH_STEP_MS = 150
# How the HUD number follows the coins (hud.money_style in config/settings.yaml):
# it jumps by each coin's value as the coin lands, or its digits roll.
MONEY_STYLES = ("count_up", "odometer")
# Multiplied into a buy button's (grayed) image while its tower is unaffordable.
DISABLED_SHADE = (150, 150, 150)


def disabled_state(state):
    """The key of a buy button's grayed look for its look `state`."""
    return "disabled" if state is None else f"{state}_disabled"


def _grayed(image: pygame.Surface) -> pygame.Surface:
    gray = pygame.transform.grayscale(image)
    gray.fill(DISABLED_SHADE, special_flags=pygame.BLEND_RGB_MULT)
    return gray


class InvisibleFont:
    """Stands in for a text object's font so the object still lays out its plate for the
    text, with the glyphs left out (the odometer draws them). Every other font call
    (size, height...) goes to the real font."""

    def __init__(self, font: pygame.font.Font) -> None:
        self._font = font

    def __getattr__(self, name: str):
        return getattr(self._font, name)

    def render(self, text: str, antialias: bool, color) -> pygame.Surface:
        return pygame.Surface(self._font.size(text), pygame.SRCALPHA)


class GameHUD:
    def __init__(
        self,
        game_state: GameState,
        tower_config: TowerConfig,
        panel_manager: PanelManager,
        money_style: str = "count_up",
        roll_ms: int = 200,
    ) -> None:
        if money_style not in MONEY_STYLES:
            raise ValueError(
                f"hud.money_style must be one of {MONEY_STYLES}, got {money_style!r}"
            )
        self._game_state = game_state
        self._tower_config = tower_config
        self.money_style = money_style
        # The coin value still in flight, which the shown number leaves out
        # (the game points it at KillFeedback.pending_money).
        self.pending_money: Callable[[], int] = lambda: 0
        self.reduce_flashing = False  # no rolling: the number just follows
        self._real_font: pygame.font.Font | None = (
            None  # odometer style: the coin text's own font
        )
        self._odometer = Odometer(roll_ms)

        self.live_text = panel_manager["game"]["live_text"]
        self.live_text.set_text(str(game_state.lives))
        self.coin_text = panel_manager["game"]["coin_text"]
        self.coin_text.set_text(str(game_state.money))
        self._shown_money = game_state.money
        self._bind_odometer()
        self.level_text = panel_manager["game"]["level_text"]
        self._flash_left_ms = 0.0
        self._bind_buy_buttons(panel_manager)

        self.fee_texts = [panel_manager["game"][f"fee_text_{i + 1}"] for i in range(4)]
        self._set_fee_texts()
        self._bind_plane_upgrade(panel_manager)

        game_state.add_money_listener(self._on_money_changed)
        game_state.add_level_listener(self._on_level_changed)
        game_state.add_lives_listener(self._on_lives_changed)
        self._check_purchasing_power(game_state.money)

    def _bind_plane_upgrade(self, panel_manager: PanelManager) -> None:
        """The plane-upgrade button and its icon each get a grayed copy of
        their look, shown once the upgrade is bought (see
        refresh_plane_upgrade)."""
        self._plane_upgrade_button = panel_manager["game"][PLANE_UPGRADE]
        self._plane_upgrade_icon = panel_manager["game"]["upgrade_plane_button_icon"]
        button = self._plane_upgrade_button
        maxed = _grayed(button.images[None])
        button.add_surface(MAXED, maxed)
        # The same grayed look while hovered: pygamine has no public setter
        # for a generated hover surface, so it goes in the hover table.
        hover_images = getattr(button, "_hover_images", None)
        if hover_images is not None:
            hover_images[MAXED] = maxed
        icon = self._plane_upgrade_icon
        icon.add_surface(MAXED, _grayed(icon.images[None]))

    def refresh_plane_upgrade(self) -> None:
        """Once planes are upgraded (the max level), the plane-upgrade button
        and its icon are grayed and clicks on it do nothing."""
        state = MAXED if self._game_state.plane_level >= 2 else None
        for obj in (self._plane_upgrade_button, self._plane_upgrade_icon):
            if obj.state != state:
                obj.set_state(state)

    def _bind_buy_buttons(self, panel_manager: PanelManager) -> None:
        """Gives each buy button a grayed copy of each of its looks, shown
        while its tower is unaffordable."""
        self.buy_buttons = [panel_manager["game"][name] for name in BUY_BUTTONS]
        for button in self.buy_buttons:
            for state, image in list(button.images.items()):
                if isinstance(state, str) and state.endswith("disabled"):
                    continue
                button.add_surface(disabled_state(state), _grayed(image))

    def refresh_buy_buttons(self) -> None:
        """Shows each buy button grayed while its tower is unaffordable; the
        plane's in its level-2 look once planes are upgraded."""
        money = self._game_state.money
        for i, button in enumerate(self.buy_buttons):
            look = "lvl2" if i == 3 and self._game_state.plane_level == 2 else None
            affordable = money >= self._tower_config.prices[i][0]
            state = look if affordable else disabled_state(look)
            if button.state != state:  # each kill pays: skip needless redraws
                button.set_state(state)

    def flash_money(self) -> None:
        """A brief red flash of the money counter (a refused purchase)."""
        self._flash_left_ms = FLASH_MS
        self._color_coin_text()

    @property
    def is_flashing(self) -> bool:
        return self._flash_left_ms > 0

    def update(self, frame_ms: float) -> None:
        """Runs the money flash on real time, and moves the shown money as coins land
        (call it after KillFeedback.update)."""
        self._sync_money()
        if not self.is_flashing:
            return
        self._flash_left_ms = max(0.0, self._flash_left_ms - frame_ms)
        self._color_coin_text()

    @property
    def shown_money(self) -> int:
        """The number the HUD shows: the real balance minus the coins still flying
        (never below zero; spending lowers it at once)."""
        return max(0, self._game_state.money - self.pending_money())

    def snap_money(self) -> None:
        """Shows the number for the current state at once, no animation (pause,
        popups, load, a new game, Reduce flashing)."""
        self._show(self.shown_money, animate=False)

    def _sync_money(self) -> None:
        self._show(self.shown_money, animate=not self.reduce_flashing)

    def _show(self, shown: int, animate: bool) -> None:
        if shown == self._shown_money and self.coin_text.text == str(shown):
            self._color_coin_text()  # it follows the real balance, not the number
            if not animate and self.money_style == "odometer":
                self._odometer.snap(str(shown))  # stop a roll in progress
            return
        direction = 1 if shown > self._shown_money else -1
        self._shown_money = shown
        self.coin_text.set_text(str(shown))
        if self.money_style == "odometer":
            if animate:
                self._odometer.set_target(str(shown), direction, self._now_ms())
            else:
                self._odometer.snap(str(shown))
            self._place_odometer()  # the plate grew or shrank
        self._color_coin_text()

    def _bind_odometer(self) -> None:
        """Odometer style: the text object keeps only the plate (it lays it out for the
        number with an invisible font) and the odometer draws the digits over it."""
        if self.money_style != "odometer":
            return
        font = self.coin_text.font
        assert font is not None, "the coin text has a font"
        self._real_font = font
        self.coin_text.font = InvisibleFont(font)
        # Laid out again with the invisible font (set_text skips an unchanged text).
        number = self.coin_text.text
        self.coin_text.set_text("")
        self.coin_text.set_text(number)
        self._odometer.snap(number)
        self._place_odometer()

    @staticmethod
    def _now_ms() -> int:
        """The odometer's clock: real time, read when it is used (like Highrise's)."""
        return pygame.time.get_ticks()

    def is_money_rolling(self) -> bool:
        """Whether any digit of the odometer is still rolling (never in count_up)."""
        return self.money_style == "odometer" and self._odometer.is_rolling(
            self._now_ms()
        )

    def _place_odometer(self) -> None:
        assert self._real_font is not None, "_bind_odometer() first"
        text = self.coin_text
        top, right, bottom, left = text.padding
        rect = text.rect
        area = pygame.Rect(
            rect.left + left,
            rect.top + top,
            rect.width - left - right,
            rect.height - top - bottom,
        )
        self._odometer.bind(area, self._real_font, text.color, rect, area.left)

    def draw_money_odometer(
        self, surface: pygame.Surface, offset: tuple[int, int] = (0, 0)
    ) -> None:
        """Draws the rolling digits over the money plate (the odometer style only);
        `offset` is how far the HUD has slid."""
        if self.money_style == "odometer":
            self._odometer.draw(surface, self._now_ms(), offset)

    def _color_coin_text(self) -> None:
        if self.is_flashing:
            step = int((FLASH_MS - self._flash_left_ms) // FLASH_STEP_MS)
            self.coin_text.set_color("red" if step % 2 == 0 else "white")
        else:
            self.coin_text.set_color("red" if self._game_state.money == 0 else "white")
        if self.money_style == "odometer":
            self._odometer.set_color(self.coin_text.color)

    def _on_money_changed(self, money: int) -> None:
        # The real balance: it picks the colors and the buy buttons. The number
        # shown follows it only as far as the coins have landed.
        self._sync_money()
        self._check_purchasing_power(money)

    def _on_level_changed(self, level: int) -> None:
        self.level_text.set_params(level=level)

    def _on_lives_changed(self, lives: int) -> None:
        self.live_text.set_text(str(lives))

    def _check_purchasing_power(self, money: int) -> None:
        for i, fee_text in enumerate(self.fee_texts):
            fee_text.set_color(
                "green" if money >= self._tower_config.prices[i][0] else "red"
            )
        self._color_coin_text()
        self.refresh_buy_buttons()
        self.refresh_plane_upgrade()

    def _set_fee_texts(self) -> None:
        for i, fee_text in enumerate(self.fee_texts):
            fee_text.set_text(money(self._tower_config.prices[i][0]))

    def refresh_language(self) -> None:
        """Re-sync the texts built in code (round counter, prices) after a
        language change."""
        self._set_fee_texts()
        self.refresh(snap=False)

    def refresh(self, snap: bool = True) -> None:
        """Re-sync all HUD text/colors from the current GameState -- for when
        fields were set directly (e.g. restoring a save) rather than through
        the mutator methods that normally fire these listeners. The money number
        snaps (a load, a new game); `snap=False` lets it roll on (a language
        change)."""
        if snap:
            self.snap_money()
        else:
            self._sync_money()
        self._check_purchasing_power(self._game_state.money)
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
        self.coin_text.set_text(str(self._shown_money))
        self._bind_odometer()
        self.level_text = panel_manager["game"]["level_text"]
        self._bind_buy_buttons(panel_manager)
        self.fee_texts = [panel_manager["game"][f"fee_text_{i + 1}"] for i in range(4)]
        self._set_fee_texts()
        self._bind_plane_upgrade(panel_manager)
        self.refresh()
