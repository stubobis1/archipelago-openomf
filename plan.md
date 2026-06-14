# Archipelago × OpenOMF Integration Plan

## Distribution Model

**This is a fork of OpenOMF**, not a mod. The AP integration requires behavioral changes
(new UI scenes, event hooks, websocket I/O, HAR unlock logic) that are outside the scope
of the OpenOMF mod system, which is limited to asset and stat replacement via zip files.

The `omf/` submodule tracks upstream OpenOMF. AP-specific changes live on a fork branch
and are maintained as a delta against upstream. Upstream gameplay (1P vs-AI, 2P local,
offline tournament) is preserved on the fork — AP mode is an additional path, not a replacement.

---

## Overview

Two-part integration:
1. **Python world** (`archipelago/worlds/openomf/`) — server-side AP world definition
   → Detailed plan: [ap-world-plan.md](ap-world-plan.md)
2. **C client** (inside `omf/`) — OpenOMF fork connects to AP server via websocket, receives/sends checks
   → apclientpp wiring (submodules, CMake, C++/C boundary): [apclientpp-plan.md](apclientpp-plan.md)
   → OMF source modifications (menu, mechlab, arena, money): [omf-plan.md](omf-plan.md)

The C client uses **apclientpp** (header-only C++ lib) via a TyrianArchipelago-style `extern "C"` wrapper.
The rest of OpenOMF stays pure C. See [apclientpp-plan.md](apclientpp-plan.md) for submodules, build changes, and the C/C++ boundary pattern.

---

## Items

### HAR (Robot) Unlocks
- 11 HARs total: Jaguar, Shadow, Thorn, Pyros, Electra, Katana, Shredder, Flail, Gargoyle, Chronos, Nova
- Player **starts with one HAR** (YAML option: specific or random)
- Receiving a HAR unlock item adds it to mechlab — player can freely swap at any time
- 10 unlock items

### HAR Stat Upgrades (Progressive, Per-HAR)
Each stat upgrade is specific to a HAR — matches vanilla mechlab behavior where enhancements are tracked per-robot (`enhancements[11]` in `sd_pilot`). Receiving a HAR-specific upgrade only benefits that HAR; you can stockpile upgrades for HARs not yet unlocked.

Stats per HAR (6 stats × vanilla max 9 = 54 progressive items per HAR, 594 total across all 11 HARs):

| Item Name                          | Stat             | Vanilla Max | Extended Max (YAML) |
|------------------------------------|------------------|-------------|---------------------|
| Progressive \<HAR\> ARM Power      | `arm_power`      | 9           | configurable        |
| Progressive \<HAR\> LEG Power      | `leg_power`      | 9           | configurable        |
| Progressive \<HAR\> ARM Speed      | `arm_speed`      | 9           | configurable        |
| Progressive \<HAR\> LEG Speed      | `leg_speed`      | 9           | configurable        |
| Progressive \<HAR\> Armor          | `armor`          | 9           | configurable        |
| Progressive \<HAR\> Stun Resist    | `stun_resistance`| 9           | configurable        |

e.g., `"Progressive Jaguar ARM Power"`, `"Progressive Nova Armor"`, etc.

**Item pool size**: 11 HARs × 6 stats × 9 levels = **594 progressive items** at vanilla max.

> YAML option: `included_hars` — limit upgrade items to only unlockable HARs to shrink pool if desired.

### Pilot Stat Upgrades (Progressive)
| Item Name                    | Stat        | Vanilla Max | Extended Max (YAML) |
|------------------------------|-------------|-------------|---------------------|
| Progressive Power            | `power`     | 25          | configurable        |
| Progressive Agility          | `agility`   | 25          | configurable        |
| Progressive Endurance        | `endurance` | 25          | configurable        |

### Filler / Trap Items
- Money bundles (small/large)
- `Nothing` filler

---

## Locations

