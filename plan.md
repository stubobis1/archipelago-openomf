# Plan: Minimize AP Delta vs Upstream OMF (from fda29f2c)

## Goal
Reduce the diff between `fda29f2c` and HEAD in non-AP `src/` files to the absolute minimum.
All AP logic moves to `src/archipelago/`. Each non-AP file gets at most a `/* AP */` one-liner.

See sub-plans: [ap-world-plan.md](ap-world-plan.md) · [apclientpp-plan.md](apclientpp-plan.md)

---

## Unavoidable changes in existing OMF files

These touch non-AP infrastructure and cannot move into `src/archipelago/`:

| File | Change | Lines |
|---|---|---|
| `settings.h` | Add `settings_archipelago` struct + field in `settings` | +8 |
| `settings.c` | Add `f_archipelago[]` field table + `S_2_F` entry | +6 |
| `sgmanager.h` | Declare `sg_save_ap`, `sg_load_ap_pilot` | +3 |
| `sgmanager.c` | Implement `sg_save_ap`, `sg_load_ap_pilot` | +40 |
| `resource_files.h` | Declare `get_ap_save_directory` | +1 |
| `resource_files.c` | Implement `get_ap_save_directory` | +8 |
| `engine.c` | Call `Archipelago_Poll()` in main tick | +3 |
| `menu_net.c` | Add ARCHIPELAGO button → `menu_ap_create` | +7 |

These are the only changes needed in existing OMF files after the refactor.

---

## Changes to revert or restructure

### `menu_main.c` — restore upstream, ~0 net delta

Current state removes ONE PLAYER, TWO PLAYERS, TOURNAMENT PLAY, NETWORK PLAY and adds ARCHIPELAGO.
Revert `menu_main_create` to upstream. Remove `#include "menu_ap.h"` and `mainmenu_enter_archipelago`.

Target diff vs `fda29f2c`: **0 lines** (file fully restored to upstream).

### `mechlab.c` — move `mechlab_find_ap_player` to AP dir

The 76-line `mechlab_find_ap_player` is pure AP logic. Move it entirely to `ap_mechlab.c`.
Rename to `ap_mechlab_find_player(scene *s) → bool`.

Three save blocks each follow the pattern:
```c
if(p1->chr != NULL && sg_save(p1->chr) != SD_SUCCESS) { ... }
```
became:
```c
if(p1->chr != NULL) {
    char ap_ident[12] = "";
    /* AP */ if(ap_mode) { ... 4 lines ... }
    int save_ret = ap_mode ? sg_save_ap(...) : sg_save(...);
}
```
Replace each with:
```c
if(p1->chr != NULL) {
    if(ap_mode) { ap_mechlab_save(player1); } else { sg_save(player1->chr); }
}
```

Tournament-index mapping block (15 lines added in `mechlab_tick`):
```c
if(ap_mode) { ap_mechlab_set_tournament(trn); }
```

`mechlab_create` AP init block (7 lines):
```c
found = ap_mode ? ap_mechlab_find_and_attach(scene) : mechlab_find_last_player(scene);
```
Where `ap_mechlab_find_and_attach` calls `ap_mechlab_find_player` then `ap_mechlab_attach`.

`mechlab_free` detach (1 line already clean): keep `if(ap_mode) ap_mechlab_detach();`

Remove `mechlab_set_hint_wrapped` — only needed by AP training focus callbacks.
AP version goes into `ap_mechlab.c` as `ap_set_hint(scene *s, const char *hint)`.
Remove from `mechlab.h` and `mechlab.c`.

Target diff vs `fda29f2c`: **~6 one-liners + 3 includes** (vs current 110+ added lines).

### `lab_menu_customize.c` — 12 functions, each → 1-line AP override

Each of 6 HAR stats has a buy callback and a price-check callback.
Current AP blocks are 5–7 lines each. Replace with:

```c
void lab_menu_customize_arm_power(component *c, void *userdata) {
    scene *s = userdata;
    game_player *p1 = game_state_get_player(s->gs, 0);
    sd_pilot *pilot = game_player_get_pilot(p1);
    if(ap_mode) { ap_customize_buy(s, pilot, AP_STAT_ARM_POWER); return; }
    if(mechlab_get_selling(s)) { ... } // vanilla unchanged
}

void lab_menu_customize_check_arm_power_price(component *c, void *userdata) {
    ...
    if(ap_mode) { ap_customize_check_price(c, pilot, AP_STAT_ARM_POWER); return; }
    if(mechlab_get_selling(s)) { ... } // vanilla unchanged
}
```

Same pattern for all 6 stats (leg_power, arm_speed, leg_speed, armor, stun_resistance).

Also 3 color callbacks:
```c
void lab_menu_customize_color_main(...) {
    if(ap_mode && !ap_has_extra_har_colors()) return;
    // vanilla unchanged
}
```

