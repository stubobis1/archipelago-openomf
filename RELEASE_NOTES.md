# One Must Fall: 2097 — Archipelago World v0.0.01

Initial release of the OpenOMF Archipelago integration. Requires the AP-patched [OpenOMF](https://github.com/stubobis1/openomf) client and original OMF:2097 game data.

---

## What is this?

One Must Fall: 2097 is a 1994 robot fighting game. You pilot a Human Assisted Robot (HAR) through a series of tournaments, earning prize money to upgrade your machine and advance to harder competitions.

This Archipelago world randomizes which HARs you can use and where HAR/pilot upgrades come from. Instead of buying everything freely in the Mechlab, upgrades arrive as items — either from your own checks or sent to you by other players in a multiworld.

---

## How to play

1. Connect to your Archipelago server from the OpenOMF main menu (**Archipelago** option).
2. You receive your starting HAR immediately on connect.
3. Fight through tournaments. Each match win and each tournament clear sends a check to the AP server.
4. Items you receive (HAR unlocks, stat upgrades, money bundles) are applied automatically. Stat upgrades take effect at the start of your next match.
5. Win your goal tournament to complete the seed.

### Tournaments

The four tournaments unlock in order as you collect **Progressive Tournament Access** items:

| Tournament | Access Required |
|---|---|
| North American Open | 0 (always available) |
| Katushai Challenge | 1 |
| WAR Invitational | 2 |
| World Championship | 3 |

Registration fees still apply — you need money in hand to enter each tournament. Earn it by winning matches and collecting money bundles from the item pool.

### Mechlab and Training

Purchases in the Mechlab and training sessions also count as checks. You still pay money when you upgrade, but the actual stat boost comes from the AP server — you might pay for a HAR upgrade and receive a pilot stat instead (or a money bundle for another player). Higher upgrade tiers require tournament access to unlock, matching the tournament progression.

---

## How randomization works

### Items

| Item | Quantity | Effect |
|---|---|---|
| HAR Unlock | 11 (1 per HAR) | Lets you pilot that HAR; starting HAR is pre-granted |
| Progressive Tournament Access | 3 | Each unlocks the next tournament in order |
| Progressive [HAR] [Stat] | up to 9× per stat per HAR | Raises that HAR's ARM Power / LEG Power / ARM Speed / LEG Speed / Armor / Stun Resist by 1 |
| Progressive [HAR] Enhancement | 1–3× per HAR | Applies the next enhancement upgrade for that HAR |
| Progressive Power / Agility / Endurance | up to 25× per stat | Raises your pilot stat by 1 |
| Ability to change HAR color | 1 | Unlocks color customization in the Mechlab |
| Money (Small) / Money (Large) | filler | Credits deposited directly to your account |

HAR Unlocks and Tournament Access are **progression** items — the AP server guarantees they appear where they are reachable. Stat upgrades are **useful** but not required for logic. Money bundles are **filler**.

### Locations (checks)

| Check type | How to clear |
|---|---|
| `[Tournament] - Beat [Pilot]` | Win that match in tournament mode |
| `Win [Tournament] (1/2/3)` | Win the full tournament (3 checks per tournament) |
| `Buy [HAR] [Stat] Upgrade [N]` | Purchase that upgrade in the Mechlab |
| `Train [Stat] Level [N]` | Purchase that training level |

Restricted pilots (difficulty-gated secret opponents) are excluded from the check pool.

---

## YAML options

```yaml
game: One Must Fall: 2097

One Must Fall: 2097:
  goal_tournament: world_championship     # north_american_open | katushai_challenge | war_invitational | world_championship | all_tournaments
  starting_har: random_selection          # jaguar | shadow | thorn | pyros | electra | katana | shredder | flail | gargoyle | chronos | nova | random_selection
  har_stat_max: 9                         # 1–20 (vanilla = 9); sets how many upgrade levels exist per HAR stat
  pilot_stat_max: 25                      # 1–50 (vanilla = 25); sets how many training levels exist per pilot stat
  buy_cost_factor: 100                    # 10–1000; 100 = vanilla prices, 200 = 2× per tier
  money_small_value: 3000                 # base credits for a Money (Small) item
  money_large_value: 15000               # base credits for a Money (Large) item
```

Money values are multiplied in-game by a per-tournament prize modifier (1× NAO / 2× Katushai / 3× WAR / 6× World Championship).

---

## Known limitations (v0.0.01)

- Difficulty-gated secret pilots are not included in the check pool.
- No deathlink support yet.
- No traps

---

## Setup

See [setup_en.md](archipelago/worlds/openomf/docs/setup_en.md) for installation and connection instructions.

Issues: https://github.com/stubobis1/archipelago-openomf/issues
