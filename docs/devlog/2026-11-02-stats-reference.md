# Generated stats reference and wiki mirror
<!-- index | refs: #82, PR #86 -->

**Date:** 2026-11-02 · **Area:** Docs, tooling · **Issue:** [#82](https://github.com/vectorviolet/chokepoint/issues/82) · **PR:** [#86](https://github.com/vectorviolet/chokepoint/pull/86) (open when this entry was written)

## Context

Players and the owner wanted an advanced stats reference: the enemies of every wave, enemy stats
as they grow wave by wave, and tower stats per level. The numbers live in `config/towers.yaml`,
`config/enemies.yaml` and `config/waves.yaml` and change with every balance pass, so a hand-kept
reference would soon be wrong. Issue #82 (owner request, 2026-11-02).

## Options

- **Generated docs plus a wiki mirror**: a script writes Markdown pages into `docs/stats/` from the
  config, CI fails when they are stale, and a workflow copies them to the GitHub wiki.
- **Wiki only**: pages written and kept in the wiki by hand.
- **Docs only**: generated pages in the repository, no wiki.

No screenshots: these are text pages; the result section describes them.

## Decision

Generated docs plus a wiki mirror (owner, 2026-11-02, in the issue).

How it is built:

- `scripts/gen_stats.py` reads the config through `util.config_loader` and takes the per-wave
  numbers from the game's own code rather than a copy of its formulas: enemy HP and kill money from
  `Enemy._calculate_stats`, the endless waves after wave 30 from `WaveManager._wave_for`, the win
  wave, sell refund and bomb interval from their constants, the starting money and lives from
  `config/settings.yaml`. Enemy names are the README's roles (the config only has them as comments).
- `--check` exits 1 when a page differs or `docs/stats/` holds a page no longer generated; `tests/test_stats_docs.py` runs it in CI, like
  `scripts/gen_devlog_index.py`. The test also checks that the scaling rule written on the enemies
  page matches the code for waves 1 to 60.
- `.github/workflows/wiki.yml` runs on a push to `main` that changes `docs/stats/` or
  `scripts/gen_stats.py`, and by hand from `main` only. It writes the pages as `Stats`,
  `Stats-Towers`, `Stats-Enemies` and `Stats-Waves` (`--wiki` renames them and rewrites their
  links), deletes `Stats*` pages that are no longer generated, and leaves every other wiki page
  alone, `Home` included. It never runs on pull requests or merge-queue groups, so it isn't a
  required check. It pushes with
  `GITHUB_TOKEN` (`contents: write`) and uses no third-party action beyond the ones CI already uses.

What the owner has to do once: enable the wiki (Settings > General > Features > Wikis), create its
first page in the web UI (a GitHub wiki has no git repository until then), and run the **Wiki**
workflow by hand once (Actions > Wiki > Run workflow). Until the wiki exists the job ends with a
"Wiki not set up" warning instead of failing; any other error reaching the wiki fails it.

## Rejected alternatives

- Wiki only: hand-kept pages drift from the config with every balance change.
- Docs only: pages inside the repository are less discoverable for players than the wiki.

## Result

`docs/stats/` holds four pages:

- `README.md`: the index, starting money and lives, the win wave, the sell refund and the units
  (px, tiles of 64 px, ms, 165 ticks per second, px/tick and px/s).
- `towers.md`: per level of each ground tower its cost, total spent, sell refund, range and blind
  spot (px and tiles), damage, reload, shots per second, DPS, DPS per $ and HP; for the plane its
  price, the UPG PLANES cost, splash radius, damage per bomb, speed, bombs per second and the
  distance between bombs.
- `enemies.md`: base stats, the tanks' guns, and HP / kill money of every enemy type for waves 1
  to 40.
- `waves.md`: every wave from 1 to 40 (31 to 40 generated, endless mode) with its enemies, count,
  spawn interval, total HP, kill money, lives at stake and the money a player would have if every
  enemy so far were killed.

No balance number changed.
