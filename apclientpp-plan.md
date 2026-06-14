# OpenOMF — apclientpp C Client Integration Plan

Pattern lifted directly from [TyrianArchipelago](https://github.com/KScl/TyrianArchipelago), which solves the same
problem: a pure-C open-source game (OpenTyrian) integrating apclientpp via a thin C++/C boundary.

---

## Dependencies (submodules)

Add as shallow submodules under `omf/src/archipelago/submodule/`:

```
apclientpp   https://github.com/black-sliver/apclientpp      branch: next
wswrap       https://github.com/black-sliver/wswrap
json         https://github.com/nlohmann/json
websocketpp  https://github.com/zaphoyd/websocketpp
asio         https://github.com/chriskohlhoff/asio
```

System deps (already available via vcpkg or system): `openssl`, `zlib`.

Define `AP_NO_SCHEMA` to drop valijson entirely — reduces bloat, no tangible downside.

---

## File Structure

```
omf/src/archipelago/
  apconnect.cpp       ← apclientpp lives here; all C++ internals + extern "C" exports
  apconnect.h         ← pure C header; only C types; included by both C and C++ code
  apitems.h           ← item/location ID constants (C-compatible)
  apstate.h           ← C structs for AP state shared to game side (APItems, APStats, etc.)
  appatcher.cpp       ← applies slot data / generated TRN overrides to game state
  appatcher.h         ← pure C header for patcher
  submodule/          ← git submodules (see above)
```

---

## C/C++ Boundary Pattern

### `apconnect.h` — pure C header (no C++ types)

```c
#pragma once
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    APCONN_NOT_CONNECTED = 0,
    APCONN_CONNECTING,
    APCONN_READY,
    APCONN_FATAL_ERROR,
} ap_connection_status_t;

// Structs exposed to C side — game reads these directly
typedef struct { /* received items, HAR unlocks, stat levels */ } ap_items_t;
typedef struct { /* money, match wins, etc. */                  } ap_stats_t;

extern ap_items_t APItems;
extern ap_stats_t APStats;

// Lifecycle
void Archipelago_Connect(const char *host, const char *slot, const char *password);
void Archipelago_Poll(void);     // call once per frame / game tick
void Archipelago_Disconnect(void);
ap_connection_status_t Archipelago_ConnectionStatus(void);

// Checks & goal
void Archipelago_SendCheck(int64_t location_id);
void Archipelago_GoalComplete(void);

// DeathLink (optional)
bool Archipelago_DeathLinkPending(void);
void Archipelago_DeathLinkClear(void);
void Archipelago_SendDeathLink(void);
```

### `apconnect.cpp` — C++ implementation

```cpp
// Suppress warnings from heavy header-only libs
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wpedantic"

#define AP_NO_SCHEMA                    // skip valijson
#define _WEBSOCKETPP_CPP11_STRICT_      // fix x86 mingw quirk
#define ASIO_STANDALONE

#include <apclient.hpp>
#include <apuuid.hpp>

#pragma GCC diagnostic pop

extern "C" {
    #include "apconnect.h"
    #include "apitems.h"
    #include "apstate.h"
    // pull in any C-side callbacks we need (e.g. message display)
    void ap_message_enqueue(const char *msg);
}

using nlohmann::json;

static std::unique_ptr<APClient> ap;

// --- item received handler ---
static void on_items_received(const std::list<APClient::NetworkItem>& items) {
    for (auto& item : items) {
        // translate item.item → APItems fields
        // e.g. HAR unlock, stat increment
        apply_item(item.item);
    }
}

// --- location checked (remote check for us) ---
static void on_location_checked(const std::list<int64_t>& locs) {
    for (auto id : locs) mark_location_checked((int)id);
}

extern "C" void Archipelago_Connect(const char *host, const char *slot, const char *pass) {
    ap = std::make_unique<APClient>(ap_get_uuid("openomf"), "One Must Fall: 2097", host);
    ap->set_room_info_handler([=]() {
        ap->ConnectSlot(slot, pass, 0b111 /* items+locations+deathlink */);
    });
    ap->set_items_received_handler(on_items_received);
    ap->set_location_checked_handler(on_location_checked);
    ap->set_slot_connected_handler([](const json& slot_data) {
        parse_slot_data(slot_data);  // read goal, settings, etc.
    });
}

extern "C" void Archipelago_Poll(void) {
    if (ap) ap->poll();
}

extern "C" void Archipelago_SendCheck(int64_t location_id) {
    if (ap) ap->LocationChecks({location_id});
}

extern "C" void Archipelago_GoalComplete(void) {
    if (ap) ap->StatusUpdate(APClient::ClientStatus::GOAL);
}
```

---

## Build System Changes (`omf/CMakeLists.txt`)

```cmake
# Enable C++ for the archipelago subdir only
enable_language(CXX)
set(CMAKE_CXX_STANDARD 17)

# AP include paths
set(AP_INCLUDES
    src/archipelago/submodule/apclientpp
    src/archipelago/submodule/wswrap/include
    src/archipelago/submodule/json/include
    src/archipelago/submodule/websocketpp
    src/archipelago/submodule/asio/asio/include
)

# Build AP client as a small static lib (keeps C++ isolated)
add_library(omf_apclient STATIC
    src/archipelago/apconnect.cpp
    src/archipelago/appatcher.cpp
)
target_include_directories(omf_apclient PRIVATE ${AP_INCLUDES})
target_compile_definitions(omf_apclient PRIVATE
    AP_NO_SCHEMA
    ASIO_STANDALONE
    _WEBSOCKETPP_CPP11_STRICT_
)
target_link_libraries(omf_apclient PRIVATE ssl crypto z)

# Link into main OpenOMF target
target_link_libraries(openomf PRIVATE omf_apclient)
```

The rest of OpenOMF stays pure C. Only `omf_apclient` is compiled as C++17.

---

## Item Application

Items received from AP server are translated to OpenOMF pilot stat changes.

```c
// apstate.h — C struct, readable from game side
typedef struct {
    // HAR unlocks — bitmask, one bit per HAR (0=Jaguar … 10=Nova)
    uint16_t har_unlocked;

    // Per-HAR stat levels [har_id][stat]
    // stat indices: 0=arm_power 1=leg_power 2=arm_speed 3=leg_speed 4=armor 5=stun_resist
    uint8_t har_stats[11][6];

    // Pilot stats
    uint8_t pilot_power;
    uint8_t pilot_agility;
    uint8_t pilot_endurance;
} ap_items_t;
```

Applied to `sd_pilot` at match-load time (not in real-time, avoids mid-fight weirdness):

```c
// In game_player.c or similar, before each match starts:
void ap_apply_to_pilot(sd_pilot *pilot) {
    pilot->arm_power      = APItems.har_stats[pilot->har_id][0];
    pilot->leg_power      = APItems.har_stats[pilot->har_id][1];
    pilot->arm_speed      = APItems.har_stats[pilot->har_id][2];
    pilot->leg_speed      = APItems.har_stats[pilot->har_id][3];
    pilot->armor          = APItems.har_stats[pilot->har_id][4];
    pilot->stun_resistance= APItems.har_stats[pilot->har_id][5];
    pilot->power          = APItems.pilot_power;
    pilot->agility        = APItems.pilot_agility;
    pilot->endurance      = APItems.pilot_endurance;
}
```

---

## Check Sending Hooks

| Game Event | Where to hook | Location ID source |
|---|---|---|
| Opponent defeated | match end / newsroom scene | `apitems.h` match ID table |
| Tournament won | tournament end cutscene | `apitems.h` tournament ID table |
| Mechlab upgrade purchased | mechlab scene purchase handler | `apitems.h` buy-location table |

---

## Save / Persistence

AP state persists in the existing CHR save file (extend `sd_pilot` / save format). No external JSON.

**Two item classes require different strategies:**

| Class | Examples | Strategy |
|---|---|---|
| Idempotent | HAR unlocks, HAR/pilot stat levels | Wipe + rebuild from server replay each session |
| One-shot consumable | Money bundles | Only apply once — guard by `last_applied_item_index` |

apclientpp replays the **full item list from index 0** on every reconnect. Idempotent items are safe to
re-apply from scratch (just overwrite). Consumables (money) must not be re-applied — track via index.

**What to persist in CHR save:**
- `uint64_t locations_checked[N]` — bitmask/list of sent location IDs; prevents re-sending checks
- `uint32_t last_applied_item_index` — highest item index where money was applied; prevents double-granting

**What NOT to persist (rebuilt from replay):**
- `APItems.har_unlocked` — rebuilt from item replay on connect
- `APItems.har_stats[11][6]` — rebuilt from item replay on connect
- `APItems.pilot_*` — rebuilt from item replay on connect

**`items_received` handler pattern:**
```cpp
static void on_items_received(const std::list<APClient::NetworkItem>& items) {
    // Reset idempotent state before replaying full list
    memset(&APItems, 0, sizeof(APItems));
    for (auto& item : items) {
        apply_har_unlock(item.item);    // idempotent — always
        apply_stat_level(item.item);    // idempotent — always
        if ((uint32_t)item.index > APState.last_applied_item_index) {
            apply_money(item.item);     // one-shot — only new items
            APState.last_applied_item_index = (uint32_t)item.index;
        }
    }
}
```

---

## Mechlab HAR Filter

Mechlab scene must only show HARs where `APItems.har_unlocked & (1 << har_id)` is set.
Starting HAR is set on connect from slot data.

---

## Connection UI

Needs a new menu scene (or extend existing config) for:
- Server host (default: `localhost`)
- Port (default: `38281`)
- Slot name
- Password (optional)

Can mirror Tyrian's approach: `apmenu.c` handles the UI, calls `apconnect.h` functions.

---

## Reference

- TyrianArchipelago `src/archipelago/` — primary reference implementation
- apclientpp: https://github.com/black-sliver/apclientpp
- AP network protocol: https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/network%20protocol.md
