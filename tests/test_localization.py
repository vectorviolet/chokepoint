"""The language setting (#120): the language files stay complete, their glyphs
are in the fonts, and the GAME tab's Language row switches every visible text
at once (no restart), is saved and loaded, and defaults to English."""

import re
from functools import partial
from pathlib import Path

import pygame
import pytest
import yaml

import app.game
from app.game import Game
from pygamine import SaveStore
from pygamine.util.localization import Localization, localization, missing_glyphs, tr
from ui.tower_info import ARROW
from util.config_loader import LANG_DIR, tower_types
from util.text import decimal, money, money_short, reward

ROOT = Path(__file__).resolve().parent.parent
# Every font a language's strings can be drawn in (config/assets.yaml).
FONT_KEYS = ("anton", "fira_sans", "fira_sans_bold")


# ── the language files ───────────────────────────────────────────────────────


def test_every_language_has_exactly_the_keys_and_placeholders_of_english():
    assert localization.check_key_coverage() == {}


def test_the_coverage_check_reports_a_missing_key_and_a_changed_placeholder(tmp_path):
    (tmp_path / "en.yaml").write_text(
        'a: "one"\nb: "{n} left"\nc: "three"\n', encoding="utf-8"
    )
    (tmp_path / "xx.yaml").write_text('a: "uno"\nb: "{m} left"\n', encoding="utf-8")
    checked = Localization()
    checked.load(tmp_path)
    report = checked.check_key_coverage()
    assert report["xx"]["missing"] == ["c"]
    assert report["xx"]["placeholders"]["b"] == {"expected": ["n"], "found": ["m"]}


def test_there_is_an_english_and_a_turkish_file():
    assert localization.languages() == {"en": "ENGLISH", "tr": "TÜRKÇE"}


@pytest.mark.parametrize("font_key", FONT_KEYS)
def test_every_font_has_every_glyph_of_every_language(assets, font_key):
    path = str(assets.font_path(font_key))
    assert localization.check_glyph_coverage(path) == {}


@pytest.mark.parametrize("font_key", FONT_KEYS)
def test_the_fonts_have_the_turkish_letters_and_the_info_panels_arrow(assets, font_key):
    text = "çÇğĞıİöÖşŞüÜ" + ARROW
    assert missing_glyphs(str(assets.font_path(font_key)), text) == []


def _keys_in_use() -> set[str]:
    """Literal language keys the game names: `text_key:` in panels.yaml and
    `tr("...")` calls or unit keys in src/."""
    panels = (ROOT / "config/panels.yaml").read_text(encoding="utf-8")
    keys = set(re.findall(r'text_key: "([^"]+)"', panels))
    for file in (ROOT / "src").rglob("*.py"):
        if "pygamine" in file.parts:
            continue
        source = file.read_text(encoding="utf-8")
        keys |= set(re.findall(r'\btr\(\s*"([a-z_0-9]+\.[a-z_0-9]+)"', source))
        keys |= set(re.findall(r'"((?:tower_info|hud|format)\.[a-z_]+)"', source))
    return keys


def test_every_key_the_game_names_exists_in_english():
    assert _keys_in_use() - set(localization.table("en")) == set()


def test_every_english_key_is_used_or_built_from_a_known_pattern():
    """Catches a leftover string nothing shows. Keys built in code from a
    pattern (window modes, tower texts, pause music) are listed here."""
    patterns = (
        r"settings\.window_mode_(fullscreen|borderless|windowed)",
        r"tower_[1-4]\.(name|strength|weakness)",
        r"pause\.music_(on|off)",
        r"tower_info\.(kills|earned|range|min_range|damage|fire_rate|hp|plane_\w+)",
        r"settings\.(on|off)",
    )
    used = _keys_in_use()
    unused = [
        key
        for key in localization.table("en")
        if key not in used and not any(re.fullmatch(p, key) for p in patterns)
    ]
    assert unused == []


def test_the_languages_have_a_display_name():
    for file in LANG_DIR.glob("*.yaml"):
        assert yaml.safe_load(file.read_text(encoding="utf-8"))["_meta"]["name"]


