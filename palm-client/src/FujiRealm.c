/*
 * FujiRealm for Palm OS -- FN Realm in the launcher.
 *
 * Same server and wire protocol as the Atari 8-bit, Lynx and Amiga clients:
 * $BF bootstrap packets, then realtime v3 COBS/CRC-16 frames, over TCP. The
 * protocol, bootstrap, terrain-cache, prediction and dialogue logic is
 * shared unchanged from lynx-client/src, and the login identity record from
 * amiga-client/src/identity.c. This file is the Palm's flow and game loop,
 * gfx.c its screen, and net.c its transport: TCP through FujiNet's N1:
 * device, over the selected cradle transport.
 *
 * The game runs inside the Palm event loop: every pass takes one event (or a
 * nilEvent after a tick) and then runs one game_step(). Timers run on
 * TimGetTicks(), never on loop counts.
 *
 * int is 16 bits here, as on the Lynx, which the shared code expects.
 */
#include <PalmOS.h>

#include "bootstrap.h"
#include "dlgmodal.h"
#include "fn_types.h"
#include "gfx.h"
#include "identity.h"
#include "net.h"
#include "palm_art.h"
#include "predict.h"
#include "rt_state.h"
#include "FujiRealmRsc.h"

#ifndef SERVER_HOST
#define SERVER_HOST "fujinet.online"
#endif
#ifndef HYBRID_SERVER_PORT
#define HYBRID_SERVER_PORT 9000
#endif
#ifndef LOGIN_SERVER_PORT
#define LOGIN_SERVER_PORT 9010
#endif

#define CREATOR APP_CREATOR
#define PREFS_ID 1
#define PREFS_VERSION 3
#define HOST_LEN 48
#define RECORD_LEN 72

/* $BF packets (docs/PROTOCOL.md). */
#define NET_MAGIC 0xBF
#define NET_VERSION 1
#define LOGIN_REQUEST 0xA0
#define LOGIN_RESPONSE 0xA1
#define NET_HELLO 0x01
#define LOGIN_OK 0
#define LOGIN_USERNAME_TAKEN 1
#define LOGIN_FAILED 0xFF
/* Server output budget: 0 is the default (Atari, 2,000 B/s), which the
 * cradle link carries comfortably. */
#define LINK_PROFILE 0

/* Timers, in milliseconds. */
#define HEARTBEAT_MS 500
#define RESYNC_RETRY_MS 2000
#define COMMIT_RETRY_MS 2000
#define MAP_SYNC_TIMEOUT_MS 6000
#define TRACER_STEP_MS 60
#define HIT_FLASH_STEP_MS 60
#define ANIM_MS 400
#define HELLO_RETRY_MS 3000
#define HELLO_MAX_TRIES 6
#define BOOTSTRAP_TIMEOUT_MS 30000
#define LOGIN_TIMEOUT_MS 10000
#define INITIAL_ART_WAIT_MS 600
/* Keep the link drained: never let more than this pass between polls. */
#define POLL_MIN_MS 40

#define FACE_NONE 0xFF
/* Tile ids (docs/TILE_ALLOCATION.md) predict.h does not name. */
#define TILE_PUMP_CONTROLS 50
#define TILE_WILHELM_WORKING 51

/* One step in each RTS_FACE_* direction. The same as predict.c's
 * predict_shot_dx/dy, which this file must not read: m68k-palmos-gcc keeps
 * const data in the code section, where another file can only reach it
 * PC-relative; from here it would be read A5-relative, from the wrong
 * memory (see the Makefile's segment check). */
static const signed char step_dx[RTS_FACE_COUNT] = { 0, 0, -1, 1, -1, 1, -1, 1 };
static const signed char step_dy[RTS_FACE_COUNT] = { -1, 1, 0, 0, -1, -1, 1, 1 };
#define CAM_MARGIN_X 5
#define CAM_MARGIN_Y 4
#define MAP_OVERWORLD 0

/* The four application keys keep their physical keyBitHard1..4 positions
 * even if the owner reassigns their launcher applications. */
#define BUTTONS_PRISM 0
#define BUTTONS_ORIGINAL 1
#define BUTTONS_COUNT 2
#define KEY_UP keyBitPageUp
#define KEY_DOWN keyBitPageDown
#define KEY_LEFT  (prefs.buttons == BUTTONS_PRISM ? keyBitHard2 : keyBitHard1)
#define KEY_RIGHT (prefs.buttons == BUTTONS_PRISM ? keyBitHard3 : keyBitHard2)
#define KEY_FIRE  (prefs.buttons == BUTTONS_PRISM ? keyBitHard4 : keyBitHard3)
#define KEY_USE   (prefs.buttons == BUTTONS_PRISM ? keyBitHard1 : keyBitHard4)
#define GAME_KEYS (KEY_UP | KEY_DOWN | keyBitHard1 | keyBitHard2 | \
                   keyBitHard3 | keyBitHard4)

typedef struct {
    char host[HOST_LEN];
    char name[NAME_MAX + 1];
    char record[RECORD_LEN];    /* identity_format(): name,token,host */
    UInt8 link;
    UInt8 buttons;
} RealmPrefs;

typedef struct {
    char host[HOST_LEN];
    char name[NAME_MAX + 1];
    char record[RECORD_LEN];
    UInt8 link;
} RealmPrefsV2;

typedef struct {
    char host[HOST_LEN];
    char name[NAME_MAX + 1];
    char record[RECORD_LEN];
} RealmPrefsV1;

static const char *const link_names[NET_LINK_COUNT] = {
    "Legacy cradle", "USB Library", "BuiltIn SerLib", "Serial Library"
};
static const char *const button_names[BUTTONS_COUNT] = {
    "Prism", "Original"
};

/* ------------------------------------------------------------------ */
/* State                                                               */

static RealmPrefs prefs;
static UInt32 tps;

static struct net_stream link;
static struct identity me;
static struct bf_parser bf;
static struct bf_packet packet;
static struct bootstrap_state boot;
static struct bootstrap_fill fill;
static struct rt_state game;
static struct predict_state predict;

static unsigned char wire[RTS_MAX_RAW + 2];
static unsigned char rx_encoded[RTS_WORKSPACE + 8];
static unsigned char rx_raw[RTS_WORKSPACE];
static unsigned char rx_encoded_len;

static unsigned client_seq;
static unsigned char fire_counter, pickup_counter, pvp_toggle_counter;
static unsigned char fire_latch, use_latch;
static unsigned char facing = RTS_FACE_DOWN, aim_dir = RTS_FACE_DOWN;
static unsigned char fire_aim = RTS_FACE_DOWN;
static unsigned char move_last_dir = FACE_NONE, input_prev_dir = FACE_NONE;
static unsigned char buffered_dir = FACE_NONE;
static unsigned long world_tick, move_last_world;

static unsigned char current_map_id;
static unsigned char map_loading, map_sync, resync_pending;
static UInt32 heartbeat_due, resync_due, commit_due, map_sync_deadline;
static UInt32 tracer_due, hit_due, anim_base, last_poll;
static unsigned char last_anim;

static unsigned char cam_x, cam_y;
static unsigned cam_origin_x, cam_origin_y;
static unsigned long last_view_key;
static unsigned char world_dirty, hud_dirty;
static unsigned char dlg_ack_pending, dlg_ack_retry;

static unsigned long corrections, resyncs, bad_frames;
static unsigned char show_diag;

/* App flow. */
static Boolean playing;         /* game_step() runs every pass */
static Boolean start_pending;   /* the game form is up: connect next pass */
static Boolean draw_ok = true;  /* false while a menu or alert covers us */
/* The system or a menu handled this pass's event and may have just drawn
 * over us; its winExitEvent only arrives next pass, so hold the frame. */
static Boolean ui_busy;
static Boolean need_login;
static FormType *game_form;

/* Input. */
static UInt32 keys;
static Int16 pen_x, pen_y;
static Boolean pen_down, pen_prev;
static unsigned char pen_mode;  /* what the current stroke does */
#define PEN_NONE 0
#define PEN_WALK 1
#define PEN_DONE 2
/* What a tap asks handle_input for. */
#define PEN_ACT_NONE 0
#define PEN_ACT_USE 1
#define PEN_ACT_FIRE 2
static unsigned char target_active, target_x, target_y, target_talk;

/* Dialogue (non-modal: one step per pass). */
static struct dlg_modal modal;
static Boolean dlg_open, dlg_redraw;

/* ------------------------------------------------------------------ */
/* Clock                                                               */

static UInt32 ms(UInt32 milliseconds)
{
    return milliseconds * tps / 1000;
}

static int due(UInt32 deadline)
{
    return (Int32)(TimGetTicks() - deadline) >= 0;
}

/* ------------------------------------------------------------------ */
/* Messages                                                            */

