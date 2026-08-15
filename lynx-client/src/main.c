#include <lynx.h>
#include <serial.h>
#include <tgi.h>
#include <joystick.h>

#include "bootstrap.h"
#include "dlgmodal.h"
#include "rt_state.h"
#include "predict.h"
#include "render.h"
#include "hudtext.h"
#include "nameentry.h"
#include "sfx.h"

/* How many of the Option1 telemetry overlays this build carries: 0 none,
 * 1 perf, 2 perf+link, 3 perf+link+video. They are development instruments
 * rather than parts of the game and cost about 1.2 KB together, in a segment
 * that has about that much left, so they are opt-in:
 *
 *   make DIAG=3
 *
 * The count is also what Option1 cycles through, so a partial build has no
 * dead positions in the rotation. Everything else diagnostic is in every
 * build: the boot status boxes, the hex bootstrap failure screen, and the
 * counters the overlays read. */
#ifndef DIAG_PAGES
#define DIAG_PAGES 0
#endif

#define SCREEN_W 160
#define SCREEN_H 102
#define BAR_COUNT 16
#define BAR_W (SCREEN_W / BAR_COUNT)

#define FUJI_DEVICE_ID 0x70
#define NET_DEVICE_ID 0x71
#define FUJICMD_ENABLE_NETSTREAM 0xF0
#define FUJICMD_OPEN_APPKEY 0xDC
#define FUJICMD_READ_APPKEY 0xDD
#define FUJICMD_WRITE_APPKEY 0xDE
#define FUJICMD_ACK 0x06
#define FUJICMD_NAK 0x15

#define NETCMD_OPEN 0x4F
#define NETCMD_CLOSE 0x43
#define NETCMD_READ 0x52
#define NETCMD_WRITE 0x57
#define N_OPEN_MODE_RW 0x0C
#define N_OPEN_TRANS_NONE 0x00

#define FUJINET_CREATOR_ID 0x3022U
#define FUJINET_APP_ID 0x02
#define FUJINET_APPKEY_IDENTITY 0x00
#define APPKEY_MODE_READ 0
#define APPKEY_MODE_WRITE 1

/* Server endpoint. Overridable at build time, the same variables the Atari
 * client's Makefile takes:
 *
 *   make SERVER_HOST=192.168.1.120 HYBRID_SERVER_PORT=9000 LOGIN_SERVER_PORT=9010
 *
 * The login port is reached over a FujiNet N: URL and the realtime port through
 * ENABLE NETSTREAM, so the host has to be baked into both a string literal and
 * a raw byte payload. */
#ifndef SERVER_HOST
#define SERVER_HOST "localhost"
#endif
#ifndef HYBRID_SERVER_PORT
#define HYBRID_SERVER_PORT 9000
#endif
#ifndef LOGIN_SERVER_PORT
#define LOGIN_SERVER_PORT 9010
#endif

#define STRINGIFY_(x) #x
#define STRINGIFY(x) STRINGIFY_(x)
/* N1: is the FujiNet network device; the trailing slash is required. */
#define LOGIN_URL "N1:TCP://" SERVER_HOST ":" STRINGIFY(LOGIN_SERVER_PORT) "/"

#define REALTIME_PORT ((unsigned)HYBRID_SERVER_PORT)

/* A SIO command frame carries its payload length in one byte, and the appkey
 * identity record has to fit the 64-byte value FujiNet stores. Fail the build
 * rather than silently truncating a long SERVER_HOST at runtime. */
typedef char server_host_fits_the_wire[
    (3 + sizeof(LOGIN_URL) <= 255 && 4 + sizeof(SERVER_HOST) <= 255 &&
     sizeof(SERVER_HOST) <= 32) ? 1 : -1];

#define NETSTREAM_FLAG_TCP 0x01
#define NETSTREAM_FLAG_REGISTER 0x02
#define NETSTREAM_FLAGS (NETSTREAM_FLAG_TCP | NETSTREAM_FLAG_REGISTER)

#define NET_MAGIC 0xBF
#define NET_VERSION 1
#define LOGIN_REQUEST 0xA0
#define LOGIN_RESPONSE 0xA1
#define NET_HELLO 0x01
#define LOGIN_OK 0
#define LOGIN_USERNAME_TAKEN 1
/* Not a status the server sends: the client's own "the exchange did not
 * happen", kept clear of the real statuses (server/protocol.py). */
#define LOGIN_FAILED 0xFF
/* HELLO flags byte = link profile id (server Phase 54). 1 declares the
 * ComLynx 62,500-baud line so the server paces this session for it instead
 * of the Atari default. Unknown ids fall back to the Atari profile. */
#define LINK_PROFILE_LYNX_COMLYNX 1

#define STATUS_PENDING 0
#define STATUS_OK 1
#define STATUS_FAIL 2

#define STREAM_RX_CAP 1024
#define STREAM_PARSE_BUDGET 16
#define BOOTSTRAP_IDLE_LIMIT 60000U
#define HELLO_RETRY_IDLE 12000U
#define HELLO_MAX_TRIES 10
#define REALTIME_TX_RETRY_LIMIT 4096U

#define HEARTBEAT_FRAMES 15
/* The dialogue modal has no renderer to pace it, so it counts server ticks
 * (10 Hz WORLD_STATE arrivals) rather than frames -- 3 ticks is the same
 * ~0.25 s the game loop's 15 frames buy. MODAL_IDLE_SPINS bounds how long a
 * silent link waits before ticking anyway; it is deliberately coarse, since
 * its only job is to stop a dead downlink from muting the uplink entirely. */
#define MODAL_HEARTBEAT_TICKS 3
#define MODAL_IDLE_SPINS 512U
/* Frames to let an attach-time MAP_CHANGE arrive before the first paint, so a
 * non-overworld login uses the right palette (Atari
 * NETSTREAM_INITIAL_ART_WAIT_FRAMES). */
#define INITIAL_ART_WAIT_FRAMES 20
/* PARERR | OVERRUN | FRAMERR | RXBRK, plus the driver's ring-overflow bit. */
#define SER_ERROR_BITS 0x9E
#define MESSAGE_SCROLL_FRAMES 15
#define MESSAGE_SCROLL_PAUSE 60
#define BULLET_RANGE 6

/* Movement is paced by WORLD_STATE arrivals rather than by any local timer:
 * the server emits one per 10 Hz tick, so it is both a real-time clock and
 * exactly the rate the server can act on, and it costs no hardware timer.
 *
 * Do NOT reintroduce clock() here. It installs a VBL interruptor whose
 * handler returns with carry indeterminate (the clc in cc65's clock.s is
 * commented out), which can stop the interruptor chain before the TGI
 * driver's irq clears SWAPREQUEST -- the page then never becomes visible
 * and tgi_busy() stalls the loop. Counting frame-loop iterations is also
 * wrong: the loop rate is not stable, so the cadence stretched with render
 * cost.
 *
 * One step per server tick is also what keeps the deltas the server sees
 * cardinal. It applies only the newest PLAYER_STATE per tick, so extra
 * steps coalesce, and a right-then-down pair inside one tick arrives as a
 * diagonal whose side-tile check fails against a wall, forcing a snap. */
#define FACE_NONE 0xFF

/* Half-band, in tiles, the player may roam before the camera follows. The
 * camera holds still inside it, so local movement stays on the cheap dirty-tile
 * repaint instead of scrolling the whole viewport every step. Scrolling starts
 * once the player reaches this many tiles from the viewport edge; tune to taste
 * (larger = the camera follows more tightly, smaller = a bigger still zone). */
#define CAM_MARGIN_X 3
#define CAM_MARGIN_Y 3

#define CACHE_RESYNC_RETRY_FRAMES 45
#define WINDOW_COMMIT_RETRY_FRAMES 45

#define MAP_OVERWORLD 0

/* Lynx TGI palettes are 16 green bytes followed by 16 blue/red bytes. */
static const unsigned char boot_palette[BAR_COUNT * 2] = {
    0x02, 0x00, 0x03, 0x09, 0x09, 0x07, 0x03, 0x04,
    0x07, 0x0D, 0x0C, 0x08, 0x04, 0x08, 0x0C, 0x0F,
    0x23, 0x11, 0x4D, 0xAF, 0xB8, 0x77, 0x35, 0x48,
    0x5E, 0x5F, 0x53, 0x22, 0x84, 0xE5, 0xF5, 0xFF
};

static unsigned char status_boxes[8];
/* The name this cart logs in as: entered by the player on first boot, then
 * read back out of the appkey identity record on every later one. */
static char username[NAME_MAX + 1];
static unsigned char username_len;
static char token_ascii[16];
static unsigned char token_len;
static unsigned long token_value;
static struct bf_parser bootstrap_parser;
static struct bf_packet bootstrap_packet;
static struct bootstrap_state bootstrap_data;
static unsigned char stream_rx_buffer[STREAM_RX_CAP];
static unsigned stream_rx_read;
static unsigned stream_rx_write;
static unsigned stream_rx_count;
static unsigned stream_rx_total;
static unsigned char diag_serial_status;
static unsigned char diag_parser_errors;
static unsigned char diag_last_parser_error;
static unsigned char diag_window_packets;

/* Live game state. */
static struct rt_state game;
static struct predict_state player_predict;
static struct bootstrap_fill window_fill;
static unsigned char resync_pending;
static unsigned char resync_retry_countdown;
static unsigned char commit_retry_countdown;
static unsigned char current_map_id;
/* Set on MAP_CHANGE, cleared when the new map's window fill completes and
 * MAP_READY is sent. While set, input is frozen and the world is not drawn:
 * the player position is already the new-map spawn, but the active terrain
 * is still the old map until the fill activates, so rendering would show the
 * player over the wrong ground. */
static unsigned char map_loading;
/* Set after a map fill completes, cleared once the server accepts our
 * position on the new map. After a transition the server holds the player at
 * the spawn and rejects any PLAYER_STATE whose coordinates differ, until the
 * client echoes the spawn exactly (its respawn_correction_ticks). Predicting
 * a move before that echo lands just fights the correction -- the source of
 * the post-entry jitter -- so movement stays frozen through the sync and the
 * heartbeat sends the authoritative spawn until a non-correction WORLD_STATE
 * confirms it. Bounded by a timeout so a lost echo cannot freeze forever. */
static unsigned char map_sync;
static unsigned char map_sync_timeout;
static unsigned char stats_sprite[HUD_TEXT_SPRITE_BYTES];
static unsigned char msg_sprite[HUD_TEXT_SPRITE_BYTES];
static unsigned char quest_sprite[HUD_TEXT_SPRITE_BYTES];
static unsigned char wire[RTS_MAX_RAW + 2];
static unsigned char rx_encoded[RTS_MAX_RAW + 2];
static unsigned char rx_raw[RTS_MAX_RAW];
static unsigned char rx_encoded_len;
static unsigned client_seq;
/* The cardinal the player sprite is drawn in, and the aim reported on every
 * packet that is not a shot. */
static unsigned char facing;
/* The raw stick direction, 0-7. Diagonals live only here. */
static unsigned char aim_dir;
/* aim_dir sampled at the moment the fire button went down, so the reported aim
 * cannot drift if the stick moves before the packet goes out. */
static unsigned char fire_aim;
static unsigned char frame_counter;
static unsigned char heartbeat_countdown;
static unsigned char fire_counter;
static unsigned char pickup_counter;
/* Incrementing edge counter the server watches to flip PvP on/off. */
static unsigned char pvp_toggle_counter;
static unsigned char fire_latch;
/* Last health seen, so a drop can be heard. Starts at 0 and rises with the
 * first HUD_UPDATE: seeding it high would make the arrival of the real figure
 * sound like taking a hit. */
static unsigned char sfx_hp_last;
static unsigned char pickup_latch;
/* A dialogue ack whose transmit failed. The pickup counter is already bumped,
 * so the retry has to carry the same buttons byte -- a bare heartbeat in its
 * place would answer a quest offer with "accept" by omission. */
static unsigned char dlg_ack_pending;
static unsigned char dlg_ack_retry;
/* Palette the current map asked for, so the boot sequence can apply it after
 * render_init() rather than being overwritten by the default. */
static unsigned char map_palette_id;
static unsigned char move_last_dir;
static unsigned char world_tick;      /* ++ per WORLD_STATE: the 10 Hz clock */
static unsigned char move_last_world; /* world_tick when we last stepped */
static unsigned char input_prev_dir;
static unsigned char buffered_dir;

/* Option1-toggled link/render diagnostics, drawn over the message line.
 * These exist to separate "the input path dropped it" from "the link is
 * behind" without guessing, since the two feel identical in play. */
