#include "live.h"
#include "player.h"
#include "controls.h"
#include "server_host_default.h"
#include <coco.h>
#include <cmoc.h>
#include <fujinet-network.h>
#include <fujinet-bus.h>

/* Sized for the largest burst (a 24-row fill). A read must not ask for more
 * than is waiting: dwread waits for every byte it asks for. */
#define LIVE_RX_MAX 512
#define LIVE_MAX_READS 8
#define LIVE_TX_CAP 192
/* COBS of a 62-byte raw frame is at most 63 bytes. */
#define LIVE_ENC_CAP 72

#define LIVE_POLL_TICKS 1
#define LIVE_COMMIT_RETRY_TICKS 30
#define LIVE_RESYNC_RETRY_TICKS 60
#define LIVE_SILENCE_TICKS 300
#define LIVE_NUDGE_TICKS 30

#define MAP_OVERWORLD 0

#define STR_(x) #x
#define STR(x) STR_(x)

struct rt_state live_game;
struct terrain_cache live_terrain;
unsigned live_world_tick;
unsigned char live_facing;
unsigned char live_map_palette;
unsigned char live_map_loading;
unsigned char live_terrain_reset;
unsigned char live_connected;
unsigned char live_have_terrain;
unsigned char live_pickup_counter;
unsigned char live_pvp_counter;
unsigned char live_dlg_decline;

static char spec[64];
static unsigned client_seq;
static unsigned char fire_counter;
static unsigned char current_map_id;
static struct terrain_fill fill;
static unsigned char resync_pending;
static unsigned resync_at;
static unsigned commit_at;
static unsigned last_poll;
static unsigned last_rx;
static unsigned char net_unit;

static unsigned char rx_buf[LIVE_RX_MAX];
static unsigned char rx_enc[LIVE_ENC_CAP];
static unsigned char rx_enc_len;
static unsigned char rx_raw[RTS_WORKSPACE];
static unsigned char tx_buf[LIVE_TX_CAP];
static unsigned char tx_len;
static unsigned char wire[RTS_MAX_RAW + 2];

static void flush(void)
{
    if (tx_len != 0) {
        controls_poll();
        network_write(spec, tx_buf, tx_len);
        tx_len = 0;
    }
}

/* Queues wire[0..len). One network_write per pass instead of one per frame:
 * per-transaction cost dominates on this link. */
static void queue_frame(unsigned char len)
{
    if ((unsigned)tx_len + len > LIVE_TX_CAP) {
        flush();
    }
    memcpy(&tx_buf[tx_len], wire, len);
    tx_len = (unsigned char)(tx_len + len);
}

static void send_state(unsigned char x, unsigned char y,
                       unsigned char facing, unsigned char fire)
{
    if (fire) {
        ++fire_counter;
    }
    ++client_seq;
    queue_frame(rt_build_player_state(wire, client_seq, x, y, facing,
                                      (fire ? RTS_BUTTON_FIRE : 0) |
                                          live_dlg_decline,
                                      fire_counter, live_pickup_counter,
                                      live_game.last_server_seq,
                                      live_pvp_counter));
    player_note_sent(client_seq);
}

void live_send_state(unsigned char facing, unsigned char fire)
{
    send_state(player_x, player_y, facing, fire);
}

static void send_resync_request(void)
{
    unsigned char fill_origin_x = 0;
    unsigned char fill_origin_y = 0;
    unsigned char fill_id = 0;
    unsigned long rows_have = 0;

    if (fill.active) {
        fill_origin_x = (unsigned char)fill.origin_x;
        fill_origin_y = (unsigned char)fill.origin_y;
        fill_id = fill.fill_id;
        rows_have = fill.rows_have;
    }
    ++client_seq;
    queue_frame(rt_build_resync_request(
        wire, client_seq, (unsigned char)live_terrain.origin_x,
        (unsigned char)live_terrain.origin_y, fill_origin_x, fill_origin_y,
        rows_have, fill_id, 0));
    live_terrain.revision_trust_next = 1;
    resync_pending = 1;
    resync_at = getTimer();
}