static void show_error(const char *what, const char *detail)
{
    FrmCustomAlert(MessageAlert, what, detail ? "\n" : "", detail ? detail : "");
}

static void show_link_error(const char *what)
{
    char detail[64];

    net_error_text(&link, detail);
    show_error(what, detail);
}

/* ------------------------------------------------------------------ */
/* Boot screen                                                         */

#define BOOT_TOP 58
#define BOOT_LINE_H 11

static Int16 boot_y = BOOT_TOP;

static void boot_title(void)
{
    static const char title[] = "FUJINET REALMS";
    const char *sub = "Palm OS  -  FujiNet N1:";
    Int16 sub_len = StrLen(sub);
    FontID old;

    gfx_clear();
    old = FntSetFont(boldFont);
    WinDrawChars(title, sizeof title - 1,
                 (SCREEN_W - FntCharsWidth(title, sizeof title - 1)) / 2, 4);
    FntSetFont(stdFont);
    WinDrawChars(sub, sub_len, (SCREEN_W - FntCharsWidth(sub, sub_len)) / 2, 17);
    FntSetFont(old);
    gfx_sprite_at(52, 34, 0);                   /* the hero, facing us */
    gfx_sprite_at(72, 34, ART_SPRITE_GOBLIN);
    gfx_sprite_at(92, 34, ART_SPRITE_ITEM_GOLD);
    boot_y = BOOT_TOP;
}

/* One status line: "label" then a result drawn by boot_result. */
static void boot_step(const char *label)
{
    if (boot_y > SCREEN_H - BOOT_LINE_H) {
        gfx_fill(0, BOOT_TOP, SCREEN_W, SCREEN_H - BOOT_TOP, 0);
        boot_y = BOOT_TOP;
    }
    gfx_fill(0, boot_y, SCREEN_W, BOOT_LINE_H, 0);
    gfx_text(4, boot_y, label, 0);
}

static void boot_note(const char *text)
{
    gfx_fill(110, boot_y, SCREEN_W - 110, BOOT_LINE_H, 0);
    gfx_text_right(SCREEN_W - 4, boot_y, text);
}

static void boot_result(const char *text)
{
    boot_note(text);
    boot_y += BOOT_LINE_H;
}

/* ------------------------------------------------------------------ */
/* $BF packets                                                         */

static unsigned char sum8(const unsigned char *buf, unsigned len)
{
    unsigned char s = 0;

    while (len--)
        s = (unsigned char)(s + *buf++);
    return s;
}

static unsigned build_bf(unsigned char type, const unsigned char *payload,
                         unsigned char len, unsigned char *frame)
{
    unsigned n = 0;

    frame[n++] = NET_MAGIC;
    frame[n++] = NET_VERSION;
    frame[n++] = type;
    frame[n++] = len;
    MemMove(frame + n, payload, len);
    n += len;
    frame[n] = sum8(frame, n);
    return n + 1;
}

/* ------------------------------------------------------------------ */
/* Login                                                               */

static unsigned char login(void)
{
    struct net_stream *s = &link;
    unsigned char payload[NAME_MAX + 1];
    unsigned char frame[NAME_MAX + 8];
    unsigned char name_len = (unsigned char)StrLen(me.name);
    UInt32 deadline;
    unsigned char byte;
    unsigned i;

    if (net_open(s, prefs.host, LOGIN_SERVER_PORT) != 0)
        return LOGIN_FAILED;
    payload[0] = name_len;
    MemMove(payload + 1, me.name, name_len);
    if (net_write(s, frame, build_bf(LOGIN_REQUEST, payload, name_len + 1, frame))) {
        net_close(s);
        return LOGIN_FAILED;
    }
    bf_parser_init(&bf);
    deadline = TimGetTicks() + ms(LOGIN_TIMEOUT_MS);
    while (!due(deadline)) {
        if (net_poll(s) < 0)
            break;
        while (net_get(s, &byte)) {
            if (bf_parser_feed(&bf, byte, &packet) != BF_FEED_PACKET ||
                packet.type != LOGIN_RESPONSE)
                continue;
            net_close(s);
            if (packet.payload_len < 2)
                return LOGIN_FAILED;
            if (packet.payload[0] != LOGIN_OK)
                return packet.payload[0];
            if (packet.payload[1] > TOKEN_MAX ||
                packet.payload[1] + 2 > packet.payload_len)
                return LOGIN_FAILED;
            for (i = 0; i < packet.payload[1]; ++i)
                me.token_ascii[i] = (char)packet.payload[2 + i];
            me.token_ascii[i] = '\0';
            me.token = identity_token_value(me.token_ascii);
            return me.token ? LOGIN_OK : LOGIN_FAILED;
        }
        SysTaskDelay(2);
    }
    net_close(s);
    return LOGIN_FAILED;
}

/* ------------------------------------------------------------------ */
/* Bootstrap                                                           */

static void send_hello(void)
{
    unsigned char payload[7];
    unsigned char frame[16];

    payload[0] = LINK_PROFILE;
    payload[1] = 1;
    payload[2] = 0;
    payload[3] = (unsigned char)(me.token & 0xFF);
    payload[4] = (unsigned char)((me.token >> 8) & 0xFF);
    payload[5] = (unsigned char)((me.token >> 16) & 0xFF);
    payload[6] = (unsigned char)((me.token >> 24) & 0xFF);
    net_write(&link, frame, build_bf(NET_HELLO, payload, sizeof payload, frame));
}