New in `ap_mechlab.c/.h`:
```c
void ap_customize_buy(scene *s, sd_pilot *pilot, int stat);
// Deducts ap_buy_price, calls ap_do_buy_har, calls ap_update_buy_har_labels.
// Uses s_buy_multipliers[stat] from ap_mechlab.c internal table.

void ap_customize_check_price(component *c, sd_pilot *pilot, int stat);
// Disables c if price > money or buy_level >= har_stat_max.

bool ap_has_extra_har_colors(void);
// Returns APItems.extra_har_colors > 0.
```

Target diff vs `fda29f2c`: **~15 one-liners + 2 includes** (vs current ~80 added lines).

### `lab_menu_training.c` — 9 functions, each → 1-line AP override

Current state modifies all 9 functions by interleaving AP branches using `ap_mode ? ... : ...`
ternaries and `/* AP */ if(ap_mode) { ... }` blocks. The upstream `prices[]` array was removed.

Restore `prices[]` array. Restore each function to upstream vanilla. Add single AP early-return:

```c
void lab_menu_training_power(component *c, void *userdata) {
    scene *s = userdata;
    if(ap_mode) { ap_training_buy(s, AP_PILOT_POWER); return; }
    // vanilla: prices[pilot->power], pilot->power++, focus, mechlab_update
}

void lab_menu_training_check_power_price(component *c, void *userdata) {
    scene *s = userdata;
    if(ap_mode) { ap_training_check_price(c, s, AP_PILOT_POWER); return; }
    // vanilla: prices[]/23 check
}
```

Focus callbacks (`lab_menu_focus_power/agility/endurance`) — same pattern:
```c
static void lab_menu_focus_power(component *c, bool focused, void *userdata) {
    if(focused) {
        scene *s = userdata;
        if(ap_mode) { ap_training_focus(s, AP_PILOT_POWER); return; }
        // vanilla: label1/label2 set, mechlab_set_hint(s, lang_get(533))
    }
}
```

`lab_menu_focus_training_done`: restore `mechlab_set_hint` (was changed to `mechlab_set_hint_wrapped`).

`lab_menu_training_create`: keep `ap_register_train_labels(label1, label2)` — 1 line, already clean.

New in `ap_mechlab.c/.h`:
```c
void ap_training_buy(scene *s, int stat);
// Deducts ap_train_price, calls ap_do_train, ap_update_train_labels, mechlab_update.

void ap_training_check_price(component *c, scene *s, int stat);
// Disables c if price > money or level >= pilot_stat_max.

void ap_training_focus(scene *s, int stat);
// Calls ap_update_train_labels + ap_focus_train + mechlab_set_hint (with wrap).
```

Target diff vs `fda29f2c`: **~10 one-liners + 2 includes + prices[] restored** (vs current ~80 added lines).

### `lab_menu_trade.c` — move ap_preview_har + 3 function overrides

`ap_preview_har` static function (14 lines added): move to `ap_mechlab.c`, make public.
The 11 focus callbacks were refactored from verbose upstream to 1-liners calling `ap_preview_har`.
Keep that refactor — it's a pure cleanup, not AP-specific.

Three functions get AP overrides:

```c
bool confirm_trade(component *c, void *userdata) {
    scene *s = userdata;
    game_player *p1 = game_state_get_player(s->gs, 0);
    if(ap_mode) { ap_confirm_trade(c, s, p1); return true; }
    // vanilla: calculate_trade_value, money delta, har swap, mechlab_update
}

void lab_menu_trade(component *c, void *userdata) {
    scene *s = userdata;
    game_player *p1 = game_state_get_player(s->gs, 0);
    if(ap_mode) { ap_do_trade(c, s, p1); return; }
    // vanilla: trade_value/har_value, snprintf with lang_get(518/519/520)
}

component *lab_menu_trade_create(scene *s) {
    if(ap_mode) return ap_trade_menu_create(s);
    // vanilla: vanilla eligible list, all 11 verbose focus callbacks if desired
}
```

The 11 focus callbacks refactor (verbose → 1-liner each) is a separate cleanup PR; keep in AP branch.

New in `ap_mechlab.c/.h`:
```c
void ap_preview_har(scene *s, int har_id);       // moved from lab_menu_trade.c
void ap_confirm_trade(component *c, scene *s, game_player *p1); // full AP confirm body
void ap_do_trade(component *c, scene *s, game_player *p1);      // AP trade text + confirm menu
component *ap_trade_menu_create(scene *s);                      // full AP trade menu
```

Target diff vs `fda29f2c`: **3 one-liners + 1 include + moved ap_preview_har** (vs current ~80 added lines).

### `lab_menu_main.c` — 2 small changes only

`lab_menu_tick_chr_loaded`: change `if(p1->chr)` → `if(ap_mode || p1->chr)`. 1 line.
`lab_menu_tick_ap_disabled`: new 5-line tick callback + 3 entries in `tick_cbs[]`. Keep as-is — it's minimal and clear.
Add `#include "archipelago/apstate.h"`.

Target diff vs `fda29f2c`: **~10 lines** — acceptable as-is.

