import pygame
from pygamine import AssetManager
from pygamine import PanelManager

from pygamine import Camera
from util.constants import TILE_SIZE, HALF_TILE
from domain.game_state import GameState, TowerConfig
from gameplay.towers import BaseTower, TowerFactory
from ui.range_ring import draw_range_ring

_TOWER_HOTKEYS = {
    pygame.K_1: 1,
    pygame.K_KP1: 1,
    pygame.K_2: 2,
    pygame.K_KP2: 2,
    pygame.K_3: 3,
    pygame.K_KP3: 3,
    pygame.K_4: 4,
    pygame.K_KP4: 4,
}

SHORTCUT_RADIUS = 18
SHORTCUT_OFFSET = (-8, -8)
SHORTCUT_BG_COLOR = (30, 30, 30)
SHORTCUT_BORDER_COLOR = (255, 255, 255)
SHORTCUT_TEXT_COLOR = (255, 255, 255)


class TowerPlacementController:
    def __init__(
        self,
        towers: list[BaseTower],
        tower_config: TowerConfig,
        assets: AssetManager,
        audio,
        game_state: GameState,
        camera: Camera,
        panel_manager: PanelManager,
        buildable_grid: list[list[bool]],
        map_width: int,
        game_area: pygame.Rect,
        feedback=None,
    ) -> None:
        """feedback: told when a tower is placed or sold (a sound and an
        effect on its tile; see ui.place_sell_feedback), or None."""
        self._towers = towers
        self._tower_config = tower_config
        self._assets = assets
        self._audio = audio
        self._game_state = game_state
        self._camera = camera
        self._panel_manager = panel_manager
        self._buildable_grid = buildable_grid
        self._map_width = map_width
        self._game_area = game_area
        self._feedback = feedback

        self.buying_tower_type: int = 0
        self.cursor_col: int | None = None
        self.cursor_row: int | None = None
        self.tower_positions: set[tuple] = set()

        self._block = assets.get_image("tile_block")
        self._enable = assets.get_image("tile_enable")
        self._tower_images = [
            assets.get_image("tower_1_lvl1"),
            assets.get_image("tower_2_lvl1"),
            assets.get_image("tower_3_lvl1"),
            assets.get_image("tower_4_lvl1"),
            assets.get_image("tower_4_lvl2"),
        ]
        self._shortcut_font = pygame.font.Font(assets.font_path("anton"), 20)

    def update_cursor(self, mouse_pos: tuple) -> None:
        if self._game_area.collidepoint(mouse_pos):
            world = self._camera.screen_to_world(mouse_pos)
            self.cursor_col = int(world.x // TILE_SIZE)
            self.cursor_row = int(world.y // TILE_SIZE)

    def is_construct_mode(self) -> bool:
        return self.buying_tower_type != 0

    def get_clicked_tower(self) -> BaseTower | None:
        for tower in self._towers:
            if tower.get_blocking_position() is None:
                continue  # a plane: it has flown off its tile and can't be selected or sold
            if self.cursor_col == tower.col and self.cursor_row == tower.row:
                return tower
        return None

    def handle_event(self, event, mouse_pos: tuple) -> None:
        self._handle_buy_tower_buttons(event, mouse_pos)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._is_over_ui(mouse_pos):
                return
            # A click on the selected tower's own upgrade/sell button keeps
            # it selected (and its info panel open) rather than counting as
            # a click elsewhere.
            if not self._handle_tower_actions(mouse_pos):
                self._handle_tower_selection()
            self._handle_tower_purchase(mouse_pos)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            self.cancel()
        if event.type == pygame.KEYDOWN:
            self._handle_tower_hotkey(event)

    def cancel(self) -> None:
        """Right click: drop the tower being placed and any selection."""
        self.buying_tower_type = 0
        self._game_state.selected_tower = None

    def _is_over_ui(self, mouse_pos: tuple) -> bool:
        for obj in self._panel_manager["game"].values():
            if hasattr(obj, "active") and not obj.active:
                continue
            if not getattr(obj, "visible", True):
                continue  # slid out of view with the rest of the HUD
            rect = getattr(obj, "rect", None)
            if rect is not None and rect.collidepoint(mouse_pos):
                return True
        return False

    def _handle_tower_hotkey(self, event) -> None:
        tower_type = _TOWER_HOTKEYS.get(event.key)
        if tower_type is None:
            return
        self.buying_tower_type = (
            0 if self.buying_tower_type == tower_type else tower_type
        )

    def _handle_tower_actions(self, mouse_pos: tuple) -> bool:
        """Upgrade/sell the selected tower if its button was clicked. True
        when the click landed on one of those buttons."""
        tower = self._game_state.selected_tower
        if tower is None or tower not in self._towers:
            return False
        hit = tower.hits_action_button(mouse_pos, self._camera)
        tower.sell(mouse_pos, self._game_state, self._towers, self._camera)
        tower.upgrade(mouse_pos, self._game_state, self._camera)
        if tower not in self._towers:  # sold
            self._game_state.selected_tower = None
            if self._feedback is not None:
                self._feedback.tower_sold(tower.position)
        return hit

    def _handle_tower_selection(self) -> None:
        if self.is_construct_mode():
            return
        clicked = self.get_clicked_tower()
        if not clicked:
            self._game_state.selected_tower = None
            return
        is_selected = self._game_state.selected_tower is clicked
        self._game_state.selected_tower = None if is_selected else clicked

    def _handle_tower_purchase(self, mouse_pos: tuple) -> None:
        if not self._game_area.collidepoint(mouse_pos) or not self.buying_tower_type:
            return
        if not self._is_placeable(self.cursor_row, self.cursor_col):
            return
        if (
            self._game_state.money
            < self._tower_config.prices[self.buying_tower_type - 1][0]
        ):
            return
        tower = TowerFactory.create(
            self.buying_tower_type,
            self.cursor_row,
            self.cursor_col,
            self._tower_config,
            self._assets,
            self._audio,
            self._map_width,
        )
        if tower.get_blocking_position() is None:
            self._towers.append(tower)
        else:
            self._towers.insert(0, tower)
        self._game_state.decrease_money(tower.buy_price)
        self.buying_tower_type = 0
        if self._feedback is not None:
            self._feedback.tower_placed(tower.position)

    def _handle_buy_tower_buttons(self, event, mouse_pos: tuple) -> None:
        for i in range(4):
            btn = self._panel_manager["game"][f"buy_tower_{i + 1}"]
            if btn.is_clicked(event, mouse_pos):
                self.buying_tower_type = 0 if self.buying_tower_type == i + 1 else i + 1

    def draw(self, surface: pygame.Surface, mouse_pos: tuple) -> None:
        if not self.buying_tower_type:
            return
        self._draw_grid_overlay(surface)
        self._draw_cursor_preview(surface, mouse_pos)

    def draw_shortcuts(self, surface: pygame.Surface) -> None:
        for i in range(4):
            btn = self._panel_manager["game"][f"buy_tower_{i + 1}"]
            left, top = btn.rect.topleft
            cx = int(left + SHORTCUT_OFFSET[0] + SHORTCUT_RADIUS)
            cy = int(top + SHORTCUT_OFFSET[1] + SHORTCUT_RADIUS)
            pygame.draw.circle(surface, SHORTCUT_BG_COLOR, (cx, cy), SHORTCUT_RADIUS)
            pygame.draw.circle(
                surface, SHORTCUT_BORDER_COLOR, (cx, cy), SHORTCUT_RADIUS, 2
            )
            label = self._shortcut_font.render(str(i + 1), True, SHORTCUT_TEXT_COLOR)
            surface.blit(label, label.get_rect(center=(cx, cy)))

    def _is_placeable(self, row: int | None, col: int | None) -> bool:
        if self.buying_tower_type == 4:
            return True
        if row is None or col is None:
            return False
        if not (
            0 <= row < len(self._buildable_grid)
            and 0 <= col < len(self._buildable_grid[0])
        ):
            return False
        if not self._buildable_grid[row][col]:
            return False
        return (row, col) not in self.tower_positions

    def _draw_grid_overlay(self, surface: pygame.Surface) -> None:
        # Only the tiles inside the viewport: blitting the whole 47x34 grid
        # every frame cost more than the rest of the frame combined.
        scaled_enable = self._camera.scale_image(self._enable)
        scaled_block = self._camera.scale_image(self._block)
        view = self._game_area
        top_left = self._camera.screen_to_world(view.topleft)
        bottom_right = self._camera.screen_to_world(view.bottomright)
        rows = len(self._buildable_grid)
        cols = len(self._buildable_grid[0]) if rows else 0
        first_col = max(0, int(top_left.x // TILE_SIZE))
        first_row = max(0, int(top_left.y // TILE_SIZE))
        last_col = min(cols - 1, int(bottom_right.x // TILE_SIZE))
        last_row = min(rows - 1, int(bottom_right.y // TILE_SIZE))
        blits = []
        for row_idx in range(first_row, last_row + 1):
            for col_idx in range(first_col, last_col + 1):
                screen = self._camera.world_to_screen(
                    (col_idx * TILE_SIZE, row_idx * TILE_SIZE)
                )
                tile = (
                    scaled_enable
                    if self._is_placeable(row_idx, col_idx)
                    else scaled_block
                )
                blits.append((tile, screen))
        surface.blits(blits, doreturn=False)

    def _draw_cursor_preview(self, surface: pygame.Surface, mouse_pos: tuple) -> None:
        index = (
            4
            if self.buying_tower_type == 4 and self._game_state.plane_level == 2
            else self.buying_tower_type - 1
        )
        mx, my = mouse_pos
        if not self._game_area.collidepoint(mouse_pos):
            old_clip = surface.get_clip()
            surface.set_clip(None)
            surface.blit(self._tower_images[index], (mx - HALF_TILE, my - HALF_TILE))
            surface.set_clip(old_clip)
            return

        scaled_tower = self._camera.scale_image(self._tower_images[index])
        cell_top_left = self._camera.world_to_screen(
            (self.cursor_col * TILE_SIZE, self.cursor_row * TILE_SIZE)
        )
        surface.blit(scaled_tower, cell_top_left)

        world_range = self._tower_config.ranges[self.buying_tower_type - 1][0]
        scaled_range = int(world_range * self._camera.scale)
        min_ranges = self._tower_config.min_ranges
        world_min_range = (
            min_ranges[self.buying_tower_type - 1][0]
            if self.buying_tower_type <= len(min_ranges)
            else 0
        )
        scaled_min_range = int(world_min_range * self._camera.scale)
        center = self._camera.world_to_screen(
            (
                self.cursor_col * TILE_SIZE + HALF_TILE,
                self.cursor_row * TILE_SIZE + HALF_TILE,
            )
        )
        buy_price = self._tower_config.prices[self.buying_tower_type - 1][0]
        cannot_afford = self._game_state.money < buy_price
        blocked = (
            not self._is_placeable(self.cursor_row, self.cursor_col) or cannot_afford
        )
        self._blit_range_ring(surface, center, scaled_range, blocked, scaled_min_range)

    @staticmethod
    def _blit_range_ring(
        surface: pygame.Surface,
        center,
        radius: int,
        blocked: bool,
        min_radius: int = 0,
    ) -> None:
        outline = (255, 0, 0, 120) if blocked else (0, 200, 0, 120)
        draw_range_ring(surface, center, radius, outline, 5, min_radius)