/* HELLO -> WELCOME + 24 terrain rows. 1 when the window is complete. */
static int bootstrap(void)
{
    UInt32 deadline = TimGetTicks() + ms(BOOTSTRAP_TIMEOUT_MS);
    UInt32 retry = TimGetTicks() + ms(HELLO_RETRY_MS);
    int tries = 1;
    unsigned char byte;
    char rows[8];

    bf_parser_init(&bf);
    bootstrap_init(&boot);
    send_hello();
    while (!due(deadline)) {
        int got = net_poll(&link);

        if (got < 0)
            return 0;
        while (net_get(&link, &byte)) {
            signed char applied;

            if (bf_parser_feed(&bf, byte, &packet) != BF_FEED_PACKET)
                continue;
            applied = bootstrap_apply(&boot, &packet);
            if (applied == BOOTSTRAP_ERROR)
                return 0;
            if (applied == BOOTSTRAP_COMPLETE)
                return 1;
        }
        if (got > 0) {
            unsigned count = 0, r;

            for (r = 0; r < BOOTSTRAP_WINDOW_H; ++r)
                count += (unsigned)((boot.rows_received >> r) & 1);
            StrPrintF(rows, "%u/24", count);
            boot_note(rows);
            retry = TimGetTicks() + ms(HELLO_RETRY_MS);
        } else if (due(retry) && tries < HELLO_MAX_TRIES) {
            /* The server restarts a bootstrap per HELLO; a lost one is cheap
             * to repeat. */
            send_hello();
            ++tries;
            retry = TimGetTicks() + ms(HELLO_RETRY_MS);
        } else {
            SysTaskDelay(2);
        }
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* Realtime sends                                                      */

static int send_frame(unsigned len)
{
    return net_write(&link, wire, len) == 0;
}

static int send_player_state(unsigned char aim, unsigned char buttons)
{
    ++client_seq;
    return send_frame(rt_build_player_state(wire, client_seq, game.player_x,
                                            game.player_y, aim, buttons,
                                            fire_counter, pickup_counter,
                                            game.last_server_seq,
                                            pvp_toggle_counter));
}

static void send_resync_request(void)
{
    unsigned char fx = 0, fy = 0, fid = 0;
    unsigned long rows_have = 0;

    if (fill.active) {
        fx = (unsigned char)fill.origin_x;
        fy = (unsigned char)fill.origin_y;
        fid = fill.fill_id;
        rows_have = fill.rows_have;
    }
    ++client_seq;
    send_frame(rt_build_resync_request(wire, client_seq,
                                       (unsigned char)boot.origin_x,
                                       (unsigned char)boot.origin_y, fx, fy,
                                       rows_have, fid, 0));
    boot.revision_trust_next = 1;
    resync_pending = 1;
    resync_due = TimGetTicks() + ms(RESYNC_RETRY_MS);
    ++resyncs;
}

static void send_map_ready(void)
{
    ++client_seq;
    send_frame(rt_build_map_ready(wire, client_seq, current_map_id,
                                  (unsigned char)boot.origin_x,
                                  (unsigned char)boot.origin_y));
}

static void service_cache_retries(void)
{
    if (boot.commit_pending && due(commit_due)) {
        ++client_seq;
        send_frame(rt_build_window_commit(wire, client_seq, boot.commit_fill_id,
                                          (unsigned char)boot.origin_x,
                                          (unsigned char)boot.origin_y,
                                          current_map_id, 1));
        commit_due = TimGetTicks() + ms(COMMIT_RETRY_MS);
    }
    if (resync_pending && due(resync_due))
        send_resync_request();
}

/* ------------------------------------------------------------------ */
/* Camera                                                              */

static void center_camera(void)
{
    unsigned char rel;

    rel = (unsigned char)(game.player_x - (unsigned char)boot.origin_x);
    cam_x = rt_camera(rel >= RTS_WINDOW_W ? RTS_WINDOW_W - 1 : rel, RTS_WINDOW_W,
                      VIEW_COLS);
    rel = (unsigned char)(game.player_y - (unsigned char)boot.origin_y);
    cam_y = rt_camera(rel >= RTS_WINDOW_H ? RTS_WINDOW_H - 1 : rel, RTS_WINDOW_H,
                      VIEW_ROWS);
    cam_origin_x = boot.origin_x;
    cam_origin_y = boot.origin_y;
}

/* Keep the same ground under a held camera when the window origin shifts,
 * then apply the hysteresis band. As the Lynx game loop. */
static void track_camera(void)
{
    unsigned shift;
    unsigned char rel;

    if (boot.origin_x != cam_origin_x) {
        if (boot.origin_x > cam_origin_x) {
            shift = boot.origin_x - cam_origin_x;
            cam_x = shift < cam_x ? (unsigned char)(cam_x - shift) : 0;
        } else {
            shift = cam_origin_x - boot.origin_x;
            cam_x = shift + cam_x < RTS_WINDOW_W - VIEW_COLS ?
                (unsigned char)(cam_x + shift) : RTS_WINDOW_W - VIEW_COLS;
        }
        cam_origin_x = boot.origin_x;
    }
    if (boot.origin_y != cam_origin_y) {
        if (boot.origin_y > cam_origin_y) {
            shift = boot.origin_y - cam_origin_y;
            cam_y = shift < cam_y ? (unsigned char)(cam_y - shift) : 0;
        } else {
            shift = cam_origin_y - boot.origin_y;
            cam_y = shift + cam_y < RTS_WINDOW_H - VIEW_ROWS ?
                (unsigned char)(cam_y + shift) : RTS_WINDOW_H - VIEW_ROWS;
        }
        cam_origin_y = boot.origin_y;
    }
    rel = (unsigned char)(game.player_x - (unsigned char)boot.origin_x);
    if (rel >= RTS_WINDOW_W)
        rel = RTS_WINDOW_W - 1;
    cam_x = rt_camera_track(cam_x, rel, RTS_WINDOW_W, VIEW_COLS, CAM_MARGIN_X);
    rel = (unsigned char)(game.player_y - (unsigned char)boot.origin_y);
    if (rel >= RTS_WINDOW_H)
        rel = RTS_WINDOW_H - 1;
    cam_y = rt_camera_track(cam_y, rel, RTS_WINDOW_H, VIEW_ROWS, CAM_MARGIN_Y);
}

/* ------------------------------------------------------------------ */
/* Realtime receive                                                    */

static void apply_frame(unsigned char raw_len)
{
    unsigned char applied = rt_apply(&game, boot.terrain, boot.origin_x,
                                     boot.origin_y, rx_raw, raw_len);

    if (applied == RTS_INVALID) {
        ++bad_frames;
        return;
    }
    if (applied == 0)
        return;
    world_dirty = 1;
    if (applied == RTS_WORLD_STATE) {
        ++world_tick;
        if (map_sync) {
            /* Waiting for the server to accept our spawn echo: a frame with
             * no correction means it has. */
            if (game.correction_flags == 0)
                map_sync = 0;
            predict_init(&predict, game.player_x, game.player_y);
        } else if (!map_loading &&
                   predict_reconcile(&predict, game.player_x, game.player_y,
                                     game.correction_flags, game.echo_client_seq,
                                     boot.terrain, boot.origin_x, boot.origin_y,
                                     &game)) {
            ++corrections;
        }
        game.player_x = predict.x;
        game.player_y = predict.y;
    } else if (applied == RTS_TERRAIN_EDGE) {
        if (!fill.active) {
            signed char r = bootstrap_apply_terrain_edge(
                &boot, game.edge.origin_x, game.edge.origin_y, game.edge.width,
                game.edge.height, game.edge.revision, game.edge.tiles,
                game.edge.tile_count);

            if (r == BOOTSTRAP_EDGE_APPLIED || r == BOOTSTRAP_EDGE_DUPLICATE) {
                ++client_seq;
                send_frame(rt_build_cache_step_ack(wire, client_seq, boot.revision,
                                                   (unsigned char)boot.origin_x,
                                                   (unsigned char)boot.origin_y));
                resync_pending = 0;
            } else {
                send_resync_request();
            }
        }
    } else if (applied == RTS_WINDOW_ROW) {
        signed char r = bootstrap_fill_apply_row(
            &fill, game.window_row.fill_id, game.window_row.origin_x,
            game.window_row.origin_y, game.window_row.row_index,
            game.window_row.tiles);

        if (r != BOOTSTRAP_FILL_IGNORED)
            resync_due = TimGetTicks() + ms(RESYNC_RETRY_MS);  /* real progress */
        if (r == BOOTSTRAP_FILL_COMPLETE) {
            bootstrap_fill_activate(&fill, &boot);
            predict.count = 0;
            resync_pending = 0;
            commit_due = TimGetTicks();
            if (map_loading) {
                predict_init(&predict, game.player_x, game.player_y);
                send_map_ready();
                map_loading = 0;
                map_sync = 1;
                map_sync_deadline = TimGetTicks() + ms(MAP_SYNC_TIMEOUT_MS);
                heartbeat_due = TimGetTicks();
                center_camera();
                game.message_dirty = 1;
                hud_dirty = 1;
            }
        }
    } else if (applied == RTS_WINDOW_COMMIT_ACK) {
        if (bootstrap_commit_ack_matches(&boot, game.window_commit_ack.fill_id,
                                         game.window_commit_ack.origin_x,
                                         game.window_commit_ack.origin_y))
            boot.commit_pending = 0;
    } else if (applied == RTS_MAP_CHANGE) {
        /* Resent every ~2 s until MAP_READY; see the Lynx client for why the
         * three cases must stay distinct. */
        if (game.map_change.map_id == current_map_id) {
            if (!map_loading)
                send_map_ready();
        } else {
            current_map_id = game.map_change.map_id;
            game.player_x = game.map_change.spawn_x;
            game.player_y = game.map_change.spawn_y;
            predict_init(&predict, game.player_x, game.player_y);
            gfx_set_palette(game.map_change.palette_id);
            fill.active = 0;
            boot.commit_pending = 0;
            MemSet(game.tracers, sizeof game.tracers, 0);
            map_loading = 1;
            resync_pending = 1;
            resync_due = TimGetTicks() + ms(RESYNC_RETRY_MS);
            hud_dirty = 1;
        }
    } else if (applied == RTS_HUD_UPDATE || applied == RTS_MESSAGE ||
               applied == RTS_QUEST_UPDATE) {
        hud_dirty = 1;
    }
}

static void realtime_pump(void)
{
    unsigned char byte;

    while (net_get(&link, &byte)) {
        if (byte != 0) {
            if (rx_encoded_len < sizeof rx_encoded)
                rx_encoded[rx_encoded_len++] = byte;
            else
                rx_encoded_len = 0;     /* oversized: resync on next zero */
            continue;
        }
        if (rx_encoded_len != 0) {
            unsigned char raw_len = rt_cobs_decode(rx_encoded, rx_encoded_len,
                                                   rx_raw);

            rx_encoded_len = 0;
            apply_frame(raw_len);
        }
    }
}

/* One network exchange if due, then parse whatever arrived. Drains up to a
 * few chunks back-to-back when the server has more waiting. */
static int pump_link(int force)
{
    int got, rounds = 0;

    if (!force && !due(last_poll + ms(POLL_MIN_MS)))
        return 0;
    do {
        got = net_poll(&link);
        last_poll = TimGetTicks();
        if (got < 0)
            return -1;
        realtime_pump();
    } while (got >= 200 && ++rounds < 4);
    return 0;
}

/* ------------------------------------------------------------------ */
/* Input                                                               */

static void input_poll(void)
{
    keys = KeyCurrentState();
    EvtGetPen(&pen_x, &pen_y, &pen_down);
}

/* RTS_FACE_* for a unit step (sx, sy), or FACE_NONE for (0, 0). */
static unsigned char face_for(int sx, int sy)
{
    static const unsigned char table[3][3] = {
        /* sy -1 */ {RTS_FACE_UP_LEFT, RTS_FACE_UP, RTS_FACE_UP_RIGHT},
        /* sy  0 */ {RTS_FACE_LEFT, FACE_NONE, RTS_FACE_RIGHT},
        /* sy  1 */ {RTS_FACE_DOWN_LEFT, RTS_FACE_DOWN, RTS_FACE_DOWN_RIGHT},
    };
    return table[sy + 1][sx + 1];
}

static unsigned char input_dir(void)
{
    int sx = 0, sy = 0;

    if (keys & KEY_LEFT)
        --sx;
    if (keys & KEY_RIGHT)
        ++sx;
    if (keys & KEY_UP)
        --sy;
    if (keys & KEY_DOWN)
        ++sy;
    return face_for(sx, sy);
}

static int sgn(int v)
{
    return v > 0 ? 1 : v < 0 ? -1 : 0;
}

/* Aim: the nearest of the eight directions, so a tap a little off-axis
 * still shoots straight. */
static unsigned char aim_toward(int dx, int dy)
{
    int ax = dx < 0 ? -dx : dx, ay = dy < 0 ? -dy : dy;

    if (ax >= 2 * ay)
        dy = 0;
    else if (ay >= 2 * ax)
        dx = 0;
    return face_for(sgn(dx), sgn(dy));
}

static int pointer_tile(unsigned char *wx, unsigned char *wy)
{
    if (!pen_down || pen_x < 0 || pen_y < 0 || pen_x >= VIEW_W || pen_y >= VIEW_H)
        return 0;
    *wx = (unsigned char)(boot.origin_x + cam_x + pen_x / TILE_PX);
    *wy = (unsigned char)(boot.origin_y + cam_y + pen_y / TILE_PX);
    return 1;
}

static unsigned char entity_at(unsigned char x, unsigned char y)
{
    unsigned char i;

    for (i = 0; i < game.beaver_count; ++i)
        if (game.beavers[i].hp && game.beavers[i].x == x && game.beavers[i].y == y)
            return 1;
    for (i = 0; i < game.remote_count; ++i)
        if ((game.remotes[i].state & RTS_REMOTE_ALIVE) &&
            game.remotes[i].x == x && game.remotes[i].y == y)
            return 1;
    return 0;
}

static void update_tracers(void)
{
    unsigned char i;

    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        struct rt_tracer *t = &game.tracers[i];
        unsigned char nx, ny;

        if (!t->active)
            continue;
        world_dirty = 1;
        if (t->steps >= RTS_BULLET_RANGE) {
            t->active = 0;
            continue;
        }
        nx = t->x;
        ny = t->y;
        if (!predict_shot_step(&nx, &ny, t->dir, boot.terrain, boot.origin_x,
                               boot.origin_y) ||
            (nx == game.player_x && ny == game.player_y) || entity_at(nx, ny)) {
            t->active = 0;
            continue;
        }
        t->x = nx;
        t->y = ny;
        ++t->steps;
    }
}

static void fire_at(unsigned char aim)
{
    ++fire_counter;
    fire_aim = aim_dir = aim;
    if (aim < RTS_FACE_FIRST_DIAGONAL)
        facing = aim;
    rt_spawn_tracer(&game, game.player_x, game.player_y, fire_aim);
    world_dirty = 1;
}

/* Terrain tiles that are people (or the pump controls): tapping one walks
 * you next to it and talks, as Use does beside them on the other clients.
 * The server talks to any NPC one orthogonal step away (game.py
 * _nearest_adjacent_npc); facing does not matter. */
static unsigned char npc_tile(unsigned char tile)
{
    return tile == PREDICT_TILE_FARMER || tile == PREDICT_TILE_GOBLIN_NPC ||
           (tile >= PREDICT_TILE_DANIEL && tile <= PREDICT_TILE_NERISSA) ||
           tile == TILE_PUMP_CONTROLS || tile == TILE_WILHELM_WORKING;
}

static unsigned char tile_at(unsigned char x, unsigned char y)
{
    unsigned char rx = (unsigned char)(x - (unsigned char)boot.origin_x);
    unsigned char ry = (unsigned char)(y - (unsigned char)boot.origin_y);

    if (rx >= RTS_WINDOW_W || ry >= RTS_WINDOW_H)
        return 0xFF;
    return boot.terrain[(unsigned)ry * RTS_WINDOW_W + rx];
}

static unsigned char friendly_kind(unsigned char kind)
{
    return kind == RTS_KIND_WILHELM || kind == RTS_KIND_WILHELM_WORKING;
}

/* Something a tap should shoot: a live monster, or a player once PvP is on. */
static unsigned char hostile_at(unsigned char x, unsigned char y)
{
    unsigned char i;

    for (i = 0; i < game.beaver_count; ++i)
        if (game.beavers[i].hp && !friendly_kind(game.beavers[i].kind) &&
            game.beavers[i].x == x && game.beavers[i].y == y)
            return 1;
    if (!game.hud_pvp_enabled)
        return 0;
    for (i = 0; i < game.remote_count; ++i)
        if ((game.remotes[i].state & RTS_REMOTE_ALIVE) &&
            game.remotes[i].x == x && game.remotes[i].y == y)
            return 1;
    return 0;
}

/* Monsters move between the tap and the tile under it, and a tile is 8
 * pixels: a tap on or beside one counts, and hx, hy get its square. */
static unsigned char hostile_near(unsigned char x, unsigned char y,
                                  unsigned char *hx, unsigned char *hy)
{
    unsigned char d;

    if (hostile_at(x, y)) {
        *hx = x;
        *hy = y;
        return 1;
    }
    for (d = 0; d < RTS_FACE_COUNT; ++d) {
        unsigned char nx = (unsigned char)(x + step_dx[d]);
        unsigned char ny = (unsigned char)(y + step_dy[d]);

        if ((nx != game.player_x || ny != game.player_y) && hostile_at(nx, ny)) {
            *hx = nx;
            *hy = ny;
            return 1;
        }
    }
    return 0;
}

static unsigned char npc_at(unsigned char x, unsigned char y)
{
    unsigned char i;

    for (i = 0; i < game.beaver_count; ++i)
        if (game.beavers[i].hp && friendly_kind(game.beavers[i].kind) &&
            game.beavers[i].x == x && game.beavers[i].y == y)
            return 1;
    return npc_tile(tile_at(x, y));
}

/* ------------------------------------------------------------------ */
/* Routing: tapped walks and talks find their way around walls, trees and
 * water instead of heading straight for the pen. A breadth-first search
 * over the 32x24 window from the goal cells gives every cell its distance
 * to them; each step takes the neighbour that gets closer. Walkability is
 * sampled once per search (predict_can_move: terrain plus live entities),
 * and a diagonal needs both side cells open, as the server requires. */

#define ROUTE_CELLS (RTS_WINDOW_W * RTS_WINDOW_H)
#define ROUTE_FAR 0xFF

static unsigned char route_open[ROUTE_CELLS];
static unsigned char route_dist[ROUTE_CELLS];
static unsigned route_queue[ROUTE_CELLS];

static unsigned char cell_open(int rx, int ry)
{
    return rx >= 0 && ry >= 0 && rx < RTS_WINDOW_W && ry < RTS_WINDOW_H &&
           route_open[ry * RTS_WINDOW_W + rx];
}

/* Can one step go from (rx,ry) by (sx,sy)? Window-relative cells. */
static unsigned char route_step_ok(int rx, int ry, int sx, int sy)
{
    if (!cell_open(rx + sx, ry + sy))
        return 0;
    return !(sx && sy) || (cell_open(rx + sx, ry) && cell_open(rx, ry + sy));
}

static void route_goal(int rx, int ry, unsigned *tail)
{
    unsigned i;

    if (!cell_open(rx, ry))
        return;
    i = (unsigned)ry * RTS_WINDOW_W + rx;
    if (route_dist[i] == 0)
        return;
    route_dist[i] = 0;
    route_queue[(*tail)++] = i;
}

/* The search, from the target's goal cells outward. Costly on a 16 MHz
 * Palm (some hundred thousand instructions), so it runs once per tap and
 * again only when the window shifts or a step turns out to be blocked;
 * route_next() reads the result. */
static unsigned char route_valid;
static unsigned route_origin_x, route_origin_y;

static void route_build(void)
{
    unsigned char ox = (unsigned char)boot.origin_x, oy = (unsigned char)boot.origin_y;
    int tx = (unsigned char)(target_x - ox), ty = (unsigned char)(target_y - oy);
    unsigned head = 0, tail = 0, i;
    unsigned char d;
    int x, y;

    route_valid = 1;
    route_origin_x = boot.origin_x;
    route_origin_y = boot.origin_y;
    for (y = 0, i = 0; y < RTS_WINDOW_H; ++y)
        for (x = 0; x < RTS_WINDOW_W; ++x, ++i) {
            route_open[i] = predict_can_move((unsigned char)(ox + x), (unsigned char)(oy + y),
                                             boot.terrain, boot.origin_x,
                                             boot.origin_y, &game);
            route_dist[i] = ROUTE_FAR;
        }
    if (tx >= RTS_WINDOW_W || ty >= RTS_WINDOW_H)
        return;                     /* left the window: nothing reachable */
    if (target_talk) {
        /* Any open square one orthogonal step from them. */
        route_goal(tx - 1, ty, &tail);
        route_goal(tx + 1, ty, &tail);
        route_goal(tx, ty - 1, &tail);
        route_goal(tx, ty + 1, &tail);
    } else if (cell_open(tx, ty)) {
        route_goal(tx, ty, &tail);
    } else {
        /* A tree, a wall: as close as it gets. */
        for (d = 0; d < RTS_FACE_COUNT; ++d)
            route_goal(tx + step_dx[d], ty + step_dy[d], &tail);
    }
    while (head < tail) {
        unsigned c = route_queue[head++];
        int cx = (int)(c % RTS_WINDOW_W), cy = (int)(c / RTS_WINDOW_W);
        unsigned char next = (unsigned char)(route_dist[c] + 1);

        for (d = 0; d < RTS_FACE_COUNT; ++d) {
            int nx = cx + step_dx[d], ny = cy + step_dy[d];
            unsigned n;

            if (!route_step_ok(cx, cy, step_dx[d], step_dy[d]))
                continue;
            n = (unsigned)ny * RTS_WINDOW_W + nx;
            if (route_dist[n] != ROUTE_FAR)
                continue;
            route_dist[n] = next;
            route_queue[tail++] = n;
        }
    }
}

/* The direction of the next step toward the target, or FACE_NONE when it
 * cannot be reached from here. A step the live world now refuses (a monster
 * moved in) is skipped, and the search reruns on the next tick. */
static unsigned char route_next(void)
{
    unsigned char ox, oy, best = FACE_NONE, best_dist = ROUTE_FAR, d, fresh = 0;
    int px, py;

    if (!route_valid || boot.origin_x != route_origin_x || boot.origin_y != route_origin_y) {
        route_build();
        fresh = 1;
    }
    ox = (unsigned char)boot.origin_x;
    oy = (unsigned char)boot.origin_y;
    px = (unsigned char)(game.player_x - ox);
    py = (unsigned char)(game.player_y - oy);
    if (px >= RTS_WINDOW_W || py >= RTS_WINDOW_H)
        return FACE_NONE;
    /* Cardinal directions come first in RTS_FACE_*, so they win ties. */
    for (d = 0; d < RTS_FACE_COUNT; ++d) {
        int nx = px + step_dx[d], ny = py + step_dy[d];
        unsigned char nd;

        if (!route_step_ok(px, py, step_dx[d], step_dy[d]))
            continue;
        nd = route_dist[ny * RTS_WINDOW_W + nx];
        if (nd < best_dist &&
            predict_can_step(game.player_x, game.player_y,
                             (unsigned char)(game.player_x + step_dx[d]),
                             (unsigned char)(game.player_y + step_dy[d]),
                             boot.terrain, boot.origin_x, boot.origin_y, &game)) {
            best_dist = nd;
            best = d;
        }
    }
    /* Nothing from a stale search: search again next tick. Nothing from a
     * fresh one: there is no way there (route_valid stays set). */
    if (best == FACE_NONE && !fresh)
        route_valid = 0;
    return best;
}

/* A stroke's first contact decides what it does: on yourself, or on the
 * text under the map, Use (Enter on the other clients); on a monster, a
 * shot toward it; on a person, walk over and talk; anywhere else, walk
 * there, following the pen while it is held and finishing the trip after
 * it lifts. */
static unsigned char handle_pen(void)
{
    unsigned char tx, ty, hx, hy, act = PEN_ACT_NONE;

    if (!pen_down) {
        pen_mode = PEN_NONE;
        pen_prev = 0;
        return PEN_ACT_NONE;
    }
    if (!pen_prev) {
        pen_mode = PEN_DONE;
        if (pen_y >= VIEW_H && pen_y < SCREEN_H && pen_x >= 0 && pen_x < SCREEN_W) {
            target_active = 0;
            act = PEN_ACT_USE;
        } else if (pointer_tile(&tx, &ty)) {
            if (tx == game.player_x && ty == game.player_y) {
                target_active = 0;
                act = PEN_ACT_USE;
            } else if (hostile_near(tx, ty, &hx, &hy)) {
                unsigned char aim = aim_toward((int)hx - game.player_x,
                                               (int)hy - game.player_y);

                if (aim != FACE_NONE) {
                    fire_at(aim);
                    act = PEN_ACT_FIRE;
                }
            } else if (npc_at(tx, ty)) {
                target_x = tx;
                target_y = ty;
                target_talk = 1;
                target_active = 1;
                route_valid = 0;
            } else {
                pen_mode = PEN_WALK;
            }
        }
    }
    if (pen_mode == PEN_WALK && pointer_tile(&tx, &ty) &&
        (!target_active || target_talk || tx != target_x || ty != target_y)) {
        target_x = tx;
        target_y = ty;
        target_talk = 0;
        target_active = 1;
        route_valid = 0;
    }
    pen_prev = 1;
    return act;
}

/* One step per server tick, with the Lynx client's cadence rules: a fresh
 * press along the axis just walked goes at once, anything else waits for the
 * next WORLD_STATE so two moves never coalesce into one diagonal delta. */
static void handle_input(void)
{
    unsigned char dir = input_dir();
    unsigned char buttons = 0, send = 0, step = 0, from_pen = 0, ok, pen;
    unsigned char is_due = world_tick != move_last_world;
    unsigned char fresh;
    unsigned char x = game.player_x, y = game.player_y;

    if (dir != FACE_NONE)
        target_active = 0;              /* keys outrank the pen */
    pen = handle_pen();
    if (pen == PEN_ACT_USE) {
        ++pickup_counter;
        send = 1;
    } else if (pen == PEN_ACT_FIRE) {
        buttons = RTS_BUTTON_FIRE;
        send = 1;
    }
    if (dir == FACE_NONE && target_active) {
        int dx = (int)target_x - game.player_x, dy = (int)target_y - game.player_y;
        int far = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy);

        if (target_talk && far <= 1) {
            /* Beside them: face them and talk. */
            target_active = 0;
            if (far == 1)
                facing = face_for(sgn(dx), sgn(dy));
            ++pickup_counter;
            send = 1;
        } else if (far == 0) {
            target_active = 0;
        } else if (is_due) {
            /* Steps go one per server tick, so that is when to pick one. */
            dir = route_next();
            if (dir == FACE_NONE && route_valid)
                target_active = 0;      /* no way there from here */
            from_pen = 1;
        }
    }
    fresh = dir != input_prev_dir;
    input_prev_dir = dir;
    if (dir != FACE_NONE) {
        unsigned char same_axis =
            move_last_dir != FACE_NONE &&
            (dir == move_last_dir ||
             (dir < RTS_FACE_FIRST_DIAGONAL &&
              move_last_dir < RTS_FACE_FIRST_DIAGONAL &&
              (dir >> 1) == (move_last_dir >> 1)));

        aim_dir = dir;
        if (dir < RTS_FACE_FIRST_DIAGONAL)
            facing = dir;
        if (is_due || (fresh && same_axis))
            step = 1;
        else if (fresh)
            buffered_dir = dir;
    }
    if (!step && is_due && buffered_dir != FACE_NONE) {
        dir = buffered_dir;
        step = 1;
    }
    if (step) {
        buffered_dir = FACE_NONE;
        x = (unsigned char)(x + step_dx[dir]);
        y = (unsigned char)(y + step_dy[dir]);
        ok = predict_move(&predict, client_seq + 1, x, y, boot.terrain,
                          boot.origin_x, boot.origin_y, &game);
        if (!ok && from_pen) {
            /* Route around: a blocked diagonal tries each axis alone. */
            int sx = step_dx[dir], sy = step_dy[dir];
            unsigned char alt = FACE_NONE;

            if (sx && sy && predict_can_move((unsigned char)(game.player_x + sx),
                                             game.player_y, boot.terrain,
                                             boot.origin_x, boot.origin_y, &game))
                alt = face_for(sx, 0);
            else if (sx && sy &&
                     predict_can_move(game.player_x,
                                      (unsigned char)(game.player_y + sy),
                                      boot.terrain, boot.origin_x,
                                      boot.origin_y, &game))
                alt = face_for(0, sy);
            if (alt == FACE_NONE) {
                target_active = 0;     /* walled in: stop trying */
            } else {
                dir = alt;
                facing = alt;
                x = (unsigned char)(game.player_x + step_dx[dir]);
                y = (unsigned char)(game.player_y + step_dy[dir]);
                ok = predict_move(&predict, client_seq + 1, x, y, boot.terrain,
                                  boot.origin_x, boot.origin_y, &game);
            }
        }
        if (ok) {
            game.player_x = x;
            game.player_y = y;
            move_last_dir = dir;
            move_last_world = world_tick;
            send = 1;
            world_dirty = 1;
        }
    }
    if (keys & KEY_FIRE) {
        if (!fire_latch) {
            fire_latch = 1;
            fire_at(aim_dir);
            buttons = RTS_BUTTON_FIRE;
            send = 1;
        }
    } else {
        fire_latch = 0;
    }
    if (keys & KEY_USE) {
        if (!use_latch) {
            use_latch = 1;
            ++pickup_counter;
            send = 1;
        }
    } else {
        use_latch = 0;
    }
    if (send) {
        heartbeat_due = TimGetTicks() +
            (send_player_state((buttons & RTS_BUTTON_FIRE) ? fire_aim : facing,
                               buttons) ? ms(HEARTBEAT_MS) : 0);
    }
}

