/*
 * FujiRealm for the Amiga -- Workbench/Kickstart 1.3 and later, 68000 up.
 *
 * Same server and wire protocol as the Atari 8-bit and Lynx clients:
 * $BF bootstrap packets, then realtime v3 COBS/CRC-16 frames, over TCP.
 * The protocol, bootstrap, terrain-cache, prediction and dialogue logic is
 * shared unchanged from lynx-client/src; this file is the Amiga's flow and
 * main loop, gfx.c/input.c its screen and controls, and net.c its transport:
 * TCP through FujiNet NIO (fujinet-nio.device) in place of Netstream.
 *
 * Use snprintf(), never sprintf(): with -lamiga on the link line, sprintf()
 * resolves to amiga.lib's RawDoFmt() wrapper (no %u, 16-bit %d).
 *
 * Every timer here runs on the clock (DateStamp, 1/50 s), not on loop
 * iterations. The Lynx counts frames because its loop is paced by the blit;
 * ours is paced by FujiBus round trips and would drift badly.
 */
#include <stdio.h>
#include <string.h>

#include <dos/dos.h>
#include <exec/types.h>
#include <exec/execbase.h>
#include <exec/resident.h>
#include <proto/dos.h>
#include <proto/exec.h>

#include "fujinet-nio.h"
#include "bootstrap.h"
#include "dlgmodal.h"
#include "gfx.h"
#include "identity.h"
#include "input.h"
#include "net.h"
#include "predict.h"
#include "rt_state.h"
#include "splash.h"

static const char version_tag[] __attribute__((used)) =
    "$VER: FujiRealm 1.0 (27.9.2026) Amiga NIO client";

#ifndef SERVER_HOST
#define SERVER_HOST "fujinet.online"
#endif
#ifndef HYBRID_SERVER_PORT
#define HYBRID_SERVER_PORT 9000
#endif
#ifndef LOGIN_SERVER_PORT
#define LOGIN_SERVER_PORT 9010
#endif
#define IDENTITY_PATH "S:FujiRealm.id"

/* $BF packets (docs/PROTOCOL.md). */
#define NET_MAGIC 0xBF
#define NET_VERSION 1
#define LOGIN_REQUEST 0xA0
#define LOGIN_RESPONSE 0xA1
#define NET_HELLO 0x01
#define LOGIN_OK 0
#define LOGIN_USERNAME_TAKEN 1
#define LOGIN_FAILED 0xFF
/* Server output budget: 0 is the default (Atari, 2,000 B/s), which a NIO
 * serial link carries with room to spare. */
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
#define POLL_MIN_MS 60

#define FACE_NONE INPUT_NONE
#define CAM_MARGIN_X 5
#define CAM_MARGIN_Y 3
#define MAP_OVERWORLD 0

/* ------------------------------------------------------------------ */
/* State                                                               */

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
static unsigned char fire_latch, use_latch, pvp_latch, quit_latch;
static unsigned char facing = RTS_FACE_DOWN, aim_dir = RTS_FACE_DOWN;
static unsigned char fire_aim = RTS_FACE_DOWN;
static unsigned char move_last_dir = FACE_NONE, input_prev_dir = FACE_NONE;
static unsigned char buffered_dir = FACE_NONE;
static unsigned long world_tick, move_last_world;

static unsigned char current_map_id, map_palette_id;
static unsigned char map_loading, map_sync, resync_pending;
static unsigned long heartbeat_due, resync_due, commit_due, map_sync_deadline;
static unsigned long tracer_due, hit_due;

static unsigned char cam_x, cam_y;
static unsigned cam_origin_x, cam_origin_y;
static unsigned long last_view_key;
static unsigned char terrain_dirty, world_dirty, hud_dirty;
static unsigned char dlg_ack_pending, dlg_ack_retry;

static unsigned long corrections, resyncs, bad_frames;
static unsigned char show_diag;

/* ------------------------------------------------------------------ */
/* Clock                                                               */

static unsigned long now_ms(void)
{
    struct DateStamp ds;

    DateStamp(&ds);
    return ((unsigned long)ds.ds_Days * 1440UL + (unsigned long)ds.ds_Minute) *
               60000UL + (unsigned long)ds.ds_Tick * 20UL;
}

