"""docs/stats/ is exactly what scripts/gen_stats.py builds from the config,
and the rules its text states match the game's code."""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "gen_stats", ROOT / "scripts" / "gen_stats.py"
)
gen_stats = importlib.util.module_from_spec(_spec)
# Registered first: its dataclass looks its own module up while being built.
sys.modules["gen_stats"] = gen_stats
_spec.loader.exec_module(gen_stats)

# The page names, known without building the pages (at collection time).
PAGE_NAMES = list(gen_stats.PAGES)


@pytest.fixture(scope="module")
def config():
    return gen_stats.load_config()


@pytest.fixture(scope="module")
def pages(config):
    return gen_stats.pages(config=config)


def test_pages_are_the_listed_ones(pages):
    assert list(pages) == PAGE_NAMES


@pytest.mark.parametrize("name", PAGE_NAMES)
def test_stats_page_is_generated_from_the_config(pages, name):
    path = gen_stats.OUT / name
    assert path.exists() and path.read_text(encoding="utf-8") == pages[name], (
        f"docs/stats/{name} is out of date: run scripts/gen_stats.py"
    )


def test_no_leftover_pages_in_docs_stats(pages):
    assert gen_stats.extra_pages(gen_stats.OUT, pages) == [], (
        "docs/stats/ has pages gen_stats.py no longer makes: run scripts/gen_stats.py"
    )


def test_stale_pages_finds_edited_missing_and_extra_pages(tmp_path, pages):
    gen_stats.write(tmp_path, pages)
    assert gen_stats.stale_pages(tmp_path, pages) == []
    (tmp_path / "towers.md").write_text("edited by hand\n", encoding="utf-8")
    (tmp_path / "waves.md").unlink()
    (tmp_path / "old.md").write_text("dropped page\n", encoding="utf-8")
    assert gen_stats.stale_pages(tmp_path, pages) == [
        "towers.md",
        "waves.md",
        "old.md",
    ]
    gen_stats.write(tmp_path, pages, prune=True)
    assert gen_stats.stale_pages(tmp_path, pages) == []


def test_scaling_rule_in_the_text_matches_the_enemy_code(config):
    # enemies.md says: base x (1 + 0.25 x (wave - 1)), rounded down,
    # kill money at least $1.
    for enemy_type, stats in config.enemies.items():
        for wave in range(1, 61):
            scale = 1 + 0.25 * (wave - 1)
            assert gen_stats.scaled_enemy(enemy_type, wave) == (
                int(stats.hp * scale),
                max(1, int(stats.kill_money * scale)),
            )


def test_authored_waves_come_from_waves_yaml(config):
    waves = gen_stats.all_waves(config.waves, config.last_authored + 2)
    for wave, wave_def in config.waves.items():
        groups, _, is_authored = waves[wave]
        assert is_authored and groups == wave_def.groups
    assert not waves[config.last_authored + 1][2]


def test_tank_without_gun_keys_uses_the_games_defaults(config):
    from gameplay.combat import tank

    bare = {
        t: dataclasses.replace(s, range=None, fire_interval_ms=None, bullet_damage=None)
        for t, s in config.enemies.items()
    }
    text = gen_stats.enemies_page(
        dataclasses.replace(config, enemies=bare), gen_stats.docs_link, 2
    )
    dps = tank.DEFAULT_BULLET_DAMAGE * 1000 / tank.DEFAULT_FIRE_INTERVAL_MS
    assert (
        f"| 5 | Tank | {gen_stats.tiles(tank.DEFAULT_RANGE)} "
        f"| {tank.DEFAULT_FIRE_INTERVAL_MS:,} ms | {tank.DEFAULT_BULLET_DAMAGE} "
        f"| {gen_stats.num(dps)} |"
    ) in text


def test_tank_firing_every_tick_has_no_division_by_zero(config):
    stats = dict(config.enemies)
    stats[5] = dataclasses.replace(stats[5], fire_interval_ms=0)
    text = gen_stats.enemies_page(
        dataclasses.replace(config, enemies=stats), gen_stats.docs_link, 2
    )
    dps = stats[5].bullet_damage * gen_stats.TICKS_PER_SECOND
    assert f"| every tick | {stats[5].bullet_damage} | {gen_stats.num(dps)} |" in text


def test_wiki_pages_link_to_wiki_names(tmp_path, config):
    gen_stats.write(tmp_path, gen_stats.wiki_pages(config))
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