static void toggle_pvp(void)
{
    ++pvp_toggle_counter;
    if (send_player_state(facing, 0))
        heartbeat_due = TimGetTicks() + ms(HEARTBEAT_MS);
}

/* ------------------------------------------------------------------ */
/* HUD                                                                 */

static void update_hud(void)
{
    char line[64];

    if (!hud_dirty && !game.message_dirty && !game.quest_dirty)
        return;
    if (hud_dirty) {
        if (game.hud_seen)
            StrPrintF(line, "HP %u/%u  Lv %u  Gold %u  PvP %s", game.hud_hp,
                      game.hud_max_hp, game.hud_level, game.hud_gold,
                      game.hud_pvp_enabled ? "on" : "off");
        else
            StrCopy(line, me.name);
        if (game.hud_seen && game.hud_pvp_enabled && game.hud_pvp_kills) {
            char kills[12];

            StrPrintF(kills, " %u", game.hud_pvp_kills);
            StrCat(line, kills);
        }
        gfx_hud_line(0, line);
    }
    if (hud_dirty || game.message_dirty) {
        gfx_hud_wrap(1, 2, map_loading ? "Entering..." :
                     game.message_seen ? game.message : "");
        game.message_dirty = 0;
    }
    if (hud_dirty || game.quest_dirty) {
        if (show_diag)
            StrPrintF(line, "@%u,%u RX%lu TX%lu P%lu C%lu R%lu X%lu L%u",
                      game.player_x, game.player_y, link.rx_total, link.tx_total,
                      link.polls, corrections, resyncs, bad_frames, link.lost);
        gfx_hud_line(3, show_diag ? line :
                     game.quest_seen && game.quest_id ? game.quest_text : "");
        game.quest_dirty = 0;
    }
    hud_dirty = 0;
}