static unsigned char diag_enabled;
static unsigned char diag_opt_latch;
static unsigned char diag_frames;
static unsigned char diag_fps;
static unsigned char diag_worlds;
static unsigned char diag_world_rate;
static unsigned char diag_corrections;
static unsigned char diag_edges;
static unsigned char diag_resyncs;
static unsigned char diag_dirty;
static unsigned char diag_badframes;   /* rejected this window */
static unsigned char diag_bad_rate;    /* rejected in the last window */
static unsigned diag_txbytes;          /* realtime bytes sent this window */
static unsigned diag_tx_rate;
static unsigned char diag_link_status; /* sticky ser_status bits */
static unsigned char opt2_latch;
static unsigned char pause_latch;
/* 0 = everything, 1 = no terrain, 2 = no terrain and no entities, 3 =
 * terrain at half scale. Modes 1-3 look wrong because nothing erases the
 * previous frame; they exist to price the tile blits by difference, not to
 * be looked at. Mode 3 keeps the call count and quarters the pixels, which
 * separates per-call cost from per-pixel cost. Cycled by the Pause button
 * since Option2 became the PvP toggle. */
static unsigned char render_mode;
/* Frames still owing a HUD redraw. The HUD panel occupies rows 80..101,
 * which terrain and entity drawing never touch, so it only has to be
 * redrawn when its content changes -- but twice, once per alternating
 * page. Rasterizing and blitting it every frame was pure waste. */
static unsigned char hud_dirty;
/* Frames still owing a full terrain repaint, one per alternating page.
 * Anything that changes what the whole viewport shows -- the camera, the
 * window origin, or a terrain cell -- sets this to 2. Otherwise only the
 * cells entities covered get repainted, which is the whole saving. */
static unsigned char terrain_dirty;
/* Stateful hysteretic camera (in window tiles). Because it persists across
 * frames it must be told when the terrain cache shifts under it: the world tile
 * shown at viewport column 0 is origin + cam, so an origin that grows by one
 * needs a cam one smaller to keep the same ground on screen. cam_origin_* track
 * the origin the camera was last reconciled against. */
static unsigned char cam_x;
static unsigned char cam_y;
static unsigned cam_origin_x;
static unsigned cam_origin_y;
/* The world tile shown at the viewport's top-left, origin + cam, last time the
 * terrain was fully repainted. A full repaint is needed only when this changes
 * -- i.e. when the view actually scrolls. While the hysteretic camera holds,
 * the origin-shift correction keeps origin + cam constant even though origin
 * and cam each move every step (the server re-centres the window), so tracking
 * the sum instead of the parts is what lets local movement stay on the cheap
 * partial repaint. */
static unsigned last_view_x;
static unsigned last_view_y;
/* Origin and camera as of the last full repaint. Tracked separately from the
 * view sum because either one moving is enough to require one; see the trigger
 * in game_loop. */
static unsigned last_origin_x;
static unsigned last_origin_y;
static unsigned char last_cam_x;
static unsigned char last_cam_y;
static unsigned char message_scroll_offset;
static unsigned char message_scroll_countdown;
static unsigned char stats_hp_shown = 0xFF;
static unsigned char stats_level_shown = 0xFF;
static unsigned stats_gold_shown = 0xFFFFU;
static unsigned char stats_pvp_shown = 0xFF;
static unsigned char stats_mode_shown = 0xFF;
static unsigned stats_pvp_kills_shown = 0xFFFFU;

/* Defined below with the other shot helpers; a map change clears live shots
 * before this point in the source. */
static void clear_tracers(void);
/* Defined below; a map change re-seeds the camera from realtime_pump. */
static void center_camera(void);

static const unsigned char hex_glyphs[16][5] = {
    { 7, 5, 5, 5, 7 }, { 2, 6, 2, 2, 7 },
    { 7, 1, 7, 4, 7 }, { 7, 1, 7, 1, 7 },
    { 5, 5, 7, 1, 1 }, { 7, 4, 7, 1, 7 },
    { 7, 4, 7, 5, 7 }, { 7, 1, 1, 1, 1 },
    { 7, 5, 7, 5, 7 }, { 7, 5, 7, 1, 7 },
    { 2, 5, 7, 5, 5 }, { 6, 5, 6, 5, 6 },
    { 7, 4, 4, 4, 7 }, { 6, 5, 5, 5, 6 },
    { 7, 4, 6, 4, 7 }, { 7, 4, 6, 4, 4 }
};

static const unsigned char glyph_r[5] = { 6, 5, 6, 5, 5 };
static const unsigned char glyph_s[5] = { 7, 4, 7, 1, 7 };
static const unsigned char glyph_p[5] = { 6, 5, 6, 4, 4 };
static const unsigned char glyph_l[5] = { 4, 4, 4, 4, 7 };
static const unsigned char glyph_w[5] = { 5, 5, 5, 7, 2 };
static const unsigned char glyph_t[5] = { 7, 2, 2, 2, 2 };

static void draw_glyph(const unsigned char *glyph, int x, int y,
                       unsigned char color)
{
    unsigned char row;
    unsigned char column;

    tgi_setcolor(color);
    for (row = 0; row < 5; ++row) {
        for (column = 0; column < 3; ++column) {
            if (glyph[row] & (4 >> column)) {
                tgi_bar(x + column * 2, y + row * 2,
                        x + column * 2 + 1, y + row * 2 + 1);
            }
        }
    }
}

static void draw_diag_label(char label, int y, unsigned char color)
{
    const unsigned char *glyph = hex_glyphs[14];

    if (label == 'R') glyph = glyph_r;
    else if (label == 'S') glyph = glyph_s;
    else if (label == 'P') glyph = glyph_p;
    else if (label == 'L') glyph = glyph_l;
    else if (label == 'W') glyph = glyph_w;
    else if (label == 'T') glyph = glyph_t;
    else if (label == 'B') glyph = hex_glyphs[11];
    draw_glyph(glyph, 8, y, color);
}

static void draw_diag_value(char label, unsigned long value,
                            unsigned char digits, int y,
                            unsigned char color)
{
    unsigned char index;
    unsigned char shift = (digits - 1) * 4;

    draw_diag_label(label, y, color);
    for (index = 0; index < digits; ++index) {
        draw_glyph(hex_glyphs[(unsigned char)((value >> shift) & 0x0F)],
                   24 + index * 9, y, color);
        if (shift >= 4) {
            shift -= 4;
        }
    }
}

static void draw_bootstrap_diagnostics(void)
{
    while (tgi_busy()) {
    }
    tgi_setpalette(boot_palette);
    tgi_setbgcolor(1);
    tgi_clear();
    draw_diag_value('R', bootstrap_data.rows_received, 6, 5, 15);
    draw_diag_value('S', diag_serial_status, 2, 17, 15);
    draw_diag_value('T', stream_rx_total, 3, 29, 15);
    draw_diag_value('P', diag_parser_errors, 2, 41, 15);
    draw_diag_value('L', diag_last_parser_error, 1, 53, 15);
    draw_diag_value('E', bootstrap_data.error_code, 1, 65, 15);
    draw_diag_value('W', diag_window_packets, 1, 77, 15);
    draw_diag_value('B', bootstrap_parser.pos, 2, 89, 15);
    tgi_updatedisplay();
}

static void draw_status_box(unsigned char index)
{
    unsigned char status = status_boxes[index];
    unsigned char color = status == STATUS_PENDING ? 6 :
                          status == STATUS_OK ? 13 : 10;
    int x = 9 + (int)index * 18;

    tgi_setcolor(color);
    tgi_bar(x, 86, x + 12, 98);
    tgi_setcolor(1);
    tgi_line(x, 86, x + 12, 86);
    tgi_line(x, 98, x + 12, 98);
    tgi_line(x, 86, x, 98);
    tgi_line(x + 12, 86, x + 12, 98);
}

static void draw_boot_pattern(void)
{
    unsigned char i;

    /* tgi_updatedisplay() requests an asynchronous VBL swap. Do not start
       another full-screen redraw while the previous draw page is becoming
       visible. */
    while (tgi_busy()) {
    }
    tgi_setpalette(boot_palette);
    tgi_setbgcolor(0);
    tgi_clear();
    for (i = 0; i < BAR_COUNT; ++i) {
        tgi_setcolor(i);
        tgi_bar(i * BAR_W, 0, (i + 1) * BAR_W - 1, SCREEN_H - 1);
    }
    tgi_setcolor(14);
    tgi_line(0, 0, SCREEN_W - 1, SCREEN_H - 1);
    tgi_line(0, SCREEN_H - 1, SCREEN_W - 1, 0);
    for (i = 0; i < 8; ++i) {
        draw_status_box(i);
    }
    tgi_updatedisplay();
}

static void set_status(unsigned char index, unsigned char status)
{
    status_boxes[index] = status;
    draw_boot_pattern();
}

static unsigned char sum8(const unsigned char *buf, unsigned char len)
{
    unsigned char i;
    unsigned char sum = 0;
    for (i = 0; i < len; ++i) {
        sum += buf[i];
    }
    return sum;
}

static unsigned char xor8(const unsigned char *buf, unsigned char len)
{
    unsigned char i;
    unsigned char ck = 0;
    for (i = 0; i < len; ++i) {
        ck ^= buf[i];
    }
    return ck;
}

static void drain_serial(void)
{
    char b;
    unsigned timeout = 1200;
    while (timeout != 0) {
        if (ser_get(&b) == SER_ERR_OK) {
            timeout = 1200;
        } else {
            --timeout;
        }
    }
}

static void putb(unsigned char b)
{
    while (ser_put((char)b) != SER_ERR_OK) {
    }
}

static void put_bytes(const unsigned char *buf, unsigned char len)
{
    unsigned char i;
    for (i = 0; i < len; ++i) {
        putb(buf[i]);
    }
}

static signed char put_bytes_realtime(const unsigned char *buf,
                                      unsigned char len)
{
    unsigned char i;
    unsigned retries;

    /* Every byte here is time the ComLynx driver spends deaf: SER_PUT
       disables the receive interrupt for the duration of a transmission
       ("no receive while transmitting" in lynx-comlynx.s). */
    diag_txbytes += len;
    for (i = 0; i < len; ++i) {
        retries = REALTIME_TX_RETRY_LIMIT;
        while (ser_put((char)buf[i]) != SER_ERR_OK) {
            if (--retries == 0) {
                /* Giving up part-way leaves an unterminated fragment on the
                   wire. COBS delimits on zero, so without one here the
                   fragment and the caller's retransmission merge into a
                   single frame at the server, which then fails CRC -- losing
                   the retry as well as the original, and taking the uplink
                   down with it for as long as the TX ring stays full.
                   Terminating the fragment costs one byte and confines the
                   damage to the frame we abandoned. */
                ++diag_txbytes;
                ser_put(0);
                return 0;
            }
        }
    }
    return 1;
}

static signed char getb_timeout(unsigned char *out, unsigned timeout)
{
    char b;
    while (timeout != 0) {
        if (ser_get(&b) == SER_ERR_OK) {
            *out = (unsigned char)b;
            return 1;
        }
        --timeout;
    }
    return 0;
}

static signed char wait_for_ack(void)
{
    unsigned char b;
    while (getb_timeout(&b, 30000)) {
        if (b == FUJICMD_ACK) {
            return 1;
        }
        if (b == FUJICMD_NAK) {
            return 0;
        }
    }
    return -1;
}

static void send_command_frame(unsigned char device_id,
                               const unsigned char *payload,
                               unsigned char payload_len)
{
    drain_serial();
    putb(device_id);
    putb(0);
    putb(payload_len);
    put_bytes(payload, payload_len);
    putb(xor8(payload, payload_len));
}

static signed char command_complete(unsigned char device_id,
                                    const unsigned char *payload,
                                    unsigned char payload_len)
{
    send_command_frame(device_id, payload, payload_len);
    if (wait_for_ack() != 1) {
        return 0;
    }
    return wait_for_ack() == 1;
}

static signed char command_read(unsigned char device_id,
                                const unsigned char *payload,
                                unsigned char payload_len,
                                unsigned char *out,
                                unsigned char *out_len,
                                unsigned char out_cap)
{
    unsigned char hi;
    unsigned char lo;
    unsigned char len;
    unsigned char ck;
    unsigned char i;

    send_command_frame(device_id, payload, payload_len);
    if (wait_for_ack() != 1) {
        return 0;
    }
    if (!getb_timeout(&hi, 30000) || !getb_timeout(&lo, 30000)) {
        return 0;
    }
    len = lo;
    if (hi != 0 || len > out_cap) {
        return 0;
    }
    for (i = 0; i < len; ++i) {
        if (!getb_timeout(&out[i], 30000)) {
            return 0;
        }
    }
    if (!getb_timeout(&ck, 30000) || ck != xor8(out, len)) {
        putb(FUJICMD_NAK);
        return 0;
    }
    putb(FUJICMD_ACK);
    *out_len = len;
    return 1;
}

static signed char open_serial(void)
{
    const struct ser_params params = {
        SER_BAUD_62500, SER_BITS_8, SER_STOP_1, SER_PAR_ODD, SER_HS_NONE
    };
    if (ser_install(lynx_comlynx_ser) != SER_ERR_OK) {
        return 0;
    }
    return ser_open(&params) == SER_ERR_OK;
}

