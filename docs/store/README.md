# Store page (itch.io)

The itch.io page at <https://umutcanekinci.itch.io/chokepoint> is edited by hand on itch.io. This
folder holds what goes into it:

- `description.html`: the page's description. Paste it into the description field in HTML
  mode. It uses only headings, paragraphs, lists, links, `code` and one image, with no inline
  styles or tables, so it reads well on phones.
- `cover.png`, `cover_itchio.png`: the cover image (itch.io shows covers at 630×500).

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
- **Screenshots:** at least 4, uploaded to the page's gallery (`docs/screenshots/` has them).
  itch.io shows them apart from the description, so the description only embeds the GIF.
- **Images:** upload the GIF through itch.io's editor instead of linking it from GitHub, so it
  loads fast and doesn't break if the file moves.
- **Theme:** colors that match the game (the logo's green), not plain black on white.

The cover, a trailer and new screenshots are tracked in #13.

When the game changes in a way players see (controls, features, towers), update
`description.html` in the same PR and paste it again.