static void send_map_ready(void)
{
    ++client_seq;
    queue_frame(rt_build_map_ready(wire, client_seq, current_map_id,
                                   (unsigned char)live_terrain.origin_x,
                                   (unsigned char)live_terrain.origin_y));
}

static void on_terrain_edge(void)
{
    signed char r;

    if (fill.active) {
        return;
    }
    r = terrain_apply_edge(&live_terrain, live_game.edge.origin_x,
                           live_game.edge.origin_y, live_game.edge.width,
                           live_game.edge.height, live_game.edge.revision,
                           live_game.edge.tiles, live_game.edge.tile_count);
    if (r == TERRAIN_EDGE_APPLIED || r == TERRAIN_EDGE_DUPLICATE) {
        ++client_seq;
        queue_frame(rt_build_cache_step_ack(
            wire, client_seq, live_terrain.revision,
            (unsigned char)live_terrain.origin_x,
            (unsigned char)live_terrain.origin_y));
        resync_pending = 0;
    } else {
        send_resync_request();
    }
}

static void on_window_row(void)
{
    signed char r = terrain_fill_apply_row(
        &fill, live_game.window_row.fill_id, live_game.window_row.origin_x,
        live_game.window_row.origin_y, live_game.window_row.row_index,
        live_game.window_row.tiles);

    if (r != TERRAIN_FILL_IGNORED) {
        resync_at = getTimer();
    }
    if (r != TERRAIN_FILL_COMPLETE) {
        return;
    }

    terrain_fill_activate(&fill, &live_terrain);
    resync_pending = 0;
    commit_at = getTimer() - LIVE_COMMIT_RETRY_TICKS;
    live_terrain_reset = 1;
    live_have_terrain = 1;

    if (live_map_loading) {
        send_map_ready();
        live_map_loading = 0;
        live_send_state(live_facing, 0);
    }
}

static void on_map_change(void)
{
    if (live_game.map_change.map_id == current_map_id) {
        if (!live_map_loading) {
            send_map_ready();
        }
        return;
    }

    current_map_id = live_game.map_change.map_id;
    live_game.player_x = live_game.map_change.spawn_x;
    live_game.player_y = live_game.map_change.spawn_y;
    player_snap(live_game.map_change.spawn_x, live_game.map_change.spawn_y);
    live_map_palette = live_game.map_change.palette_id;
    fill.active = 0;
    live_terrain.commit_pending = 0;
    live_map_loading = 1;
    resync_pending = 1;
    resync_at = getTimer();
}

static void on_frame(void)
{
    unsigned char raw_len = rt_cobs_decode(rx_enc, rx_enc_len, rx_raw);
    unsigned char applied;

    applied = rt_apply(&live_game, live_terrain.tiles, live_terrain.origin_x,
                       live_terrain.origin_y, rx_raw, raw_len);

    switch (applied) {
    case RTS_WORLD_STATE:
        ++live_world_tick;
        player_on_world_state();
        break;
    case RTS_TERRAIN_EDGE:
        on_terrain_edge();
        break;
    case RTS_WINDOW_ROW:
        on_window_row();
        break;
    case RTS_WINDOW_COMMIT_ACK:
        if (terrain_commit_ack_matches(&live_terrain,
                                       live_game.window_commit_ack.fill_id,
                                       live_game.window_commit_ack.origin_x,
                                       live_game.window_commit_ack.origin_y)) {
            live_terrain.commit_pending = 0;
        }
        break;
    case RTS_MAP_CHANGE:
        on_map_change();
        break;
    default:
        break;
    }
}

static void feed_byte(unsigned char b)
{
    if (b != 0) {
        if (rx_enc_len < LIVE_ENC_CAP) {
            rx_enc[rx_enc_len++] = b;
        } else {
            rx_enc_len = 0;
        }
        return;
    }
    if (rx_enc_len != 0) {
        on_frame();
        rx_enc_len = 0;
    }
}

