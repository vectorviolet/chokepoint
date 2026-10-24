import pygame

from ui.menu_background import MenuBackground, SCROLL_SPEED


def test_construction_scales_the_map_2x_and_computes_max_scroll():
    map_surface = pygame.Surface((100, 80))

    bg = MenuBackground(map_surface, viewport=(150, 100))

    assert bg._bg.get_size() == (200, 160)
    assert bg._max_x == 200 - 150
    assert bg._max_y == 160 - 100


def test_max_scroll_never_goes_negative_when_the_viewport_is_larger_than_the_map():
    map_surface = pygame.Surface((50, 50))

    bg = MenuBackground(map_surface, viewport=(400, 300))

    assert bg._max_x == 0
    assert bg._max_y == 0


def test_update_advances_position_by_scroll_speed_each_call():
    bg = MenuBackground(pygame.Surface((100, 100)), viewport=(50, 50))

    bg.update()

    assert bg._x == SCROLL_SPEED
    assert bg._y == SCROLL_SPEED


def test_update_reverses_direction_and_clamps_at_the_max_bound():
    bg = MenuBackground(pygame.Surface((100, 100)), viewport=(50, 50))
    bg._x = bg._max_x
    bg._y = bg._max_y

    bg.update()

    assert bg._dx < 0
    assert bg._dy < 0
    assert bg._x == bg._max_x  # clamped, not overshot
    assert bg._y == bg._max_y


def test_update_reverses_direction_and_clamps_at_the_zero_bound():
    bg = MenuBackground(pygame.Surface((100, 100)), viewport=(50, 50))
    bg._x = bg._y = 0.0
    bg._dx = bg._dy = -SCROLL_SPEED

    bg.update()

    assert bg._dx > 0
    assert bg._dy > 0
    assert bg._x == 0.0
    assert bg._y == 0.0


def test_draw_blits_the_current_viewport_slice_without_raising():
    bg = MenuBackground(pygame.Surface((100, 100)), viewport=(50, 50))
    target = pygame.Surface((50, 50))

    bg.draw(target)



def test_update_pans_by_a_fractional_number_of_ticks():
    """Game.update() passes the frame's length in ticks, so the pan speed is
    the same at any frame rate."""
    bg = MenuBackground(pygame.Surface((100, 100)), viewport=(50, 50))

    bg.update(2.5)

    assert bg._x == SCROLL_SPEED * 2.5
    assert bg._y == SCROLL_SPEED * 2.5