static void parse_token_value(void)
{
    unsigned char i;
    token_value = 0;
    for (i = 0; i < token_len; ++i) {
        if (token_ascii[i] >= '0' && token_ascii[i] <= '9') {
            token_value = token_value * 10 + (unsigned long)(token_ascii[i] - '0');
        }
    }
}

/* Cached identity record: "<username>,<token>,<host>".
 *
 * The username is stored rather than compiled in, so the name the player
 * picked on first boot is the name every later boot logs in as. It is read
 * back out of the record here; a record written by a build that still hardcoded
 * "LynxTest" parses as that name and keeps working.
 *
 * The host is part of the record because the token is only meaningful to the
 * server that issued it. Without it, pointing a cart at a different
 * SERVER_HOST would reuse the previous server's token, skip the login
 * entirely, and then sit there failing to authenticate. A record whose host
 * does not match this build is simply rejected, which falls through to a fresh
 * login and re-stores it -- including for records written before the host was
 * recorded at all. */
static signed char parse_identity_value(const unsigned char *buf,
                                        unsigned char len)
{
    unsigned char i = 0;
    unsigned char j = 0;
    static const char host[] = SERVER_HOST;

    while (i < len && buf[i] != ',') {
        /* Same rule the server applies (protocol.py _username_bytes): printable
           ASCII only. A record that fails it is not one we wrote, so it must
           not be pre-filled into the picker or sent as a login. */
        if (i >= NAME_MAX || buf[i] < 32 || buf[i] > 126) {
            return 0;
        }
        username[i] = (char)buf[i];
        ++i;
    }
    if (i == 0 || i >= len) {
        return 0;
    }
    username[i] = '\0';
    username_len = i;
    ++i; /* the comma */
    while (i < len && buf[i] >= '0' && buf[i] <= '9' && j < sizeof(token_ascii)) {
        token_ascii[j++] = (char)buf[i++];
    }
    token_len = j;
    if (i >= len || buf[i++] != ',') {
        return 0;
    }
    for (j = 0; j < sizeof(host) - 1; ++j) {
        if (i >= len || buf[i++] != (unsigned char)host[j]) {
            return 0;
        }
    }
    /* Reject a longer stored host that merely starts with ours. */
    if (i < len && buf[i] != 0) {
        return 0;
    }
    parse_token_value();
    return token_value != 0;
}

/* FujiNet addresses an appkey by (creator, app, key). Deriving the key from the
 * endpoint gives every server its own slot, so rebuilding against a different
 * SERVER_HOST no longer discards the token the previous one issued, and
 * switching back finds it again. Without this, each host change forces a fresh
 * login -- which the login server refuses outright, because the username is
 * still held by the record the previous login created.
 *
 * Slot 0 stays reserved for the pre-Phase-13 record that carried no host, so an
 * old cart's key is never mistaken for a tagged one. Two endpoints can collide
 * on a slot; the host stored inside the record (see parse_identity_value) is
 * what catches that, costing one re-login rather than a wrong token. */
static unsigned char appkey_slot(void)
{
    static const char host[] = SERVER_HOST;
    unsigned char h = 0;
    unsigned char i;

    for (i = 0; i < sizeof(host) - 1; ++i) {
        h = (unsigned char)((h << 1) | (h >> 7));
        h ^= (unsigned char)host[i];
    }
    /* Two servers on one host are still two servers. */
    h ^= (unsigned char)(HYBRID_SERVER_PORT & 0xFF);
    h = (unsigned char)((h << 1) | (h >> 7));
    h ^= (unsigned char)(LOGIN_SERVER_PORT & 0xFF);
    return h == FUJINET_APPKEY_IDENTITY ? (unsigned char)(h + 1) : h;
}

static signed char appkey_open(unsigned char mode)
{
    unsigned char payload[7];
    payload[0] = FUJICMD_OPEN_APPKEY;
    payload[1] = (unsigned char)(FUJINET_CREATOR_ID & 0xFF);
    payload[2] = (unsigned char)(FUJINET_CREATOR_ID >> 8);
    payload[3] = FUJINET_APP_ID;
    payload[4] = appkey_slot();
    payload[5] = mode;
    payload[6] = 0;
    return command_complete(FUJI_DEVICE_ID, payload, sizeof(payload));
}

static signed char try_load_appkey(void)
{
    unsigned char payload[1] = { FUJICMD_READ_APPKEY };
    unsigned char data[66];
    unsigned char len;

    if (!appkey_open(APPKEY_MODE_READ)) {
        return 0;
    }
    if (!command_read(FUJI_DEVICE_ID, payload, sizeof(payload), data, &len, sizeof(data))) {
        return 0;
    }
    return parse_identity_value(data, len);
}

static signed char store_appkey(void)
{
    static const char host[] = SERVER_HOST;
    unsigned char payload[65];
    unsigned char len;
    unsigned char i;

    if (!appkey_open(APPKEY_MODE_WRITE)) {
        return 0;
    }
    payload[0] = FUJICMD_WRITE_APPKEY;
    for (i = 1; i < sizeof(payload); ++i) {
        payload[i] = 0;
    }
    len = 1;
    for (i = 0; i < username_len; ++i) {
        payload[len++] = (unsigned char)username[i];
    }
    payload[len++] = ',';
    for (i = 0; i < token_len && len < sizeof(payload) - 1; ++i) {
        payload[len++] = (unsigned char)token_ascii[i];
    }
    /* Tag the record with the server that issued this token; see
       parse_identity_value. The guard on SERVER_HOST's length keeps this
       inside the 64-byte value. */
    payload[len++] = ',';
    for (i = 0; i < sizeof(host) - 1 && len < sizeof(payload); ++i) {
        payload[len++] = (unsigned char)host[i];
    }
    return command_complete(FUJI_DEVICE_ID, payload, sizeof(payload));
}

static void build_bf_packet(unsigned char type, const unsigned char *payload,
                            unsigned char payload_len, unsigned char *frame,
                            unsigned char *frame_len)
{
    unsigned char len = 0;
    frame[len++] = NET_MAGIC;
    frame[len++] = NET_VERSION;
    frame[len++] = type;
    frame[len++] = payload_len;
    while (payload_len != 0) {
        frame[len++] = *payload++;
        --payload_len;
    }
    frame[len] = sum8(frame, len);
    *frame_len = len + 1;
}

static signed char network_open_login(void)
{
    static const unsigned char url[] = LOGIN_URL;
    /* cmd + mode + translation + the URL including its terminator. Sized from
       the URL so a longer SERVER_HOST cannot overrun it. */
    unsigned char payload[3 + sizeof(url)];
    unsigned char len = 0;
    unsigned char i;

    payload[len++] = NETCMD_OPEN;
    payload[len++] = N_OPEN_MODE_RW;
    payload[len++] = N_OPEN_TRANS_NONE;
    for (i = 0; i < sizeof(url); ++i) {
        payload[len++] = url[i];
    }
    return command_complete(NET_DEVICE_ID, payload, len);
}

static signed char network_write(const unsigned char *buf, unsigned char len)
{
    unsigned char payload[40];
    unsigned char i;
    payload[0] = NETCMD_WRITE;
    for (i = 0; i < len; ++i) {
        payload[i + 1] = buf[i];
    }
    return command_complete(NET_DEVICE_ID, payload, len + 1);
}

static signed char network_read(unsigned char *out, unsigned char *out_len,
                                unsigned char out_cap)
{
    unsigned char payload[1] = { NETCMD_READ };
    return command_read(NET_DEVICE_ID, payload, sizeof(payload), out, out_len, out_cap);
}

static void network_close(void)
{
    unsigned char payload[1] = { NETCMD_CLOSE };
    command_complete(NET_DEVICE_ID, payload, sizeof(payload));
}

static signed char read_expected_bf_from_network(unsigned char expected_type,
                                                 unsigned char *out,
                                                 unsigned char *out_len)
{
    unsigned char chunk[64];
    unsigned char chunk_len;
    unsigned char frame[40];
    unsigned char pos = 0;
    unsigned char want = 4;
    unsigned char i;
    unsigned char polls = 60;

    while (polls-- != 0) {
        if (!network_read(chunk, &chunk_len, sizeof(chunk))) {
            continue;
        }
        for (i = 0; i < chunk_len; ++i) {
            frame[pos++] = chunk[i];
            if (pos == 1 && frame[0] != NET_MAGIC) {
                pos = 0;
                continue;
            }
            if (pos == 2 && frame[1] != NET_VERSION) {
                pos = 0;
                continue;
            }
            if (pos == 4) {
                want = frame[3] + 5;
                if (want > sizeof(frame)) {
                    pos = 0;
                    want = 4;
                }
            }
            if (pos >= want) {
                if (sum8(frame, want - 1) == frame[want - 1] &&
                    frame[2] == expected_type) {
                    *out_len = frame[3];
                    for (i = 0; i < *out_len; ++i) {
                        out[i] = frame[4 + i];
                    }
                    return 1;
                }
                pos = 0;
                want = 4;
            }
        }
    }
    return 0;
}

/* Logs in as `username`. Returns the server's LOGIN_* status, or LOGIN_FAILED
 * if the exchange never completed -- the caller has to tell "that name is
 * taken, ask for another" apart from "the link is down", because only the
 * first is worth re-prompting for. */
static unsigned char login_with_username(void)
{
    unsigned char payload[NAME_MAX + 1];
    unsigned char frame[16];
    unsigned char frame_len;
    unsigned char response[24];
    unsigned char response_len;
    unsigned char i;

    if (!network_open_login()) {
        return LOGIN_FAILED;
    }
    payload[0] = username_len;
    for (i = 0; i < username_len; ++i) {
        payload[i + 1] = (unsigned char)username[i];
    }
    build_bf_packet(LOGIN_REQUEST, payload, username_len + 1, frame, &frame_len);
    if (!network_write(frame, frame_len)) {
        network_close();
        return LOGIN_FAILED;
    }
    if (!read_expected_bf_from_network(LOGIN_RESPONSE, response, &response_len)) {
        network_close();
        return LOGIN_FAILED;
    }
    network_close();
    if (response_len < 2) {
        return LOGIN_FAILED;
    }
    if (response[0] != LOGIN_OK) {
        return response[0];
    }
    if (response[1] > sizeof(token_ascii)) {
        return LOGIN_FAILED;
    }
    token_len = response[1];
    for (i = 0; i < token_len; ++i) {
        token_ascii[i] = (char)response[i + 2];
    }
    parse_token_value();
    return token_value != 0 ? LOGIN_OK : LOGIN_FAILED;
}

static signed char enable_realtime_netstream(void)
{
    static const unsigned char host[] = SERVER_HOST;
    /* cmd + port (2) + the host including its terminator + flags. Sized from
       the host so a longer SERVER_HOST cannot overrun it. */
    unsigned char payload[4 + sizeof(host)];
    unsigned char len = 0;
    unsigned char i;

    payload[len++] = FUJICMD_ENABLE_NETSTREAM;
    payload[len++] = (unsigned char)(REALTIME_PORT & 0xFF);
    payload[len++] = (unsigned char)(REALTIME_PORT >> 8);
    for (i = 0; i < sizeof(host); ++i) {
        payload[len++] = host[i];
    }
    payload[len++] = NETSTREAM_FLAGS;
    return command_complete(FUJI_DEVICE_ID, payload, len);
}

static void raw_send_hello(void)
{
    unsigned char payload[7];
    unsigned char frame[16];
    unsigned char frame_len;
    payload[0] = LINK_PROFILE_LYNX_COMLYNX;
    payload[1] = 1;
    payload[2] = 0;
    payload[3] = (unsigned char)(token_value & 0xFF);
    payload[4] = (unsigned char)((token_value >> 8) & 0xFF);
    payload[5] = (unsigned char)((token_value >> 16) & 0xFF);
    payload[6] = (unsigned char)((token_value >> 24) & 0xFF);
    build_bf_packet(NET_HELLO, payload, sizeof(payload), frame, &frame_len);
    put_bytes(frame, frame_len);
}

static void stream_rx_reset(void)
{
    stream_rx_read = 0;
    stream_rx_write = 0;
    stream_rx_count = 0;
    stream_rx_total = 0;
}

static signed char stream_rx_drain(void)
{
    char serial_byte;
    unsigned char result;
    signed char received = 0;

    while (stream_rx_count < STREAM_RX_CAP) {
        result = ser_get(&serial_byte);
        if (result == SER_ERR_NO_DATA) {
            break;
        }
        if (result != SER_ERR_OK) {
            return -1;
        }
        stream_rx_buffer[stream_rx_write++] = (unsigned char)serial_byte;
        if (stream_rx_write == STREAM_RX_CAP) {
            stream_rx_write = 0;
        }
        ++stream_rx_count;
        ++stream_rx_total;
        received = 1;
    }
    return received;
}

static unsigned char stream_rx_get(unsigned char *byte)
{
    if (stream_rx_count == 0) {
        return 0;
    }
    *byte = stream_rx_buffer[stream_rx_read++];
    if (stream_rx_read == STREAM_RX_CAP) {
        stream_rx_read = 0;
    }
    --stream_rx_count;
    return 1;
}