def test_decimals_use_the_languages_separator():
    assert decimal(1.5) == "1.5"
    assert decimal(1.6667, ".2f") == "1.67"
    assert money_short(1500) == "1.5K $"
    localization.set_language("tr")
    assert decimal(1.5) == "1,5"
    assert decimal(1.6667, ".2f") == "1,67"
    assert decimal(3) == "3"
    assert money_short(1500) == "1,5 bin $"


def test_the_tower_panel_shows_decimal_commas_in_turkish(tower_config, assets):
    from gameplay.towers import TowerFactory
    from ui.tower_info import stat_texts

    class Audio:
        def play_sfx(self, *args, **kwargs):
            pass

    cannon = TowerFactory.create(3, 5, 5, tower_config, assets, Audio(), 3008)
    plane = TowerFactory.create(4, 5, 5, tower_config, assets, Audio(), 3008)
    assert stat_texts(cannon)["min_range"] == "1.5 tiles"
    assert stat_texts(plane)["fire_rate"] == "2.00/s"
    localization.set_language("tr")
    assert stat_texts(cannon)["min_range"] == "1,5 kare"
    assert stat_texts(cannon)["fire_rate"].endswith("/sn")
    assert "," in stat_texts(cannon)["fire_rate"]
    assert stat_texts(plane)["fire_rate"] == "2,00/sn"
    assert "," in stat_texts(plane)["min_range"]  # flight speed, tiles/s


def test_every_tower_in_towers_yaml_has_its_texts_in_every_language():
    """The buy tooltip names a tower's keys from its type, so a tower added to
    towers.yaml without its `tower_<type>` texts must fail here, not in play."""
    for code in localization.languages():
        table = localization.table(code)
        for tower_type in tower_types():
            for part in ("name", "strength", "weakness"):
                assert f"tower_{tower_type}.{part}" in table, (code, tower_type, part)


def test_there_is_a_buy_button_for_every_tower():
    from ui.hud_slide import BUY_BUTTONS

    assert len(BUY_BUTTONS) == len(tower_types())


def test_the_money_formats():
    assert money(100) == "100 $"
    assert money_short(600) == "600 $"
    assert money_short(5000) == "5K $"
    assert reward(12) == "+$12"
    localization.set_language("tr")
    assert money_short(5000) == "5 bin $"


# ── the setting, in a real Game ──────────────────────────────────────────────


@pytest.fixture
def make_game(monkeypatch, tmp_path, fake_ticks):
    monkeypatch.setattr(app.game, "SaveStore", partial(SaveStore, directory=tmp_path))
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    return Game


@pytest.fixture
def game(make_game):
    return make_game()


def click(game, name):
    obj = game.panel_manager["settings"][name]
    game.mouse.position = obj.rect.center
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        game.handle_event(pygame.event.Event(kind, button=1, pos=obj.rect.center))


def text(game, panel, name) -> str:
    return game.panel_manager[panel][name].text


def test_the_default_language_is_english(game):
    assert localization.language == "en"
    assert text(game, "main_menu", "play_text") == "PLAY"


def test_the_game_tab_has_a_language_row_showing_the_language_name(game):
    game._open_settings("main_menu")
    game._show_settings_tab("game")
    assert text(game, "settings", "language_label_text") == "LANGUAGE"
    assert text(game, "settings", "language_value_text") == "ENGLISH"


