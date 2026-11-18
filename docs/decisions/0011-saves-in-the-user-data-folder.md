# 0011. Saves in the user-data folder (packaged build only)
<!-- index | refs: #176, PR #197 -->

- **Status:** Accepted
- **Date:** 2026-11-17
- **Issues / PRs:** [#176](https://github.com/vectorviolet/chokepoint/issues/176)

## Context

The game kept `saves/` relative to the working directory. For a downloaded build that means next to
`chokepoint.exe`: an installer into `Program Files` can't write there without admin rights, an
uninstall or an update would delete the saves with the folder, and a portable zip moved to another
folder loses them. Other things rely on that cwd-relative default today: every worktree has its own
`saves/` (the play-test save, the saves-isolation rules in CLAUDE.md), the tests redirect
`SaveStore`'s default folder, and the browser build's `localStorage` key is
`pygamine:saves/<name>.json`.

## Decision

- **The packaged build** (`sys._MEIPASS` is set, as `resource_root()` tests; PyInstaller) saves to `user_data_dir("chokepoint") / "saves"`
  (pygamine): `%APPDATA%\VectorViolet\chokepoint\saves`, `~/Library/Application Support/VectorViolet/chokepoint/saves`,
  or `$XDG_DATA_HOME` (default `~/.local/share`)`/VectorViolet/chokepoint/saves`.
- **Running from source and the browser build** keep `SaveStore`'s own default, the cwd-relative
  `saves/`. pygbag isn't frozen, so the `localStorage` keys don't change (a test checks the key).
- One helper decides, `util.paths.packaged_saves_dir()` (`None` means "use the default"), and
  `Game._make_store` is the only place that builds the two stores.
- **No migration** of old saves next to the executable (the owner's decision): the game is young,
  and a copy step has its own failure cases.

## Rejected alternatives

- **User-data folder everywhere.** Breaks worktree save isolation and the play-test save, and the
  tests' redirect, for no gain to players who run from source.
- **A `--portable` or marker-file mode.** Not needed yet; the zip build keeps working as before
  with its saves in the user-data folder too.
- **Migrating old saves.** Dropped by the owner.

## Consequences

An uninstall or update never touches saves, and they stay after an uninstall. Before this change
the packaged game wrote its saves into its own bundle folder (the game chdirs into
`sys._MEIPASS`, which for PyInstaller 6 is `chokepoint\_internal` on Windows and inside the app
bundle on macOS), so old saves are in `_internal\saves`. They are not moved; a player can copy
`save.json` and `settings.json` into the new folder by hand. The installer deletes `_internal` on
an update, so installing over an old unzipped folder drops them.
