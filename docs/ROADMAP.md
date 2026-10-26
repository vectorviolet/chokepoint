# Roadmap

Sizes are rough: [S] small, [M] medium, [L] large. [x] marks a finished item.

## 1.0: feel, clarity, balance

### Feedback (feel)
- [M] Kill reward feedback: floating "+$N" text above the enemy and a few coins flying to the money counter
- [S] Life lost: sound + short red vignette pulse at the screen edges
- [S] Tower placed / sold: sound + small effect (dust, coins)
- [S] Plane bomb impact: explosion effect + sound where each bomb lands

### Information (ui)
- [M] Tower info panel on click: kills, money earned, range, damage, fire rate, HP (bar + number), and how each stat changes on upgrade ("Damage 40 → 70")
- [S] Tooltips on the buy buttons: one-line strength and weakness per tower
- [S] Enemy info on click: HP as numbers ("320 / 420")

### Interface (ui)
- [M] Pause panel with music and SFX controls; remove the in-game music toggle (keep it on the main menu)
- [S] Continuous placement while Shift is held
- [x] Tab hides the whole HUD; counters reappear briefly on change (done, 1bc4c4f)

### Balance and content
- [M] Balance: fix the early difficulty spike (waves 5–9) and rework wave composition for waves 10–25 (see the readiness report), validated by playtesting
- [S] Heavy cannon inner range: can't hit enemies too close to it

### Technical (perf)
- [S] Spike test: measure FPS with hundreds of enemies and towers; add object pooling only if the measurements show a problem

### Store (store)
- [M] New cover image, screenshots and gameplay GIF with the new effects; refresh the itch.io page

## 1.1+: depth and content

- [L] Progression: start with few tower types and a small level cap; unlock towers or abilities at wave milestones
- [M] Abilities: limited-use skills such as mines on the path, a temporary buff to all towers, moving a tower for a fee
- [M] Plane route: choose the bombing run's direction (mouse wheel) when launching
- [L] New maps, including multiple spawn and exit points
- [L] Procedural map generator
- [M] Enemy types only some towers can hit
- [S] Clear obstacles on the map for money to unlock build tiles
- [M] Small timed events during waves to keep the player active
- [S] Multiple save slots (settings and the run are already separate files)
