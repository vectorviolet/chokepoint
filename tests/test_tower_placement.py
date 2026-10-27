import pygame
from pygame import Rect

from domain.game_state import GameState
from gameplay.combat.tower_placement import TowerPlacementController
from pygamine import Camera
from gameplay.towers import TowerFactory
from util.constants import TILE_SIZE
from gameplay.towers import PLANE_TYPE

GAME_AREA = Rect(0, 0, 1536, 1080)
MAP_WIDTH = 3008
MAP_HEIGHT = 2176
GROUND_TYPE = 1


class FakeAudio:
    def __init__(self):
        self.played = []

    def play_sfx(self, path):
        self.played.append(path)


class FakeButton:
    def __init__(self, rect, active=True):
        self.rect = rect
        self.active = active
        self.clicked = False

    def is_clicked(self, event, mouse_pos) -> bool:
        return self.clicked


def make_panel():
    # Positioned well outside GAME_AREA (matches the real HUD strip at
    # x: 1536-1920, see CLAUDE.md's Coordinate system section) so a mouse
    # click inside the play area never accidentally collides with one.
    return {
        f"buy_tower_{i + 1}": FakeButton(Rect(1600 + i * 80, 20, 40, 40))
        for i in range(4)
    }


def make_controller(
    tower_config, assets, *, buildable_grid=None, game_state=None, towers=None
):
    grid = (
        buildable_grid
        if buildable_grid is not None
        else [[True] * 47 for _ in range(34)]
    )
    camera = Camera(Rect(GAME_AREA), MAP_WIDTH, MAP_HEIGHT, scroll_rect=Rect(GAME_AREA))
    gs = (
        game_state
        if game_state is not None
        else GameState(start_money=1_000_000, start_lives=10)
    )
    panel = make_panel()
    controller = TowerPlacementController(
        towers if towers is not None else [],
        tower_config,
        assets,
        FakeAudio(),
        gs,
        camera,
        {"game": panel},
        grid,
        MAP_WIDTH,
        Rect(GAME_AREA),
    )
    return controller, panel, gs


def make_tower(tower_config, assets, *, tower_type=GROUND_TYPE, row=0, col=0):
    return TowerFactory.create(
        tower_type, row, col, tower_config, assets, audio=None, map_width=MAP_WIDTH
    )


def buy_button_event():
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=1)


# ── cursor / construct mode ─────────────────────────────────────────────────


def test_update_cursor_tracks_the_tile_under_the_mouse_inside_the_game_area(
    tower_config, assets
):
    controller, _, _ = make_controller(tower_config, assets)

    controller.update_cursor((3 * TILE_SIZE + 5, 2 * TILE_SIZE + 5))

    assert controller.cursor_col == 3
    assert controller.cursor_row == 2


def test_update_cursor_does_not_move_when_the_mouse_is_outside_the_game_area(
    tower_config, assets
):
    controller, _, _ = make_controller(tower_config, assets)
    controller.update_cursor((5, 5))

    controller.update_cursor((GAME_AREA.right + 100, 5))

    assert controller.cursor_col == 0  # unchanged from the first, in-bounds call


def test_is_construct_mode_reflects_buying_tower_type(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)
    assert controller.is_construct_mode() is False

    controller.buying_tower_type = 1
    assert controller.is_construct_mode() is True


def test_get_clicked_tower_matches_cursor_col_row(tower_config, assets):
    tower = make_tower(tower_config, assets, row=2, col=3)
    controller, _, _ = make_controller(tower_config, assets, towers=[tower])
    controller.cursor_col, controller.cursor_row = 3, 2

    assert controller.get_clicked_tower() is tower


def test_get_clicked_tower_returns_none_when_nothing_matches(tower_config, assets):
    tower = make_tower(tower_config, assets, row=2, col=3)
    controller, _, _ = make_controller(tower_config, assets, towers=[tower])
    controller.cursor_col, controller.cursor_row = 9, 9

    assert controller.get_clicked_tower() is None


# ── buy-tower buttons ────────────────────────────────────────────────────────


def test_clicking_a_buy_button_enters_construct_mode(tower_config, assets):
    controller, panel, _ = make_controller(tower_config, assets)
    panel["buy_tower_1"].clicked = True

    controller.handle_event(buy_button_event(), mouse_pos=(0, 0))

    assert controller.buying_tower_type == 1


def test_clicking_the_same_buy_button_again_exits_construct_mode(tower_config, assets):
    controller, panel, _ = make_controller(tower_config, assets)
    controller.buying_tower_type = 1
    panel["buy_tower_1"].clicked = True

    controller.handle_event(buy_button_event(), mouse_pos=(0, 0))

    assert controller.buying_tower_type == 0


