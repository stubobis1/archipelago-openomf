# OpenOMF — C Source Modification Plan

What needs to change in the OMF codebase to support Archipelago mode.
All paths relative to `omf/src/`.

---

## 1. Main Menu — Remove 1P/2P, Add AP Connect

**File**: `game/scenes/mainmenu/menu_main.c`

Lines 122–124 currently:
```c
menu_attach(menu, button_create("ONE PLAYER GAME", NULL, false, false, mainmenu_1v1, s));
menu_attach(menu, button_create("TWO PLAYER GAME", NULL, false, false, mainmenu_1v2, s));
menu_attach(menu, button_create("TOURNAMENT PLAY", NULL, false, false, mainmenu_mechlab, s));
```

Changes:
- **Remove** `ONE PLAYER GAME` (`mainmenu_1v1`) — single non-tournament vs-AI fight not relevant to AP
- **Remove** `TWO PLAYER GAME` (`mainmenu_1v2`) — local vs human not part of AP mode
- **Add** `ARCHIPELAGO` button → new `mainmenu_archipelago()` handler → goes to AP connect screen
- Keep `TOURNAMENT PLAY` as a non-AP offline mode (or hide it behind a config flag)

New handler (add to `menu_main.c`):
```c
void mainmenu_archipelago(component *c, void *userdata) {
    scene *s = userdata;
    menu_set_submenu(c->parent, menu_ap_create(s));
}
```

---

## 2. New AP Connect Screen (new file)

**New file**: `game/scenes/mainmenu/menu_ap.c` + `menu_ap.h`

Model on `game/scenes/mainmenu/menu_connect.c` (the existing network connect screen).

Fields:
- Server address (text input, default `localhost`)
- Port (text input, default `38281`)
- Slot name (text input)
- Password (text input, optional)

On connect:
```c
static void menu_ap_connect(component *c, void *userdata) {
    // call into apconnect.h
    Archipelago_Connect(addr, slot, password);
    // transition to mechlab once APCONN_READY
    game_state_set_next(s->gs, SCENE_MECHLAB);
}
```

Needs a per-tick poll callback that calls `Archipelago_Poll()` while connecting, checks
`Archipelago_ConnectionStatus()`, and shows a status string (connecting / error / ready).

Save host/port/slot to settings so they persist between sessions
(add fields to `game/utils/settings.c` + `game/utils/settings.h`).

---

## 3. HAR Selection — Replace Affordability with Unlock Bitmask

**File**: `game/scenes/vs.c`, lines 517–529

Current logic collects HARs the player can *afford* by trade-in value + money:
```c
int trade_value = calculate_trade_value(player1->pilot);   // line 517
for(int i = 0; i < 11; i++) {                             // line 524
    if(i == player1->pilot->har_id) { ... }               // line 525
    if(har_price(i) < trade_value + player1->pilot->money) // line 529
        available[n++] = i;
}
```

Replace affordability check with AP unlock bitmask:
```c
for(int i = 0; i < 11; i++) {
    if(APItems.har_unlocked & (1u << i))
        available[n++] = i;
}
```

`calculate_trade_value()` and `har_price()` are no longer used for HAR selection in AP mode.

---

## 4. HAR Trade Menu — Remove

**File**: `game/scenes/mechlab/lab_menu_trade.c`

In vanilla, players can trade HARs for money. In AP mode, HARs come from unlock items — no trading.

- Remove the trade menu entry from `game/scenes/mechlab/lab_menu_main.c`
- Or gate it: `if (!ap_mode) menu_attach(menu, trade_button)`

`lab_menu_trade.c` itself can stay (for offline mode), just don't attach it in AP mode.

---

## 5. Mechlab Customize — Upgrade Purchase → AP Check

**File**: `game/scenes/mechlab/lab_menu_customize.c`

This is the main change. Each upgrade currently does two things:
1. Deducts `price` from `pilot->money`
2. Increments the stat (e.g., `pilot->arm_power++`)

In AP mode, step 2 is replaced by sending a location check. The stat increment comes back from
the AP server as an item received, applied at next match load.