static int due(unsigned long deadline)
{
    return (long)(now_ms() - deadline) >= 0;
}

/* ------------------------------------------------------------------ */
/* Boot screen                                                         */

static unsigned char boot_row = 4;

static void boot_title(void)
{
    static const char title[] = "F U J I R E A L M";
    static const char sub[] = "AMIGA  -  FUJINET NIO";

    gfx_clear(PEN_NAVY);
    gfx_text((TEXT_COLS - (sizeof title - 1)) / 2, 1, PEN_GOLD, PEN_NAVY, title,
             sizeof title - 1);
    gfx_text((TEXT_COLS - (sizeof sub - 1)) / 2, 2, PEN_SKY, PEN_NAVY, sub,
             sizeof sub - 1);
    boot_row = 4;
}

/* One status line: "label ..." then OK/FAIL/text appended by boot_result. */
static void boot_step(const char *label)
{
    char line[TEXT_COLS + 1];
    unsigned n = strlen(label);

    if (boot_row >= TEXT_ROWS - 2)
        boot_title();
    memset(line, ' ', TEXT_COLS);
    memcpy(line + 2, label, n > 30 ? 30 : n);
    gfx_text(0, boot_row, PEN_WHITE, PEN_NAVY, line, TEXT_COLS);
}

static void boot_result(const char *text, unsigned char ink)
{
    gfx_text(32, boot_row, ink, PEN_NAVY, text, (unsigned char)strlen(text));
    ++boot_row;
}

/* Show why we stopped and wait for Esc/Return. */
static void boot_fail(const char *why, const char *detail)
{
    boot_result("FAIL", PEN_RED);
    ++boot_row;
    gfx_text(2, boot_row++, PEN_GOLD, PEN_NAVY, why, (unsigned char)strlen(why));
    if (detail)
        gfx_text(2, boot_row++, PEN_SKY, PEN_NAVY, detail,
                 (unsigned char)strlen(detail));
    ++boot_row;
    gfx_text(2, boot_row, PEN_WHITE, PEN_NAVY, "PRESS RETURN TO QUIT", 20);
    input_flush_chars();
    for (;;) {
        int ch;

        input_poll();
        ch = input_char();
        if (ch == '\r' || ch == 0x1B)
            return;
        Delay(2);
    }
}

/* ------------------------------------------------------------------ */
/* FujiNet bring-up                                                    */

/* Load fujinet-nio.device as a resident device ourselves, as
 * fujinet-load-resident does: LoadSeg, find the ROMTag in the first hunk,
 * InitResident. Running the loader through Execute() instead hangs when we
 * were started from Workbench on 1.3, which has no CLI for it to use. */
static int load_nio_device(const char *path)
{
    static const char name[] = "fujinet-nio.device";
    BPTR seglist = LoadSeg((UBYTE *)path);
    UWORD *p, *end;

    if (!seglist)
        return 0;
    p = (UWORD *)((ULONG *)BADDR(seglist) + 1);
    end = (UWORD *)((UBYTE *)BADDR(seglist) + ((ULONG *)BADDR(seglist))[-1] - 4);
    for (; p + sizeof(struct Resident) / 2 <= end; ++p) {
        struct Resident *r = (struct Resident *)p;

        if (r->rt_MatchWord == RTC_MATCHWORD && r->rt_MatchTag == r &&
            r->rt_Type == NT_DEVICE && r->rt_Name &&
            strcmp((const char *)r->rt_Name, name) == 0) {
            InitResident(r, seglist);
            return FindName(&SysBase->DeviceList, (UBYTE *)name) != NULL;
        }
    }
    UnLoadSeg(seglist);
    return 0;
}

/* Connect to FujiNet, loading fujinet-nio.device first if it is not
 * resident: from DEVS: (Install-FujiNet-WB13), NIO:, or our own drawer. */
static int connect_fujinet(void)
{
    static const char *const paths[] = {
        "DEVS:fujinet-nio.device", "NIO:fujinet-nio.device", "fujinet-nio.device",
    };
    unsigned i;

    if (net_init() == 0)
        return 0;
    net_done();
    if (FindName(&SysBase->DeviceList, (UBYTE *)"fujinet-nio.device"))
        return 1;               /* resident but not answering */
    for (i = 0; i < sizeof paths / sizeof paths[0]; ++i) {
        BPTR lock = Lock((UBYTE *)paths[i], ACCESS_READ);

        if (!lock)
            continue;
        UnLock(lock);
        if (load_nio_device(paths[i]) && net_init() == 0)
            return 0;
        net_done();
    }
    return 1;
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
    memcpy(frame + n, payload, len);
    n += len;
    frame[n] = sum8(frame, n);
    return n + 1;
}

