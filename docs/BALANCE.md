# Balance: simulated runs

Measurements for issue #70, taken with `scripts/balance_sim.py`, so balance changes (#10, the
owner's call) can be judged by data first and then confirmed by a few playtests. **No balance
number changed for this document.** The full per-wave tables are in
[`docs/balance/report.md`](balance/report.md), with one CSV per strategy next to it.

## How to run it

From the repo root:

```bash
uv run python scripts/balance_sim.py                                   # all six strategies, 40 waves
uv run python scripts/balance_sim.py --strategy gun_cannon --waves 10  # one strategy, a short run
```

Options: `--strategy` (one of the six below; default all), `--waves` (40), `--seed` (70),
`--game-speed` (4, the game's x4; 1 or 2 also work) and `--out` (`docs/balance`, overwritten).
The default run takes about **8 minutes** on the machine below (gun_spam 144 s, gun_cannon 133 s,
mixed 106 s, missile 86 s, plane_spam 20 s, minimal 4 s): late waves with hundreds of towers are
the slow part. `tests/test_balance_sim.py` runs 3 waves of one strategy in CI.

Like the smoke test, the script sends every save to a temporary folder and fails if the real
`saves/` changed (a lost run deletes its save, as in the real game).

## Method

- **The real game.** Each strategy plays a fresh run in a real `Game()`: the game's own waves,
  enemy stats and scaling, targeting, tank fire, money, lives and game over. Nothing is drawn; the
  fixed tick (`_tick()`) runs as fast as the CPU allows. The game speed is x4 by default, as a
  player who fast-forwards would play; a plane_spam run at x1 gave the same result (died in wave
  29; plane ROI 0.08 at both speeds).
- **Start:** 200 money, 10 lives (`config/settings.yaml`). The victory popup after wave 25 is
  answered with Continue. A run ends after `--waves` waves or when lives reach 0.
- **Bots** (`scripts/balance_bots.py`) look at their money every 0.5 s of game time. Each is an
  opener, then a cycle of steps, played strictly in order: a bot waits (saves up) when it can't
  afford the next step. Purchases go through the game's rules: placement through
  `TowerPlacementController` (only free build tiles, only with the money), upgrades through the
  tower's own upgrade button, UPG PLANES as the HUD does it.
- **Where to build:** each tower goes on the free build tile that covers the most path within its
  range (outside the cannon's blind spot). "Front" tiles are those right beside the path (tile
  centre 0.5 to 1.6 tiles from it), "back" the row behind (1.6 to 3 tiles); when a ring is full,
  any free tile. Destroyed towers free their tile, so the bot rebuilds there.
- **Planes** are placed at the left end of the path's longest horizontal straight (y = 576, x 1408
  to 2624, near the entrance) and fly right along it, against the walking enemies. A plane is
  launched only while an enemy is on that straight.
- **Seed:** the game has no randomness, so results are deterministic; the seed only breaks ties
  between equally good build tiles. Same seed and options, same files byte for byte (tested).
- **Damage** is enemy HP taken, overkill not counted, credited to the tower whose shot or bomb hit
  (`BaseTower.damage_dealt`, a statistics counter added for this). **Kill money** goes to the
  tower that dealt the killing blow (the existing `money_earned`, as shown in the info panel).
  **ROI** is a tower type's kill money divided by everything spent on that type (purchases,
  rebuilds and upgrades; UPG PLANES counts for planes).

### The strategies

| strategy | plan |
|---|---|
| gun_spam | Rapid guns only, on the best tiles on both sides of the path. |
| gun_cannon | 6 guns, then repeat: gun, gun, heavy cannon in the back row, upgrade a cannon. |
| missile | 6 guns, then repeat: missile, upgrade it to level 2, then to level 3. |
| plane_spam | The gun_cannon build up to wave 19; from wave 20 only planes (UPG PLANES after the 5th). |
| mixed | 6 guns, then repeat: gun, missile, cannon (back), upgrade missile, upgrade cannon, upgrade missile, gun; from wave 20 also a plane each cycle, if enemies are on the straight. |
| minimal | Guns only, bought only from a lost life until a wave passes without one. |

The 6-gun opener is there because the early waves pay very little (wave 1: 24 money) and guns are
the cheapest damage: a first version that opened with missiles or saved for a cannon or plane at
once lost all 10 lives by wave 6 to 9. These are simple, readable plans, not optimal play; a plan
that loses may only mean the plan is poor.

## Machine

| | |
|---|---|
| CPU | 13th Gen Intel Core i7-13620H |
| RAM | 24 GB |
| OS | Windows 11 Education 10.0.26200 |
| Python | CPython 3.13.14 |
| pygame-ce | 2.5.7 (SDL 2.32.10), `SDL_VIDEODRIVER=dummy` |
| Commit | `origin/main` at 6e6463a plus this branch |
| Options | `--waves 40 --seed 70 --game-speed 4` |

## Results (2026-10-29)