def test_hotkey_toggles_buying_tower_type(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)

    controller.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2), mouse_pos=(0, 0)
    )
    assert controller.buying_tower_type == 2

    controller.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2), mouse_pos=(0, 0)
    )
    assert controller.buying_tower_type == 0


def test_unrelated_hotkey_does_nothing(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)

    controller.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z), mouse_pos=(0, 0)
    )

    assert controller.buying_tower_type == 0


# ── placement ────────────────────────────────────────────────────────────────


def test_is_placeable_plane_type_ignores_the_buildable_grid(tower_config, assets):
    controller, _, _ = make_controller(
        tower_config, assets, buildable_grid=[[False] * 47 for _ in range(34)]
    )
    controller.buying_tower_type = PLANE_TYPE

    assert controller._is_placeable(0, 0) is True


def test_is_placeable_ground_type_requires_a_buildable_cell(tower_config, assets):
    grid = [[True] * 47 for _ in range(34)]
    grid[5][5] = False
    controller, _, _ = make_controller(tower_config, assets, buildable_grid=grid)
    controller.buying_tower_type = GROUND_TYPE

    assert controller._is_placeable(5, 5) is False
    assert controller._is_placeable(5, 6) is True


def test_is_placeable_rejects_a_cell_already_occupied_by_a_blocking_tower(
    tower_config, assets
):
    controller, _, _ = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    controller.tower_positions = [(5, 5)]

    assert controller._is_placeable(5, 5) is False


