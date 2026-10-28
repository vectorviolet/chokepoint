"""The index tables in docs/devlog/README.md and docs/decisions/README.md are
exactly what scripts/gen_devlog_index.py builds from the entry files, and every
entry carries the metadata the script needs."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "gen_devlog_index", ROOT / "scripts" / "gen_devlog_index.py"
)
gen_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_index)


def test_every_entry_has_its_index_metadata():
    devlog = [p.name for p in gen_index.DEVLOG.glob("2*.md")]
    adrs = [p.name for p in gen_index.DECISIONS.glob("0*.md")]
    assert devlog and adrs
    assert len(gen_index.devlog_entries()) == len(devlog)
    assert len(gen_index.adr_entries()) == len(adrs)


@pytest.mark.parametrize("readme, table", gen_index.targets())
def test_readme_index_is_generated_from_the_entries(readme, table):
    text = readme.read_text(encoding="utf-8")
    assert gen_index.updated_readme(text, table) == text, (
        f"{readme.relative_to(ROOT).as_posix()} is out of date: "
        "run scripts/gen_devlog_index.py"
    )


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_devlog_entry_reads_title_area_and_date(tmp_path):
    _write(
        tmp_path / "2026-01-02-b.md",
        "# Second\n<!-- index | refs: #2 -->\n\n**Date:** x · **Area:** UI, bug · **Issue:** #2\n",
    )
    _write(
        tmp_path / "2026-01-02-a.md",
        "# First\n<!-- index | refs: #1, PR #3 | area: Audio | title: Override -->\n",
    )
    _write(
        tmp_path / "2026-01-01-z.md",
        "# Zed\n<!-- index | refs: #9 -->\n**Area:** Tooling\n",
    )
    _write(tmp_path / "README.md", "# Not an entry\n")
    table = gen_index.render_devlog(gen_index.devlog_entries(tmp_path))
    assert table.splitlines()[2:] == [
        "| 2026-01-01 | [Zed](2026-01-01-z.md) | Tooling | #9 |",
        "| 2026-01-02 | [Override](2026-01-02-a.md) | Audio | #1, PR #3 |",
        "| 2026-01-02 | [Second](2026-01-02-b.md) | UI, bug | #2 |",
    ]


def test_adr_reads_number_title_status_and_date(tmp_path):
    _write(
        tmp_path / "0002-b.md",
        "# 0002. Two\n<!-- index | refs: #5 -->\n\n- **Status:** Accepted (see PR #6)\n"
        "- **Date:** 2026-02-03\n",
    )
    _write(
        tmp_path / "0001-a.md",
        "# 0001. One\n<!-- index | refs: #4 | status: Superseded by 0002 -->\n\n"
        "- **Status:** Accepted\n- **Date:** 2026-02-01\n",
    )
    table = gen_index.render_adrs(gen_index.adr_entries(tmp_path))
    assert table.splitlines()[2:] == [
        "| [0001](0001-a.md) | One | Superseded by 0002 | 2026-02-01 | #4 |",
        "| [0002](0002-b.md) | Two | Accepted | 2026-02-03 | #5 |",
    ]


def test_missing_metadata_names_the_file(tmp_path):
    _write(tmp_path / "2026-01-01-new.md", "# New\n\n**Area:** UI\n")
    with pytest.raises(gen_index.EntryError, match="2026-01-01-new.md"):
        gen_index.devlog_entries(tmp_path)


def test_updated_readme_replaces_only_between_markers():
    text = f"intro\n{gen_index.BEGIN}\nold\n{gen_index.END}\noutro\n"
    assert gen_index.updated_readme(text, "new") == (
        f"intro\n{gen_index.BEGIN}\nnew\n{gen_index.END}\noutro\n"
    )