static signed char bootstrap_process_rx(void)
{
    unsigned char byte;
    unsigned char budget = STREAM_PARSE_BUDGET;
    signed char parsed;
    signed char applied;

    while (budget-- != 0 && stream_rx_get(&byte)) {
        parsed = bf_parser_feed(&bootstrap_parser, byte, &bootstrap_packet);
        if (parsed == BF_FEED_ERROR) {
            ++diag_parser_errors;
            diag_last_parser_error = bootstrap_parser.last_error;
            continue;
        }
        if (parsed != BF_FEED_PACKET) {
            continue;
        }
        if (bootstrap_packet.type == BF_WINDOW) {
            ++diag_window_packets;
        }
        applied = bootstrap_apply(&bootstrap_data, &bootstrap_packet);
        if (applied == BOOTSTRAP_ERROR) {
            return -1;
        }
        if (applied == BOOTSTRAP_COMPLETE) {
            return 1;
        }
    }
    return 0;
}

static signed char raw_receive_bootstrap(void)
{
    unsigned idle = 0;
    unsigned char hello_tries = 1;
    signed char drained;
    signed char processed;

    bf_parser_init(&bootstrap_parser);
    bootstrap_init(&bootstrap_data);
    diag_serial_status = 0;
    diag_parser_errors = 0;
    diag_last_parser_error = BF_ERROR_NONE;
    diag_window_packets = 0;

    /* The firmware ACKs ENABLE NETSTREAM before it resolves the host and
       opens the TCP socket, so UART bytes sent in that window never reach
       the server. Re-send HELLO after each quiet interval until the
       bootstrap starts flowing (the server restarts it per HELLO). */
    raw_send_hello();
    while (idle < BOOTSTRAP_IDLE_LIMIT) {
        drained = stream_rx_drain();
        if (drained < 0) {
            break;
        }
        processed = bootstrap_process_rx();
        if (processed < 0) {
            break;
        }
        if (processed > 0) {
            set_status(5, STATUS_OK);
            set_status(6, STATUS_OK);
            return 1;
        }
        if (drained > 0 || stream_rx_count != 0) {
            idle = 0;
        } else {
            ++idle;
            if (idle >= HELLO_RETRY_IDLE && hello_tries < HELLO_MAX_TRIES) {
                raw_send_hello();
                ++hello_tries;
                idle = 0;
            }
        }
    }
    ser_status(&diag_serial_status);
    if (bootstrap_data.got_welcome) {
        set_status(5, STATUS_OK);
        set_status(6, STATUS_FAIL);
    } else {
        set_status(5, STATUS_FAIL);
    }
    draw_bootstrap_diagnostics();
    return 0;
}

/* ------------------------------------------------------------------ */
/* Live game                                                          */

/* aim is the facing byte to report, 0-7. It is explicit rather than read from
 * the global because only the packet carrying a fire may report a diagonal:
 * the server aims the shot from this byte, and everything else should keep
 * reporting the cardinal the sprite is drawn in. */
static signed char send_player_state(unsigned seq, unsigned char x,
                                     unsigned char y, unsigned char aim,
                                     unsigned char buttons)
{
    unsigned char len;

    len = rt_build_player_state(wire, seq, x, y, aim, buttons,
                                fire_counter, pickup_counter,
                                game.last_server_seq, pvp_toggle_counter);
    return put_bytes_realtime(wire, len);
}

/* Send (or re-send) a RESYNC_REQUEST reporting the client's active origin
 * plus whatever rows of an in-progress full-window fill already arrived, so
 * the server can NACK just the missing rows instead of restarting. Arms the
 * retry timer and the terrain-edge trust flag (see bootstrap.h) so the next
 * geometrically-adjacent TERRAIN_EDGE is accepted as a fresh baseline. */
static void send_resync_request(void)
{
    unsigned char len;
    unsigned char fill_origin_x = 0;
    unsigned char fill_origin_y = 0;
    unsigned char fill_id = 0;
    unsigned long rows_have = 0;

    if (window_fill.active) {
        fill_origin_x = (unsigned char)window_fill.origin_x;
        fill_origin_y = (unsigned char)window_fill.origin_y;
        fill_id = window_fill.fill_id;
        rows_have = window_fill.rows_have;
    }
    ++client_seq;
    len = rt_build_resync_request(wire, client_seq,
                                  (unsigned char)bootstrap_data.origin_x,
                                  (unsigned char)bootstrap_data.origin_y,
                                  fill_origin_x, fill_origin_y, rows_have,
                                  fill_id, 0);
    put_bytes_realtime(wire, len);
    bootstrap_data.revision_trust_next = 1;
    resync_pending = 1;
    resync_retry_countdown = CACHE_RESYNC_RETRY_FRAMES;
    ++diag_resyncs;
}

/* Tell the server the new map is loaded so it unpauses the player. The
 * WINDOW_COMMIT that Phase 7 already sends handles the terrain-cache
 * handshake; MAP_READY is the separate signal that ends transition_loading.
 * The server re-sends MAP_CHANGE every ~2 s until this arrives, and the
 * MAP_CHANGE handler is idempotent, so a lost MAP_READY simply repeats. */
static void send_map_ready(void)
{
    unsigned char len;

    ++client_seq;
    len = rt_build_map_ready(wire, client_seq, current_map_id,
                             (unsigned char)bootstrap_data.origin_x,
                             (unsigned char)bootstrap_data.origin_y);
    put_bytes_realtime(wire, len);
}

/* Per-frame retry timers for the two outstanding cache-recovery handshakes:
 * a WINDOW_COMMIT awaiting WINDOW_COMMIT_ACK, and a RESYNC_REQUEST awaiting
 * its first TERRAIN_EDGE/WINDOW_ROW response. */
static void service_cache_retries(void)
{
    unsigned char len;

    if (bootstrap_data.commit_pending) {
        if (commit_retry_countdown == 0) {
            ++client_seq;
            len = rt_build_window_commit(wire, client_seq,
                                         bootstrap_data.commit_fill_id,
                                         (unsigned char)bootstrap_data.origin_x,
                                         (unsigned char)bootstrap_data.origin_y,
                                         current_map_id, 1);
            put_bytes_realtime(wire, len);
            commit_retry_countdown = WINDOW_COMMIT_RETRY_FRAMES;
        } else {
            --commit_retry_countdown;
        }
    }
    if (resync_pending) {
        if (resync_retry_countdown == 0) {
            send_resync_request();
        } else {
            --resync_retry_countdown;
        }
    }
}

static void realtime_pump(void)
{
    unsigned char byte;
    unsigned char raw_len;
    unsigned char applied;

    while (stream_rx_get(&byte)) {
        if (byte != 0) {
            if (rx_encoded_len < sizeof(rx_encoded)) {
                rx_encoded[rx_encoded_len++] = byte;
            } else {
                rx_encoded_len = 0; /* oversized: discard to next delimiter */
            }
            continue;
        }
        if (rx_encoded_len == 0) {
            continue;
        }
        raw_len = rt_cobs_decode(rx_encoded, rx_encoded_len, rx_raw);
        rx_encoded_len = 0;
        applied = rt_apply(&game, bootstrap_data.terrain,
                           bootstrap_data.origin_x, bootstrap_data.origin_y,
                           rx_raw, raw_len);
        if (applied == RTS_INVALID) {
            /* Bad length/version/CRC, or a COBS decode that produced
               nothing. If this tracks our own transmit rate, reception is
               being corrupted by half-duplex collisions. */
            ++diag_badframes;
        }
        if (applied == RTS_WORLD_STATE) {
            /* apply_world_state() just wrote the raw authoritative position
             * into game.player_x/y; reconcile it against locally predicted
             * moves and write the result (still possibly ahead of the
             * server) back for rendering/movement to use. */
            ++world_tick;
            ++diag_worlds;
            if (map_sync) {
                /* Waiting for the server to accept our spawn echo. A world
                   frame without a correction means it has, so movement can
                   safely resume; keep the prediction anchored on the
                   authoritative position until then. */
                if (game.correction_flags == 0) {
                    map_sync = 0;
                }
                predict_init(&player_predict, game.player_x, game.player_y);
            } else if (!map_loading &&
                       predict_reconcile(&player_predict, game.player_x,
                                         game.player_y, game.correction_flags,
                                         game.echo_client_seq,
                                         bootstrap_data.terrain,
                                         bootstrap_data.origin_x,
                                         bootstrap_data.origin_y, &game)) {
                ++diag_corrections;
            }
            game.player_x = player_predict.x;
            game.player_y = player_predict.y;
        } else if (applied == RTS_TERRAIN_EDGE) {
            signed char edge_result;
            unsigned char len;

            if (!window_fill.active) {
                edge_result = bootstrap_apply_terrain_edge(
                    &bootstrap_data, game.edge.origin_x, game.edge.origin_y,
                    game.edge.width, game.edge.height, game.edge.revision,
                    game.edge.tiles, game.edge.tile_count);
                if (edge_result == BOOTSTRAP_EDGE_APPLIED) {
                    ++diag_edges;
                }
                if (edge_result == BOOTSTRAP_EDGE_APPLIED ||
                    edge_result == BOOTSTRAP_EDGE_DUPLICATE) {
                    ++client_seq;
                    len = rt_build_cache_step_ack(
                        wire, client_seq, bootstrap_data.revision,
                        (unsigned char)bootstrap_data.origin_x,
                        (unsigned char)bootstrap_data.origin_y);
                    put_bytes_realtime(wire, len);
                    resync_pending = 0;
                } else {
                    send_resync_request();
                }
            }
        } else if (applied == RTS_WINDOW_ROW) {
            signed char fill_result = bootstrap_fill_apply_row(
                &window_fill, game.window_row.fill_id,
                game.window_row.origin_x, game.window_row.origin_y,
                game.window_row.row_index, game.window_row.tiles);

            if (fill_result != BOOTSTRAP_FILL_IGNORED) {
                /* Real progress: push the retry clock back out so we don't
                 * re-send a whole RESYNC_REQUEST over the half-duplex link
                 * while the server is already correctly streaming rows.
                 * resync_pending stays set until the fill completes, so a
                 * genuine stall (no row for a full retry interval) still
                 * re-requests -- now reporting just what's still missing. */
                resync_retry_countdown = CACHE_RESYNC_RETRY_FRAMES;
            }
            if (fill_result == BOOTSTRAP_FILL_COMPLETE) {
                bootstrap_fill_activate(&window_fill, &bootstrap_data);
                player_predict.count = 0;
                resync_pending = 0;
                commit_retry_countdown = 0;
                /* Every cell just changed, so both pages owe a full repaint --
                   unconditionally, not only on a map change. The server can
                   force a resync at the same origin when story terrain changes
                   under us (repairing the bridge unmasks ten road cells that
                   were being sent as water). With the repaint tied to the
                   camera moving, that arrives invisibly and the player keeps
                   seeing water on solid ground. */
                terrain_dirty = 2;
                last_view_x = 0xFFFF;
                last_view_y = 0xFFFF;
                last_origin_x = 0xFFFF;
                last_cam_x = 0xFF;
                if (map_loading) {
                    /* The new map's terrain is now active. Reset prediction
                       onto the spawn and tell the server we are ready. */
                    predict_init(&player_predict, game.player_x,
                                 game.player_y);
                    send_map_ready();
                    map_loading = 0;
                    /* Sync our position to the server before predicting: it
                       is holding us at the spawn and will reject mismatching
                       moves until we echo it (see map_sync). Heartbeat now,
                       so the echo goes out without waiting a full interval. */
                    map_sync = 1;
                    map_sync_timeout = 120;
                    heartbeat_countdown = 0;
                    /* The player teleported and the origin jumped; re-seed the
                       hysteretic camera on the spawn rather than letting the
                       per-frame shift correction chase a huge delta. */
                    center_camera();
                    /* Replace the ENTERING banner with the live server
                       message again. */
                    game.message_dirty = 1;
                }
            }
        } else if (applied == RTS_WINDOW_COMMIT_ACK) {
            if (bootstrap_commit_ack_matches(
                    &bootstrap_data, game.window_commit_ack.fill_id,
                    game.window_commit_ack.origin_x,
                    game.window_commit_ack.origin_y)) {
                bootstrap_data.commit_pending = 0;
            }
        } else if (applied == RTS_MAP_CHANGE) {
            /* The server re-sends MAP_CHANGE every ~2 s until it sees
               MAP_READY. Three cases, and getting them apart matters:
               - same map, still loading: a duplicate mid-load. Ignore it, or
                 the staged fill restarts and a slow link never finishes.
               - same map, already loaded: our MAP_READY was lost. Just
                 re-answer; do NOT restart the load, or a lost reply loops
                 the player back onto the ENTERING banner forever.
               - a different map: a genuine transition to load. */
            if (game.map_change.map_id == current_map_id) {
                if (!map_loading) {
                    send_map_ready();
                }
            } else {
                current_map_id = game.map_change.map_id;
                game.player_x = game.map_change.spawn_x;
                game.player_y = game.map_change.spawn_y;
                predict_init(&player_predict, game.player_x, game.player_y);
                /* Re-tint for the new map before its terrain arrives, so the
                   ENTERING banner and the first painted rows already use the
                   right palette. Remembered too, because render_init() runs
                   after this during boot and would otherwise reset it. */
                map_palette_id = game.map_change.palette_id;
                render_set_palette(map_palette_id);
                /* Drop any overworld cache work in flight; the server starts
                   a fresh full-window fill for the new map. */
                window_fill.active = 0;
                bootstrap_data.commit_pending = 0;
                clear_tracers();
                map_loading = 1;
                /* Arm the resync retry so a WINDOW_ROW dropped on the slow
                   link is re-requested. The server does not resend rows on
                   its own until a WINDOW_COMMIT times out, and the client
                   only commits once the fill completes, so without this a
                   single lost row deadlocks the load (banner stuck on
                   ENTERING...). The retry reports the rows already received,
                   so only the missing ones come back. */
                resync_pending = 1;
                resync_retry_countdown = CACHE_RESYNC_RETRY_FRAMES;
                /* Freeze the world and show a banner. The world layers are
                   not redrawn while loading (see game_loop), so this text
                   survives until the new map cuts in. */
                hud_text_render(msg_sprite, "ENTERING...", 11, 14);
                hud_dirty = 2;
            }
        }
    }
}

