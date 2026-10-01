#include "gime.h"
#include "palette.h"
#include "tiles.h"
#include "ram.h"
#include "display.h"
#include "live.h"
#include "player.h"
#include "controls.h"
#include "hwscroll.h"
#include "prefs.h"
#include "hud.h"
#include "ovl_api.h"
#include "art.h"
#include "rt_state.h"
#include "sound.h"
#include <coco.h>
#include <cmoc.h>

/* The game (stage 2). Launched by setup.c once a login exists: takes the
 * login and host FRLOGIN hands over (ovl_api.h), reads the display target,
 * attaches to the realtime server (which streams the terrain in-band), and
 * plays. Kept free of login, bootstrap and printf code. */

/* Border: dark green on 512K, red on 128K. $FF9A takes a 6-bit RGB code
 * directly, not a palette slot. */
#define BORDER_512K 2  /* dark green */
#define BORDER_128K 36 /* red */
#define BORDER_LOST 63 /* white: the server has gone quiet */

/* Walk cadence: ticks a held direction waits between steps. The Atari's
 * presets; V cycles them. */
#define WALK_PRESETS 5
#define DEFAULT_WALK 1
static const unsigned char walk_ticks[WALK_PRESETS] = { 6, 8, 10, 12, 15 };

/* PLAYER_STATE goes out at least this often (Atari NET_REALTIME_SEND_DELAY = 4
 * jiffies), and at once after a predicted step or a shot. The Lynx and
 * Intellivision use a 15-frame bare heartbeat, which suits their slower links. */
#define SEND_TICKS 4

/* Ticks between a shot's steps (Atari BULLET_DELAY = 3). */
#define BULLET_TICKS 3
#define WORLD_WAIT_TICKS 1200

static const unsigned char black_clut[16] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
};
/* Black but for the text color. */
static unsigned char wait_clut[16] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
};
static unsigned char f1_was_down = 0;
static unsigned char f2_was_down = 0;
static unsigned char g_is_512k;
static unsigned char g_display_target;
static unsigned char g_palette_id;
static unsigned char g_hud_owed;
static unsigned char g_border;
static unsigned char g_hw;          /* hardware-scroll renderer active */
static unsigned char window_key_was = 0; /* OVL_* + 1 of the key held, or 0 */
static unsigned g_ovl_send_clk;
static struct ovl_handoff g_handoff;
static unsigned char g_items_saved;

static void apply_palette(void)
{
    gime_set_palette(coco_clut[g_palette_id][g_display_target]);
}

/* F1 is the dedicated in-game display-target toggle key (no options/
 * pause screen exists anywhere in this codebase to put it on instead).
 * Only the palette needs reapplying -- tile data references palette
 * indices, not raw colors, so no redraw is needed either RAM path. */
static void check_display_toggle(void)
{
    unsigned char down = isKeyPressed(KEY_PROBE_F1, KEY_BIT_F1) ? 1 : 0;

    if (down && !f1_was_down) {
        g_display_target = display_target_toggle();
        apply_palette();
        hud_note(g_display_target == DISPLAY_COMPOSITE ? "CMP" : "RGB",
                 getTimer());
    }
    f1_was_down = down;
}

/* F2 turns sound on and off; the HUD's note shows which. */
static void check_sound_toggle(void)
{
    unsigned char down = isKeyPressed(KEY_PROBE_F2, KEY_BIT_F2) ? 1 : 0;

    if (down && !f2_was_down) {
        sound_on ^= 1;
        pref_sound_save(sound_on);
        hud_set_sound(sound_on);
    }
    f2_was_down = down;
}

/* The server's MESSAGE ids that sound (Atari sfx_message_map). */
static void message_sound(unsigned char id)
{
    if (id == 5 || id == 15) {         /* beaver or goblin killed */
        sound_play(SND_KILL);
    } else if (id == 10) {             /* level up */
        sound_play(SND_LEVELUP);
    } else if (id >= 11 && id <= 13) { /* died; respawned */
        sound_play(SND_DEATH);
    }
}

static void set_border(unsigned char code)
{
    g_border = code;
    *(unsigned char *)0xFF9A = code;
}

