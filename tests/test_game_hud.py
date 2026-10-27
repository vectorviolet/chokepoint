import pygame

from domain.game_state import GameState
from ui.game_hud import GameHUD


class FakeText:
    def __init__(self):
        self.text = None
        self.color = None
        self.state_texts = {}

    def set_text(self, text, *, state=None):
        if state is None:
            self.text = text
        else:
            self.state_texts[state] = text

    def set_color(self, color):
        self.color = color


class FakeBuyButton:
    """A buy button's looks, like pygamine's StateObject."""

    def __init__(self, states=(None,)):
        self.images = {state: pygame.Surface((8, 8)) for state in states}
        self.state = None
        self.set_state_calls = 0

    def add_surface(self, state, surface):
        self.images[state] = surface

    def set_state(self, state):
        self.state = state
        self.set_state_calls += 1


def make_panel():
    panel = {
        "live_text": FakeText(),
        "coin_text": FakeText(),
        "level_text": FakeText(),
    }
    for i in range(4):
        panel[f"fee_text_{i + 1}"] = FakeText()
    panel["upgrade_plane_button_text"] = FakeText()
    for i in range(3):
        panel[f"buy_tower_{i + 1}"] = FakeBuyButton()
    panel["buy_tower_4"] = FakeBuyButton((None, "lvl2"))
    return panel


def make_hud(tower_config, *, money=1000, lives=10):
    panel = make_panel()
    game_state = GameState(start_money=money, start_lives=lives)
    hud = GameHUD(game_state, tower_config, {"game": panel})
    return hud, panel, game_state


def test_construction_seeds_live_and_coin_text(tower_config):
    hud, panel, game_state = make_hud(tower_config, money=250, lives=7)

    assert panel["live_text"].text == "7"
    assert panel["coin_text"].text == "250"


def test_construction_seeds_fee_prices_from_tower_config(tower_config):
    hud, panel, game_state = make_hud(tower_config)

    for i in range(4):
        assert panel[f"fee_text_{i + 1}"].text == f"{tower_config.prices[i][0]} $"


def test_construction_colors_fee_text_red_when_nothing_is_affordable(tower_config):
    cheapest = min(tower_config.prices[i][0] for i in range(4))
    hud, panel, game_state = make_hud(tower_config, money=cheapest - 1)

    assert all(panel[f"fee_text_{i + 1}"].color == "red" for i in range(4))


def test_construction_colors_fee_text_green_when_affordable(tower_config):
    priciest = max(tower_config.prices[i][0] for i in range(4))
    hud, panel, game_state = make_hud(tower_config, money=priciest)

    assert all(panel[f"fee_text_{i + 1}"].color == "green" for i in range(4))


def test_coin_text_turns_red_at_exactly_zero_money(tower_config):
    hud, panel, game_state = make_hud(tower_config, money=0)

    assert panel["coin_text"].color == "red"


def test_on_money_changed_updates_coin_text_and_purchasing_colors(tower_config):
    hud, panel, game_state = make_hud(tower_config, money=1_000_000)

    game_state.decrease_money(1_000_000)  # fires the money listener -> back to 0

    assert panel["coin_text"].text == "0"
    assert panel["coin_text"].color == "red"
    assert all(panel[f"fee_text_{i + 1}"].color == "red" for i in range(4))


def test_on_level_changed_updates_level_text(tower_config):
    hud, panel, game_state = make_hud(tower_config)

    game_state.advance_level()

    assert panel["level_text"].text == "Level 2"


def test_on_lives_changed_updates_live_text(tower_config):
    hud, panel, game_state = make_hud(tower_config, lives=10)

    game_state.decrease_lives(3)

    assert panel["live_text"].text == "7"


def test_refresh_resyncs_from_directly_mutated_game_state(tower_config):
    hud, panel, game_state = make_hud(tower_config, money=100, lives=10)
    # Simulate a direct restore (e.g. loading a save) that bypasses the
    # mutator methods that would normally fire listeners.
    game_state.money = 42
    game_state.lives = 3
    game_state.level = 5

    hud.refresh()

    assert panel["coin_text"].text == "42"
    assert panel["live_text"].text == "3"
    assert panel["level_text"].text == "Level 5"


def test_rebind_panel_refetches_text_objects_and_reapplies_prices(tower_config):
    hud, old_panel, game_state = make_hud(tower_config, money=99, lives=4)
    new_panel = make_panel()

    hud.rebind_panel({"game": new_panel})

    assert hud.coin_text is new_panel["coin_text"]
    assert new_panel["coin_text"].text == "99"
    assert new_panel["live_text"].text == "4"
    for i in range(4):
        assert new_panel[f"fee_text_{i + 1}"].text == f"{tower_config.prices[i][0]} $"
    # The old panel's objects are untouched by a later state change.
    game_state.increase_money(1)
    assert old_panel["coin_text"].text == "99"
    assert new_panel["coin_text"].text == "100"


def test_plane_upgrade_button_shows_its_configured_price_on_hover(tower_config):
    hud, panel, _ = make_hud(tower_config)
    price = tower_config.prices[3][1]

    expected = f"{price / 1000:g}K $" if price >= 1000 else f"{price} $"
    assert panel["upgrade_plane_button_text"].state_texts == {"hover": expected}


def test_buy_buttons_are_only_updated_when_their_look_changes(tower_config):
    hud, panel, game_state = make_hud(tower_config, money=10_000)
    calls = [panel[f"buy_tower_{i + 1}"].set_state_calls for i in range(4)]

    game_state.increase_money(5)  # a kill reward: every tower still affordable

    assert [panel[f"buy_tower_{i + 1}"].set_state_calls for i in range(4)] == calls


def test_buy_buttons_grey_out_when_money_falls_short(tower_config):
    hud, panel, game_state = make_hud(tower_config, money=tower_config.prices[0][0])

    assert panel["buy_tower_1"].state is None
    assert panel["buy_tower_2"].state == "disabled"
    game_state.decrease_money(1)
    assert panel["buy_tower_1"].state == "disabled"
