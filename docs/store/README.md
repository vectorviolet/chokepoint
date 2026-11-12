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
- **Theme:** colors that match the game's green, not plain black on white; the values set in the
  theme editor are in [Theme settings](#theme-settings) below.
- **GitHub social preview:** `docs/design/social-preview.png` (1280x640, GitHub's 2:1), built by
  `scripts/make_social_preview.py` from the HUD-hidden screenshot and the logo. It is a stopgap:
  remake it from the store banner art when #174 delivers it. Upload it by hand in the repository's
  Settings > Social preview (GitHub has no API for it).
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
| Uploads | `chokepoint-windows.zip`, `chokepoint-linux.zip`, `chokepoint-osx.zip`. The release workflow's butler jobs push the unpacked builds to the `windows`, `linux` and `osx` channels and itch.io names the files after the channels (the GitHub release zips are `chokepoint-windows.zip`, `chokepoint-linux.zip` and `chokepoint-macos.zip`). Tick the matching platform on each file's "Executable for" boxes (Windows, Linux, macOS) |
| Description | paste `docs/store/description.html` in HTML mode |
| Genre | Strategy, Survival (as on the live page) |
| Tags (max 10; not the genre or platforms; the live page has these 7) | 2D, Endless, Military, Open Source, Singleplayer, Top-Down, Tower Defense |
| AI generation disclosure | **Yes.** Ticked: **Code** (Claude Code as a coding assistant) and **Text** (the store text, README and Turkish strings were drafted with Claude and reviewed by the owner). **Graphics is not ticked**: the art is Kenney's and La Red Games' packs and the logo was made by the owner in Canva. Not Sounds: Kenney's packs and Sakura Girl's music. |
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

## Theme settings

Set in the theme editor of the live page ("Edit theme"), as the owner has them now:

| Group | Setting | Value |
|---|---|---|
| Color | BG | `#45d93c` (bright green) |
| Color | BG 2 | `#265c2e` (dark green) |
| Color | Text | `#ffffff` |
| Color | Link | `#fa5c5c` (red) |
| Text | Font | Anonymous Pro |
| Text | Size | Large |
| Layout | Screenshots | Auto (sidebar) |
| Images | Banner | none yet (#174), align Center |
| Images | Background | repeat Both, align Right, Fixed (the page shows a Fixed option; whether it is ticked is not recorded here) |

Contrast (WCAG ratio, 4.5 is the readable minimum for body text): white text is fine on BG 2 (7.9) but
weak on the bright BG (1.9); the red link `#fa5c5c` is weak on both (2.5 on BG 2, 1.7 on BG). Which
areas of the page use BG and which BG 2 depends on the layout, so check the live page. If text sits
on the bright green, use dark text such as `#0B2E12` (8.0 on BG) or move it onto BG 2; a link
color of `#FFE278` (the logo's yellow, 6.2 on BG 2) reads well on the dark green.

When the game changes in a way players see (controls, features, towers), update
`description.html` in the same PR and paste it again.