/* Everything on screen again, after a menu or alert covered it. */
static void redraw_all(void)
{
    if (dlg_open) {
        dlg_redraw = 1;
        return;
    }
    gfx_hud_frame();
    hud_dirty = world_dirty = 1;
    game.message_dirty = game.quest_dirty = 1;
}

/* ------------------------------------------------------------------ */
/* Dialogue                                                            */

#define DLG_BTN_Y 142
#define DLG_BTN_H 15

static const char *speaker_name(unsigned char speaker)
{
    switch (speaker) {
    case RTS_SPEAKER_NERISSA: return "Nerissa";
    case RTS_SPEAKER_DANIEL: return "Daniel";
    case RTS_SPEAKER_WILHELM: return "Wilhelm";
    case RTS_SPEAKER_LUCIAN: return "Lucian";
    case RTS_SPEAKER_GRIX: return "Grix";
    default: return NULL;
    }
}

static Boolean dlg_offer(void)
{
    return (game.dlg.flags & RTS_DLG_FLAG_QUEST_OFFER) != 0;
}

static void draw_button(int x, int w, const char *label)
{
    FontID old = FntSetFont(boldFont);
    Int16 len = StrLen(label);

    gfx_frame(x, DLG_BTN_Y, w, DLG_BTN_H);
    WinDrawChars(label, len, x + (w - FntCharsWidth(label, len)) / 2, DLG_BTN_Y + 2);
    FntSetFont(old);
}

