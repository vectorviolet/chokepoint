import pygame

from ui import hp_bar


class FakeCamera:
    def __init__(self, scale=1.0):
        self.scale = scale

    def world_to_screen(self, world_pos):
        return pygame.math.Vector2(world_pos)


def test_draw_is_a_no_op_at_full_health():
    surface = pygame.Surface((100, 100))
    surface.fill((1, 2, 3))

    hp_bar.draw(surface, FakeCamera(), (50, 50), hp=100, max_hp=100)

    assert surface.get_at((50, 50))[:3] == (1, 2, 3)


def test_draw_is_a_no_op_when_hp_or_max_hp_is_none():
    surface = pygame.Surface((100, 100))
    surface.fill((1, 2, 3))

    hp_bar.draw(surface, FakeCamera(), (50, 50), hp=None, max_hp=100)
    hp_bar.draw(surface, FakeCamera(), (50, 50), hp=50, max_hp=None)

    assert surface.get_at((50, 50))[:3] == (1, 2, 3)


def test_draw_renders_at_full_health_when_forced():
    surface = pygame.Surface((100, 100))
    surface.fill((1, 2, 3))

    hp_bar.draw(surface, FakeCamera(), (50, 50), hp=100, max_hp=100, force=True)

    bar_top = 50 - hp_bar.DEFAULT_OFFSET - hp_bar.BAR_HEIGHT
    assert surface.get_at((50, bar_top + 1))[:3] != (1, 2, 3)


def test_color_thresholds():
    assert hp_bar.health_color(1.0) == (80, 220, 80)
    assert hp_bar.health_color(0.61) == (80, 220, 80)
    assert hp_bar.health_color(0.6) == (220, 200, 60)
    assert hp_bar.health_color(0.31) == (220, 200, 60)
    assert hp_bar.health_color(0.3) == (220, 60, 60)
    assert hp_bar.health_color(0.0) == (220, 60, 60)


def test_draw_low_health_uses_the_red_tier():
    surface = pygame.Surface((100, 100))
    surface.fill((1, 2, 3))

    hp_bar.draw(surface, FakeCamera(), (50, 50), hp=10, max_hp=100)

    bar_top = 50 - hp_bar.DEFAULT_OFFSET - hp_bar.BAR_HEIGHT
    bar_left = 50 - hp_bar.BAR_WIDTH // 2
    assert surface.get_at((bar_left + 1, bar_top + 1))[:3] == (220, 60, 60)


def test_draw_at_zoomed_out_camera_does_not_raise_and_stays_local():
    surface = pygame.Surface((400, 400))
    surface.fill((9, 9, 9))

    hp_bar.draw(surface, FakeCamera(scale=2.0), (200, 200), hp=10, max_hp=100)

    assert surface.get_at((0, 0))[:3] == (9, 9, 9)