### `arena.c` — 2 AP blocks → 2 one-liners

Match-win block (13 lines):
```c
if(ap_mode && is_tournament(gs) && p1->chr) ap_arena_match_win(gs, p1, p2);
```

Save block (9 lines):
```c
if(p1->chr) {
    if(ap_mode) { ap_arena_save(p1); } else if(sg_save(p1->chr) != SD_SUCCESS) {
        log_error("Failed to save pilot %s", p1->chr->pilot.name);
    }
}
```

The `!ap_mode` guards on the money/kick-out checks stay as-is (already 1 word each).

New in `ap_mechlab.c/.h`:
```c
void ap_arena_match_win(game_state *gs, game_player *p1, game_player *p2);
// Finds matched enemy in chr->enemies[], calls ap_on_match_win(trn_index), clamps money.

void ap_arena_save(game_player *p1);
// GetSaveIdent, persist har_money, APSaveState, sg_save_ap. Logs errors internally.
```

Target diff vs `fda29f2c`: **~8 lines + 3 includes** (vs current ~30 added lines).

### `newsroom.c` — already 1 line, keep

```c
/* AP */ if(ap_mode) ap_on_tournament_win();
```
Leave as-is. Move `#include "archipelago/ap_mechlab.h"` and `apstate.h` to top grouped with other AP includes.

### `trnselect.c` — already 1 line, keep

```c
if(ap_mode) { ap_filter_trnlist(&local->tournaments); }
```
Leave as-is.

### `mechlab.h`

Remove `mechlab_set_hint_wrapped` declaration — no longer needed in non-AP code.

---

## New wrapper functions in `ap_mechlab.c/.h`

| Function | Called from | Absorbs |
|---|---|---|
| `ap_preview_har(scene*, int)` | lab_menu_trade.c focus cbs | static `ap_preview_har` in lab_menu_trade.c |
| `ap_confirm_trade(component*, scene*, game_player*)` | confirm_trade | AP blocks in confirm_trade |
| `ap_do_trade(component*, scene*, game_player*)` | lab_menu_trade | AP branch + snprintf |
| `ap_trade_menu_create(scene*)` | lab_menu_trade_create | AP init block + `ap_trade_page` call |
| `ap_customize_buy(scene*, sd_pilot*, int)` | lab_menu_customize × 6 | per-stat AP buy blocks |
| `ap_customize_check_price(component*, sd_pilot*, int)` | lab_menu_customize × 6 | per-stat price-check blocks |
| `ap_has_extra_har_colors(void)` | lab_menu_customize × 3 | `APItems.extra_har_colors` access |
| `ap_training_buy(scene*, int)` | lab_menu_training × 3 | buy callbacks AP branches |
| `ap_training_check_price(component*, scene*, int)` | lab_menu_training × 3 | price-check AP branches |
| `ap_training_focus(scene*, int)` | lab_menu_training × 3 | focus callback AP branches |
| `ap_mechlab_find_player(scene*) → bool` | mechlab.c | `mechlab_find_ap_player` (76 lines) |
| `ap_mechlab_find_and_attach(scene*) → bool` | mechlab.c | find + attach combo |
| `ap_mechlab_save(game_player*)` | mechlab.c × 2, arena.c | save ident + har_money + APSaveState |
| `ap_mechlab_set_tournament(sd_tournament_file*)` | mechlab.c | tournament-index mapping block |
| `ap_arena_match_win(game_state*, game_player*, game_player*)` | arena.c | match-win block |
| `ap_set_hint(scene*, const char*)` | ap_mechlab.c internally | replaces mechlab_set_hint_wrapped |

---

## Final change summary

| File | Action | Net delta vs fda29f2c |
|---|---|---|
| `menu_main.c` | Fully restore upstream | 0 |
| `menu_net.c` | Add AP submenu button | +7 |
| `engine.c` | Add Poll call | +3 |
| `settings.h/.c` | AP settings struct | +14 |
| `sgmanager.h/.c` | AP save/load fns | +44 |
| `resource_files.h/.c` | AP save dir | +9 |
| `mechlab.h` | Remove hint_wrapped | -2 |
| `mechlab.c` | Remove find_ap_player (76L), 4 one-liners | ~+10 |
| `arena.c` | 2 one-liners + !ap_mode guards | ~+10 |
| `newsroom.c` | 1 line already clean | +3 |
| `trnselect.c` | 1 line already clean | +5 |
| `lab_menu_main.c` | tick_ap_disabled + 1 change | ~+10 |
| `lab_menu_customize.c` | 12 one-liners + 3 guards | ~+18 |
| `lab_menu_training.c` | Restore prices[]; 9 one-liners | ~+12 |
| `lab_menu_trade.c` | Remove ap_preview_har; 3 overrides | ~+10 |
| `ap_mechlab.c/.h` | +16 new wrapper functions | +~250 (all in AP dir) |
| `menu_ap.c/.h` | New files (AP dir) | new |
