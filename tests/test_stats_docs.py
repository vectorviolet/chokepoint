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


# ── pictures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def assets():
    from pygamine import AssetManager

    manager = AssetManager()
    manager.load_manifest(ROOT / "config" / "assets.yaml")
    return manager


@pytest.fixture(scope="module")
def images(config):
    return gen_stats.all_pictures(config)


def raw(assets, key):
    import pygame

    return pygame.image.load(assets.image_path(key))


def test_docs_stats_images_are_generated_from_the_config(images):
    assert gen_stats.stale_images(gen_stats.OUT, images) == [], (
        "docs/stats/images/ is out of date: run scripts/gen_stats.py"
    )


def test_pictures_are_found_through_the_asset_keys(config, assets):
    # Every level of every tower and every enemy has a picture, found from
    # the keys the game itself looks up; no hand-kept list of files.
    for tower_type, levels in enumerate(config.towers.max_levels, start=1):
        covered = [p.alt for p in config.tower_pictures[tower_type]]
        for level in range(1, levels + 1):
            assets.image_path(f"tower_{tower_type}_lvl{level}")  # a KeyError fails
        assert covered == [f"Level {n}" for n in range(1, levels + 1)]
    assert sorted(config.enemy_pictures) == sorted(config.enemies)
    for enemy_type in config.enemies:
        assets.image_path(f"enemy_{enemy_type}")


def test_ground_tower_picture_is_the_platform_with_the_turret_on_top(config, assets):
    import pygame

    for tower_type in gen_stats.GROUND_TOWER_TYPES:
        for picture in config.tower_pictures[tower_type]:
            platform = raw(assets, f"tower_{tower_type}_platform")
            turret = raw(assets, f"tower_{tower_type}_lvl{picture.first_level}")
            # What GroundTower draws: platform, then the unrotated turret,
            # both centered on the tower's position.
            expected = pygame.Surface(picture.surface.get_size(), pygame.SRCALPHA)
            center = expected.get_rect().center
            expected.blit(platform, platform.get_rect(center=center))
            expected.blit(turret, turret.get_rect(center=center))
            assert gen_stats.pixels(picture.surface) == gen_stats.pixels(expected)
            assert gen_stats.pixels(picture.surface) != gen_stats.pixels(
                gen_stats.compose([platform])
            ), "the turret is missing"


def test_plane_picture_is_the_sprite_without_the_shadow(config, assets):
    for picture in config.tower_pictures[gen_stats.PLANE_TYPE]:
        level = picture.first_level
        plane = raw(assets, f"tower_{gen_stats.PLANE_TYPE}_lvl{level}")
        assert gen_stats.pixels(picture.surface) == gen_stats.pixels(
            gen_stats.compose([plane])
        )


def test_levels_sharing_a_sprite_get_one_picture(config, assets):
    class SameSprite:
        def image_path(self, key):
            return assets.image_path("tower_2_lvl1" if "lvl" in key else key)

    pictures = gen_stats.tower_pictures(config.towers, SameSprite())
    assert [p.alt for p in pictures[2]] == ["Levels 1-3"]
    assert [p.alt for p in pictures[3]] == ["Levels 1-2"]
    assert [p.file for p in pictures[2]] == ["stats-tower-2-level-1.png"]


def test_pages_link_pictures_that_exist(pages, images):
    import re

    linked = {
        m
        for text in pages.values()
        for m in re.findall(r"\]\(images/([^)]+\.png)\)", text)
    }
    assert linked == set(images)


def reencoded(path):
    """The same pixels as `path`, saved with other PNG settings (as another
    zlib or libpng build would write them)."""
    from PIL import Image

    before = path.read_bytes()
    Image.open(path).save(path, compress_level=0)
    assert path.read_bytes() != before
    return path


def test_stale_images_finds_changed_resized_missing_and_extra_images(tmp_path, images):
    import pygame

    gen_stats.write_images(tmp_path, images)
    assert gen_stats.stale_images(tmp_path, images) == []
    folder = tmp_path / gen_stats.IMAGES_DIR
    names = sorted(images)
    changed, resized, missing = names[0], names[1], names[2]
    recolored = images[changed].copy()
    recolored.set_at((32, 32), (1, 2, 3, 255))
    pygame.image.save(recolored, folder / changed)
    pygame.image.save(pygame.Surface((65, 64), pygame.SRCALPHA), folder / resized)
    (folder / missing).unlink()
    (folder / "old.png").write_bytes(b"not generated any more")
    expected = [f"images/{n}" for n in (changed, resized, missing)]
    assert gen_stats.stale_images(tmp_path, images) == [*expected, "images/old.png"]
    gen_stats.write_images(tmp_path, images, prune=True)
    assert gen_stats.stale_images(tmp_path, images) == []


def test_stale_images_compares_pixels_not_png_bytes(tmp_path, images):
    gen_stats.write_images(tmp_path, images)
    folder = tmp_path / gen_stats.IMAGES_DIR
    for name in images:
        reencoded(folder / name)
    assert gen_stats.stale_images(tmp_path, images) == []
    # And a rewrite leaves files with the right pixels untouched.
    before = {n: (folder / n).read_bytes() for n in images}
    gen_stats.write_images(tmp_path, images, prune=True)
    assert {n: (folder / n).read_bytes() for n in images} == before


def test_an_undecodable_image_is_stale(tmp_path, images):
    gen_stats.write_images(tmp_path, images)
    name = sorted(images)[0]
    (tmp_path / gen_stats.IMAGES_DIR / name).write_bytes(b"garbage")
    assert gen_stats.stale_images(tmp_path, images) == [f"images/{name}"]


def test_wiki_copy_has_the_images_its_pages_link(tmp_path, config, images):
    gen_stats.write(tmp_path, gen_stats.wiki_pages(config))
    gen_stats.write_images(tmp_path, images)
    text = (tmp_path / "Stats-Towers.md").read_text(encoding="utf-8")
    assert "![Level 1](images/stats-tower-2-level-1.png)" in text
    for name in images:
        assert (tmp_path / "images" / name).exists()


def test_a_directory_in_place_of_an_image_is_stale(tmp_path, images):
    gen_stats.write_images(tmp_path, images)
    name = sorted(images)[0]
    (tmp_path / gen_stats.IMAGES_DIR / name).unlink()
    (tmp_path / gen_stats.IMAGES_DIR / name).mkdir()
    assert gen_stats.stale_images(tmp_path, images) == [f"images/{name}"]


def test_text_pages_do_not_decode_any_png(monkeypatch):
    import pygame

    def no_load(*args, **kwargs):
        raise AssertionError("a PNG was decoded")

    monkeypatch.setattr(pygame.image, "load", no_load)
    config = gen_stats.load_config()
    gen_stats.pages(config=config)
    gen_stats.wiki_pages(config)