static void dialogue_draw_page(void)
{
    const char *name = speaker_name(game.dlg.speaker);
    char page[12];

    gfx_clear();
    if (name)
        gfx_text(4, 3, name, 1);
    StrPrintF(page, "%u/%u", game.dlg.page_index + 1,
              game.dlg.page_count ? game.dlg.page_count : 1);
    gfx_text_right(SCREEN_W - 4, 3, page);
    WinDrawLine(2, 16, SCREEN_W - 3, 16);
    gfx_wrap(4, 20, SCREEN_W - 8, DLG_BTN_Y - 2, game.dlg.text, game.dlg.len);
    if (dlg_offer()) {
        draw_button(4, 72, "Accept");
        draw_button(SCREEN_W - 76, 72, "Decline");
    } else {
        draw_button(4, SCREEN_W - 8, "Tap to continue");
    }
}

static unsigned char dialogue_buttons(void)
{
    unsigned char mask = 0;

    if (keys & (KEY_USE | KEY_FIRE))
        mask |= DLG_BTN_A;
    if (keys & KEY_LEFT)
        mask |= DLG_BTN_B;
    /* A tap anywhere is Enter, except on the Decline button. */
    if (pen_down && pen_y >= 0 && pen_y < SCREEN_H) {
        if (dlg_offer() && pen_y >= DLG_BTN_Y - 4 && pen_x >= SCREEN_W / 2)
            mask |= DLG_BTN_B;
        else
            mask |= DLG_BTN_A;
    }
    return mask;
}

static void dialogue_send_ack(unsigned char decline)
{
    ++pickup_counter;
    if (send_player_state(facing, decline ? RTS_BUTTON_DIALOGUE_DECLINE : 0)) {
        heartbeat_due = TimGetTicks() + ms(HEARTBEAT_MS);
    } else {
        dlg_ack_retry = decline ? RTS_BUTTON_DIALOGUE_DECLINE : 0;
        dlg_ack_pending = 1;
    }
}

static void dialogue_begin(void)
{
    game.dlg.request = 0;
    game.dlg.active = 1;
    input_poll();
    dlg_modal_open(&modal, dialogue_buttons());
    MemSet(game.tracers, sizeof game.tracers, 0);
    target_active = 0;
    dlg_open = 1;
    dlg_redraw = 0;
}

static void dialogue_end(void)
{
    dlg_open = 0;
    game.dlg.active = 0;
    game.dlg.dirty = 0;
    game.dlg.request = 0;
    /* The keys or stroke that closed the scene must not fire or use. */
    fire_latch = use_latch = 1;
    pen_prev = pen_down;
    pen_mode = PEN_DONE;
    gfx_clear();
    redraw_all();
}

static void dialogue_step(void)
{
    unsigned char effects;

    input_poll();
    if (due(heartbeat_due)) {
        if (dlg_ack_pending) {
            if (send_player_state(facing, dlg_ack_retry))
                dlg_ack_pending = 0;
        } else {
            send_player_state(facing, 0);
        }
        heartbeat_due = TimGetTicks() + ms(HEARTBEAT_MS);
    }
    service_cache_retries();
    if (map_loading || modal.closing) {
        dialogue_end();
        return;
    }
    if (!draw_ok || ui_busy)
        return;
    effects = dlg_modal_step(&modal, game.dlg.dirty, game.dlg.page_index,
                             game.dlg.flags, dialogue_buttons());
    game.dlg.dirty = 0;
    if ((effects & DLG_EFFECT_DRAW) || dlg_redraw) {
        dlg_redraw = 0;
        dialogue_draw_page();
    }
    if (effects & DLG_EFFECT_ACK_ACCEPT)
        dialogue_send_ack(0);
    if (effects & DLG_EFFECT_ACK_DECLINE)
        dialogue_send_ack(1);
    if (effects & DLG_EFFECT_CLOSE)
        dialogue_end();
}

/* ------------------------------------------------------------------ */
/* Game                                                                */

static void stop_game(void)
{
    playing = 0;
    dlg_open = 0;
    net_close(&link);
    KeySetMask(keyBitsAll);
}

static void leave_to_setup(void)
{
    stop_game();
    FrmGotoForm(SetupForm);
}

static void lose_connection(void)
{
    char detail[64];

    net_error_text(&link, detail);
    stop_game();
    show_error("The connection to the realm was lost.", detail);
    FrmGotoForm(SetupForm);
}