Pattern for each upgrade button handler (e.g., arm power buy, ~line 101):
```c
// BEFORE:
pilot->money -= price;
pilot->arm_power++;

// AFTER (AP mode):
// ap_price = vanilla_price * buy_cost_factor^(level-1), where factor comes from slot data
int32_t ap_price = (int32_t)(price * pow(APSeedSettings.buy_cost_factor, pilot->arm_power));
pilot->money -= ap_price;
int level = pilot->arm_power;  // current level = which check to send
int64_t loc_id = ap_buy_location_id(pilot->har_id, STAT_ARM_POWER, level);
Archipelago_SendCheck(loc_id);
// pilot->arm_power is NOT incremented here — comes back via item received
```

The "sell upgrade" path (refunding money for downgrading, ~line 94) is **removed in AP mode** —
you cannot sell AP items back.

Display (`lab_menu_customize_check_arm_power_price`, ~line 108):
- Disable "buy" button if: `price > pilot->money` OR `already sent check for this slot`
- Disable "sell" button always in AP mode (no selling)

---

## 6. Training Menu — Pilot Stats → AP Check

**File**: `game/scenes/mechlab/lab_menu_training.c`

Same pattern as customize. Currently `lab_menu_training_power` (~line 25):
```c
pilot->money -= price;
pilot->power++;
```

In AP mode:
```c
pilot->money -= price;
int64_t loc_id = ap_buy_location_id_pilot(PILOT_STAT_POWER, pilot->power);
Archipelago_SendCheck(loc_id);
// pilot->power NOT incremented — comes from AP item
```

Disable button if: `price > pilot->money` OR check already sent for this level.

---

## 7. Apply AP Stats to Pilot at Match Load

**New function** — call just before arena scene loads (in `game/scenes/vs.c` or `game/protos/scene.c`).

```c
// In ap_state.h / apconnect.h — called by C game code
void ap_apply_to_pilot(sd_pilot *pilot) {
    if (!ap_mode) return;
    uint8_t *s = APItems.har_stats[pilot->har_id];
    pilot->arm_power       = s[0];
    pilot->leg_power       = s[1];
    pilot->arm_speed       = s[2];
    pilot->leg_speed       = s[3];
    pilot->armor           = s[4];
    pilot->stun_resistance = s[5];
    pilot->power           = APItems.pilot_power;
    pilot->agility         = APItems.pilot_agility;
    pilot->endurance       = APItems.pilot_endurance;
}
```

Call site: `game/scenes/vs.c` in the match setup path, or `game/scenes/arena.c` before fight start.

---

## 8. Match Win → Send Check + Money

**File**: `game/scenes/arena.c`, lines 338–342

Current:
```c
fight_stats->profit = fight_stats->bonuses + fight_stats->winnings - fight_stats->repair_cost;
p1->pilot->money += fight_stats->profit;
```

In AP mode, after awarding money, also send the match location check:
```c
p1->pilot->money += fight_stats->profit;   // match winnings still apply

if (ap_mode && fight_stats->winner == 0) {
    int64_t loc_id = ap_match_location_id(current_tournament, current_opponent_index);
    Archipelago_SendCheck(loc_id);
}
```

**Remove auto-sell-on-debt** (lines 372–376): no selling in AP mode. Money clamps to 0 (see §16).

---

## 9. Tournament Win → Send Check + Goal

**File**: `game/scenes/mechlab.c` (tournament completion detection) or `game/scenes/newsroom.c`

When all opponents in a tournament are defeated:
```c
if (ap_mode) {
    int64_t loc_id = ap_tournament_location_id(current_tournament);
    Archipelago_SendCheck(loc_id);

    if (is_goal_tournament(current_tournament))
        Archipelago_GoalComplete();
}
```

Locate exact trigger point — likely in `newsroom.c` or `mechlab.c` around the tournament
progression logic.

---

## 10. Money Items from AP Server

**File**: `game/archipelago/apconnect.cpp` (in `on_items_received` handler)

Money is a **one-shot consumable** — must not be re-applied on reconnect. Guard by `item.index`:

```cpp
// inside on_items_received, after handling idempotent items:
if ((uint32_t)item.index > APState.last_applied_item_index) {
    switch (item_type(item.item)) {
        case ITEM_MONEY_SMALL: APStats.pending_money += APSeedSettings.money_small; break;
        case ITEM_MONEY_LARGE: APStats.pending_money += APSeedSettings.money_large; break;
    }
    APState.last_applied_item_index = (uint32_t)item.index;
}
```