/* ------------------------------------------------------------------ */
/* Login                                                               */

/* Why the last login() failed, for the boot screen. */
static char login_why[40];

static unsigned char login(void)
{
    struct net_stream *s = &link;
    unsigned char payload[NAME_MAX + 1];
    unsigned char frame[NAME_MAX + 8];
    unsigned char name_len = (unsigned char)strlen(me.name);
    unsigned long deadline;
    unsigned char byte;
    unsigned i;

    login_why[0] = '\0';
    if (net_open(s, SERVER_HOST, LOGIN_SERVER_PORT) != 0) {
        snprintf(login_why, sizeof login_why, "OPEN: %s", net_error_text(s));
        return LOGIN_FAILED;
    }
    payload[0] = name_len;
    memcpy(payload + 1, me.name, name_len);
    if (net_write(s, frame, build_bf(LOGIN_REQUEST, payload, name_len + 1, frame))) {
        fn_write_diagnostics_t d;

        fn_write_get_last_diagnostics(&d);
        snprintf(login_why, sizeof login_why, "SEND: %s X%u T%u S%u Z%u H%u",
                 net_error_text(s), (unsigned)d.exchanges,
                 (unsigned)d.transport_retry, (unsigned)d.service_retry,
                 (unsigned)d.zero_accepted, (unsigned)s->handle);
        net_close(s);
        return LOGIN_FAILED;
    }
    bf_parser_init(&bf);
    deadline = now_ms() + LOGIN_TIMEOUT_MS;
    while (!due(deadline)) {
        if (net_poll(s) < 0) {
            snprintf(login_why, sizeof login_why, "RECV: %s (%lu BYTES)",
                     net_error_text(s), s->rx_total);
            break;
        }
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
        Delay(2);
    }
    if (!login_why[0])
        snprintf(login_why, sizeof login_why, "NO REPLY (%lu BYTES, %lu POLLS)",
                 s->rx_total, s->polls);
    net_close(s);
    return LOGIN_FAILED;
}

/* Keyboard name entry: 1-8 letters or digits, uppercase. 0 if Esc. */
static int prompt_for_name(int taken)
{
    char name[NAME_MAX + 1];
    unsigned char n = (unsigned char)strlen(me.name);
    int ch;

    memcpy(name, me.name, n + 1);
    boot_title();
    gfx_text(2, 5, PEN_WHITE, PEN_NAVY, "WELCOME, ADVENTURER.", 20);
    if (taken)
        gfx_text(2, 7, PEN_RED, PEN_NAVY, "THAT NAME IS TAKEN - TRY ANOTHER.", 33);
    gfx_text(2, 9, PEN_WHITE, PEN_NAVY, "YOUR NAME (1-8 LETTERS OR DIGITS):", 34);
    gfx_text(2, 14, PEN_GREY, PEN_NAVY, "RETURN TO PLAY, ESC TO QUIT", 27);
    input_flush_chars();
    for (;;) {
        char shown[NAME_MAX + 2];

        memset(shown, ' ', sizeof shown);
        memcpy(shown, name, n);
        shown[n] = '_';
        gfx_text(4, 11, PEN_GOLD, PEN_BLUE, shown, sizeof shown);
        do {
            input_poll();
            ch = input_char();
            if (ch < 0)
                Delay(2);
        } while (ch < 0);
        if (ch == 0x1B)
            return 0;
        if (ch == '\r' && n > 0)
            break;
        if (ch == '\b' && n > 0)
            name[--n] = '\0';
        else if (ch != '\b' && ch != '\r' && n < NAME_MAX) {
            name[n++] = (char)ch;
            name[n] = '\0';
        }
    }
    memcpy(me.name, name, n + 1);
    return 1;
}