static void update_stats_sprite(void)
{
    /* A couple of glyphs of headroom over HUD_TEXT_COLS so fmt_u16 can never
       run past the buffer when PvP kills push the line to its widest; the
       renderer truncates to HUD_TEXT_COLS for display. */
    char text[HUD_TEXT_COLS + 8];
    unsigned char len = 0;
    unsigned char hp = game.hud_seen ? game.hud_hp : game.health;
    unsigned char max_hp = game.hud_seen ? game.hud_max_hp : 0;
    unsigned char level = game.hud_seen ? game.hud_level : 1;
    unsigned char pvp = game.hud_seen ? game.hud_pvp_enabled : 0;
    unsigned pvp_kills = game.hud_seen ? game.hud_pvp_kills : 0;

    /* Let a HUD change already in flight finish reaching both alternating
       pages before producing the next one. hud_dirty counts down to 0 over
       two frames (one per page); a new render before then leaves the two
       pages showing different versions, which reads as flickering text --
       very visible in the PvP realm where kills/HP change every tick. The
       counter is force-decremented every frame in game_loop, so this can
       only ever delay a HUD update by a frame or two, never freeze it. */
    if (hud_dirty) {
        return;
    }

    if (hp == stats_hp_shown && level == stats_level_shown &&
        game.hud_gold == stats_gold_shown && pvp == stats_pvp_shown &&
        pvp_kills == stats_pvp_kills_shown &&
        render_mode == stats_mode_shown) {
        return;
    }
    stats_mode_shown = render_mode;
    stats_hp_shown = hp;
    stats_level_shown = level;
    stats_gold_shown = game.hud_gold;
    stats_pvp_shown = pvp;
    stats_pvp_kills_shown = pvp_kills;

    /* A render layer probe is on: say so, at the front of the line where it
       cannot be truncated away. M1 (no terrain) and M2 (no terrain, no
       entities) deliberately leave stale pixels, so on screen they are
       indistinguishable from a repaint bug -- which is exactly how one got
       mistaken for one. Only M0 is a real frame. */
    if (render_mode != 0) {
        text[len++] = 'M';
        text[len++] = (char)('0' + render_mode);
        text[len++] = '!';
        text[len++] = ' ';
    }
    text[len++] = '#'; /* heart glyph */
    len = fmt_u16(text, len, hp);
    if (max_hp != 0) {
        text[len++] = '/';
        len = fmt_u16(text, len, max_hp);
    }
    text[len++] = ' ';
    text[len++] = ' ';
    text[len++] = 'G';
    text[len++] = ':';
    len = fmt_u16(text, len, game.hud_gold);
    text[len++] = ' ';
    text[len++] = ' ';
    text[len++] = 'L';
    text[len++] = ':';
    len = fmt_u16(text, len, level);
    /* Mirror the Atari HUD: a "PvP" tag plus the player's kill count, shown
       only while PvP is active. A single separator (the other fields use two)
       keeps the tag inside the 31-glyph line at realistic hp/gold/level widths. */
    if (pvp) {
        text[len++] = ' ';
        text[len++] = 'P';
        text[len++] = 'V';
        text[len++] = 'P';
        text[len++] = ':';
        len = fmt_u16(text, len, pvp_kills);
    }
    hud_text_render(stats_sprite, text, len, 15);
    hud_dirty = 2;
}

#if DIAG_PAGES >= 1
/* One line of link/render telemetry:
 *   F frames/s   the render loop's real rate; if this is low, input is
 *                sampled too rarely and short taps are missed outright
 *   W WORLD_STATE/s   should sit at the server's 10 Hz tick; below that
 *                means the output budget is dropping coalesced updates
 *   P pending predicted moves not yet acknowledged
 *   C corrections (hard snaps) since boot
 *   E terrain edges applied     R resync requests sent
 * C climbing while walking means the server keeps rejecting predictions;
 * R climbing means the cache fell far enough behind to need a full refill,
 * which is what an "invisible wall" pause looks like from in here. */

#if DIAG_PAGES >= 3
/* Video page: the two framebuffer addresses the renderer uses, whether it
 * confirmed which one Suzy draws into, and which one that is.
 *
 * The terrain layer is a raw CPU copy into one of those two pages, so if the
 * page bookkeeping is wrong the whole layer targets the buffer Suzy is not
 * using -- and the symptom is sprite trails, which look like a drawing bug
 * rather than a bookkeeping one. Expect E018 and C038, the cc65 TGI driver's
 * own page constants, with B=1. B=0 means the parity probe was inconclusive and
 * terrain is switched off entirely; D flips every frame. Anything else explains
 * the trails outright.
 *
 * These addresses used to be read back from Mikey's display register at $FD94,
 * which is write-only on hardware -- that read is what produced the trails in
 * the first place. If this page ever shows something unexpected, suspect the
 * probe in calibrate_draw_page(), not a register. */
static void update_diag_video_sprite(void)
{
    char text[HUD_TEXT_COLS];
    unsigned char len = 0;
    unsigned page0 = 0;
    unsigned page1 = 0;
    unsigned char ok = 0;
    unsigned char draw_page = 0;

    render_video_info(&page0, &page1, &ok, &draw_page);

    text[len++] = 'P';
    len = fmt_hex16(text, len, page0);
    text[len++] = ' ';
    len = fmt_hex16(text, len, page1);
    text[len++] = ' ';
    text[len++] = 'B';
    len = fmt_u16(text, len, ok);
    text[len++] = ' ';
    text[len++] = 'D';
    len = fmt_u16(text, len, draw_page);
    hud_text_render(msg_sprite, text, len, 10);
    hud_dirty = 2;
}
#endif /* DIAG_PAGES >= 3 */

#if DIAG_PAGES >= 2
static void update_diag_link_sprite(void)
{
    char text[HUD_TEXT_COLS];
    unsigned char len = 0;

    /* X: frames rejected per second (bad CRC/length/version). If this rises
         with movement it is our own transmitting deafening the receiver.
       T: realtime bytes sent per second. Deaf time is T*11/62500 seconds,
         so T=320 is about 5.6% of the second spent unable to receive.
       S: sticky serial status, error bits only -- 80 ring overflow, 10 parity,
         08 overrun, 04 framing, 02 break. Any of these means bytes were
         actually lost. TXRDY/RXRDY/TXEMPTY are masked out: TXEMPTY is set
         whenever the transmitter is idle, so leaving it in made every healthy
         link report a non-zero status. */
    text[len++] = 'M';
    len = fmt_u16(text, len, render_mode);
    text[len++] = ' ';
    text[len++] = 'X';
    len = fmt_u16(text, len, diag_bad_rate);
    text[len++] = ' ';
    text[len++] = 'T';
    len = fmt_u16(text, len, diag_tx_rate);
    text[len++] = ' ';
    text[len++] = 'S';
    len = fmt_u16(text, len, diag_link_status);
    hud_text_render(msg_sprite, text, len, 12);
    hud_dirty = 2;
}
#endif /* DIAG_PAGES >= 2 */

static void update_diag_sprite(void)
{
    char text[HUD_TEXT_COLS];
    unsigned char len = 0;

    text[len++] = 'M';
    len = fmt_u16(text, len, render_mode);
    text[len++] = ' ';
    text[len++] = 'F';
    len = fmt_u16(text, len, diag_fps);
    text[len++] = ' ';
    text[len++] = 'W';
    len = fmt_u16(text, len, diag_world_rate);
    text[len++] = ' ';
    text[len++] = 'P';
    len = fmt_u16(text, len, player_predict.count);
    text[len++] = ' ';
    text[len++] = 'C';
    len = fmt_u16(text, len, diag_corrections);
    text[len++] = ' ';
    text[len++] = 'E';
    len = fmt_u16(text, len, diag_edges);
    text[len++] = ' ';
    text[len++] = 'R';
    len = fmt_u16(text, len, diag_resyncs);
    hud_text_render(msg_sprite, text, len, 12);
    hud_dirty = 2;
}
#endif /* DIAG_PAGES >= 1 */

/* Sample Option1 directly: cc65's joystick driver masks it out ($F3).
 * Pause is not in the joystick register at all -- it is bit 0 of Suzy's
 * SWITCHES register, which nothing else in the cc65 runtime reads. */
static void update_diagnostics(void)
{
    unsigned char opt = (SUZY.joystick & BUTTON_OPTION1) != 0;
    unsigned char opt2 = (SUZY.joystick & BUTTON_OPTION2) != 0;
    unsigned char pause = (SUZY.switches & BUTTON_PAUSE) != 0;

#if DIAG_PAGES >= 1
    /* Option1 cycles: off -> perf -> link -> video -> off, stopping at
       whichever pages this build has. */
    if (opt && !diag_opt_latch) {
        diag_enabled = diag_enabled >= DIAG_PAGES ? 0 : diag_enabled + 1;
        diag_dirty = 1;
        if (!diag_enabled) {
            game.message_dirty = 1; /* restore the real message line */
        }
    }
    diag_opt_latch = opt;
#else
    /* The overlay pages are compiled out, so Option1 has nothing to cycle. */
    (void)opt;
#endif

    /* Option2 toggles PvP: bump the counter the server edge-detects and push a
       PLAYER_STATE at once so the flip is not deferred to the next move or
       heartbeat. It used to cycle render_mode (the render-layer cost probe);
       that debug path is left intact below but is no longer bound to a button. */
    if (opt2 && !opt2_latch) {
        ++pvp_toggle_counter;
        ++client_seq;
        heartbeat_countdown =
            send_player_state(client_seq, game.player_x, game.player_y,
                              facing, 0) ?
            HEARTBEAT_FRAMES : 1;
    }
    opt2_latch = opt2;

    /* Pause cycles the render-layer cost probe (M0 -> M1 -> M2 -> M0), the
       binding Option2 had before it became the PvP toggle. M3 (half-scale
       terrain) went away with the Suzy terrain path it measured. Leaving a mode
       forces a full repaint on both pages, since M1/M2 deliberately leave stale
       pixels behind that a partial repaint would never erase. */
    if (pause && !pause_latch) {
        render_mode = render_mode >= 2 ? 0 : render_mode + 1;
        diag_dirty = 1;
        terrain_dirty = 2;
    }
    pause_latch = pause;

    /* The server's 10 Hz WORLD_STATE stream is the reference clock: ten of
       them is one second, so frames counted across them is a true fps.
       This deliberately avoids clock() -- see MOVE cadence note above. */
    ++diag_frames;
    if (diag_worlds >= 10) {
        diag_fps = diag_frames;
        diag_world_rate = diag_worlds;
        diag_bad_rate = diag_badframes;
        diag_tx_rate = diag_txbytes;
        diag_frames = 0;
        diag_worlds = 0;
        diag_badframes = 0;
        diag_txbytes = 0;
        {
            /* Error bits only, accumulated. TXRDY/RXRDY/TXEMPTY are normal
               states -- TXEMPTY is set whenever the transmitter is idle, i.e.
               nearly always -- so including them made a healthy link report a
               scary-looking 0x28 whose only real content was one OVERRUN.
               0x80 is the driver's own ring-overflow flag. */
            unsigned char now = 0;

            ser_status(&now);
            diag_link_status |= (unsigned char)(now & SER_ERROR_BITS);
        }
        diag_dirty = 1;
    }
    /* Only rasterize when the figures actually change -- once a second, not
       every frame. Re-rendering ~27 glyphs into a 396-byte sprite per frame
       cost more than everything it was measuring, dragging 21 fps down to 6
       and making the instrument report its own overhead. */
    /* !hud_dirty: hold off re-rasterizing the diag line until the previous
       HUD change has reached both pages, same anti-flicker rule as the
       stats/message lines. diag_dirty stays set so it renders on the next
       clean frame. */
#if DIAG_PAGES >= 1
    if (diag_enabled && diag_dirty && !hud_dirty) {
        if (diag_enabled == 1) {
            update_diag_sprite();
        }
#if DIAG_PAGES >= 2
        else if (diag_enabled == 2) {
            update_diag_link_sprite();
        }
#endif
#if DIAG_PAGES >= 3
        else if (diag_enabled == 3) {
            update_diag_video_sprite();
        }
#endif
        diag_dirty = 0;
    }
#endif
}

