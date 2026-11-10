# Store page (itch.io)

The itch.io page at <https://umutcanekinci.itch.io/chokepoint> is edited by hand on itch.io. This
folder holds what goes into it:

- `description.html`: the page's description. Paste it into the description field in HTML
  mode. It uses only headings, paragraphs, lists, links, `strong`, `code` and one image, with no inline
  styles or tables, so it reads well on phones.

The release workflow uploads the builds with Butler; it never touches the page text.

## Checklist for the edit page

Fields that live outside the description, following itch.io's
[quality guidelines](https://itch.io/docs/creators/quality-guidelines):

- **Short description or tagline:** "Hold the line through 25 rounds of tower defense, then go
  endless."
- **Classification:** Games. **Kind of project:** Downloadable. **Release status:** In
  development until 1.0, then Released.
- **Platforms:** Windows, macOS, Linux (only the ones the release builds are tested on).
- **Genre:** Strategy.
- **Tags:** only relevant ones, preferring itch.io's suggestions: Tower Defense, 2D, Top-Down,
  Singleplayer, Endless, Open Source, Pygame. Don't tag the game's own name.
- **Languages:** English, Turkish (the two the game ships).
- **Inputs:** Mouse, Keyboard.
- **AI disclosure:** answer it on the edit page to match the description's line (Claude Code
  was a coding assistant; check what itch.io's form asks about code, graphics, sound and text).
- **Screenshots:** at least 4, uploaded to the page's gallery in this order (all in
  `docs/screenshots/`, 1920x1080): `02_gameplay.png`, `08_placing_tower.png`,
  `11_tank_fight.png`, `12_plane_bombing.png`, `03_upgrades.png` and `01_menu.png`. Optional
  extras: `14_turkish.png` (the Turkish UI), `15_victory.png`, `17_hud_hidden.png` (a clean
  battlefield) and `plane-run.gif` (`docs/`, a bombing run). itch.io shows them apart from the
  description, so the description only embeds the preview GIF. `scripts/capture_readme.py` retakes
  them all.
- **Images:** `description.html` links the GIF from GitHub so it works when pasted as is. Better:
  upload `docs/preview.gif` through itch.io's editor and swap the image on the page for the
  uploaded one, so it loads fast and doesn't break if the file moves in the repo.
- **Theme:** colors that match the game (its green, and the logo's yellow and orange), not plain black on white.
- **Cover:** `docs/store/cover.png` (630×500, itch.io's cover size): the bomb run on the upper road,
  chosen by the owner; upload it through the edit page. How it was made: `scripts/capture_readme.py
  --covers <folder>` (see the [store media devlog entry](../devlog/2026-11-09-store-media.md)).
- **Trailer:** none for 1.0 (the GIF only). Tracked in #13.

When the game changes in a way players see (controls, features, towers), update
`description.html` in the same PR and paste it again.