unsigned char live_connect(const char *host, unsigned long token)
{
    static const unsigned char preamble[4] = { 'R', 'T', '3', '\n' };

    strcpy(spec, "N1:TCP://");
    strcat(spec, host);
    strcat(spec, ":" STR(HYBRID_SERVER_PORT) "/");

    rt_state_init(&live_game);
    memset(live_terrain.tiles, 0, sizeof(live_terrain.tiles));
    terrain_init(&live_terrain, 0, 0);
    terrain_fill_init(&fill);
    live_world_tick = 0;
    live_facing = RTS_FACE_DOWN;
    live_map_palette = 0;
    live_map_loading = 0;
    live_terrain_reset = 0;
    live_have_terrain = 0;
    live_connected = 1;
    client_seq = 1; /* the AUTH frame uses seq 0 */
    fire_counter = 0;
    live_pickup_counter = 0;
    live_pvp_counter = 0;
    live_dlg_decline = 0;
    current_map_id = MAP_OVERWORLD;
    resync_pending = 0;
    rx_enc_len = 0;
    tx_len = 0;
    last_poll = getTimer();
    last_rx = last_poll;
    commit_at = last_poll;
    resync_at = last_poll;

    net_unit = network_unit(spec);
    if (network_open(spec, 12, 0) != FN_ERR_OK ||
        network_write(spec, preamble, 4) != FN_ERR_OK ||
        network_write(spec, wire, rt_build_auth(wire, token)) != FN_ERR_OK) {
        network_close(spec);
        return 0;
    }
    return 1;
}

void live_close(void)
{
    network_close(spec);
}

void live_pump(void)
{
    NetworkStatus st;
    uint16_t got;
    uint16_t i;
    unsigned char reads = 0;
    unsigned now = getTimer();

    if ((unsigned)(now - last_poll) < LIVE_POLL_TICKS) {
        return;
    }
    last_poll = now;

    /* network_read_nb's status and read without its second status call: each
     * call costs several DriveWire round trips. A short read ends the pass. */
    while (reads < LIVE_MAX_READS) {
        if (network_unit_status(net_unit, &st) != FN_ERR_OK || st.avail == 0) {
            break;
        }
        controls_poll();
        got = LIVE_RX_MAX;
        if (st.avail < LIVE_RX_MAX) {
            got = st.avail;
        }
        network_bus_read((unsigned char)(FUJI_DEVICEID_NETWORK + net_unit - 1),
                         rx_buf, got);
        ++reads;
        last_rx = now;
        for (i = 0; i < got; ++i) {
            feed_byte(rx_buf[i]);
        }
        if (got < LIVE_RX_MAX) {
            break;
        }
    }

    live_connected = (unsigned)(now - last_rx) < LIVE_SILENCE_TICKS;
}

void live_service(void)
{
    unsigned now = getTimer();

    if (live_terrain.commit_pending &&
        (unsigned)(now - commit_at) >= LIVE_COMMIT_RETRY_TICKS) {
        ++client_seq;
        queue_frame(rt_build_window_commit(
            wire, client_seq, live_terrain.commit_fill_id,
            (unsigned char)live_terrain.origin_x,
            (unsigned char)live_terrain.origin_y, current_map_id, 1));
        commit_at = now;
    }
    if (resync_pending &&
        (unsigned)(now - resync_at) >= LIVE_RESYNC_RETRY_TICKS) {
        send_resync_request();
    }
    flush();
}

unsigned char live_wait_ready(unsigned timeout_ticks)
{
    unsigned start = getTimer();
    unsigned last_nudge = start - LIVE_NUDGE_TICKS;
    unsigned now;

    while (!live_game.world_seen || !live_have_terrain) {
        live_pump();
        live_service();
        now = getTimer();
        if ((unsigned)(now - start) >= timeout_ticks) {
            return 0;
        }
        /* The server sends nothing until it has seen a PLAYER_STATE. Our
         * position is unknown, so this one is a refused step: the reply
         * carries the real position. */
        if (!live_game.world_seen &&
            (unsigned)(now - last_nudge) >= LIVE_NUDGE_TICKS) {
            send_state(0, 0, RTS_FACE_DOWN, 0);
            last_nudge = now;
        }
    }
    return 1;
}