def test_is_placeable_rejects_out_of_bounds_cells(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE

    assert controller._is_placeable(None, None) is False
    assert controller._is_placeable(-1, 0) is False
    assert controller._is_placeable(0, 999) is False


def test_purchase_places_a_tower_and_deducts_its_price(tower_config, assets):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    controller.update_cursor((5 * TILE_SIZE + 5, 5 * TILE_SIZE + 5))
    money_before = gs.money

    controller.handle_event(
        buy_button_event(), mouse_pos=(5 * TILE_SIZE + 5, 5 * TILE_SIZE + 5)
    )

    assert len(controller._towers) == 1
    placed = controller._towers[0]
    assert placed.tower_type == GROUND_TYPE
    assert gs.money == money_before - placed.buy_price
    assert controller.buying_tower_type == 0  # construct mode exits after a purchase


def test_purchase_does_nothing_when_money_is_insufficient(tower_config, assets):
    gs = GameState(start_money=0, start_lives=10)
    controller, panel, gs = make_controller(tower_config, assets, game_state=gs)
    controller.buying_tower_type = GROUND_TYPE
    pos = (5 * TILE_SIZE + 5, 5 * TILE_SIZE + 5)
    controller.update_cursor(pos)

    controller.handle_event(buy_button_event(), mouse_pos=pos)

    assert controller._towers == []
    assert controller.buying_tower_type == GROUND_TYPE  # still in construct mode


def test_purchase_does_nothing_when_the_cell_is_not_buildable(tower_config, assets):
    grid = [[True] * 47 for _ in range(34)]
    grid[5][5] = False
    controller, panel, gs = make_controller(tower_config, assets, buildable_grid=grid)
    controller.buying_tower_type = GROUND_TYPE
    pos = (5 * TILE_SIZE + 5, 5 * TILE_SIZE + 5)
    controller.update_cursor(pos)

    controller.handle_event(buy_button_event(), mouse_pos=pos)

    assert controller._towers == []


def test_clicking_over_a_ui_button_never_places_a_tower(tower_config, assets):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    button_pos = panel["buy_tower_1"].rect.center
    controller.update_cursor(button_pos)

    controller.handle_event(buy_button_event(), mouse_pos=button_pos)

    assert controller._towers == []


def test_clicking_over_an_inactive_ui_object_is_not_treated_as_ui(tower_config, assets):
    controller, panel, gs = make_controller(tower_config, assets)
    # Moved inside GAME_AREA (unlike the real HUD strip) so update_cursor()
    # actually resolves a placeable cell here -- this test is specifically
    # about the active-flag check in _is_over_ui, not about cursor bounds.
    panel["buy_tower_1"].rect = Rect(5 * TILE_SIZE, 5 * TILE_SIZE, 40, 40)
    panel["buy_tower_1"].active = False
    controller.buying_tower_type = GROUND_TYPE
    pos = panel["buy_tower_1"].rect.center
    controller.update_cursor(pos)

    controller.handle_event(buy_button_event(), mouse_pos=pos)

    # The button rect at `pos` is inactive, so _is_over_ui skips it -- the
    # purchase should proceed as a normal in-world click.
    assert len(controller._towers) == 1


# ── selection ────────────────────────────────────────────────────────────────


def test_clicking_a_tower_selects_it(tower_config, assets):
    tower = make_tower(tower_config, assets, row=2, col=3)
    controller, _, gs = make_controller(tower_config, assets, towers=[tower])
    pos = (3 * TILE_SIZE + 5, 2 * TILE_SIZE + 5)
    controller.update_cursor(pos)

    controller.handle_event(buy_button_event(), mouse_pos=pos)

    assert gs.selected_tower is tower


def test_clicking_the_same_tower_again_deselects_it(tower_config, assets):
    tower = make_tower(tower_config, assets, row=2, col=3)
    controller, _, gs = make_controller(tower_config, assets, towers=[tower])
    gs.selected_tower = tower
    pos = (3 * TILE_SIZE + 5, 2 * TILE_SIZE + 5)
    controller.update_cursor(pos)

    controller.handle_event(buy_button_event(), mouse_pos=pos)

    assert gs.selected_tower is None


def test_clicking_empty_ground_deselects_the_current_tower(tower_config, assets):
    tower = make_tower(tower_config, assets, row=2, col=3)
    controller, _, gs = make_controller(tower_config, assets, towers=[tower])
    gs.selected_tower = tower
    pos = (20 * TILE_SIZE + 5, 20 * TILE_SIZE + 5)
    controller.update_cursor(pos)

    controller.handle_event(buy_button_event(), mouse_pos=pos)

    assert gs.selected_tower is None


def test_selection_is_skipped_while_in_construct_mode(tower_config, assets):
    tower = make_tower(tower_config, assets, row=2, col=3)
    controller, _, gs = make_controller(tower_config, assets, towers=[tower])
    controller.buying_tower_type = GROUND_TYPE  # cheap ground tower, plenty of money
    pos = (3 * TILE_SIZE + 5, 2 * TILE_SIZE + 5)
    controller.update_cursor(pos)

    controller.handle_event(buy_button_event(), mouse_pos=pos)

    # Purchase logic ran instead of selection -- selected_tower was never
    # touched by _handle_selection (which early-returns in construct mode).
    assert gs.selected_tower is None


# ── drawing (smoke) ──────────────────────────────────────────────────────────


def test_draw_is_a_no_op_outside_construct_mode(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)
    surface = pygame.Surface((1536, 1080))
    surface.fill((1, 2, 3))

    controller.draw(surface, mouse_pos=(100, 100))

    assert surface.get_at((0, 0))[:3] == (1, 2, 3)


def test_draw_in_construct_mode_does_not_raise(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    controller.update_cursor((5 * TILE_SIZE, 5 * TILE_SIZE))
    surface = pygame.Surface((1536, 1080))

    controller.draw(surface, mouse_pos=(5 * TILE_SIZE, 5 * TILE_SIZE))


def test_draw_cursor_preview_outside_the_game_area_does_not_raise(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    surface = pygame.Surface((1536, 1080))

    controller.draw(surface, mouse_pos=(GAME_AREA.right + 50, 50))


def test_draw_shortcuts_does_not_raise(tower_config, assets):
    controller, _, _ = make_controller(tower_config, assets)
    surface = pygame.Surface((1920, 1080))

    controller.draw_shortcuts(surface)


# ── right click / planes / grid overlay ─────────────────────────────────────


def test_right_click_cancels_placement_and_clears_the_selection(tower_config, assets):
    tower = make_tower(tower_config, assets, row=2, col=2)
    controller, _, gs = make_controller(tower_config, assets, towers=[tower])
    controller.buying_tower_type = 3
    gs.selected_tower = tower

    controller.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=3), (500, 500)
    )

    assert controller.buying_tower_type == 0
    assert gs.selected_tower is None


def test_a_flying_plane_cannot_be_clicked_and_selected(tower_config, assets):
    """A plane keeps the row/col it was launched from while it flies away;
    clicking that empty tile must not select it (that used to put an
    invisible sell button on the tile)."""
    plane = make_tower(tower_config, assets, tower_type=PLANE_TYPE, row=3, col=4)
    controller, _, _ = make_controller(tower_config, assets, towers=[plane])
    controller.cursor_row, controller.cursor_col = 3, 4

    assert controller.get_clicked_tower() is None


class CountingSurface(pygame.Surface):
    def __init__(self, size):
        super().__init__(size)
        self.blitted = 0

    def blits(self, blit_sequence, doreturn=True):
        blit_sequence = list(blit_sequence)
        self.blitted += len(blit_sequence)
        return super().blits(blit_sequence, doreturn=doreturn)


def test_grid_overlay_only_draws_the_tiles_inside_the_viewport(tower_config, assets):
    controller, _, _ = make_controller(
        tower_config, assets
    )  # 47x34 grid, 1536x1080 view
    controller.buying_tower_type = GROUND_TYPE
    surface = CountingSurface(GAME_AREA.size)

    controller._draw_grid_overlay(surface)

    visible_cols = (
        GAME_AREA.width // TILE_SIZE + 1
    )  # 24 whole + the partial edge column
    visible_rows = -(-GAME_AREA.height // TILE_SIZE)  # 16.9 -> 17
    assert surface.blitted == visible_cols * visible_rows
    assert surface.blitted < 47 * 34


# ── Shift: continuous placement (#9) ────────────────────────────────────────


def _hold_shift(monkeypatch, held: bool) -> None:
    """Mouse events carry no `mod`, so the controller reads the keyboard
    state at placement time; fake it."""
    mods = pygame.KMOD_LSHIFT if held else pygame.KMOD_NONE
    monkeypatch.setattr(pygame.key, "get_mods", lambda: mods)


def _tile_pos(col, row):
    return (col * TILE_SIZE + 5, row * TILE_SIZE + 5)


def _place_at(controller, col, row):
    pos = _tile_pos(col, row)
    controller.update_cursor(pos)
    controller.handle_event(buy_button_event(), mouse_pos=pos)


def test_shift_held_keeps_the_type_selected_and_a_second_placement_works(
    tower_config, assets, monkeypatch
):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    _hold_shift(monkeypatch, True)

    _place_at(controller, 5, 5)
    assert controller.buying_tower_type == GROUND_TYPE

    _place_at(controller, 6, 5)
    assert [(t.row, t.col) for t in controller._towers] == [(5, 6), (5, 5)]
    assert controller.buying_tower_type == GROUND_TYPE


def test_right_shift_also_keeps_the_type_selected(tower_config, assets, monkeypatch):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    monkeypatch.setattr(pygame.key, "get_mods", lambda: pygame.KMOD_RSHIFT)

    _place_at(controller, 5, 5)

    assert controller.buying_tower_type == GROUND_TYPE


def test_shift_held_but_unaffordable_ends_placement_mode(
    tower_config, assets, monkeypatch
):
    price = tower_config.prices[GROUND_TYPE - 1][0]
    gs = GameState(start_money=price + price // 2, start_lives=10)  # one, not two
    controller, panel, gs = make_controller(tower_config, assets, game_state=gs)
    controller.buying_tower_type = GROUND_TYPE
    _hold_shift(monkeypatch, True)

    _place_at(controller, 5, 5)

    assert len(controller._towers) == 1
    assert controller.buying_tower_type == 0


def test_without_shift_placement_mode_ends_as_before(tower_config, assets, monkeypatch):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    _hold_shift(monkeypatch, False)

    _place_at(controller, 5, 5)

    assert len(controller._towers) == 1
    assert controller.buying_tower_type == 0


def test_right_click_cancels_while_shift_is_held(tower_config, assets, monkeypatch):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    _hold_shift(monkeypatch, True)
    _place_at(controller, 5, 5)

    controller.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONUP, button=3), _tile_pos(6, 5)
    )

    assert controller.buying_tower_type == 0


def test_releasing_shift_alone_does_not_end_placement_mode(
    tower_config, assets, monkeypatch
):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    _hold_shift(monkeypatch, True)
    _place_at(controller, 5, 5)

    _hold_shift(monkeypatch, False)
    controller.handle_event(
        pygame.event.Event(pygame.KEYUP, key=pygame.K_LSHIFT, mod=pygame.KMOD_NONE),
        _tile_pos(6, 5),
    )
    assert controller.buying_tower_type == GROUND_TYPE

    _place_at(controller, 6, 5)  # the next placement without Shift ends it
    assert len(controller._towers) == 2
    assert controller.buying_tower_type == 0


def test_shift_placement_cannot_stack_two_towers_on_one_tile(
    tower_config, assets, monkeypatch
):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = GROUND_TYPE
    _hold_shift(monkeypatch, True)

    _place_at(controller, 5, 5)
    _place_at(controller, 5, 5)  # before any tick refreshes tower_positions

    assert len(controller._towers) == 1


def test_shift_held_keeps_planes_selected_too(tower_config, assets, monkeypatch):
    controller, panel, gs = make_controller(tower_config, assets)
    controller.buying_tower_type = PLANE_TYPE
    _hold_shift(monkeypatch, True)

    _place_at(controller, 5, 5)
    _place_at(controller, 5, 5)  # planes block no tile

    assert len(controller._towers) == 2
    assert controller.buying_tower_type == PLANE_TYPE