/* One frame of sound. Two triggers live here rather than at the sites that
 * cause them, because both are edges in server state rather than local events:
 * the health drop that means damage (the Atari client reads the same byte, at
 * fujirealm.asm:3094) and the arrival of a MESSAGE. Firing is local and is
 * played from handle_input instead.
 *
 * message_seen has no other consumer -- it is cleared here so a message sounds
 * once rather than every frame it stays on the HUD. */
static void update_sfx(void)
{
    /* Only the HUD's health is authoritative -- game.health before the first
       HUD_UPDATE is a placeholder, and watching it would sound a hit at the
       moment the real figure arrives. */
    if (game.hud_seen) {
        if (game.hud_hp < sfx_hp_last) {
            sfx_play(SFX_HURT);
        }
        sfx_hp_last = game.hud_hp;
    }
    if (game.message_seen) {
        game.message_seen = 0;
        sfx_for_message(game.message_id);
    }
    sfx_step();
}

static void update_msg_sprite(void)
{
    unsigned char visible;

    if (diag_enabled) {
        return;
    }
    /* Same double-buffer serialization as update_stats_sprite: don't emit
       a new message-line version while the last one is still propagating to
       the second page. Any pending message_dirty / scroll step just waits a
       frame; hud_dirty always drains, so nothing stalls. */
    if (hud_dirty) {
        return;
    }
    if (game.message_dirty) {
        game.message_dirty = 0;
        message_scroll_offset = 0;
        message_scroll_countdown = MESSAGE_SCROLL_PAUSE;
    } else if (game.message_len <= HUD_TEXT_COLS) {
        return;
    } else if (message_scroll_countdown != 0) {
        --message_scroll_countdown;
        return;
    } else {
        ++message_scroll_offset;
        if (message_scroll_offset + HUD_TEXT_COLS > game.message_len) {
            message_scroll_offset = 0;
            message_scroll_countdown = MESSAGE_SCROLL_PAUSE;
        } else {
            message_scroll_countdown = MESSAGE_SCROLL_FRAMES;
        }
    }
    visible = game.message_len - message_scroll_offset;
    hud_dirty = 2;
    hud_text_render(msg_sprite, &game.message[message_scroll_offset],
                    visible, 14);
}

/* Third HUD line: the active quest. The server owns the text, so there is no
 * local quest-name table to keep in step with new chains. quest_id 0 means no
 * active quest -- which now happens mid-campaign, when a chain completes -- and
 * must blank the line rather than leave the last quest's text up forever. */
static void update_quest_sprite(void)
{
    if (!game.quest_dirty || hud_dirty) {
        return;
    }
    game.quest_dirty = 0;
    hud_dirty = 2;
    if (game.quest_id == 0) {
        hud_text_render(quest_sprite, "", 0, 11);
    } else {
        hud_text_render(quest_sprite, game.quest_text, game.quest_len, 11);
    }
}

static void clear_tracers(void)
{
    unsigned char i;

    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        game.tracers[i].active = 0;
    }
    game.tracer_next = 0;
}

static void start_bullet(void)
{
    rt_spawn_tracer(&game, game.player_x, game.player_y, fire_aim);
}

/* Advance every live shot one tile. A shot dies on the first blocking terrain
 * tile or actor it enters, or once it has travelled RTS_BULLET_RANGE tiles --
 * whichever comes first -- so a tracer no longer sails over enemies or walls.
 * These are cosmetic: the server stays authoritative for damage. */
/* A live enemy or remote player standing on this cell. predict_can_move used to
 * cover this as a side effect, but the shot stepper deliberately uses the
 * narrower shot blocker set, so actors are now tested on their own. */
static unsigned char entity_at(unsigned char x, unsigned char y)
{
    unsigned char i;

    for (i = 0; i < game.beaver_count; ++i) {
        if (game.beavers[i].hp != 0 && game.beavers[i].x == x &&
            game.beavers[i].y == y) {
            return 1;
        }
    }
    for (i = 0; i < game.remote_count; ++i) {
        if ((game.remotes[i].state & RTS_REMOTE_ALIVE) != 0 &&
            game.remotes[i].x == x && game.remotes[i].y == y) {
            return 1;
        }
    }
    return 0;
}

static void update_tracers(void)
{
    unsigned char i;
    struct rt_tracer *t;
    unsigned char nx;
    unsigned char ny;

    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        t = &game.tracers[i];
        if (!t->active) {
            continue;
        }
        if (t->steps >= BULLET_RANGE) {
            t->active = 0;
            continue;
        }
        nx = t->x;
        ny = t->y;
        /* Terrain, the world edge and the diagonal corner rule in one call, on
         * the shot blocker set rather than the movement one. */
        if (!predict_shot_step(&nx, &ny, t->dir, bootstrap_data.terrain,
                               bootstrap_data.origin_x,
                               bootstrap_data.origin_y)) {
            t->active = 0;
            continue;
        }
        /* Actors are checked separately: a shot dies on the cell before the one
         * it would have entered, so it visibly halts on contact rather than
         * overlapping its target. */
        if ((nx == game.player_x && ny == game.player_y) ||
            entity_at(nx, ny)) {
            t->active = 0;
            continue;
        }
        t->x = nx;
        t->y = ny;
        ++t->steps;
    }
}

static void handle_input(void)
{
    unsigned char joy = joy_read(0);
    unsigned char buttons = 0;
    unsigned char send = 0;
    unsigned char dir = FACE_NONE;
    unsigned char step = 0;
    unsigned char due;
    unsigned char fresh;
    unsigned char x = game.player_x;
    unsigned char y = game.player_y;

    /* Diagonals first: the Lynx stick reports both axes at once, and testing
       the cardinals first would collapse every diagonal to whichever axis was
       checked earliest. */
    if (JOY_UP(joy) && JOY_LEFT(joy)) {
        dir = RTS_FACE_UP_LEFT;
    } else if (JOY_UP(joy) && JOY_RIGHT(joy)) {
        dir = RTS_FACE_UP_RIGHT;
    } else if (JOY_DOWN(joy) && JOY_LEFT(joy)) {
        dir = RTS_FACE_DOWN_LEFT;
    } else if (JOY_DOWN(joy) && JOY_RIGHT(joy)) {
        dir = RTS_FACE_DOWN_RIGHT;
    } else if (JOY_UP(joy)) {
        dir = RTS_FACE_UP;
    } else if (JOY_DOWN(joy)) {
        dir = RTS_FACE_DOWN;
    } else if (JOY_LEFT(joy)) {
        dir = RTS_FACE_LEFT;
    } else if (JOY_RIGHT(joy)) {
        dir = RTS_FACE_RIGHT;
    }

    /* One step per server tick. Comparing for inequality is wrap-safe and
       needs no elapsed-time arithmetic at all. */
    due = world_tick != move_last_world;

    /* Edge-detect the stick so a tap is distinguishable from a hold. */
    fresh = dir != input_prev_dir;
    input_prev_dir = dir;

    if (dir != FACE_NONE) {
        /* For cardinals RTS_FACE_* pack the axis in bit 1: up/down = 0,
           left/right = 1. A fresh press repeating the direction we last
           stepped cannot reach the server as an unintended diagonal however it
           coalesces, so it goes at once and tapping stays responsive. Holding a
           direction, or changing to a different one, waits for the cadence
           slot -- stepping immediately would put two moves inside one 10 Hz
           server tick, arriving as a single doubled delta that the server
           rejects. Diagonals only qualify for the fast path when the direction
           is unchanged, since every diagonal already moves both axes. */
        unsigned char same_axis =
            move_last_dir != FACE_NONE &&
            (dir == move_last_dir ||
             (dir < RTS_FACE_FIRST_DIAGONAL &&
              move_last_dir < RTS_FACE_FIRST_DIAGONAL &&
              (dir >> 1) == (move_last_dir >> 1)));

        /* The aim reported for a shot follows the stick exactly, diagonals
           included. The drawn/reported facing only tracks cardinals, matching
           the Atari: walking diagonally should not leave the next un-aimed
           shot pointing at a corner. */
        aim_dir = dir;
        if (dir < RTS_FACE_FIRST_DIAGONAL) {
            facing = dir;
        }
        if (due || (fresh && same_axis)) {
            step = 1;
        } else if (fresh) {
            /* Remember a press the cadence just gated. Without this, a tap
               shorter than the remaining wait -- very easy to do on a
               perpendicular turn -- is discarded outright and the press
               appears to do nothing, which is what made the D-pad need two
               or three tries. */
            buffered_dir = dir;
        }
    }

    if (!step && due && buffered_dir != FACE_NONE) {
        /* The slot opened after the button was already released. */
        dir = buffered_dir;
        step = 1;
    }
    if (step) {
        buffered_dir = FACE_NONE;
        /* Same delta table the shot stepper uses, so a diagonal step and a
           diagonal shot can never disagree about which way 4-7 point. */
        x = (unsigned char)(x + predict_shot_dx[dir]);
        y = (unsigned char)(y + predict_shot_dy[dir]);
        /* Anchor the cadence on movement that actually happened. A step
           refused by terrain or an entity must not consume the slot, or
           walking into a wall would also delay turning away from it. */
        if (predict_move(&player_predict, client_seq + 1, x, y,
                         bootstrap_data.terrain, bootstrap_data.origin_x,
                         bootstrap_data.origin_y, &game)) {
            game.player_x = x;
            game.player_y = y;
            move_last_dir = dir;
            move_last_world = world_tick;
            send = 1;
        }
    }

    if (JOY_BTN_A(joy)) {
        if (!fire_latch) {
            fire_latch = 1;
            sfx_play(SFX_SHOOT);
            ++fire_counter;
            buttons = RTS_BUTTON_FIRE;
            fire_aim = aim_dir;
            start_bullet();
            send = 1;
        }
    } else {
        fire_latch = 0;
    }
    if (JOY_BTN_B(joy)) {
        if (!pickup_latch) {
            pickup_latch = 1;
            ++pickup_counter;
            send = 1;
        }
    } else {
        pickup_latch = 0;
    }

    if (send) {
        ++client_seq;
        /* Only the packet carrying the fire bit reports the raw stick aim, so
           a diagonal shot is possible without a diagonal walk retargeting the
           next one. fire_aim is FACE_NONE-free: it is only read when the bit
           is set, and set in the same breath above. */
        if (send_player_state(client_seq, game.player_x, game.player_y,
                              (buttons & RTS_BUTTON_FIRE) ? fire_aim : facing,
                              buttons)) {
            heartbeat_countdown = HEARTBEAT_FRAMES;
        } else {
            heartbeat_countdown = 1;
        }
    }
}

/* Re-centre the hysteretic camera on the player and reconcile it to the
 * current window origin. Used at game start and after a map change, where the
 * player teleports and the origin jumps, so the per-frame shift correction
 * cannot track it incrementally. */
static void center_camera(void)
{
    unsigned char rel;

    rel = game.player_x - (unsigned char)bootstrap_data.origin_x;
    cam_x = rt_camera(rel >= RTS_WINDOW_W ? RTS_WINDOW_W - 1 : rel,
                      RTS_WINDOW_W, VIEW_COLS);
    rel = game.player_y - (unsigned char)bootstrap_data.origin_y;
    cam_y = rt_camera(rel >= RTS_WINDOW_H ? RTS_WINDOW_H - 1 : rel,
                      RTS_WINDOW_H, VIEW_ROWS);
    cam_origin_x = bootstrap_data.origin_x;
    cam_origin_y = bootstrap_data.origin_y;
}

/* Drain the serial RX ring into the app buffer; wired into the CPU tile
 * blitter so a long repaint keeps emptying the driver's 256-byte ring. */
static void pump_serial(void)
{
    stream_rx_drain();
}

/* ------------------------------------------------------------------------- */
/* Dialogue modal (DIALOGUE_PAGE, type 24).
 *
 * Layout on the 160x102 screen: a speaker name, the wrapped body, an n/m page
 * counter, and a prompt. Glyphs are 5px tall on a 7px pitch, so eight body
 * lines fit between the speaker and the counter -- 141 characters at 31 columns
 * needs five for ordinary prose, and eight covers the pathological case of
 * nothing but long words.
 *
 * Every line is rasterized into the shared msg_sprite and blitted immediately.
 * tgi_sprite blocks until Suzy is done, so one buffer is safe, and eight
 * dedicated hudtext sprites would cost 3.1 KB that MAIN does not have. */