Accumulate in `APStats.pending_money` (C struct); drain into `pilot->money` at mechlab entry.
The pilot pointer is not safely accessible from C++ at item-received time.

---

## 11. Starting Money

**File**: `game/scenes/mechlab.c`, line 428

```c
player1->pilot->money = 2000;   // hardcoded starting money for new pilots
```

In AP mode, set starting money from AP slot data (received in `slot_connected` handler).
Add `starting_money` to slot data and `APStats`, apply here instead of hardcode.

---

## 12. Mechlab HAR Buy Screen (vs.c)

**File**: `game/scenes/vs.c`

The inter-tournament HAR swap screen (between matches) shows affordable HARs.
In AP mode this becomes a "pick from unlocked HARs" screen.

The HAR swap triggered at the start of a new tournament (`vs.c` around the HAR selection block)
should filter by `APItems.har_unlocked` bitmask instead of afford check (see §3 above).

HAR is still purchased for the swap in vanilla — in AP mode, no money cost for swapping HARs.
Remove the `pilot->money -= har_price(i)` call in this path.

---

## 13. In-Game AP Connection Status Indicator

**File**: `game/scenes/arena.c`, function `arena_render_overlay` (line 1457)

The arena already renders a `player_ping` text object for networked play (lines 1493–1502)
using the `text_draw()` / `text_set_from_c()` pattern. The AP status indicator follows
the same approach.

Add a persistent `text *ap_status_text` to `arena_local` (alongside `player_ping`).

In `arena_render_overlay`:
```c
// After existing ping rendering (~line 1502)
if (ap_mode) {
    const char *status;
    switch (Archipelago_ConnectionStatus()) {
        case APCONN_READY:          status = "AP: OK";           break;
        case APCONN_CONNECTING:     status = "AP: CONNECTING..."; break;
        case APCONN_FATAL_ERROR:    status = "AP: ERROR";        break;
        default:                    status = "AP: OFFLINE";      break;
    }
    text_set_from_c(local->ap_status_text, status);
    text_draw(local->ap_status_text, 130, 40);  // bottom-right of HUD, adjust as needed
}
```

Color: green for READY, yellow for CONNECTING, red for ERROR/OFFLINE.
Use `text_set_color()` or a colored font variant if available.

Also call `Archipelago_Poll()` from `arena_tick` (or `game_state.c`) once per tick
so the connection stays alive during a fight.

Status should also be visible in **mechlab** and **newsroom** scenes — add the same
`text_draw` call to their respective render functions so the player always knows
their connection state between matches.

---

## 14. Item Received — Sound

**File**: `game/archipelago/apconnect.h` + `apconnect.cpp`; hook registered from `game/scenes/mechlab.c`

AP C++ code must not include `audio/audio.h` directly. Use a callback:

```c
// apconnect.h
void ap_set_item_received_sound_callback(void (*cb)(void));
```

```cpp
// apconnect.cpp
static void (*g_item_sound_cb)(void) = NULL;
void ap_set_item_received_sound_callback(void (*cb)(void)) { g_item_sound_cb = cb; }

// inside on_items_received, after applying each item:
if (g_item_sound_cb) g_item_sound_cb();
```

```c
// mechlab.c or game init path:
static void play_ap_item_sound(void) {
    audio_play_sound_simple(19, 0);  // confirm/select sound — tune after playtesting
}
ap_set_item_received_sound_callback(play_ap_item_sound);
```

Sound IDs 19 (confirm) and 20 (navigate) are the known UI sounds. SOUNDS.DAT has up to 299 entries
— worth cycling through in-game to find a more appropriate reward sound.

---

## 15. Item Received — AP Logo Animation

**New files**: `game/archipelago/ap_display.c` + `ap_display.h`
**Assets**: `resources/archipelago/ap1.png`–`ap7.png` (non-progressive), `app1.png`–`app7.png` (progressive)

The apdoom AP logo frames are 28×28, 8-bit paletted PNGs — compatible with
`sd_vga_image_from_png_in_memory` + `surface_create_from_vga` directly. No RGBA conversion needed.

### Data

```c
// ap_display.h
void ap_display_init(void);
void ap_display_show_item(bool progressive);  // trigger animation
void ap_display_tick(int dt_ms);
void ap_display_render(void);
void ap_display_free(void);
```