/* Brings the screen up to date with the renderer in use (mode: HW_PRESENT_*). */
static void present(unsigned char mode)
{
    if (g_hw) {
        hw_present(live_terrain.tiles, live_terrain.origin_x,
                   live_terrain.origin_y, view_x, view_y, &live_game, mode);
        return;
    }
    draw_world(live_terrain.tiles, live_terrain.origin_x, live_terrain.origin_y,
               (unsigned char)(view_x - live_terrain.origin_x),
               (unsigned char)(view_y - live_terrain.origin_y), &live_game,
               mode == HW_PRESENT_FULL);
    if (g_hud_owed != 0) {
        hud_blit(0);
        --g_hud_owed;
    }
    gime_flip_display();
}

/* BREAK leaves the game for BASIC's OK prompt: a warm start through the
 * reset vector, like the RESET button (restores text mode and the palette,
 * keeps memory, does not rerun AUTOEXEC). The loaded program overwrote the
 * BASIC program area, so that is emptied first, as NEW does. */
static void check_exit(void)
{
    unsigned txttab;

    if (!isKeyPressed(KEY_PROBE_BREAK, KEY_BIT_BREAK)) {
        return;
    }
    live_close();
    sound_shutdown();
    if (g_hw) {
        hw_leave();
    }
    *(unsigned char *)0xFF98 = 0; /* graphics mode off */
    txttab = *(unsigned *)0x19;
    *(unsigned *)txttab = 0;
    *(unsigned *)0x1B = txttab + 2; /* VARTAB */
    *(unsigned *)0x1D = txttab + 2; /* ARYTAB */
    *(unsigned *)0x1F = txttab + 2; /* ARYEND */
    asm {
        orcc #$50
        jmp [$FFFE]
    }
}

/* The renderers' code is saved at startup and put back after each overlay
 * window. On 128K, block 6 is BASIC's 80-column screen, so the save goes in
 * the HUD block between the image and the terrain fill buffer, which fits
 * all but hwscroll.c, never used on 128K (tools/ovl_region.py checks). */
#define SAVE_BLOCK_512K 6
#define SAVE_BLOCK_128K 7
#define SAVE_OFS_128K (HUD_IMAGE_STRIDE * HUD_LINES)
#define COPY_CHUNK 512

static unsigned region_len(void)
{
    return (unsigned)ovl_region_end - (unsigned)ovl_region_start;
}

/* Copies len bytes between low memory and block at ofs, a chunk per
 * bracket so interrupts are not held off for long. */
static void block_copy(unsigned char *low, unsigned char block, unsigned ofs,
                       unsigned len, unsigned char to_block)
{
    unsigned n;

    *(unsigned char *)0xFFAC = block;
    while (len != 0) {
        n = len;
        if (n > COPY_CHUNK) {
            n = COPY_CHUNK;
        }
        GFX_ENTER();
        if (to_block) {
            memcpy(GFX_WINDOW + ofs, low, n);
        } else {
            memcpy(low, GFX_WINDOW + ofs, n);
        }
        GFX_LEAVE();
        low += n;
        ofs += n;
        len -= n;
    }
}

static void region_save(unsigned char to_block)
{
    unsigned char *region = (unsigned char *)ovl_region_start;
    unsigned len = region_len();

    if (g_is_512k) {
        block_copy(region, SAVE_BLOCK_512K, 0, len, to_block);
    } else {
        if (len > TERRAIN_FILL_OFS - SAVE_OFS_128K) {
            len = TERRAIN_FILL_OFS - SAVE_OFS_128K;
        }
        block_copy(region, SAVE_BLOCK_128K, SAVE_OFS_128K, len, to_block);
    }
}

static void ovl_service(void)
{
    unsigned now = getTimer();

    live_pump();
    if ((unsigned)(now - g_ovl_send_clk) >= SEND_TICKS) {
        g_ovl_send_clk = now;
        live_send_state(live_facing, 0);
    }
    live_service();
}

static void ovl_clear(void)
{
    unsigned char row;

    for (row = 0; row < PLAYFIELD_ROWS; ++row) {
        GFX_ENTER();
        memset(GFX_WINDOW + (unsigned)row * TILE_ROW_BYTES, 0, TILE_ROW_BYTES);
        GFX_LEAVE();
    }
}

static void ovl_show(void)
{
    gime_flip_display();
    apply_palette();
}

static struct ovl_api g_ovl_api;