#define DLG_X 2
#define DLG_SPEAKER_Y 2
#define DLG_BODY_Y 12
#define DLG_BODY_LINES 8
#define DLG_LINE_PITCH 7
#define DLG_PAGE_Y 72
#define DLG_PROMPT_Y 84
#define DLG_INK_SPEAKER 14
#define DLG_INK_BODY 15
#define DLG_INK_PROMPT 10

/* Speaker ids are NPC subtypes; the names are ours, the prose is the
 * server's. Anything unexpected (including 0, a scene with no speaker such as
 * the Deep Pump controls) draws nothing rather than a bogus name. */
static const char *dialogue_speaker_name(unsigned char speaker)
{
    switch (speaker) {
    case RTS_SPEAKER_NERISSA:
        return "NERISSA";
    case RTS_SPEAKER_DANIEL:
        return "DANIEL";
    case RTS_SPEAKER_WILHELM:
        return "WILHELM";
    case RTS_SPEAKER_LUCIAN:
        return "LUCIAN";
    case RTS_SPEAKER_GRIX:
        return "GRIX";
    default:
        return 0;
    }
}

static void dialogue_draw_line(const char *text, unsigned char len,
                               unsigned char ink, signed int y)
{
    hud_text_render(msg_sprite, text, len, ink);
    render_modal_text(msg_sprite, DLG_X, y);
    /* A page is eleven of these, each ~600 put_pixel calls. Drain between
       lines or the driver's 256-byte RX ring overflows mid-render. */
    stream_rx_drain();
}

static void dialogue_draw_page(void)
{
    const char *speaker;
    unsigned char pos = 0;
    unsigned char start;
    unsigned char len;
    unsigned char line;
    char buf[HUD_TEXT_COLS + 8];
    unsigned char at;

    /* render_modal_begin() waits out the previous blit before clearing, and
       its wait is a bare spin. That is the same mistake the game loop had:
       a whole frame deaf is more than the driver's 256-byte RX ring can
       absorb mid-page-burst. Wait here instead, draining as we go, so the
       one inside has nothing left to wait for. */
    while (tgi_busy()) {
        stream_rx_drain();
    }
    render_modal_begin();

    speaker = dialogue_speaker_name(game.dlg.speaker);
    if (speaker != 0) {
        len = 0;
        while (speaker[len] != 0) {
            ++len;
        }
        dialogue_draw_line(speaker, len, DLG_INK_SPEAKER, DLG_SPEAKER_Y);
    }

    for (line = 0; line < DLG_BODY_LINES; ++line) {
        len = hud_wrap_next(game.dlg.text, game.dlg.len, &pos, HUD_TEXT_COLS,
                            &start);
        if (len == 0) {
            break;
        }
        dialogue_draw_line(game.dlg.text + start, len, DLG_INK_BODY,
                           (signed int)(DLG_BODY_Y + line * DLG_LINE_PITCH));
    }

    /* "n/m", 1-based like the Atari's page counter. */
    if (game.dlg.page_count > 1) {
        at = fmt_u16(buf, 0, (unsigned)game.dlg.page_index + 1);
        buf[at++] = '/';
        at = fmt_u16(buf, at, game.dlg.page_count);
        dialogue_draw_line(buf, at, DLG_INK_PROMPT, DLG_PAGE_Y);
    }

    if (game.dlg.flags & RTS_DLG_FLAG_LAST_PAGE) {
        if (game.dlg.flags & RTS_DLG_FLAG_QUEST_OFFER) {
            dialogue_draw_line("A=YES  B=NO", 11, DLG_INK_PROMPT,
                               DLG_PROMPT_Y);
        } else {
            dialogue_draw_line("A=DONE", 6, DLG_INK_PROMPT, DLG_PROMPT_Y);
        }
    } else {
        dialogue_draw_line("A=NEXT", 6, DLG_INK_PROMPT, DLG_PROMPT_Y);
    }

    render_modal_end();
}

/* Acknowledge the shown page. The bump and the decline bit must ride the same
 * PLAYER_STATE: the server only reads the buttons byte on the tick the pickup
 * counter changed (game.py:1474), so splitting them loses the answer. */
static void dialogue_send_ack(unsigned char decline)
{
    ++pickup_counter;
    ++client_seq;
    if (send_player_state(client_seq, game.player_x, game.player_y, facing,
                          decline ? RTS_BUTTON_DIALOGUE_DECLINE : 0)) {
        heartbeat_countdown = HEARTBEAT_FRAMES;
    } else {
        /* Retry on the next frame. The counter stays bumped, so the retry
           carries the same answer rather than a bare heartbeat. */
        heartbeat_countdown = 1;
        dlg_ack_retry = decline ? RTS_BUTTON_DIALOGUE_DECLINE : 0;
        dlg_ack_pending = 1;
    }
}

/* Current action-button mask, for dlg_input_latch(). The Option buttons and
 * the D-pad are not part of a dialogue, so they are masked out here rather
 * than left for the latch to reason about. */
static unsigned char dialogue_buttons(void)
{
    unsigned char joy = joy_read(0);
    unsigned char mask = 0;

    if (JOY_BTN_A(joy)) {
        mask |= DLG_BTN_A;
    }
    if (JOY_BTN_B(joy)) {
        mask |= DLG_BTN_B;
    }
    return mask;
}

static void dialogue_modal(void)
{
    struct dlg_modal modal;
    unsigned char effects;
    unsigned char last_world = world_tick;
    unsigned idle_spins = 0;
    unsigned char due;

    game.dlg.request = 0;
    game.dlg.active = 1;
    /* Seeding the latch with whatever is down swallows the button that opened
       the scene; the game-loop latches do the same for fire/pickup. */
    fire_latch = 1;
    pickup_latch = 1;
    dlg_modal_open(&modal, dialogue_buttons());
    /* Carried over from the game loop it counts frames, not server ticks;
       zero it so the first paced tick transmits instead of waiting out a
       stale count in the wrong unit. */
    heartbeat_countdown = 0;
    clear_tracers();

    for (;;) {
        /* The link keeps running underneath: the watchdog needs traffic, the
           terrain cache keeps streaming, and our own ack has to get out. */
        stream_rx_drain();
        realtime_pump();

        /* The retry countdowns below count *frames*, because the game loop
           runs exactly one iteration per frame -- it blocks on the Suzy blit.
           This loop has no renderer and no frame wait, so decrementing them
           per iteration fires them thousands of times a second:
           the heartbeat, the resync retry and the commit retry all become
           floods. On a half-duplex link where SER_PUT keeps us deaf for the
           whole transmission, that is how simply opening a dialogue took the
           uplink down -- acks never landed, so A appeared dead, and the
           prediction queue never drained afterwards, so movement froze while
           turning still worked.

           Pace on the server's 10 Hz WORLD_STATE instead, the same timer-free
           real-time base the movement cadence uses. The spin fallback keeps a
           silent link ticking over slowly rather than either flooding it or
           going completely quiet. */
        due = 0;
        if (world_tick != last_world) {
            last_world = world_tick;
            idle_spins = 0;
            due = 1;
        } else if (++idle_spins >= MODAL_IDLE_SPINS) {
            idle_spins = 0;
            due = 1;
        }

        /* Input and the redraw below stay per-iteration: they are local, cost
           the link nothing, and gating them would make the modal feel
           sluggish. Only transmission is paced. */
        if (due) {
            if (dlg_ack_pending) {
                ++client_seq;
                if (send_player_state(client_seq, game.player_x,
                                      game.player_y, facing, dlg_ack_retry)) {
                    dlg_ack_pending = 0;
                    heartbeat_countdown = MODAL_HEARTBEAT_TICKS;
                }
            } else if (heartbeat_countdown == 0) {
                ++client_seq;
                heartbeat_countdown =
                    send_player_state(client_seq, game.player_x,
                                      game.player_y, facing, 0) ?
                    MODAL_HEARTBEAT_TICKS : 1;
            } else {
                --heartbeat_countdown;
            }
            service_cache_retries();
        }

        /* A map change outranks the conversation: the world is about to be
           replaced and the game loop owns that handshake. */
        if (map_loading || modal.closing) {
            break;
        }

        effects = dlg_modal_step(&modal, game.dlg.dirty, game.dlg.page_index,
                                 game.dlg.flags, dialogue_buttons());
        game.dlg.dirty = 0;

        if (effects & DLG_EFFECT_DRAW) {
            dialogue_draw_page();
        }
        if (effects & DLG_EFFECT_ACK_ACCEPT) {
            dialogue_send_ack(0);
        }
        if (effects & DLG_EFFECT_ACK_DECLINE) {
            dialogue_send_ack(1);
        }
        if (effects & DLG_EFFECT_CLOSE) {
            break;
        }
    }

    game.dlg.active = 0;
    game.dlg.dirty = 0;
    game.dlg.request = 0;
    /* Rebuild the game view: the modal cleared both pages, and the HUD text
       sprites were overwritten. */
    fire_latch = 1;
    pickup_latch = 1;
    terrain_dirty = 2;
    hud_dirty = 2;
    game.message_dirty = 1;
    last_view_x = 0xFFFF;
    last_view_y = 0xFFFF;
    last_origin_x = 0xFFFF;
    last_cam_x = 0xFF;
}