### Init

Load all 14 frames at AP init time (not per-frame):

```c
// ap_display.c
static surface ap_frames_normal[7];
static surface ap_frames_progressive[7];

void ap_display_init(void) {
    for (int i = 0; i < 7; i++) {
        // load resources/archipelago/ap{i+1}.png and app{i+1}.png
        // via sd_vga_image_from_png_in_memory + surface_create_from_vga
    }
}
```

Use OMF's existing resource path resolution to locate `resources/archipelago/`.

### Animation

```c
static int  ap_timer;
static int  ap_frame;
static bool ap_showing;
static bool ap_progressive;

void ap_display_tick(int dt_ms) {
    if (!ap_showing) return;
    ap_timer += dt_ms;
    ap_frame = (ap_timer / 80) % 7;  // ~80 ms/frame ≈ 12 fps
    if (ap_timer > 3000) ap_showing = false;
}

void ap_display_render(void) {
    if (!ap_showing) return;
    surface *frames = ap_progressive ? ap_frames_progressive : ap_frames_normal;
    video_draw(&frames[ap_frame], 280, 170);  // bottom-right HUD; adjust coordinates
}
```

`ap_display_tick()` is called from the same tick path as `Archipelago_Poll()`.
`ap_display_render()` is called from `arena_render_overlay` and the mechlab render function,
so the animation plays both mid-fight and between matches.

`ap_display_show_item(progressive)` is called from the item-received callback alongside the sound.

---

## 16. Repair Cost

**File**: `game/scenes/arena.c`, `fight_stats->repair_cost`

Keep repair costs — they make the money economy meaningful. Clamp `pilot->money` to 0 after deducting; no debt allowed.

```c
p1->pilot->money -= fight_stats->repair_cost;
if (p1->pilot->money < 0) p1->pilot->money = 0;
```

The existing auto-sell-on-debt path (lines 372–376) is removed in AP mode (nothing to sell).

---

## Summary — Files Modified

| File | Change |
|---|---|
| `game/scenes/mainmenu/menu_main.c` | Remove 1P/2P buttons, add ARCHIPELAGO button |
| `game/scenes/mainmenu/menu_ap.c` (**new**) | AP connect screen (host/port/slot/password) |
| `game/scenes/mainmenu/menu_ap.h` (**new**) | Header for above |
| `game/scenes/vs.c` | HAR selection: afford check → unlock bitmask; remove HAR buy cost |
| `game/scenes/mechlab/lab_menu_customize.c` | Upgrade buy: stat++ → `Archipelago_SendCheck()`; remove sell |
| `game/scenes/mechlab/lab_menu_training.c` | Pilot stat buy: stat++ → `Archipelago_SendCheck()` |
| `game/scenes/mechlab/lab_menu_trade.c` | Gate behind non-AP mode |
| `game/scenes/mechlab/lab_menu_main.c` | Hide trade menu in AP mode |
| `game/scenes/arena.c` | Match win: send check; remove auto-sell-on-debt; AP status overlay in `arena_render_overlay` |
| `game/scenes/mechlab.c` | Tournament win: send check + goal; starting money from slot data |
| `game/scenes/newsroom.c` | Investigate as tournament completion hook; AP status overlay |
| `game/scenes/mechlab.c` + `mechlab/lab_dash_main.c` | AP status overlay in HUD |
| `game/utils/settings.c` + `.h` | Add AP connection settings fields |
| `game/archipelago/apconnect.cpp` (**new**) | apclientpp wrapper (see apclientpp-plan.md) |
| `game/archipelago/apconnect.h` (**new**) | Pure-C interface; includes `ap_set_item_received_sound_callback` |
| `game/archipelago/apstate.h` (**new**) | `ap_items_t`, `ap_stats_t` C structs |
| `game/archipelago/apitems.h` (**new**) | Location/item ID constants |
| `game/archipelago/ap_display.c` (**new**) | AP logo animation (14 frames, 28×28 paletted PNG) |
| `game/archipelago/ap_display.h` (**new**) | `ap_display_init/show_item/tick/render/free` |
| `resources/archipelago/ap1–7.png` (**new**) | Non-progressive AP logo frames (from apdoom) |
| `resources/archipelago/app1–7.png` (**new**) | Progressive AP logo frames (from apdoom) |
