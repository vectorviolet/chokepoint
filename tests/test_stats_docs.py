"""docs/stats/ is exactly what scripts/gen_stats.py builds from the config,
and the rules its text states match the game's code."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "gen_stats", ROOT / "scripts" / "gen_stats.py"
)
gen_stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_stats)


@pytest.mark.parametrize("name, text", gen_stats.pages().items())
def test_stats_page_is_generated_from_the_config(name, text):
    path = gen_stats.OUT / name
    assert path.exists() and path.read_text(encoding="utf-8") == text, (
        f"docs/stats/{name} is out of date: run scripts/gen_stats.py"
    )


def test_check_passes_on_the_committed_pages():
    assert gen_stats.main(["--check"]) == 0


def test_stale_pages_finds_edited_and_missing_pages(tmp_path):
    gen_stats.write(tmp_path, gen_stats.pages())
    assert gen_stats.stale_pages(tmp_path) == []
    (tmp_path / "towers.md").write_text("edited by hand\n", encoding="utf-8")
    (tmp_path / "waves.md").unlink()
    assert gen_stats.stale_pages(tmp_path) == ["towers.md", "waves.md"]


def test_scaling_rule_in_the_text_matches_the_enemy_code():
    # enemies.md says: base x (1 + 0.25 x (wave - 1)), rounded down,
    # kill money at least $1.
    for enemy_type, stats in gen_stats.load_enemy_stats().items():
        for wave in range(1, 61):
            scale = 1 + 0.25 * (wave - 1)
            assert gen_stats.scaled_enemy(enemy_type, wave) == (
                int(stats.hp * scale),
                max(1, int(stats.kill_money * scale)),
            )


def test_authored_waves_come_from_waves_yaml():
    authored = gen_stats.load_wave_compositions()
    waves = gen_stats.all_waves(max(authored) + 2)
    for wave, wave_def in authored.items():
        groups, _, is_authored = waves[wave]
        assert is_authored and groups == wave_def.groups
    assert not waves[max(authored) + 1][2]


def test_wiki_pages_link_to_wiki_names(tmp_path):
    assert gen_stats.main(["--wiki", str(tmp_path)]) == 0
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == sorted(name + ".md" for name in gen_stats.PAGES.values())
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "edits made here are overwritten" in text
        for page in gen_stats.PAGES:
            assert f"]({page})" not in text, f"{path.name} links to {page}"
    assert "[Towers](Stats-Towers)" in (tmp_path / "Stats.md").read_text(
        encoding="utf-8"
    )