/* Runs an overlay window over the playfield, then restores the renderers. */
static void run_overlay(unsigned char which)
{
    struct ovl_header hdr;
    struct controls drain;
    unsigned char *region = (unsigned char *)ovl_region_start;
    unsigned char (*entry)(const struct ovl_api *, unsigned char);

    block_copy((unsigned char *)&hdr, OVL_BLOCK, 0, sizeof(hdr), 0);
    if (hdr.magic[0] != OVL_MAGIC0 || hdr.magic[1] != OVL_MAGIC1 ||
        hdr.load != (unsigned)region || hdr.len > region_len()) {
        return;
    }
    /* Everything until the window's first show() happens unseen. */
    gime_set_palette(black_clut);
    if (g_hw) {
        hw_leave(); /* before the copy: it lives in the region */
    }
    gime_select_buffers(g_is_512k);
    ovl_clear();
    hud_blit(1);
    block_copy(region, OVL_BLOCK, sizeof(hdr), hdr.len, 0);
    memset(region + hdr.len, 0, region_len() - hdr.len);
    gime_window_playfield();

    g_ovl_api.service = ovl_service;
    g_ovl_api.clear = ovl_clear;
    g_ovl_api.text = text_draw;
    g_ovl_api.show = ovl_show;
    g_ovl_api.fire_mask = controls_fire_mask();
    g_ovl_api.game = &live_game;
    g_ovl_api.pickup = &live_pickup_counter;
    g_ovl_api.decline = &live_dlg_decline;
    g_ovl_send_clk = getTimer();
    entry = (unsigned char (*)(const struct ovl_api *, unsigned char))hdr.entry;
    entry(&g_ovl_api, which);

    region_save(0);
    gime_window_playfield();
    /* Repaint the game unseen, as at startup. */
    gime_set_palette(black_clut);
    if (g_hw) {
        hw_init();
    }
    g_hud_owed = 2;
    present(HW_PRESENT_FULL);
    apply_palette();
    controls_read(&drain);
}

/* H, M and I open the help, map and inventory windows. */
static void check_window_keys(void)
{
    unsigned char key = 0;

    if (controls_keys_valid()) {
        if (isKeyPressed(KEY_PROBE_H, KEY_BIT_H)) {
            key = OVL_HELP + 1;
        } else if (isKeyPressed(KEY_PROBE_M, KEY_BIT_M)) {
            key = OVL_MAP + 1;
        } else if (isKeyPressed(KEY_PROBE_I, KEY_BIT_I)) {
            key = OVL_INVENTORY + 1;
        }
    }
    if (key != 0 && key != window_key_was) {
        run_overlay((unsigned char)(key - 1));
    }
    window_key_was = key;
}

/* Server-opened windows: a dialogue page, or a quest offer. They wait out a
 * map load, as on the Atari. */
static void check_server_windows(void)
{
    if (live_map_loading) {
        return;
    }
    if (live_game.dlg.request) {
        live_game.dlg.request = 0;
        run_overlay(OVL_DIALOGUE);
    } else if (live_game.message_dirty &&
               live_game.message_id == RTS_MSG_QUEST_OFFER) {
        run_overlay(OVL_QUEST_OFFER);
    }
}

/* Saves newly carried items; the inventory window lists only those. */
static void update_items_seen(void)
{
    if (live_game.inv.seen != g_items_saved) {
        g_items_saved = live_game.inv.seen;
        pref_items_seen_save(g_handoff.token, g_items_saved);
    }
}

/* Hit blinks tick once per loop pass: at this frame rate a 60 Hz count
 * (the Atari's) would end before a frame showed it. */
static void update_hit_flash(void)
{
    static unsigned char last_health = 0;
    unsigned char i;

    for (i = 0; i < live_game.beaver_count; ++i) {
        if (live_game.beavers[i].hit_timer != 0) {
            --live_game.beavers[i].hit_timer;
        }
    }
    if (live_game.health < last_health) {
        player_hit_timer = RTS_HIT_FLASH_FRAMES;
        sound_play(SND_HURT);
    } else if (player_hit_timer != 0) {
        --player_hit_timer;
    }
    last_health = live_game.health;
}

/* HUD walk speed: 1-5, 5 fastest. */
static void update_status(unsigned char walk_idx)
{
    hud_set_walk((unsigned char)(WALK_PRESETS - walk_idx));
}