static void game_step(void)
{
    unsigned char anim;
    unsigned long key;

    EvtResetAutoOffTimer();
    if (pump_link(0) < 0) {
        lose_connection();
        return;
    }
    if (dlg_open) {
        dialogue_step();
        return;
    }
    if (game.dlg.request && !map_loading && !map_sync && draw_ok) {
        dialogue_begin();
        return;
    }
    if (map_sync && due(map_sync_deadline))
        map_sync = 0;       /* echo lost: fall back rather than freeze */
    input_poll();
    if (!map_loading && !map_sync && draw_ok)
        handle_input();
    if (due(heartbeat_due))
        heartbeat_due = TimGetTicks() +
            (send_player_state(facing, 0) ? ms(HEARTBEAT_MS) : 0);
    service_cache_retries();

    if (due(tracer_due)) {
        tracer_due = TimGetTicks() + ms(TRACER_STEP_MS);
        if (!map_loading)
            update_tracers();
    }
    if (due(hit_due)) {
        unsigned char i;

        hit_due = TimGetTicks() + ms(HIT_FLASH_STEP_MS);
        for (i = 0; i < game.beaver_count; ++i) {
            if (game.beavers[i].hit_timer) {
                --game.beavers[i].hit_timer;
                world_dirty = 1;
            }
        }
    }
    anim = (unsigned char)(((TimGetTicks() - anim_base) / ms(ANIM_MS)) & 1);
    if (anim != last_anim) {
        last_anim = anim;
        world_dirty = 1;
    }
    if (!draw_ok || ui_busy)
        return;
    if (show_diag && (link.polls & 15) == 0)
        game.quest_dirty = 1;
    update_hud();

    if (map_loading)
        return;             /* world frozen behind the Entering banner */
    track_camera();
    key = ((unsigned long)(boot.origin_x + cam_x) << 24) |
          ((unsigned long)(boot.origin_y + cam_y) << 16) |
          ((unsigned long)cam_x << 8) | cam_y;
    if (key != last_view_key || game.tile_changed) {
        last_view_key = key;
        game.tile_changed = 0;
        world_dirty = 1;
    }
    if (world_dirty) {
        gfx_render_world(&game, boot.terrain, boot.origin_x, boot.origin_y,
                         cam_x, cam_y, facing, anim);
        world_dirty = 0;
    }
}

/* Log in if needed, connect, load the world, and enter it. 1 when playing;
 * on failure the reason has been shown. */
static int start_game(void)
{
    char where[HOST_LEN + 8];
    UInt32 start;

    boot_title();
    if (need_login) {
        unsigned char status;

        boot_step("Logging in as");
        boot_note(me.name);
        status = login();
        if (status == LOGIN_USERNAME_TAKEN) {
            show_error("That name is taken.", "Pick another one.");
            return 0;
        }
        if (status != LOGIN_OK) {
            show_link_error("Could not log in.");
            return 0;
        }
        boot_result("OK");
        identity_format(&me, prefs.host, prefs.record);
        PrefSetAppPreferences(CREATOR, PREFS_ID, PREFS_VERSION, &prefs,
                              sizeof prefs, true);
        need_login = 0;
    }

    StrPrintF(where, "%s:%u", prefs.host, (unsigned)HYBRID_SERVER_PORT);
    boot_step(where);
    if (net_open(&link, prefs.host, HYBRID_SERVER_PORT) != 0) {
        show_link_error("Could not connect to the realm.");
        return 0;
    }
    boot_result("OK");
    boot_step("Loading the world");
    if (!bootstrap()) {
        if (!link.open || link.last_error)
            show_link_error("The world did not load.");
        else
            show_error("The world did not load.",
                       boot.got_welcome ? "Terrain incomplete." : "No welcome.");
        net_close(&link);
        return 0;
    }
    boot_result("OK");
    boot_step("Entering the realm");

    /* Realtime starts only after a PLAYER_STATE. Bootstrap gives us the
     * terrain window but not the player's saved position; its centre is
     * wrong near map edges. Send an impossible position to request the
     * server's authoritative WORLD_STATE without moving the player. */
    net_write(&link, (const unsigned char *)"RT3\n", 4);
    send_frame(rt_build_auth(wire, me.token));
    client_seq = 0;
    game.player_x = 0xFF;
    game.player_y = 0xFF;
    send_player_state(RTS_FACE_DOWN, 0);

    rt_state_init(&game);
    predict_init(&predict, 0, 0);
    bootstrap_fill_init(&fill);
    client_seq = 1;                  /* the AUTH frame used seq 0 */
    current_map_id = MAP_OVERWORLD;
    gfx_set_palette(0);
    map_loading = map_sync = resync_pending = 0;
    boot.commit_pending = 0;
    rx_encoded_len = 0;
    world_tick = move_last_world = 0;
    move_last_dir = input_prev_dir = buffered_dir = FACE_NONE;
    target_active = 0;
    fire_latch = use_latch = 1;
    pen_prev = 1;
    pen_mode = PEN_DONE;
    dlg_open = dlg_ack_pending = 0;
    corrections = resyncs = bad_frames = 0;
    heartbeat_due = TimGetTicks() + ms(HEARTBEAT_MS);

    /* Wait for the first authoritative world frame. */
    start = TimGetTicks();
    while (!game.world_seen) {
        if (pump_link(1) < 0 || due(start + ms(BOOTSTRAP_TIMEOUT_MS))) {
            show_link_error("The realm did not respond.");
            net_close(&link);
            return 0;
        }
        SysTaskDelay(2);
    }
    /* A save that is not on the overworld gets its MAP_CHANGE a moment after
     * the first WORLD_STATE: wait briefly before painting. */
    start = TimGetTicks();
    while (current_map_id == MAP_OVERWORLD && !due(start + ms(INITIAL_ART_WAIT_MS)))
        if (pump_link(1) < 0)
            break;

    center_camera();
    last_view_key = 0xFFFFFFFFUL;
    anim_base = tracer_due = hit_due = TimGetTicks();
    last_anim = 0xFF;
    gfx_clear();
    redraw_all();
    /* The hard keys play the game instead of launching apps. */
    KeySetMask(~(UInt32)GAME_KEYS);
    playing = 1;
    return 1;
}

/* ------------------------------------------------------------------ */
/* Game form                                                           */

static void show_about(void)
{
    FormType *form = FrmInitForm(AboutForm);

    FrmDoDialog(form);
    FrmDeleteForm(form);
}

static Boolean game_menu(UInt16 id)
{
    switch (id) {
    case GameMenuPvp:
        toggle_pvp();
        return true;
    case GameMenuDiag:
        show_diag = !show_diag;
        game.quest_dirty = 1;
        return true;
    case GameMenuHelpPlay:
        FrmHelp(HelpPlayString);
        return true;
    case GameMenuHelpTalk:
        FrmHelp(HelpTalkString);
        return true;
    case GameMenuAbout:
        show_about();
        return true;
    case GameMenuLeave:
        leave_to_setup();
        return true;
    }
    return false;
}

static Boolean GameHandleEvent(EventType *event)
{
    switch (event->eType) {
    case frmOpenEvent:
        FrmDrawForm(FrmGetActiveForm());
        start_pending = 1;
        return true;
    case frmUpdateEvent:
        if (playing)
            redraw_all();
        return true;
    case menuEvent:
        return playing && game_menu(event->data.menu.itemID);
    case keyDownEvent:
        if (!playing || (event->data.keyDown.modifiers & commandKeyMask))
            return false;
        if (event->data.keyDown.chr == 'p' || event->data.keyDown.chr == 'P') {
            toggle_pvp();
            return true;
        }
        return false;
    case penDownEvent:
    case penMoveEvent:
    case penUpEvent:
        return playing;     /* read by polling; keep the form from acting */
    case frmCloseEvent:
        game_form = NULL;
        break;
    default:
        break;
    }
    return false;
}

/* ------------------------------------------------------------------ */
/* Setup form                                                          */

static FieldType *get_field(FormType *form, UInt16 id)
{
    return FrmGetObjectPtr(form, FrmGetObjectIndex(form, id));
}

static void set_field_text(FormType *form, UInt16 id, const char *text)
{
    MemHandle handle = MemHandleNew(StrLen(text) + 1);
    MemHandle old;
    FieldType *field = get_field(form, id);

    if (handle == NULL)
        return;
    StrCopy(MemHandleLock(handle), text);
    MemHandleUnlock(handle);
    old = FldGetTextHandle(field);
    FldSetTextHandle(field, handle);
    if (old)
        MemHandleFree(old);
}

static void get_field_text(FormType *form, UInt16 id, char *out, UInt16 size)
{
    const char *text = FldGetTextPtr(get_field(form, id));

    if (text == NULL)
        text = "";
    StrNCopy(out, text, size - 1);
    out[size - 1] = '\0';
}

static void set_status(FormType *form, const char *text)
{
    set_field_text(form, SetupStatusField, text);
    FldDrawField(get_field(form, SetupStatusField));
}