def test_the_arrows_switch_every_visible_text_at_once(game):
    game._open_settings("main_menu")
    game._show_settings_tab("game")

    click(game, "language_next_button")

    assert localization.language == "tr"
    assert text(game, "settings", "language_value_text") == "TÜRKÇE"
    assert text(game, "settings", "settings_title_text") == "AYARLAR"
    assert text(game, "settings", "language_label_text") == "DİL"
    assert text(game, "main_menu", "play_text") == "OYNA"
    assert text(game, "credits", "back_text") == "GERİ"
    assert text(game, "game", "gameover_title_text") == "OYUN BİTTİ"
    # Texts the game builds in code: toggles, window mode, the pause menu's
    # music button, the round counter, the victory subtitle, the plane upgrade.
    assert text(game, "settings", "skip_intro_value_text") == "KAPALI"
    assert text(game, "settings", "window_mode_value_text") in {
        "TAM EKRAN",
        "ÇERÇEVESİZ",
        "PENCERELİ",
    }
    assert text(game, "game", "pause_music_text") == "MÜZİK: AÇIK"
    assert text(game, "game", "level_text") == f"Tur {game.game_state.level}"
    assert text(game, "game", "victory_subtitle_text") == "25. tur tamamlandı"
    upgrade = game.panel_manager["game"]["upgrade_plane_button_text"]
    assert upgrade.states["default"] == "UÇAK GELİŞTİR"

    click(game, "language_back_button")  # and back, with no restart
    assert localization.language == "en"
    assert text(game, "settings", "settings_title_text") == "SETTINGS"
    assert text(game, "game", "level_text") == f"Round {game.game_state.level}"
    assert text(game, "game", "pause_music_text") == "MUSIC: ON"
    assert upgrade.states["default"] == "UPG PLANES"


def test_both_arrows_wrap_around_the_languages(game):
    game._open_settings("main_menu")
    game._show_settings_tab("game")
    click(game, "language_back_button")  # before English: the last language
    assert localization.language == "tr"
    click(game, "language_next_button")  # after the last: English
    assert localization.language == "en"


def test_the_toggle_labels_follow_the_language(game):
    game.set_toggle("skip_intro", True)
    game.set_language("tr")
    assert text(game, "settings", "skip_intro_value_text") == "AÇIK"


def test_an_open_buy_tooltip_follows_the_language(game):
    game._start_new_game()
    game.buy_tooltip.show(3)
    assert text(game, "game", "buy_tooltip_title_text") == "Heavy cannon"
    game.set_language("tr")
    assert text(game, "game", "buy_tooltip_title_text") == "Ağır top"
    assert text(game, "game", "buy_tooltip_strength_label") == "İyi"


def test_the_language_is_saved_and_loaded(make_game):
    first = make_game()
    first.set_language("tr")
    first._save_settings()
    localization.set_language("en")  # a launch starts from the saved file only

    second = make_game()

    assert localization.language == "tr"
    assert text(second, "main_menu", "play_text") == "OYNA"
    assert text(second, "settings", "language_value_text") == "TÜRKÇE"


def test_a_saved_language_that_is_not_available_loads_as_english(make_game):
    first = make_game()
    first.settings_store.save({"language": "klingon"})
    localization.set_language("tr")

    second = make_game()

    assert localization.language == "en"
    assert text(second, "main_menu", "play_text") == "PLAY"


@pytest.mark.parametrize("bad", [[], {}, 7, None, ["tr"]])
def test_a_saved_language_of_the_wrong_type_loads_as_english(make_game, bad):
    first = make_game()
    first.settings_store.save({"language": bad})

    second = make_game()

    assert localization.language == "en"
    assert text(second, "main_menu", "play_text") == "PLAY"


def test_reset_to_default_goes_back_to_english(game):
    game.set_language("tr")
    game._reset_settings()
    assert localization.language == "en"
    assert text(game, "main_menu", "play_text") == "PLAY"
    assert game.settings_store.load()["language"] == "en"


def test_an_unknown_language_is_refused_and_changes_nothing(game):
    with pytest.raises(KeyError):
        game.set_language("klingon")
    assert localization.language == "en"
    assert text(game, "main_menu", "play_text") == "PLAY"


def test_a_canvas_resize_keeps_the_language(game):
    game.set_language("tr")
    size = (1280, 720)
    game.window = pygame.Surface(size)
    game.set_size(size)
    game.on_canvas_resized(size)
    assert text(game, "main_menu", "play_text") == "OYNA"
    assert text(game, "game", "level_text") == f"Tur {game.game_state.level}"
    assert text(game, "settings", "language_value_text") == "TÜRKÇE"
    assert tr("menu.play") == "OYNA"