static void game_loop(void)
{
    unsigned char rel;
    unsigned char draw_flags;
    unsigned shift;
    unsigned view_x;
    unsigned view_y;

    rt_state_init(&game);
    predict_init(&player_predict, 0, 0);
    bootstrap_fill_init(&window_fill);
    resync_pending = 0;
    resync_retry_countdown = 0;
    commit_retry_countdown = 0;
    hud_text_init(stats_sprite);
    hud_text_init(msg_sprite);
    hud_text_init(quest_sprite);
    hud_text_render(msg_sprite, "WELCOME TO FUJIREALM", 20, 14);
    rx_encoded_len = 0;
    client_seq = 1; /* the auth frame used seq 0 */
    fire_counter = 0;
    pickup_counter = 0;
    pvp_toggle_counter = 0;
    fire_latch = 0;
    pickup_latch = 0;
    sfx_init();
    sfx_hp_last = 0;
    dlg_ack_pending = 0;
    dlg_ack_retry = 0;
    map_palette_id = 0;
    stats_pvp_shown = 0xFF;
    stats_pvp_kills_shown = 0xFFFFU;
    /* move_last_dir deliberately survives releasing the D-pad: a quick
       release and perpendicular re-press must not bypass the cadence and
       coalesce two axes into one server tick. FACE_NONE has no real axis,
       so it never matches one. */
    move_last_dir = FACE_NONE;
    input_prev_dir = FACE_NONE;
    buffered_dir = FACE_NONE;
    /* A real facing from the start: an un-aimed first shot must not report
       FACE_NONE, which the server refuses outright. */
    facing = RTS_FACE_DOWN;
    aim_dir = RTS_FACE_DOWN;
    fire_aim = RTS_FACE_DOWN;
    diag_enabled = 0;
    diag_opt_latch = 0;
    diag_frames = 0;
    diag_fps = 0;
    diag_worlds = 0;
    diag_world_rate = 0;
    diag_corrections = 0;
    diag_edges = 0;
    diag_resyncs = 0;
    diag_dirty = 1;
    hud_dirty = 2;
    /* render_init() clears both pages, so both owe a full repaint. */
    terrain_dirty = 2;
    last_view_x = 0xFFFF;
    last_view_y = 0xFFFF;
    last_origin_x = 0xFFFF;
    last_origin_y = 0xFFFF;
    last_cam_x = 0xFF;
    last_cam_y = 0xFF;
    diag_badframes = 0;
    diag_bad_rate = 0;
    diag_txbytes = 0;
    diag_tx_rate = 0;
    diag_link_status = 0;
    opt2_latch = 0;
    pause_latch = 1; /* held at boot must not immediately cycle the probe */
    render_mode = 0;
    world_tick = 0;
    move_last_world = 0;
    current_map_id = MAP_OVERWORLD;
    map_loading = 0;
    map_sync = 0;
    map_sync_timeout = 0;
    clear_tracers();
    heartbeat_countdown = HEARTBEAT_FRAMES;
    message_scroll_offset = 0;
    message_scroll_countdown = 0;

    /* Wait for the first authoritative world frame before rendering. */
    while (!game.world_seen) {
        stream_rx_drain();
        realtime_pump();
    }
    /* A player whose save puts them anywhere but the overworld gets an
       unsolicited MAP_CHANGE at attach, carrying the palette for the map they
       are standing in. It can arrive a frame or two after the first
       WORLD_STATE, so give it a bounded window before the first paint --
       otherwise a cave or arena login draws its first screens in overworld
       green. Falls through to the overworld default on timeout. */
    for (rel = 0; rel < INITIAL_ART_WAIT_FRAMES && current_map_id ==
                  MAP_OVERWORLD; ++rel) {
        stream_rx_drain();
        realtime_pump();
    }
    /* Player position is authoritative now; seed the hysteretic camera on it. */
    center_camera();
    render_init();
    /* After render_init, which installs the boot palette. */
    render_set_palette(map_palette_id);
    render_set_rx_pump(pump_serial);

    for (;;) {
        stream_rx_drain();
        realtime_pump();

        /* A dialogue scene takes over the screen and the input. It runs its own
           receive/heartbeat loop, so the link stays up while it blocks; on
           return the whole view is owed a repaint. Ignored while a map loads --
           that handshake belongs to this loop. */
        if (game.dlg.request && !map_loading && !map_sync) {
            dialogue_modal();
            continue;
        }

        /* While a map is loading, input and the world are frozen; only the
           receive pump, cache retries, and the ENTERING banner run. Movement
           also stays frozen through the brief post-load position sync so
           prediction does not fight the server's respawn correction. */
        if (map_sync && map_sync_timeout != 0) {
            if (--map_sync_timeout == 0) {
                map_sync = 0; /* echo lost: fall back rather than freeze */
            }
        }
        if (!map_loading && !map_sync) {
            handle_input();
        }
        if (heartbeat_countdown == 0) {
            ++client_seq;
            heartbeat_countdown =
                send_player_state(client_seq, game.player_x, game.player_y,
                                  facing, 0) ?
                HEARTBEAT_FRAMES : 1;
        } else {
            --heartbeat_countdown;
        }
        service_cache_retries();

        update_stats_sprite();
        update_quest_sprite();
        if (!map_loading) {
            update_msg_sprite();
            update_tracers();
        }
        update_diagnostics();
        update_sfx();

        /* The ComLynx driver's hardware RX ring is only 256 bytes; keep
         * draining it into the much larger software buffer while waiting
         * on the Suzy blit instead of spinning blind, or a burst of
         * WINDOW_ROW traffic can silently overflow it. Draining only moves
         * bytes into the ring, so it cannot mutate the terrain cache. */
        while (tgi_busy()) {
            stream_rx_drain();
        }
        stream_rx_drain();
        realtime_pump();

        /* Derive the camera only after the last pump, so it comes from the
           same origin and terrain this frame is about to draw. A
           TERRAIN_EDGE applied after the camera was computed shifts the
           cache under a stale camera, and the whole window visibly jumps a
           tile and then back on the following frame -- most noticeable when
           the player stops against an obstacle and the server's pending
           cache steps all flush at once. */
        /* Reconcile the stateful camera to any window-origin shift since last
           frame, so a held camera keeps the same ground on screen: an origin
           that grew by one needs a cam one smaller (and vice versa), clamped
           into the window. Then apply the hysteresis band. */
        if (bootstrap_data.origin_x != cam_origin_x) {
            if (bootstrap_data.origin_x > cam_origin_x) {
                shift = bootstrap_data.origin_x - cam_origin_x;
                cam_x = shift < cam_x ? cam_x - (unsigned char)shift : 0;
            } else {
                shift = cam_origin_x - bootstrap_data.origin_x;
                cam_x = shift + cam_x < RTS_WINDOW_W - VIEW_COLS ?
                    cam_x + (unsigned char)shift : RTS_WINDOW_W - VIEW_COLS;
            }
            cam_origin_x = bootstrap_data.origin_x;
        }
        if (bootstrap_data.origin_y != cam_origin_y) {
            if (bootstrap_data.origin_y > cam_origin_y) {
                shift = bootstrap_data.origin_y - cam_origin_y;
                cam_y = shift < cam_y ? cam_y - (unsigned char)shift : 0;
            } else {
                shift = cam_origin_y - bootstrap_data.origin_y;
                cam_y = shift + cam_y < RTS_WINDOW_H - VIEW_ROWS ?
                    cam_y + (unsigned char)shift : RTS_WINDOW_H - VIEW_ROWS;
            }
            cam_origin_y = bootstrap_data.origin_y;
        }

        rel = game.player_x - (unsigned char)bootstrap_data.origin_x;
        if (rel >= RTS_WINDOW_W) {
            rel = RTS_WINDOW_W - 1;
        }
        cam_x = rt_camera_track(cam_x, rel, RTS_WINDOW_W, VIEW_COLS,
                                CAM_MARGIN_X);
        rel = game.player_y - (unsigned char)bootstrap_data.origin_y;
        if (rel >= RTS_WINDOW_H) {
            rel = RTS_WINDOW_H - 1;
        }
        cam_y = rt_camera_track(cam_y, rel, RTS_WINDOW_H, VIEW_ROWS,
                                CAM_MARGIN_Y);

        /* Full repaint whenever the window origin or the camera moved, or a
           terrain cell mutated.

           Triggering on origin + cam (the world tile at the viewport's
           top-left) instead is strictly cheaper and looks correct on paper:
           while the hysteretic camera holds, the origin-shift correction
           cancels the server's re-centre, so the same world tiles stay on
           screen and only the cells entities covered need repainting. That is
           what e2c5687 did, and on hardware it smears a trail behind every
           moving sprite -- the partial path does not erase them. Before that
           commit the origin changed every step (the server re-centres the
           window each move), so movement always took a full repaint and the
           partial path only ever ran while standing still, which is the only
           state it was ever validated in.

           So: keep the partial path for a genuinely static view, where it
           halves the frame cost and is known to work, and pay the full repaint
           the moment anything scrolls. Do not re-narrow this trigger without
           testing the result on hardware -- render_tests.c models the
           bookkeeping and passes either way, so it will not catch the
           regression for you. */
        view_x = bootstrap_data.origin_x + cam_x;
        view_y = bootstrap_data.origin_y + cam_y;
        if (view_x != last_view_x || view_y != last_view_y ||
            bootstrap_data.origin_x != last_origin_x ||
            bootstrap_data.origin_y != last_origin_y ||
            cam_x != last_cam_x || cam_y != last_cam_y ||
            game.tile_changed) {
            last_view_x = view_x;
            last_view_y = view_y;
            last_origin_x = bootstrap_data.origin_x;
            last_origin_y = bootstrap_data.origin_y;
            last_cam_x = cam_x;
            last_cam_y = cam_y;
            game.tile_changed = 0;
            terrain_dirty = 2;
        }

        ++frame_counter;
        draw_flags = hud_dirty != 0 ? RENDER_HUD : 0;
        if (map_loading) {
            /* Freeze the world layers: the player is at the new spawn but
               the active terrain is still the old map, so drawing them
               together would be wrong. Both pages converge on the frozen
               image within two frames, so there is no flicker. */
            draw_flags |= RENDER_HUD;
        } else if (render_mode == 0) {
            draw_flags |= RENDER_TERRAIN | RENDER_ENTITIES;
        } else if (render_mode == 1) {
            draw_flags |= RENDER_ENTITIES;
        }
        render_frame(&game, bootstrap_data.terrain,
                     bootstrap_data.origin_x, bootstrap_data.origin_y,
                     cam_x, cam_y, facing, (frame_counter >> 3) & 1,
                     stats_sprite, msg_sprite, quest_sprite, draw_flags,
                     terrain_dirty != 0);
        if (hud_dirty != 0) {
            --hud_dirty;
        }
        if (terrain_dirty != 0) {
            --terrain_dirty;
        }
    }
}

/* ------------------------------------------------------------------------- */
/* Name entry.
 *
 * Shown only when there is no usable cached identity -- a first boot, a cart
 * rebuilt against a different SERVER_HOST, or a name the server says is taken.
 * Everything it decides lives in nameentry.c and is host-tested; this is the
 * screen and the joypad around it.
 *
 * It borrows the dialogue modal's line renderer, so it costs no sprite of its
 * own: the same msg_sprite is rasterized and blitted per line. */

/* The picker takes the pad mask straight from joy_read(), so its button bits
 * have to be the driver's. If that ever stops being true, fail here rather
 * than on hardware -- there is no Lynx emulator to catch it in between. */
typedef char name_btn_layout_check[
    (NAME_BTN_UP == JOY_UP_MASK && NAME_BTN_DOWN == JOY_DOWN_MASK &&
     NAME_BTN_A == JOY_BTN_A_MASK && NAME_BTN_B == JOY_BTN_B_MASK &&
     NAME_BTN_MASK == (JOY_UP_MASK | JOY_DOWN_MASK |
                       JOY_BTN_A_MASK | JOY_BTN_B_MASK)) ? 1 : -1];

#define NAME_PROMPT_Y 16
#define NAME_VALUE_Y 34
#define NAME_HELP_Y 60

static void name_draw_line(const char *text, unsigned char ink, signed int y)
{
    unsigned char len = 0;
    while (text[len] != 0) {
        ++len;
    }
    dialogue_draw_line(text, len, ink, y);
}

static void prompt_for_name(unsigned char taken)
{
    char line[NAME_MAX + 2];
    unsigned char poll;
    /* Both alternating pages owe a repaint after every change, or the flip
       shows the previous character half the time. */
    unsigned char pages_owed = 2;

    /* Seed with whatever name we know: a rebuild against a new server, or a
       name the server refused, should not make the player type it all again. */
    name_entry_init(username);

    for (;;) {
        if (pages_owed != 0) {
            --pages_owed;
            render_modal_begin();
            /* The rejection replaces the title rather than adding a line:
               a fifth name_draw_line call is a few dozen bytes, and this
               screen shares a segment with the diagnostics overlays. */
            name_draw_line(taken ? "NAME TAKEN - PICK ANOTHER" :
                                   "ENTER YOUR NAME",
                           DLG_INK_SPEAKER, NAME_PROMPT_Y);
            name_entry_display(line);
            name_draw_line(line, DLG_INK_BODY, NAME_VALUE_Y);
            name_draw_line("UP DN PICK  A ADD  B DEL",
                           DLG_INK_PROMPT, NAME_HELP_Y);
            name_draw_line("A ON _ STARTS",
                           DLG_INK_PROMPT, NAME_HELP_Y + DLG_LINE_PITCH);
            render_modal_end();
        }

        /* NAME_BTN_* are the JOY_*_MASK bits, so the pad byte goes straight
           in; see nameentry.h. */
        poll = name_entry_poll(joy_read(0));
        if (poll == NAME_POLL_DONE) {
            break;
        }
        if (poll == NAME_POLL_CHANGED) {
            pages_owed = 2;
        }
    }

    for (username_len = 0; username_len < name_state.len; ++username_len) {
        username[username_len] = name_state.buf[username_len];
    }
    username[username_len] = '\0';
}

static void run_client(void)
{
    if (!open_serial()) {
        set_status(0, STATUS_FAIL);
        return;
    }
    set_status(0, STATUS_OK);

    if (try_load_appkey()) {
        set_status(1, STATUS_OK);
        set_status(2, STATUS_OK);
        set_status(3, STATUS_OK);
    } else {
        unsigned char status;
        unsigned char taken = 0;
        unsigned char attempts = 3;

        set_status(1, STATUS_FAIL);
        /* render_init() has to run before anything can be drawn as sprites;
           game_loop calls it again later, which only re-clears the pages. */
        render_init();
        hud_text_init(msg_sprite);
        for (;;) {
            prompt_for_name(taken);
            status = login_with_username();
            if (status != LOGIN_USERNAME_TAKEN || --attempts == 0) {
                break;
            }
            /* Only a taken name is worth asking again for; a dead link would
               otherwise trap the player in the picker forever. */
            taken = 1;
        }
        /* The picker owned the screen; put the status boxes back. */
        draw_boot_pattern();
        if (status != LOGIN_OK) {
            set_status(2, STATUS_FAIL);
            return;
        }
        set_status(2, STATUS_OK);
        set_status(3, store_appkey() ? STATUS_OK : STATUS_FAIL);
    }

    if (!enable_realtime_netstream()) {
        set_status(4, STATUS_FAIL);
        return;
    }
    set_status(4, STATUS_OK);
    stream_rx_reset();
    if (!raw_receive_bootstrap()) {
        return;
    }

    putb('R');
    putb('T');
    putb('3');
    putb('\n');
    put_bytes(wire, rt_build_auth(wire, token_value));
    /* The server will not start feeding WORLD_STATE until it has seen one
       PLAYER_STATE, so we have to send a position before it has told us
       where we are. It adopts whatever we claim, so the claim has to be the
       best guess available: the window origin plus half a window.
       That is exact whenever the window is centred on the player, and wrong
       by the clamp whenever the player is near a map edge -- the overworld
       spawn moved to (1, 92), a corner, where the origin clamps to (0, 72)
       and this guess lands 15 tiles away. game_loop adopts the authoritative
       position from the first WORLD_STATE, so pass the guess as a position
       only and keep the aim neutral. */
    (void)send_player_state(
        1,
        (unsigned char)(bootstrap_data.origin_x + BOOTSTRAP_WINDOW_W / 2),
        (unsigned char)(bootstrap_data.origin_y + BOOTSTRAP_WINDOW_H / 2),
        RTS_FACE_DOWN, 0);
    game_loop();
}

void main(void)
{
    tgi_install(lynx_160_102_16_tgi);
    tgi_init();
    while (tgi_busy()) {
    }
    tgi_setframerate(60);
    joy_install(lynx_stdjoy_joy);
    draw_boot_pattern();
    run_client();
    for (;;) {
    }
}