/* Trim and uppercase a name; 1 if it is 1-8 letters or digits. */
static int clean_name(char *name)
{
    char *p = name, *q = name;

    while (*p == ' ')
        ++p;
    for (; *p && *p != ' '; ++p) {
        char c = *p;

        if (c >= 'a' && c <= 'z')
            c = (char)(c - 'a' + 'A');
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')))
            return 0;
        *q++ = c;
    }
    *q = '\0';
    return q > name && q - name <= NAME_MAX && *p == '\0';
}

static void trim(char *s)
{
    char *p = s;
    UInt16 n;

    while (*p == ' ')
        ++p;
    if (p != s)
        MemMove(s, p, StrLen(p) + 1);
    n = StrLen(s);
    while (n > 0 && s[n - 1] == ' ')
        s[--n] = '\0';
}

static void setup_play(FormType *form)
{
    char name[16];
    char error[48];

    get_field_text(form, SetupNameField, name, sizeof name);
    get_field_text(form, SetupServerField, prefs.host, sizeof prefs.host);
    trim(prefs.host);
    if (!clean_name(name)) {
        set_status(form, "Name: 1-8 letters or digits.");
        return;
    }
    if (prefs.host[0] == '\0') {
        set_status(form, "Enter a server.");
        return;
    }
    if (net_init(prefs.link) != 0) {
        if (prefs.link == NET_LINK_LEGACY && net_link_error() == 0)
            set_status(form, "Legacy needs Palm OS 3.3+.");
        else {
            StrPrintF(error, "Link open failed (error %x).", net_link_error());
            set_status(form, error);
        }
        return;
    }
    StrCopy(prefs.name, name);
    need_login = !(identity_parse(&me, prefs.record, StrLen(prefs.record), prefs.host) &&
                   StrCompare(me.name, name) == 0);
    if (need_login) {
        MemSet(&me, sizeof me, 0);
        StrCopy(me.name, name);
    }
    PrefSetAppPreferences(CREATOR, PREFS_ID, PREFS_VERSION, &prefs, sizeof prefs, true);
    FrmGotoForm(GameForm);
}

static void setup_show(FormType *form)
{
    set_field_text(form, SetupNameField, prefs.name);
    set_field_text(form, SetupServerField, prefs.host);
    LstSetSelection(FrmGetObjectPtr(form, FrmGetObjectIndex(form, SetupLinkList)), prefs.link);
    CtlSetLabel(FrmGetObjectPtr(form, FrmGetObjectIndex(form, SetupLinkTrigger)),
                (char *)link_names[prefs.link]);
    LstSetSelection(FrmGetObjectPtr(form, FrmGetObjectIndex(form, SetupButtonsList)),
                    prefs.buttons);
    CtlSetLabel(FrmGetObjectPtr(form, FrmGetObjectIndex(form, SetupButtonsTrigger)),
                (char *)button_names[prefs.buttons]);
    FrmDrawForm(form);
    FrmSetFocus(form, FrmGetObjectIndex(form, prefs.name[0] ? SetupServerField :
                                        SetupNameField));
}

static Boolean SetupHandleEvent(EventType *event)
{
    FormType *form = FrmGetActiveForm();

    switch (event->eType) {
    case frmOpenEvent:
        setup_show(form);
        return true;
    case ctlSelectEvent:
        if (event->data.ctlSelect.controlID == SetupPlayButton) {
            setup_play(form);
            return true;
        }
        break;
    case popSelectEvent:
        if (event->data.popSelect.controlID == SetupLinkTrigger) {
            Int16 selected = event->data.popSelect.selection;
            if (selected >= 0 && selected < NET_LINK_COUNT)
                prefs.link = (UInt8)selected;
            return false;
        }
        if (event->data.popSelect.controlID == SetupButtonsTrigger) {
            Int16 selected = event->data.popSelect.selection;
            if (selected >= 0 && selected < BUTTONS_COUNT)
                prefs.buttons = (UInt8)selected;
            return false;
        }
        break;
    case menuEvent:
        switch (event->data.menu.itemID) {
        case SetupMenuDefault:
            set_field_text(form, SetupServerField, SERVER_HOST);
            FldDrawField(get_field(form, SetupServerField));
            return true;
        case SetupMenuForget:
            prefs.record[0] = '\0';
            prefs.name[0] = '\0';
            PrefSetAppPreferences(CREATOR, PREFS_ID, PREFS_VERSION, &prefs,
                                  sizeof prefs, true);
            set_field_text(form, SetupNameField, "");
            FldDrawField(get_field(form, SetupNameField));
            set_status(form, "Name forgotten.");
            return true;
        case SetupMenuAbout:
            show_about();
            return true;
        case SetupMenuHelpPlay:
            FrmHelp(HelpPlayString);
            return true;
        case SetupMenuHelpTalk:
            FrmHelp(HelpTalkString);
            return true;
        }
        break;
    default:
        break;
    }
    return false;
}

/* ------------------------------------------------------------------ */
/* Application                                                         */

static Boolean AppHandleEvent(EventType *event)
{
    FormType *form;

    if (event->eType != frmLoadEvent)
        return false;
    form = FrmInitForm(event->data.frmLoad.formID);
    FrmSetActiveForm(form);
    if (event->data.frmLoad.formID == GameForm) {
        game_form = form;
        FrmSetEventHandler(form, GameHandleEvent);
    } else {
        FrmSetEventHandler(form, SetupHandleEvent);
    }
    return true;
}

/* Menus and alerts draw over the game: stop drawing until they close. */
static void track_windows(const EventType *event)
{
    WinHandle ours;

    if (!game_form)
        return;
    ours = FrmGetWindowHandle(game_form);
    if (event->eType == winExitEvent && event->data.winExit.exitWindow == ours) {
        draw_ok = false;
    } else if (event->eType == winEnterEvent &&
               event->data.winEnter.enterWindow == ours) {
        draw_ok = true;
        if (playing)
            redraw_all();
    }
}

static void EventLoop(void)
{
    EventType event;
    Err err;

    do {
        EvtGetEvent(&event, playing ? 1 : start_pending ? 0 : evtWaitForever);
        track_windows(&event);
        ui_busy = false;
        if (SysHandleEvent(&event) || MenuHandleEvent(0, &event, &err))
            ui_busy = true;
        else if (!AppHandleEvent(&event))
            FrmDispatchEvent(&event);
        if (event.eType == appStopEvent)
            break;
        if (start_pending && game_form && draw_ok) {
            start_pending = 0;
            if (!start_game()) {
                stop_game();
                FrmGotoForm(SetupForm);
            }
        } else if (playing) {
            game_step();
        }
    } while (1);
}

/* The Serial Manager with SrmOpen first shipped in Palm OS 3.3. */
static Boolean has_new_serial_manager(void)
{
    UInt32 value;

    return FtrGet(sysFileCSerialMgr, sysFtrNewSerialPresent, &value) == errNone &&
           value != 0;
}

static void load_prefs(void)
{
    UInt16 size = sizeof prefs;
    Int16 version;

    MemSet(&prefs, sizeof prefs, 0);
    version = PrefGetAppPreferences(CREATOR, PREFS_ID, &prefs, &size, true);
    if (version == 1 && size == sizeof(RealmPrefsV1)) {
        prefs.link = NET_LINK_LEGACY;
        prefs.buttons = BUTTONS_ORIGINAL;
    } else if (version == 2 && size == sizeof(RealmPrefsV2)) {
        prefs.buttons = BUTTONS_ORIGINAL;
    } else if (version != PREFS_VERSION || size != sizeof prefs) {
        MemSet(&prefs, sizeof prefs, 0);
        StrCopy(prefs.host, SERVER_HOST);
        prefs.link = has_new_serial_manager() ? NET_LINK_LEGACY : NET_LINK_USB;
        prefs.buttons = BUTTONS_PRISM;
    }
    prefs.host[HOST_LEN - 1] = '\0';
    prefs.name[NAME_MAX] = '\0';
    prefs.record[RECORD_LEN - 1] = '\0';
    if (prefs.link >= NET_LINK_COUNT)
        prefs.link = has_new_serial_manager() ? NET_LINK_LEGACY : NET_LINK_USB;
    if (prefs.buttons >= BUTTONS_COUNT)
        prefs.buttons = BUTTONS_PRISM;
}

UInt32 PilotMain(UInt16 cmd, MemPtr cmdPBP, UInt16 launchFlags)
{
    (void)cmdPBP;
    (void)launchFlags;
    if (cmd != sysAppLaunchCmdNormalLaunch)
        return 0;
    tps = SysTicksPerSecond();
    load_prefs();
    if (gfx_open() != 0) {
        gfx_close();
        show_error("This Palm cannot show the game's art.", NULL);
        return 0;
    }
    FrmGotoForm(SetupForm);
    EventLoop();
    stop_game();
    FrmCloseAllForms();
    net_done();
    gfx_close();
    return 0;
}