| strategy | result | lives left | lives lost 1-10 | lost 11-25 | lost 26+ | spent | earned | money left | towers lost | ROI gun | ROI missile | ROI cannon | ROI plane |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gun_spam | died in wave 32 | 0 | 4 | 0 | 6 | 85100 | 135068 | 50168 | 409 | 1.59 |  |  |  |
| gun_cannon | cleared 40 of 40 | 6 | 4 | 0 | 0 | 492120 | 514954 | 23034 | 579 | 0.6 |  | 1.13 |  |
| missile | cleared 40 of 40 | 3 | 7 | 0 | 0 | 510460 | 514711 | 4451 | 148 | 2.71 | 1.01 |  |  |
| plane_spam | died in wave 29 | 0 | 4 | 0 | 6 | 66460 | 69564 | 3304 | 42 | 4.36 |  | 4.25 | 0.08 |
| mixed | cleared 40 of 40 | 6 | 4 | 0 | 0 | 510400 | 514954 | 4754 | 341 | 0.58 | 1.49 | 0.92 | 0.09 |
| minimal | died in wave 12 | 0 | 9 | 1 | 0 | 1700 | 3052 | 1552 | 0 | 1.8 |  |  |  |

Every run that kills everything earns the same total (514,954 by wave 40), since all income is
kill money.

## The four observations

### 1. Waves 1 to 10 almost always cost a few lives: confirmed

Every strategy loses lives early, and only there: 4 lives in waves 4 to 6 for gun_spam,
gun_cannon, plane_spam and mixed (the six-gun start is the same), 7 for missile (3 more in wave
10), 9 for minimal. Even gun_spam, which spends every coin on the cheapest damage the moment it
has it, leaks in waves 4, 5 and 6 (the first fast runners and the denser wave 6).

The cause is money: waves 1 to 10 pay 1,921 in all (wave 1: 24, wave 5: 84), so by wave 4 a
player has about 4 guns and can't buy a fifth in time. Minimal shows the floor: buying only after
a leak, it loses lives in waves 4, 5, 6, 7 and 9, is down to 1 life by wave 10 and dies in wave
12 with 17 guns.

### 2. Waves 10 to 25 are trivial: confirmed

From wave 11 to 25 no strategy that buys normally loses a single life (0 for gun_spam,
gun_cannon, missile, plane_spam and mixed). The income grows from about 700 to 6,400 a wave, and
every build turns it straight into more towers. The guns-plus-cannons build the owner described
(gun_cannon) clears waves 11 to 25 with cannons doing 69% of the damage and guns 31%. Even
minimal, which buys nothing after wave 9 unless it leaks, holds waves 10 and 11 with 17 guns.

### 3. From wave 25, tanks wear down the tower lines: confirmed in part

Tanks (wave 25 on; their HP is 5,600 to 16,000 by then) destroy towers every wave, and more each
wave: gun_cannon loses 7 towers in wave 27, 42 in wave 30 and 35 to 63 a wave from wave 32 on;
mixed 13 in wave 30 and 36 to 48 a wave from wave 36. Guns alone can't answer them: tanks
outrange them (tank range 280 and 320, gun 160), so gun_spam loses 13 to 135 guns a wave from
wave 27 and dies in wave 32 with **50,168 money unspent**, because the map is full (442 tiles).
Planes alone (plane_spam) die in wave 29.

But the builds with cannons or missiles hold to wave 40 without losing a life: they rebuild what
the tanks destroy and spend almost all their income doing it (gun_cannon spends 454,640 in
waves 26 to 40 and ends with 657 towers). So in these runs the late game is an economy drain
rather than a wall that can't be held. Caveat: the bots rebuild within half a second of game
time, on the best tiles, at x4, every time; a player can't, so the pressure in a real run is
higher than here.

### 4. Planes pay for themselves: refuted in these runs

Planes earned 8% (plane_spam) and 9% (mixed) of what was spent on them: plane_spam spent 51,200
on planes and UPG PLANES for 4,308 of kill money; mixed 79,200 for 7,427. They do land damage
(19% of all damage in plane_spam's waves 26 to 29, 3% in mixed's late waves), but a bomb does 100
or 200 damage against enemies with hundreds to thousands of HP, so the towers further down the
path take the killing blow and the money. Planes alone don't hold: plane_spam switched to planes
at wave 20 and died in wave 29, while every ground build with cannons or missiles cleared 40.

Caveat: the bot launches planes at one place (the longest straight) whenever enemies are on it.
A player who times planes on dense groups, or whose towers are weaker so bombs land the last hit
more often, may see more money per plane. The info panel's money earned for a plane shows this
in a playtest.

## Reading the per-wave tables

`docs/balance/report.md` and the CSVs have one row per wave: lives at the end and lost in the
wave, money at the end, earned and spent in the wave, enemies killed and escaped, ground towers
standing and destroyed, damage dealt by each tower type, and each type's ROI so far. The CSVs
add the kill money per type per wave, the totals spent and earned per type and each wave's game
time (`wave_s`).