### Per-Match Checks
Each opponent defeated in a tournament = one check.
- Format: `"<Tournament Name> - Beat <Pilot Name>"` 
- e.g., `"World Championship - Beat Kreissack"`
- Number of checks = sum of all enemy_count across included tournaments

### Per-Tournament Checks
Winning a complete tournament = one check.
- Format: `"Win <Tournament Name>"`
- e.g., `"Win World Championship"`

### Buy Locations (Mechlab Purchase Checks)
In vanilla OMF, money buys HAR upgrades. Since upgrades come from AP items, the **act of purchasing** a slot at mechlab becomes a location check instead.
- Player still spends money (keeps economy loop alive)
- Receiving the upgrade comes from AP, not the purchase
- Purchases are **per-HAR** — matches the item structure
- Format: `"Buy <HAR> <Stat> Upgrade <N>"` (e.g., `"Buy Jaguar ARM Power Upgrade 3"`)
- Count per stat per HAR = vanilla max (or extended max, per YAML)
- Only available for currently **unlocked** HARs (can't buy upgrades for locked HARs)
  - These locations are locked behind unlocking that HAR
- These checks require sufficient money (enforced by Rules)
- Cost scales on top of vanilla: `ap_cost(n) = vanilla_cost(n) * buy_cost_factor^(n-1)`
  - vanilla_cost already scales via `upgrade_level_multiplier[level]` (1×, 3×, 7×, 12×, 18×, 30×, 50×, 75×, 120×)
  - factor 1.0 = vanilla costs unchanged; factor 2.0 = upgrade 2 costs 2× vanilla, upgrade 3 costs 4× vanilla, etc.
- Max buy locations at vanilla: 11 HARs × 6 stats × 9 slots = **594 locations**

---

## Options (YAML)

```yaml
game: One Must Fall: 2097

openomf_options:
  goal:
    # tournament: win a specific tournament
    # all_tournaments: win all tournaments
    type: tournament
    tournament_name: "WORLD CHAMPIONSHIP"  # or "random"

  starting_har:
    # specific HAR name or "random"
    value: "JAGUAR"

  har_stat_max:
    # max per HAR stat (vanilla = 9, extended = up to ~20)
    value: 9

  pilot_stat_max:
    # max per pilot stat (vanilla = 25, extended up to ~50)
    value: 25

  include_buy_locations:
    # whether mechlab purchases are location checks
    value: true

  buy_cost_factor:
    # per-level cost multiplier applied cumulatively on top of vanilla mechlab prices
    # ap_cost(n) = vanilla_cost(n) * buy_cost_factor^(n-1)
    # 1.0 = vanilla prices, 2.0 = each upgrade 2x vanilla for that level, max 10.0
    # range: 0.1 to 10.0 (stored as integer 10–1000 in YAML, divided by 100 at runtime)
    value: 1.0

  generate_tournaments:
    # generate randomized TRN files for the seed
    # (shuffle opponents across tournaments)
    value: false
```

---

## Goal

**Tournament Victory**: Player must win the configured goal tournament (all opponents in sequence).

**All Tournaments**: Player must win every tournament (sorted by registration fee = natural progression).

Completion sends `goal_complete` to AP server.

---

## Generated Tournaments (Optional Feature)

When `generate_tournaments: true`:
- AP world generates `.TRN` data by shuffling/rearranging pilot opponents across tournaments
- Saves generated TRN data in the slot data / output files
- OpenOMF loads the generated TRNs instead of vanilla files
- Enables true location randomization (opponent order is shuffled per seed)

This is a Phase 2 feature.

---

## Architecture

```
AP Server (Python)
    ↕ websocket (AP protocol)
OpenOMF (C)
  └── ap_client.c  — connects to server, sends checks, receives items
  └── ap_state.c   — tracks received items, applies to game_player
```

### Communication Flow
1. OpenOMF connects to AP server at startup (IP/port in settings)
2. On **opponent defeated**: send location check to server
3. On **tournament won**: send location check + check for goal
4. On **item received**: AP client queues item; game applies it (stat increment, HAR unlock)
5. Stats are applied to `sd_pilot` in `game_player` each time a match loads

### Item Application in C
- HAR stats: modify `pilot->arm_power`, `pilot->leg_power`, etc. (clamped or extended)
- Pilot stats: modify `pilot->power`, `pilot->agility`, `pilot->endurance`
- HAR unlocks: track unlocked set; mechlab only shows unlocked HARs

---

## Implementation Phases

### Phase 1 — Python World (AP server side)
Full task list: **[ap-world-plan.md](ap-world-plan.md)**

Summary:
- [ ] Scaffold `worlds/openomf/` — `__init__.py`, `Items.py`, `Locations.py`, `Options.py`, `Rules.py`, `Regions.py`
- [ ] Parse vanilla TRN files → `data/tournaments.py` (static data used at gen time)
- [ ] Implement item/location tables, regions, rules, completion condition
- [ ] Item/location balance: buy locations are the balancing valve — generate enough buy slots to cover any gap, filler for remainder
- [ ] Write required docs: `en_One Must Fall 2097.md`, `setup_en.md`

### Phase 2 — C Client (OpenOMF side)
Full task list: **[apclientpp-plan.md](apclientpp-plan.md)**

Summary:
- [ ] Add apclientpp + deps as git submodules under `omf/src/archipelago/submodule/`
- [ ] `apconnect.cpp` / `apconnect.h` — apclientpp wrapper with `extern "C"` boundary
- [ ] `apstate.h` — C structs for AP state (`ap_items_t`, `ap_stats_t`)
- [ ] Hook match-end → `Archipelago_SendCheck()`
- [ ] Hook mechlab purchase → `Archipelago_SendCheck()` for buy locations
- [ ] Apply `APItems` to `sd_pilot` at match load
- [ ] Filter mechlab HAR list to `APItems.har_unlocked` bitmask
- [ ] Connection UI (host/port/slot/password)
- [ ] CHR save: persist `locations_checked[]` + `last_applied_item_index`; rebuild idempotent state from replay
- [ ] CMakeLists: `enable_language(CXX)`, `omf_apclient` static lib target

### Phase 3 — Generated Tournaments
- [ ] Python: generate randomized TRN data, embed in slot data
- [ ] C: load generated TRN data from slot data at connect time

---

## Item/Location ID Range

Base ID: `2097000` (decimal prefix `2097`; no conflicts in current AP game list)

```
HAR Unlocks:             2097_0000 – 2097_000A  (11 items)
HAR Stat Progressives:   2097_0100 – 2097_02FF  (11 HARs × 6 stats; ~66 item types)
Pilot Stat Progressives: 2097_0300 – 2097_0302  (3 stats)
Match Locations:         2097_1000 – 2097_1FFF
Tournament Locations:    2097_2000 – 2097_20FF
Buy Locations:           2097_3000 – 2097_5FFF  (11 × 6 × max_upgrades; needs wide range)
```

---

## Open Questions

- ~~How does the C client persist AP state across sessions?~~ **Decided**: CHR save file. Idempotent state (HAR unlocks, stats) wiped + rebuilt from server replay each connect. One-shot consumables (money) guarded by `last_applied_item_index` in save. See [apclientpp-plan.md](apclientpp-plan.md#save--persistence).
- ~~Does money carry over normally, or does AP also handle money as items?~~ **Decided**: Money comes from AP filler items. Tracked via `last_applied_item_index` to prevent double-grant on reconnect. See [omf-plan.md](omf-plan.md#10-money-items-from-ap-server).
- ~~Trap design?~~ **Decided**: No traps for initial release.
- ~~Which AP base ID range?~~ **Decided**: `2097xxx` base (no conflicts in current AP game list).
