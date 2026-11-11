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
- **Classification:** Games. **Kind of project:** Downloadable. **Release status:**
  Released (1.0.0 is out).
- **Platforms:** Windows, macOS, Linux (only the ones the release builds are tested on).
- **Genre:** Strategy.
- **Tags:** see [Field values](#field-values) below.
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

## Field values

What to set on the edit page, field by field (the owner edits the page by hand; copy from here).
Pricing, visibility and the other owner choices follow Highrise's page unless the page already says
otherwise.

| Field | Value |
|---|---|
| Title / project URL | Chokepoint / `chokepoint` |
| Short description or tagline | Hold the line through 25 rounds of tower defense, then go endless. |
| Classification / kind / release status | Games / Downloadable / Released |
| Pricing | the owner's choice (Highrise uses $0 or donate, suggested $2.00) |
| Uploads | `chokepoint-windows.zip`, `chokepoint-linux.zip`, `chokepoint-osx.zip` (uploaded by the release workflow's butler jobs). Tick the matching platform on each file's "Executable for" boxes (Windows, Linux, macOS) |
| Description | paste `docs/store/description.html` in HTML mode |
| Genre | Strategy |
| Tags (max 10; not the genre or platforms, so drop "strategy") | Tower Defense, 2D, Top-Down, Singleplayer, Endless, Survival, Military, Open Source |
| AI generation disclosure | **Yes.** Kinds: **Code** (Claude Code as a coding assistant) and **Text & Dialog** (the store text, README and Turkish strings were drafted with Claude and reviewed by the owner). Not Graphics: the art is Kenney's and La Red Games' packs and the logo was made by the owner in Canva (check that this is still true before submitting). Not Sounds: Kenney's packs and Sakura Girl's music. |
| Statement of AI usage (shown publicly) | Built with Claude Code as a coding assistant; game design, art direction, playtesting and review by the developer. |
| App store links | none |
| Custom noun | leave blank |
| Download and install instructions | see the block below |
| Community | Comments suggested on, discussion board off (the owner decides) |
| Visibility and access | Public once the page is ready |
| Cover image | `docs/store/cover.png` (630x500) |
| Banner | not made yet, tracked in #174 (the approach in Highrise's `scripts/make_cover.py` can be reused) |
| Gameplay video or trailer | none yet, tracked in #174 |
| Screenshots (3 to 5) | in the order listed in the Screenshots item above |

**Download and install instructions** (paste into the field):

```
Download the zip for your system, unzip it and run the game. No Python or installer needed.

Windows: run chokepoint.exe. The game isn't code-signed, so the first launch may show "Windows protected your PC": click More info, then Run anyway.
macOS: open Chokepoint.app. The app isn't signed, so macOS blocks the first launch: open System Settings > Privacy & Security, click Open Anyway next to Chokepoint, then Open.
Linux: run ./chokepoint/chokepoint from the unzipped folder.

Your run is saved automatically; press CONTINUE to resume it.
```

When the game changes in a way players see (controls, features, towers), update
`description.html` in the same PR and paste it again.