/* The live game: input, prediction, sends, receive, camera, redraw -- in
 * the order the Atari client runs them. Never returns. */
static void game_loop(void)
{
    struct controls ctl;
    unsigned char repeat_dir = CTL_NONE;
    unsigned char aim = RTS_FACE_DOWN;
    unsigned char facing = RTS_FACE_DOWN;
    unsigned char walk_idx = DEFAULT_WALK;
    unsigned char fire_now;
    unsigned char input_now;
    unsigned char v_was_down = 0;
    unsigned char v_down;
    unsigned char lost_shown = 0;
    unsigned char pid;
    unsigned repeat_clk = 0;
    unsigned send_clk = getTimer();
    unsigned bullet_clk = getTimer();
    unsigned now;
    unsigned shown_vx = view_x;
    unsigned shown_vy = view_y;
    unsigned char have_frame = 1;
    unsigned char changed;
    unsigned char mode;
    unsigned char hud_new;

    for (;;) {
        live_pump();
        player_apply_correction_step();
        now = getTimer();
        sprite_anim = (unsigned char)((now >> 3) & 1); /* Atari RTCLOK & 8 */
        fire_now = 0;
        input_now = 0;

        if (!live_map_loading) {
            controls_read(&ctl);

            if (ctl.dir == CTL_NONE) {
                repeat_dir = CTL_NONE;
            } else {
                aim = ctl.dir;
                if (ctl.dir < RTS_FACE_FIRST_DIAGONAL) {
                    facing = ctl.dir;
                }
                /* A new direction steps at once; a held one waits out the
                 * cadence. The gate opens whether or not the step is legal,
                 * so walking into a wall does not delay turning away. */
                if (ctl.dir != repeat_dir ||
                    (unsigned)(now - repeat_clk) >= walk_ticks[walk_idx]) {
                    repeat_dir = ctl.dir;
                    repeat_clk = now;
                    player_try_move(ctl.dir);
                }
            }

            fire_now = ctl.fire;
            /* SPACE also talks to an adjacent NPC, as on the Atari. */
            if (ctl.fire || ctl.interact) {
                ++live_pickup_counter;
                live_game.dlg.closed = 0;
                input_now = 1;
            }
            if (ctl.pvp) {
                ++live_pvp_counter;
                input_now = 1;
            }

            v_down = controls_keys_valid() &&
                     isKeyPressed(KEY_PROBE_V, KEY_BIT_V) ? 1 : 0;
            if (v_down && !v_was_down) {
                walk_idx = (unsigned char)((walk_idx + 1) % WALK_PRESETS);
            }
            v_was_down = v_down;
        }
        check_display_toggle();
        check_sound_toggle();
        check_exit();
        check_window_keys();
        check_server_windows();
        update_items_seen();

        /* A predicted step or a button press goes out at once; otherwise the
         * state repeats on the heartbeat interval. */
        if (input_now || fire_now || player_send_pending ||
            (unsigned)(now - send_clk) >= SEND_TICKS) {
            send_clk = now;
            live_facing = facing;
            live_send_state(fire_now ? aim : facing, fire_now);
        }
        live_service();

        if (fire_now) {
            player_fire(aim);
            sound_play(SND_SHOOT);
        }
        if ((unsigned)(now - bullet_clk) >= BULLET_TICKS) {
            bullet_clk = now;
            player_tracers_step();
        }

        if (live_terrain_reset) {
            live_terrain_reset = 0;
            if ((unsigned)(player_x - view_x) >= VIEW_COLS ||
                (unsigned)(player_y - view_y) >= VIEW_ROWS) {
                player_snap(player_x, player_y);
            }
            have_frame = 0;
        }
        player_update_view();
        update_hit_flash();

        pid = live_map_palette;
        if (pid < PALETTE_ID_COUNT && pid != g_palette_id) {
            g_palette_id = pid;
            apply_palette();
        }
        if (!live_connected && !lost_shown) {
            lost_shown = 1;
            *(unsigned char *)0xFF9A = BORDER_LOST;
        } else if (live_connected && lost_shown) {
            lost_shown = 0;
            *(unsigned char *)0xFF9A = g_border;
        }

        update_status(walk_idx);
        hud_new = 0;
        if (live_game.message_dirty) {
            message_sound(live_game.message_id);
        }
        if (hud_update(&live_game, now)) {
            if (g_hw) {
                hw_hud_refresh();
                hud_new = 1;
            } else {
                hud_blit(1);
            }
        }

        if (live_map_loading) {
            continue;
        }
        /* Present only when something on screen changed. */
        changed = sprites_update(&live_game, view_x, view_y, player_x,
                                 player_y, live_facing);
        if (!have_frame || changed || view_x != shown_vx ||
            view_y != shown_vy || live_game.tile_changed || hud_new) {
            if (!have_frame) {
                mode = HW_PRESENT_FULL;
            } else if (live_game.tile_changed) {
                mode = HW_PRESENT_TILES;
            } else {
                mode = HW_PRESENT_MOVE;
            }
            present(mode);
            have_frame = 1;
            shown_vx = view_x;
            shown_vy = view_y;
            live_game.tile_changed = 0;
            live_game.changed_n = 0;
        }
    }
}