/* Cached identity, or a fresh login under a name the player picks. */
static int establish_identity(void)
{
    unsigned char status = LOGIN_FAILED;
    int attempts = 3, taken = 0;

    boot_step("IDENTITY");
    if (identity_load(&me, IDENTITY_PATH, SERVER_HOST)) {
        boot_result(me.name, PEN_GOLD);
        return 1;
    }
    boot_result("NEW", PEN_SKY);
    me.name[0] = '\0';
    while (attempts-- > 0) {
        if (!prompt_for_name(taken))
            return 0;
        boot_title();
        boot_step("LOGIN AS");
        boot_result(me.name, PEN_GOLD);
        boot_step("LOGIN SERVER");
        status = login();
        if (status != LOGIN_USERNAME_TAKEN)
            break;
        boot_result("TAKEN", PEN_RED);
        taken = 1;
    }
    if (status != LOGIN_OK) {
        boot_fail("COULD NOT LOG IN.", login_why[0] ? login_why : SERVER_HOST);
        return 0;
    }
    boot_result("OK", PEN_SKY);
    boot_step("SAVE " IDENTITY_PATH);
    boot_result(identity_save(&me, IDENTITY_PATH, SERVER_HOST) ? "OK" : "NO",
                PEN_SKY);
    return 1;
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
    unsigned long deadline = now_ms() + BOOTSTRAP_TIMEOUT_MS;
    unsigned long retry = now_ms() + HELLO_RETRY_MS;
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
                count += (boot.rows_received >> r) & 1;
            snprintf(rows, sizeof rows, "%2u/24", count);
            gfx_text(32, boot_row, PEN_SKY, PEN_NAVY, rows, 5);
            retry = now_ms() + HELLO_RETRY_MS;
        } else if (due(retry) && tries < HELLO_MAX_TRIES) {
            /* The server restarts a bootstrap per HELLO; a lost one is cheap
             * to repeat. */
            send_hello();
            ++tries;
            retry = now_ms() + HELLO_RETRY_MS;
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
    resync_due = now_ms() + RESYNC_RETRY_MS;
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
        commit_due = now_ms() + COMMIT_RETRY_MS;
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
            resync_due = now_ms() + RESYNC_RETRY_MS;   /* real progress */
        if (r == BOOTSTRAP_FILL_COMPLETE) {
            bootstrap_fill_activate(&fill, &boot);
            predict.count = 0;
            resync_pending = 0;
            commit_due = now_ms();
            terrain_dirty = 1;
            if (map_loading) {
                predict_init(&predict, game.player_x, game.player_y);
                send_map_ready();
                map_loading = 0;
                map_sync = 1;
                map_sync_deadline = now_ms() + MAP_SYNC_TIMEOUT_MS;
                heartbeat_due = now_ms();
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
            map_palette_id = game.map_change.palette_id;
            gfx_set_palette(map_palette_id);
            fill.active = 0;
            boot.commit_pending = 0;
            memset(game.tracers, 0, sizeof game.tracers);
            map_loading = 1;
            resync_pending = 1;
            resync_due = now_ms() + RESYNC_RETRY_MS;
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

static unsigned long last_poll;

/* One network exchange if due, then parse whatever arrived. Drains up to a
 * few chunks back-to-back when the server has more waiting. */
static int pump_link(int force)
{
    int got, rounds = 0;

    if (!force && !due(last_poll + POLL_MIN_MS) && link.rx_count == 0)
        return 0;
    do {
        got = net_poll(&link);
        last_poll = now_ms();
        if (got < 0)
            return -1;
        realtime_pump();
    } while (got >= 256 && ++rounds < 4);
    return 0;
}

/* ------------------------------------------------------------------ */
/* Input and shots                                                     */

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

/* ------------------------------------------------------------------ */
/* Mouse: left click/hold walks to the pointer, right click shoots at it,
 * clicking your own tile is Use. */

static unsigned char target_active, target_x, target_y, mouse_use_latch;

static int pointer_tile(unsigned char *wx, unsigned char *wy)
{
    int mx, my;

    input_mouse_pos(&mx, &my);
    if (mx < 0 || my < 0 || mx >= VIEW_W || my >= VIEW_H)
        return 0;
    *wx = (unsigned char)(boot.origin_x + cam_x + mx / TILE_PX);
    *wy = (unsigned char)(boot.origin_y + cam_y + my / TILE_PX);
    return 1;
}

static int sgn(int v)
{
    return v > 0 ? 1 : v < 0 ? -1 : 0;
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

/* Aim: the nearest of the eight directions to the pointer, so a click a
 * little off-axis still shoots straight. */
static unsigned char aim_toward(int dx, int dy)
{
    int ax = dx < 0 ? -dx : dx, ay = dy < 0 ? -dy : dy;

    if (ax >= 2 * ay)
        dy = 0;
    else if (ay >= 2 * ax)
        dx = 0;
    return face_for(sgn(dx), sgn(dy));
}

/* One step per server tick, with the Lynx client's cadence rules: a fresh
 * press along the axis just walked goes at once, anything else waits for the
 * next WORLD_STATE so two moves never coalesce into one diagonal delta. */
static void handle_input(void)
{
    unsigned char dir = input_dir();
    unsigned char buttons = 0, send = 0, step = 0;
    unsigned char is_due = world_tick != move_last_world;
    unsigned char fresh = dir != input_prev_dir;
    unsigned char x = game.player_x, y = game.player_y;

    unsigned char from_mouse = 0, ok;
    unsigned char tx, ty;

    if (dir != FACE_NONE)
        target_active = 0;              /* keys and stick outrank the mouse */
    if (input_mouse_left()) {
        if (pointer_tile(&tx, &ty)) {
            if (tx == game.player_x && ty == game.player_y) {
                target_active = 0;
                if (!mouse_use_latch) {
                    mouse_use_latch = 1;
                    ++pickup_counter;   /* click yourself: use / talk */
                    send = 1;
                }
            } else {
                target_x = tx;
                target_y = ty;
                target_active = 1;
            }
        }
    } else {
        mouse_use_latch = 0;
    }
    if (dir == FACE_NONE && target_active) {
        if (game.player_x == target_x && game.player_y == target_y) {
            target_active = 0;
        } else {
            dir = face_for(sgn((int)target_x - game.player_x),
                           sgn((int)target_y - game.player_y));
            from_mouse = 1;
        }
    }
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
        x = (unsigned char)(x + predict_shot_dx[dir]);
        y = (unsigned char)(y + predict_shot_dy[dir]);
        ok = predict_move(&predict, client_seq + 1, x, y, boot.terrain,
                          boot.origin_x, boot.origin_y, &game);
        if (!ok && from_mouse) {
            /* Route around: a blocked diagonal tries each axis alone. */
            int sx = predict_shot_dx[dir], sy = predict_shot_dy[dir];
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
                x = (unsigned char)(game.player_x + predict_shot_dx[dir]);
                y = (unsigned char)(game.player_y + predict_shot_dy[dir]);
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
    if (input_fire()) {
        if (!fire_latch) {
            fire_latch = 1;
            ++fire_counter;
            buttons = RTS_BUTTON_FIRE;
            fire_aim = aim_dir;
            rt_spawn_tracer(&game, game.player_x, game.player_y, fire_aim);
            send = 1;
        }
    } else {
        fire_latch = 0;
    }
    if (input_mouse_right_click() && pointer_tile(&tx, &ty)) {
        unsigned char aim = aim_toward((int)tx - game.player_x,
                                       (int)ty - game.player_y);

        if (aim != FACE_NONE) {
            ++fire_counter;
            buttons = RTS_BUTTON_FIRE;
            fire_aim = aim_dir = aim;
            if (aim < RTS_FACE_FIRST_DIAGONAL)
                facing = aim;
            rt_spawn_tracer(&game, game.player_x, game.player_y, fire_aim);
            send = 1;
            world_dirty = 1;
        }
    }
    if (input_use()) {
        if (!use_latch) {
            use_latch = 1;
            ++pickup_counter;
            send = 1;
        }
    } else {
        use_latch = 0;
    }
    if (input_pvp()) {
        if (!pvp_latch) {
            pvp_latch = 1;
            ++pvp_toggle_counter;
            send = 1;
        }
    } else {
        pvp_latch = 0;
    }
    if (send) {
        heartbeat_due = now_ms() +
            (send_player_state((buttons & RTS_BUTTON_FIRE) ? fire_aim : facing,
                               buttons) ? HEARTBEAT_MS : 0);
    }
}

/* ------------------------------------------------------------------ */
/* HUD                                                                 */

static unsigned char hud_line_dirty[4];

static void update_hud(void)
{
    char line[TEXT_COLS + 1];

    if (!hud_dirty && !game.message_dirty && !game.quest_dirty)
        return;
    if (hud_dirty) {
        if (game.hud_seen)
            snprintf(line, sizeof line, "HP %u/%u  LV %u  GOLD %u  PVP %s %u",
                    (unsigned)game.hud_hp, (unsigned)game.hud_max_hp,
                    (unsigned)game.hud_level, (unsigned)game.hud_gold,
                    game.hud_pvp_enabled ? "ON" : "OFF",
                    (unsigned)game.hud_pvp_kills);
        else
            snprintf(line, sizeof line, "%s", me.name);
        gfx_hud_line(0, PEN_GOLD, line);
        hud_line_dirty[3] = 1;
    }
    if (hud_dirty || game.message_dirty) {
        if (map_loading)
            gfx_hud_line(1, PEN_WHITE, "ENTERING...");
        else
            gfx_hud_line(1, PEN_WHITE, game.message_seen ? game.message : "");
        game.message_dirty = 0;
    }
    if (hud_dirty || game.quest_dirty) {
        gfx_hud_line(2, PEN_SKY, game.quest_seen && game.quest_id ?
                     game.quest_text : "");
        game.quest_dirty = 0;
    }
    if (hud_line_dirty[3]) {
        if (show_diag)
            snprintf(line, sizeof line, "RX %lu TX %lu POLL %lu C%lu R%lu X%lu",
                    link.rx_total, link.tx_total, link.polls, corrections,
                    resyncs, bad_frames);
        else
            snprintf(line, sizeof line, "LMB WALK  RMB/SPC FIRE  RET USE  P PVP");
        gfx_hud_line(3, PEN_GREY, line);
        hud_line_dirty[3] = 0;
    }
    hud_dirty = 0;
}

/* ------------------------------------------------------------------ */
/* Dialogue                                                            */

static const char *speaker_name(unsigned char speaker)
{
    switch (speaker) {
    case RTS_SPEAKER_NERISSA: return "NERISSA";
    case RTS_SPEAKER_DANIEL: return "DANIEL";
    case RTS_SPEAKER_WILHELM: return "WILHELM";
    case RTS_SPEAKER_LUCIAN: return "LUCIAN";
    case RTS_SPEAKER_GRIX: return "GRIX";
    default: return NULL;
    }
}

static void dialogue_draw_page(void)
{
    const char *text = game.dlg.text;
    const char *name = speaker_name(game.dlg.speaker);
    unsigned char len = game.dlg.len, pos = 0, row = 4;
    char buf[40];

    gfx_fill_rows(0, VIEW_ROWS * 2, PEN_NAVY);
    if (name)
        gfx_text(2, 1, PEN_GOLD, PEN_NAVY, name, (unsigned char)strlen(name));
    /* Word wrap to 36 columns. */
    while (pos < len && row < 16) {
        unsigned char width = 36, cut;

        while (pos < len && text[pos] == ' ')
            ++pos;
        if (len - pos <= width) {
            cut = (unsigned char)(len - pos);
        } else {
            cut = width;
            while (cut > 0 && text[pos + cut] != ' ')
                --cut;
            if (cut == 0)
                cut = width;
        }
        gfx_text(2, row++, PEN_WHITE, PEN_NAVY, text + pos, cut);
        pos = (unsigned char)(pos + cut);
    }
    snprintf(buf, sizeof buf, "%u/%u", (unsigned)game.dlg.page_index + 1,
            (unsigned)(game.dlg.page_count ? game.dlg.page_count : 1));
    gfx_text(34, 17, PEN_GREY, PEN_NAVY, buf, (unsigned char)strlen(buf));
    if (game.dlg.flags & RTS_DLG_FLAG_QUEST_OFFER)
        gfx_text(2, 18, PEN_SKY, PEN_NAVY, "RETURN: ACCEPT   ESC: DECLINE", 29);
    else
        gfx_text(2, 18, PEN_SKY, PEN_NAVY, "RETURN: CONTINUE", 16);
}

static unsigned char dialogue_buttons(void)
{
    unsigned char mask = 0;

    if (input_use() || input_fire())
        mask |= DLG_BTN_A;
    if (input_quit())
        mask |= DLG_BTN_B;
    return mask;
}

static void dialogue_send_ack(unsigned char decline)
{
    ++pickup_counter;
    if (send_player_state(facing, decline ? RTS_BUTTON_DIALOGUE_DECLINE : 0)) {
        heartbeat_due = now_ms() + HEARTBEAT_MS;
    } else {
        dlg_ack_retry = decline ? RTS_BUTTON_DIALOGUE_DECLINE : 0;
        dlg_ack_pending = 1;
    }
}

static int dialogue_modal(void)
{
    struct dlg_modal modal;
    unsigned char effects;

    game.dlg.request = 0;
    game.dlg.active = 1;
    input_poll();
    dlg_modal_open(&modal, dialogue_buttons());
    memset(game.tracers, 0, sizeof game.tracers);
    for (;;) {
        if (pump_link(0) < 0)
            return -1;
        input_poll();
        if (due(heartbeat_due)) {
            if (dlg_ack_pending) {
                if (send_player_state(facing, dlg_ack_retry))
                    dlg_ack_pending = 0;
            } else {
                send_player_state(facing, 0);
            }
            heartbeat_due = now_ms() + HEARTBEAT_MS;
        }
        service_cache_retries();
        if (map_loading || modal.closing)
            break;
        effects = dlg_modal_step(&modal, game.dlg.dirty, game.dlg.page_index,
                                 game.dlg.flags, dialogue_buttons());
        game.dlg.dirty = 0;
        if (effects & DLG_EFFECT_DRAW)
            dialogue_draw_page();
        if (effects & DLG_EFFECT_ACK_ACCEPT)
            dialogue_send_ack(0);
        if (effects & DLG_EFFECT_ACK_DECLINE)
            dialogue_send_ack(1);
        if (effects & DLG_EFFECT_CLOSE)
            break;
        Delay(1);
    }
    game.dlg.active = 0;
    game.dlg.dirty = 0;
    game.dlg.request = 0;
    /* The keys that closed the scene must not fire, use or quit. */
    fire_latch = use_latch = quit_latch = 1;
    terrain_dirty = world_dirty = hud_dirty = 1;
    game.message_dirty = 1;
    return 0;
}

/* ------------------------------------------------------------------ */
/* Game loop                                                           */

static void game_loop(void)
{
    unsigned long anim_base, start;
    unsigned char anim, last_anim = 0xFF;

    rt_state_init(&game);
    predict_init(&predict, 0, 0);
    bootstrap_fill_init(&fill);
    client_seq = 1;                  /* the AUTH frame used seq 0 */
    current_map_id = MAP_OVERWORLD;
    heartbeat_due = now_ms() + HEARTBEAT_MS;
    quit_latch = 1;

    /* Wait for the first authoritative world frame. */
    start = now_ms();
    while (!game.world_seen) {
        if (pump_link(1) < 0 || due(start + BOOTSTRAP_TIMEOUT_MS)) {
            boot_fail("THE REALM DID NOT RESPOND.", net_error_text(&link));
            return;
        }
    }
    /* A save that is not on the overworld gets its MAP_CHANGE (and palette)
     * a moment after the first WORLD_STATE: wait briefly before painting. */
    start = now_ms();
    while (current_map_id == MAP_OVERWORLD && !due(start + INITIAL_ART_WAIT_MS))
        pump_link(1);

    center_camera();
    gfx_clear(PEN_NAVY);
    gfx_set_palette(map_palette_id);
    gfx_hud_frame();
    hud_dirty = terrain_dirty = world_dirty = 1;
    game.message_dirty = game.quest_dirty = 1;
    anim_base = now_ms();
    tracer_due = hit_due = now_ms();

    for (;;) {
        unsigned long key;

        if (pump_link(0) < 0) {
            gfx_clear(PEN_NAVY);
            boot_title();
            boot_step("CONNECTION");
            boot_fail("THE CONNECTION TO THE REALM WAS LOST.",
                      net_error_text(&link));
            return;
        }
        input_poll();
        if (input_quit()) {
            if (!quit_latch)
                break;
        } else {
            quit_latch = 0;
        }

        if (game.dlg.request && !map_loading && !map_sync) {
            if (dialogue_modal() < 0)
                return;
            continue;
        }
        if (map_sync && due(map_sync_deadline))
            map_sync = 0;       /* echo lost: fall back rather than freeze */
        if (!map_loading && !map_sync)
            handle_input();
        if (due(heartbeat_due)) {
            heartbeat_due = now_ms() + (send_player_state(facing, 0) ? HEARTBEAT_MS : 0);
        }
        service_cache_retries();

        if (due(tracer_due)) {
            tracer_due = now_ms() + TRACER_STEP_MS;
            if (!map_loading)
                update_tracers();
        }
        if (due(hit_due)) {
            unsigned char i;

            hit_due = now_ms() + HIT_FLASH_STEP_MS;
            for (i = 0; i < game.beaver_count; ++i) {
                if (game.beavers[i].hit_timer) {
                    --game.beavers[i].hit_timer;
                    world_dirty = 1;
                }
            }
        }
        anim = (unsigned char)(((now_ms() - anim_base) / ANIM_MS) & 1);
        if (anim != last_anim) {
            last_anim = anim;
            world_dirty = 1;
        }
        update_hud();

        if (map_loading)
            continue;           /* world frozen behind the ENTERING banner */
        track_camera();
        key = ((unsigned long)(boot.origin_x + cam_x) << 24) |
              ((unsigned long)(boot.origin_y + cam_y) << 16) |
              ((unsigned long)cam_x << 8) | cam_y;
        if (key != last_view_key || game.tile_changed) {
            last_view_key = key;
            game.tile_changed = 0;
            terrain_dirty = 1;
        }
        if (terrain_dirty || world_dirty) {
            gfx_render_world(&game, boot.terrain, boot.origin_x, boot.origin_y,
                             cam_x, cam_y, facing, anim, terrain_dirty);
            terrain_dirty = world_dirty = 0;
        } else {
            Delay(1);           /* nothing to draw: give the CPU back */
        }
    }
}

/* ------------------------------------------------------------------ */

static void run(void)
{
    char where[48];

    boot_title();
    boot_step("FUJINET NIO");
    if (connect_fujinet() != 0) {
        boot_fail("FUJINET NIO IS NOT AVAILABLE.",
                  "LOAD FUJINET-NIO.DEVICE (FUJINET-LOAD-RESIDENT)");
        return;
    }
    boot_result("OK", PEN_SKY);
    if (!establish_identity())
        return;

    snprintf(where, sizeof where, "%s:%u", SERVER_HOST, (unsigned)HYBRID_SERVER_PORT);
    boot_step(where);
    if (net_open(&link, SERVER_HOST, HYBRID_SERVER_PORT) != 0) {
        boot_fail("COULD NOT CONNECT TO THE REALM.", net_error_text(&link));
        return;
    }
    boot_result("OK", PEN_SKY);
    boot_step("LOADING THE WORLD");
    if (!bootstrap()) {
        boot_fail("THE WORLD DID NOT LOAD.",
                  boot.got_welcome ? "TERRAIN INCOMPLETE" : "NO WELCOME");
        return;
    }
    gfx_text(32, boot_row, PEN_SKY, PEN_NAVY, "OK   ", 5);
    ++boot_row;
    boot_step("ENTERING THE REALM");

    /* Realtime on the same stream: preamble, AUTH, then a first position.
     * The server adopts the claimed spot until its first WORLD_STATE
     * corrects it; the window centre is the best guess available. */
    net_write(&link, (const unsigned char *)"RT3\n", 4);
    send_frame(rt_build_auth(wire, me.token));
    client_seq = 0;
    game.player_x = (unsigned char)(boot.origin_x + BOOTSTRAP_WINDOW_W / 2);
    game.player_y = (unsigned char)(boot.origin_y + BOOTSTRAP_WINDOW_H / 2);
    send_player_state(RTS_FACE_DOWN, 0);
    game_loop();
}

int main(int argc, char **argv)
{
    (void)argv;
    show_diag = argc > 1;       /* any argument: link diagnostics line */
    if (gfx_open() != 0) {
        gfx_close();
        return RETURN_FAIL;
    }
    input_init(gfx_window());
    splash_show();
    run();
    net_close(&link);
    net_done();
    gfx_close();
    return RETURN_OK;
}
