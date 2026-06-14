# OpenOMF — Archipelago World (Python Side) Plan

Reference: [Adding Games](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/adding%20games.md) |
[World API](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/world%20api.md) |
[APQuest example world](https://github.com/ArchipelagoMW/Archipelago/tree/main/worlds/apquest)

---

## Hard Requirements Checklist (from AP docs)

### World folder
- [ ] `worlds/openomf/` directory
- [ ] `worlds/openomf/__init__.py` containing `World` subclass
- [ ] Any subdirectory with `.py` files gets its own `__init__.py` (for frozen build packaging)

### World subclass (`__init__.py`) must have:
- [ ] Unique `game` string: `"One Must Fall: 2097"`
- [ ] `WebWorld` subclass instance (`web = OpenOMFWeb()`)
- [ ] `item_name_to_id` dict
- [ ] `location_name_to_id` dict
- [ ] `create_item(name)` implementation
- [ ] At least one `Region` (origin = `"Menu"`)
- [ ] Non-zero locations added to regions
- [ ] Item pool count **exactly equals** location count
- [ ] `completion_condition` set: `multiworld.completion_condition[self.player] = lambda state: ...`

### Documentation (required)
- [ ] `worlds/openomf/docs/en_One Must Fall 2097.md` — game info page
- [ ] `worlds/openomf/docs/setup_en.md` — client setup guide (how to connect OpenOMF to AP)

### WebWorld subclass must have:
- [ ] `tutorials` list referencing the setup doc

---

## Encouraged Features Checklist (from AP docs)

- [ ] `get_filler_item_name()` — return money bundle or `"Nothing"` rather than random item
- [ ] `options_dataclass` — all YAML options (see Options section below)
- [ ] `options` type hint on the World class
- [ ] Bug report page URL in `WebWorld`
- [ ] `option_groups` for webhost organization
- [ ] `options_presets` dict (e.g., `"Vanilla"`, `"Chaos"`, `"Speed"` presets)
- [ ] `item_name_groups` dict (e.g., `"HAR Unlocks"`, `"HAR Upgrades"`, `"Pilot Upgrades"`)
- [ ] `location_name_groups` dict (e.g., `"Match Checks"`, `"Tournament Checks"`, `"Buy Checks"`)

---

## File Structure

```
worlds/openomf/
  __init__.py          ← World class, region/location/item creation, completion condition
  Items.py             ← item definitions, IDs, classification
  Locations.py         ← location definitions, IDs, access rules metadata
  Options.py           ← all YAML options
  Rules.py             ← logic rules (access conditions per location)
  Regions.py           ← region definitions and connections
  data/
    __init__.py
    tournaments.py     ← parsed vanilla TRN data (enemy lists, tournament names/IDs)
  docs/
    en_One Must Fall 2097.md
    setup_en.md
```

---

## Options (`Options.py`)

```python
class GoalTournament(Choice):
    """Which tournament must be won to complete the seed."""
    display_name = "Goal Tournament"
    # Populated from vanilla TRN files at generation time
    # + special value "all" to require winning every tournament

class StartingHAR(Choice):
    """Which HAR the player begins with."""
    display_name = "Starting HAR"
    option_jaguar   = 0
    option_shadow   = 1
    option_thorn    = 2
    option_pyros    = 3
    option_electra  = 4
    option_katana   = 5
    option_shredder = 6
    option_flail    = 7
    option_gargoyle = 8
    option_chronos  = 9
    option_nova     = 10
    option_random   = 11
    default = 0

class HARStatMax(Range):
    """Maximum level for each HAR stat (vanilla = 9)."""
    display_name = "HAR Stat Max"
    range_start = 9
    range_end = 20
    default = 9

class PilotStatMax(Range):
    """Maximum level for each pilot stat (vanilla = 25)."""
    display_name = "Pilot Stat Max"
    range_start = 25
    range_end = 50
    default = 25

class IncludeBuyLocations(Toggle):
    """Include mechlab purchase slots as location checks."""
    display_name = "Include Buy Locations"
    default = 1

class BuyCostFactor(Range):
    """Per-level cost multiplier applied cumulatively on top of vanilla mechlab prices.
    ap_cost(n) = vanilla_cost(n) * (buy_cost_factor/100)^(n-1)
    100 = vanilla prices unchanged. 200 = each successive upgrade costs 2x vanilla for
    that level. Max 1000 = 10x vanilla per step. Min 10 = 10% of vanilla per step."""
    display_name = "Buy Cost Factor"
    range_start = 10
    range_end = 1000
    default = 100

class GenerateTournaments(Toggle):
    """Randomize opponent order within tournaments."""
    display_name = "Generate Tournaments"
    default = 0

# DeathLink: skipped for initial release
```

---

## Items (`Items.py`)

### Classification

| Category | Classification | Reason |
|---|---|---|
| HAR Unlocks | `progression` | Gate access to buy locations for that HAR |
| HAR Stat Progressives | `useful` | Power items, not strictly required for access |
| Pilot Stat Progressives | `useful` | |
| Money bundles | `filler` | |
| Nothing | `filler` | |

### Item count (vanilla defaults)

| Category | Count |
|---|---|
| HAR Unlocks | 10 (starting HAR is not an item) |
| HAR Stat Progressives | 11 HARs × 6 stats × 9 levels = 594 |
| Pilot Stat Progressives | 3 stats × 25 levels = 75 |
| **Total progression/useful** | **679** |
| Filler | location_count − 679 |

---

## Locations (`Locations.py`)

### Generation-time enumeration

Vanilla TRN files are read at world-generation time (via `data/tournaments.py`) to enumerate:
- All tournament names and their enemy pilot names (for match location names)
- Number of opponents per tournament (for buy-location count)

```python
# data/tournaments.py
# Pre-parsed from vanilla OMF TRN files — list of (tournament_name, [pilot_names])
VANILLA_TOURNAMENTS = [
    ("Warrior's Challenge",  ["Crystal", "Steffan", ...]),
    ("World Championship",   ["Milano", "Christian", ...]),
    # ...
]
```

### Location naming

```
"Warrior's Challenge - Beat Crystal"       # per-match
"Win Warrior's Challenge"                  # per-tournament
"Buy Jaguar ARM Power Upgrade 1"           # buy location, HAR-specific
```

### Access rules (`Rules.py`)

- **Buy locations for HAR X**: require `APItems.har_unlocked` has HAR X (i.e., HAR unlock item received)
- **Later tournaments**: require wins of prior tournaments (by match location checks) OR just money progression
- **Goal location**: require the goal tournament's win location

---

## Regions (`Regions.py`)

Regions map to tournament progression:

```
Menu
 └─► Warrior's Challenge     (always accessible)
      └─► Regional Tournament (requires Win Warrior's Challenge)
           └─► ...
                └─► World Championship (requires all prior wins OR configured goal)
```

Buy locations for each HAR are in a region accessible when that HAR is unlocked.

---

## Slot Data

Sent to the C client on connect. Must include:
- `goal_tournament`: tournament name string
- `starting_har`: HAR id (0–10)
- `har_stat_max`: int
- `pilot_stat_max`: int
- `generated_tournaments`: (Phase 3) serialized TRN opponent lists

---

## Item / Location Count Balance

AP requires item count == location count. This is satisfied naturally by design:

- Match + tournament locations are fixed by the TRN data (deterministic per option set)
- HAR unlock items (10) + stat progressives (594 + 75 at vanilla max) are also fixed
- **Buy locations are the balancing valve**: generate exactly enough buy slots to cover any remaining gap, or use filler (money bundles) for small remainders
- If `include_buy_locations = false`, pad with filler items instead
- Because buy locations correspond 1:1 to the same upgrade items, the pool is inherently balanced when buy locations are enabled — no manual counting needed

Validate with an assertion in `create_items` / `create_regions` during generation.

---

## Prohibited / Gotchas (from AP docs)

- Do **not** `=` assign to `multiworld.regions` or `multiworld.itempool` — use `append`/`extend`/`+=`
- Do **not** manually place items that are in the itempool
- Do **not** use `eval` or `yaml.load` directly (use `Utils.parse_yaml`)

---

## Submission / PR Notes (from AP docs)

When ready to submit to the main AP repo:
1. Fork `ArchipelagoMW/Archipelago`, add world under `worlds/openomf/`
2. Follow [contributing guide](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/contributing.md)
3. Check [world maintainer doc](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/world%20maintainer.md)
4. Base ID: `2097xxx` (decided)
5. Add `worlds/openomf/docs/en_One Must Fall 2097.md` and `setup_en.md` before PR

---

## Phase 1 Task List

- [ ] Scaffold `worlds/openomf/` with all required files and stubs
- [ ] Parse vanilla TRN files → `data/tournaments.py` (static data, not runtime)
- [ ] Implement `Items.py` with all IDs and classifications
- [ ] Implement `Locations.py` with all IDs (match + tournament + buy)
- [ ] Implement `Options.py`
- [ ] Implement `Regions.py` with tournament progression graph
- [ ] Implement `Rules.py` with HAR-unlock gates on buy locations
- [ ] Implement `__init__.py` World class (wire everything together)
- [ ] Validate item count == location count across all option combinations
- [ ] Write `docs/en_One Must Fall 2097.md`
- [ ] Write `docs/setup_en.md`
- [ ] Generate a test seed and verify location/item tables