/* Leaves graphics mode, shows msg, and reboots into the setup program. */
static void show_text(unsigned char col, const char *msg)
{
    display_text_colors(); /* before width() too, so no other colors show */
    width(80);
    display_text_colors();
    locate(col, 11);
    while (*msg) {
        putchar(*msg++);
    }
}

static void fail(const char *msg)
{
    sound_shutdown();
    *(unsigned char *)0xFF98 = 0; /* graphics mode off */
    show_text(0, msg);
    putchar('\r');
    waitkey(0);
    coldStart();
}

int main(void)
{
    unsigned char t;

    initCoCoSupport();
    *(unsigned char *)0xFFD9 = 0; /* 1.79 MHz */
    t = display_target_saved();
    g_display_target = t == DISPLAY_UNSET ? DISPLAY_RGB : t;

    /* Graphics mode from the start: on 128K the 80-column text screen is the
     * art block. Nothing but "Please wait..." shows until the first paint. */
    set_border(0);
    gime_set_palette(black_clut);
    gime_init_mode();
    g_is_512k = ram_probe_is_512k();
    region_save(1);
    gime_select_buffers(g_is_512k);
    hud_init();
    ovl_clear();
    text_draw(13, 11, "Please wait...");
    hud_blit(1);
    gime_window_playfield();
    wait_clut[3] = g_display_target == DISPLAY_COMPOSITE ? 48 : 63;
    gime_set_palette(wait_clut);

    block_copy((unsigned char *)&g_handoff, OVL_BLOCK, OVL_HANDOFF_OFS,
               sizeof(g_handoff), 0);
    if (g_handoff.magic != OVL_HANDOFF_MAGIC) {
        fail("No saved login. Press a key.");
    }
    g_items_saved = g_handoff.items_seen;
    if (!live_connect(g_handoff.host, g_handoff.token)) {
        fail("Cannot reach server. Press a key.");
    }

    if (!live_wait_ready(WORLD_WAIT_TICKS)) {
        fail("No world data. Press a key.");
    }

    block_copy(wait_clut, ART_BLOCK, 0, 2, 0);
    if (wait_clut[0] != ART_MAGIC0 || wait_clut[1] != ART_MAGIC1) {
        fail("No art loaded. Press a key.");
    }

    /* The first paint happens unseen. */
    gime_set_palette(black_clut);
    g_palette_id = PALETTE_ID_OVERWORLD;
    live_game.inv.seen |= g_items_saved;
    g_hud_owed = 2;
    hud_init();
    g_hw = g_is_512k; /* hardware scrolling needs the 512K ring blocks */
    if (g_hw) {
        hw_init();
    }

    player_snap(live_game.player_x, live_game.player_y);
    player_update_view();
    update_status(DEFAULT_WALK);
    sound_on = pref_sound_load();
    hud_set_sound(sound_on);
    sound_init();
    hud_update(&live_game, getTimer());
    live_terrain_reset = 0;
    live_game.tile_changed = 0;
    live_game.changed_n = 0;
    sprites_update(&live_game, view_x, view_y, player_x, player_y, live_facing);
    present(HW_PRESENT_FULL);
    if (live_map_palette < PALETTE_ID_COUNT) {
        g_palette_id = live_map_palette;
    }
    apply_palette();
    set_border(g_is_512k ? BORDER_512K : BORDER_128K);
    game_loop();

    return 0;
}
