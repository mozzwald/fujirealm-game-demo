#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "bootstrap.h"
#include "dlgmodal.h"
#include "hudtext.h"
#include "predict.h"
#include "render.h"
#include "rt_state.h"
#include "../art/lynx_art.h"

static unsigned char sum8(const unsigned char *buf, unsigned char len)
{
    unsigned char i;
    unsigned char sum = 0;
    for (i = 0; i < len; ++i) {
        sum += buf[i];
    }
    return sum;
}

static unsigned crc16_ccitt(const unsigned char *data, unsigned char len)
{
    unsigned char i;
    unsigned char bit;
    unsigned crc = 0xFFFF;
    for (i = 0; i < len; ++i) {
        crc ^= (unsigned)data[i] << 8;
        for (bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
        }
    }
    return crc & 0xFFFF;
}

static unsigned char cobs_encode(const unsigned char *in, unsigned char in_len,
                                 unsigned char *out)
{
    unsigned char read = 0;
    unsigned char write = 1;
    unsigned char code_index = 0;
    unsigned char code = 1;

    while (read < in_len) {
        if (in[read] == 0) {
            out[code_index] = code;
            code_index = write++;
            code = 1;
            ++read;
        } else {
            out[write++] = in[read++];
            ++code;
        }
    }
    out[code_index] = code;
    return write;
}

static unsigned char build_bf(unsigned char type, const unsigned char *payload,
                              unsigned char payload_len, unsigned char *frame)
{
    unsigned char i;
    unsigned char len = 0;

    frame[len++] = BF_MAGIC;
    frame[len++] = BF_VERSION;
    frame[len++] = type;
    frame[len++] = payload_len;
    for (i = 0; i < payload_len; ++i) {
        frame[len++] = payload[i];
    }
    frame[len] = sum8(frame, len);
    return len + 1;
}

static signed char feed_frame(struct bf_parser *parser,
                              const unsigned char *frame, unsigned char len,
                              struct bf_packet *packet)
{
    signed char result = BF_FEED_NONE;
    unsigned char i;

    for (i = 0; i < len; ++i) {
        result = bf_parser_feed(parser, frame[i], packet);
    }
    return result;
}

static void test_login_request(void)
{
    const unsigned char expected[] = {
        0xBF, 0x01, 0xA0, 0x09, 0x08,
        'L', 'y', 'n', 'x', 'T', 'e', 's', 't',
        0xBC
    };
    assert(sum8(expected, sizeof(expected) - 1) == expected[sizeof(expected) - 1]);
}

static void test_hello_checksum(void)
{
    unsigned char hello[] = {
        0xBF, 0x01, 0x01, 0x07, 0x00, 0x01, 0x00,
        0x78, 0x56, 0x34, 0x12, 0x00
    };
    hello[sizeof(hello) - 1] = sum8(hello, sizeof(hello) - 1);
    assert(hello[sizeof(hello) - 1] == 0xDD);
}

static void test_crc_and_cobs(void)
{
    unsigned char raw[] = {
        0x04, 0x03, 0x0D, 0x00, 0x00, 0x00,
        0x78, 0x56, 0x34, 0x12, 0x00, 0x00
    };
    unsigned char encoded[16];
    unsigned crc = crc16_ccitt(raw, 10);
    unsigned char len;

    raw[10] = (unsigned char)(crc & 0xFF);
    raw[11] = (unsigned char)(crc >> 8);
    assert(crc == 0xE7D6);
    len = cobs_encode(raw, sizeof(raw), encoded);
    assert(len == 13);
    assert(memcmp(encoded, "\x04\x04\x03\x0D\x01\x01\x07\x78\x56\x34\x12\xD6\xE7", 13) == 0);
}

static void test_initial_player_state_vector(void)
{
    const unsigned char expected[] = {
        0x04, 0x03, 0x03, 0x01, 0x02, 0x01,
        0x06, 0x0A, 0x14, 0x03, 0x66, 0xD7
    };
    unsigned char raw[] = {
        0x03, 0x03, 0x01, 0x00, 0x01, 0x00, 0x0A, 0x14, 0x03, 0, 0
    };
    unsigned char encoded[16];
    unsigned crc = crc16_ccitt(raw, 9);
    unsigned char len;

    raw[9] = (unsigned char)(crc & 0xFF);
    raw[10] = (unsigned char)(crc >> 8);
    assert(crc == 0xD766);
    len = cobs_encode(raw, sizeof(raw), encoded);
    assert(len == sizeof(expected));
    assert(memcmp(encoded, expected, sizeof(expected)) == 0);
}

static void test_bf_stream_parser(void)
{
    const unsigned char payload[] = { 1, 0x34, 0x12, 4, BF_VERSION };
    unsigned char frame[BF_MAX_FRAME];
    unsigned char len;
    unsigned char i;
    struct bf_parser parser;
    struct bf_packet packet;

    bf_parser_init(&parser);
    assert(bf_parser_feed(&parser, 0x42, &packet) == BF_FEED_NONE);
    len = build_bf(BF_WELCOME, payload, sizeof(payload), frame);
    for (i = 0; i + 1 < len; ++i) {
        assert(bf_parser_feed(&parser, frame[i], &packet) == BF_FEED_NONE);
    }
    assert(bf_parser_feed(&parser, frame[len - 1], &packet) == BF_FEED_PACKET);
    assert(packet.type == BF_WELCOME);
    assert(packet.payload_len == sizeof(payload));
    assert(memcmp(packet.payload, payload, sizeof(payload)) == 0);

    frame[len - 1] ^= 1;
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_ERROR);
    assert(parser.last_error == BF_ERROR_CHECKSUM);
    frame[len - 1] ^= 1;
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
}

static void make_window_payload(unsigned char *payload, unsigned char chunk_y)
{
    unsigned char i;
    unsigned base = (unsigned)chunk_y * BOOTSTRAP_WINDOW_W;

    payload[0] = 0x22;
    payload[1] = 0x22;
    payload[2] = 10;
    payload[3] = 0;
    payload[4] = 20;
    payload[5] = 0;
    payload[6] = BOOTSTRAP_WINDOW_W;
    payload[7] = BOOTSTRAP_WINDOW_H;
    payload[8] = chunk_y;
    payload[9] = 3;
    payload[10] = 96;
    payload[11] = 0;
    for (i = 0; i < 96; ++i) {
        payload[12 + i] = (unsigned char)(base + i);
    }
}

static void test_bootstrap_window_assembly(void)
{
    const unsigned char welcome[] = { 1, 0x34, 0x12, 4, BF_VERSION };
    unsigned char payload[BF_MAX_PAYLOAD];
    unsigned char frame[BF_MAX_FRAME];
    unsigned char len;
    unsigned char chunk_y;
    signed char applied = BOOTSTRAP_IGNORED;
    struct bf_parser parser;
    struct bf_packet packet;
    struct bootstrap_state state;

    bf_parser_init(&parser);
    bootstrap_init(&state);

    make_window_payload(payload, 0);
    len = build_bf(BF_WINDOW, payload, sizeof(payload), frame);
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
    assert(bootstrap_apply(&state, &packet) == BOOTSTRAP_WINDOW);
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
    assert(bootstrap_apply(&state, &packet) == BOOTSTRAP_WINDOW);

    len = build_bf(BF_WELCOME, welcome, sizeof(welcome), frame);
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
    assert(bootstrap_apply(&state, &packet) == BOOTSTRAP_WELCOME);

    for (chunk_y = 3; chunk_y < BOOTSTRAP_WINDOW_H; chunk_y += 3) {
        make_window_payload(payload, chunk_y);
        len = build_bf(BF_WINDOW, payload, sizeof(payload), frame);
        assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
        applied = bootstrap_apply(&state, &packet);
    }
    assert(applied == BOOTSTRAP_COMPLETE);
    assert(state.got_welcome == 1);
    assert(state.player_id == 1);
    assert(state.seed == 0x1234);
    assert(state.tick == 0x2222);
    assert(state.origin_x == 10);
    assert(state.origin_y == 20);
    assert(state.rows_received == BOOTSTRAP_ALL_ROWS);
    assert(state.terrain[0] == 0);
    assert(state.terrain[BOOTSTRAP_TERRAIN_SIZE - 1] == 0xFF);

    make_window_payload(payload, 23);
    payload[9] = 3;
    len = build_bf(BF_WINDOW, payload, sizeof(payload), frame);
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
    assert(bootstrap_apply(&state, &packet) == BOOTSTRAP_ERROR);
    assert(state.error_code == BOOT_ERROR_WINDOW_GEOMETRY);
}

static void test_fragmented_bootstrap_stream_with_hello_echo(void)
{
    const unsigned char hello[] = { 0, 1, 0, 0x78, 0x56, 0x34, 0x12 };
    const unsigned char welcome[] = { 1, 0x34, 0x12, 4, BF_VERSION };
    const unsigned char burst_sizes[] = { 1, 7, 2, 31, 16, 113, 3 };
    unsigned char payload[BF_MAX_PAYLOAD];
    unsigned char frame[BF_MAX_FRAME];
    unsigned char wire[1024];
    unsigned char frame_len;
    unsigned char chunk_y;
    unsigned wire_len = 0;
    unsigned index;
    unsigned end;
    unsigned char burst = 0;
    signed char parsed;
    signed char applied = BOOTSTRAP_IGNORED;
    struct bf_parser parser;
    struct bf_packet packet;
    struct bootstrap_state state;

    wire[wire_len++] = 0x55;
    wire[wire_len++] = 0x00;
    frame_len = build_bf(0x01, hello, sizeof(hello), frame);
    assert(frame_len == BOOTSTRAP_HELLO_FRAME_SIZE);
    memcpy(&wire[wire_len], frame, frame_len);
    wire_len += frame_len;
    frame_len = build_bf(BF_WELCOME, welcome, sizeof(welcome), frame);
    memcpy(&wire[wire_len], frame, frame_len);
    wire_len += frame_len;
    for (chunk_y = 0; chunk_y < BOOTSTRAP_WINDOW_H;
         chunk_y += BOOTSTRAP_WINDOW_CHUNK_ROWS) {
        make_window_payload(payload, chunk_y);
        frame_len = build_bf(BF_WINDOW, payload, sizeof(payload), frame);
        memcpy(&wire[wire_len], frame, frame_len);
        wire_len += frame_len;
    }
    assert(wire_len == 2 + BOOTSTRAP_HELLO_FRAME_SIZE +
                       BOOTSTRAP_EXPECTED_BYTES);

    bf_parser_init(&parser);
    bootstrap_init(&state);
    index = 0;
    while (index < wire_len && applied != BOOTSTRAP_COMPLETE) {
        end = index + burst_sizes[burst++ % sizeof(burst_sizes)];
        if (end > wire_len) {
            end = wire_len;
        }
        while (index < end) {
            parsed = bf_parser_feed(&parser, wire[index++], &packet);
            if (parsed == BF_FEED_PACKET) {
                applied = bootstrap_apply(&state, &packet);
            }
        }
    }
    assert(applied == BOOTSTRAP_COMPLETE);
    assert(index == wire_len);
    assert(state.rows_received == BOOTSTRAP_ALL_ROWS);
}

static void test_bootstrap_restart_adopts_new_generation(void)
{
    const unsigned char welcome[] = { 1, 0x34, 0x12, 4, BF_VERSION };
    unsigned char payload[BF_MAX_PAYLOAD];
    unsigned char frame[BF_MAX_FRAME];
    unsigned char len;
    unsigned char chunk_y;
    signed char applied = BOOTSTRAP_IGNORED;
    struct bf_parser parser;
    struct bf_packet packet;
    struct bootstrap_state state;

    bf_parser_init(&parser);
    bootstrap_init(&state);

    len = build_bf(BF_WELCOME, welcome, sizeof(welcome), frame);
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
    assert(bootstrap_apply(&state, &packet) == BOOTSTRAP_WELCOME);

    /* Two chunks from a bootstrap the server later restarts. */
    for (chunk_y = 0; chunk_y < 6; chunk_y += BOOTSTRAP_WINDOW_CHUNK_ROWS) {
        make_window_payload(payload, chunk_y);
        payload[0] = 0x11;
        len = build_bf(BF_WINDOW, payload, sizeof(payload), frame);
        assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
        assert(bootstrap_apply(&state, &packet) == BOOTSTRAP_WINDOW);
    }
    assert(state.tick == 0x2211);
    assert(state.rows_received != 0);

    /* A fresh WELCOME plus a full window set at a newer tick supersedes
       the partial one. */
    len = build_bf(BF_WELCOME, welcome, sizeof(welcome), frame);
    assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
    assert(bootstrap_apply(&state, &packet) == BOOTSTRAP_WELCOME);
    for (chunk_y = 0; chunk_y < BOOTSTRAP_WINDOW_H;
         chunk_y += BOOTSTRAP_WINDOW_CHUNK_ROWS) {
        make_window_payload(payload, chunk_y);
        len = build_bf(BF_WINDOW, payload, sizeof(payload), frame);
        assert(feed_frame(&parser, frame, len, &packet) == BF_FEED_PACKET);
        applied = bootstrap_apply(&state, &packet);
    }
    assert(applied == BOOTSTRAP_COMPLETE);
    assert(state.tick == 0x2222);
    assert(state.rows_received == BOOTSTRAP_ALL_ROWS);
    assert(state.terrain[BOOTSTRAP_TERRAIN_SIZE - 1] == 0xFF);
}

static unsigned char build_rt_raw(unsigned char type, unsigned char status,
                                  unsigned seq, const unsigned char *payload,
                                  unsigned char payload_len,
                                  unsigned char *raw)
{
    unsigned char i;
    unsigned crc;

    raw[0] = payload_len;
    raw[1] = RTS_VERSION;
    raw[2] = type;
    raw[3] = status;
    raw[4] = (unsigned char)(seq & 0xFF);
    raw[5] = (unsigned char)(seq >> 8);
    for (i = 0; i < payload_len; ++i) {
        raw[6 + i] = payload[i];
    }
    crc = rt_crc16(raw, payload_len + 6);
    raw[payload_len + 6] = (unsigned char)(crc & 0xFF);
    raw[payload_len + 7] = (unsigned char)(crc >> 8);
    return payload_len + 8;
}

static void test_rt_outgoing_server_vectors(void)
{
    const unsigned char expected_auth[] = {
        0x04, 0x04, 0x03, 0x0D, 0x01, 0x01, 0x07,
        0x78, 0x56, 0x34, 0x12, 0xD6, 0xE7, 0x00
    };
    const unsigned char expected_player[] = {
        0x04, 0x08, 0x03, 0x01, 0x02, 0x02, 0x0B, 0x0A, 0x14,
        0x03, 0x01, 0x07, 0x08, 0x56, 0x34, 0x69, 0x79, 0x00
    };
    unsigned char out[RTS_MAX_RAW + 2];
    unsigned char len;

    len = rt_build_auth(out, 0x12345678UL);
    assert(len == sizeof(expected_auth));
    assert(memcmp(out, expected_auth, sizeof(expected_auth)) == 0);
    len = rt_build_player_state(out, 2, 10, 20, RTS_FACE_RIGHT,
                                RTS_BUTTON_FIRE, 7, 8, 0x3456, 0);
    assert(len == sizeof(expected_player));
    assert(memcmp(out, expected_player, sizeof(expected_player)) == 0);
}

static void test_rt_state_packets(void)
{
    const unsigned char world_payload[] = {
        20, 24, 7, 1, 0x44, 0x33, 6, 12, 22,
        21, 23, 4, RTS_KIND_GOBLIN
    };
    const unsigned char hud_payload[] = {
        7, 12, 3, 0x34, 0x12, 0x78, 0x56,
        0xCD, 0xAB, 1, 2, 0
    };
    const unsigned char message_payload[] = {
        9, 5, 'H', 'E', 'L', 'L', 'O'
    };
    const unsigned char remote_payload[] = {
        30, 31, RTS_FACE_LEFT, RTS_REMOTE_ALIVE,
        32, 33, RTS_FACE_RIGHT, 0
    };
    unsigned char raw[RTS_MAX_RAW];
    unsigned char terrain[RTS_WINDOW_W * RTS_WINDOW_H];
    unsigned char len;
    struct rt_state state;

    memset(terrain, 0, sizeof(terrain));
    rt_state_init(&state);
    len = build_rt_raw(RTS_WORLD_STATE, 1, 0x1234, world_payload,
                       sizeof(world_payload), raw);
    assert(rt_apply(&state, terrain, 10, 20, raw, len) == RTS_WORLD_STATE);
    assert(state.world_seen == 1);
    assert(state.player_x == 20 && state.player_y == 24);
    assert(state.health == 7 && state.last_server_seq == 0x1234);
    assert(state.echo_client_seq == 0x3344);
    assert(state.beaver_count == 1);
    assert(state.beavers[0].x == 21 && state.beavers[0].y == 23);
    assert(state.beavers[0].kind == RTS_KIND_GOBLIN);
    assert(terrain[2 * RTS_WINDOW_W + 2] == 6);

    len = build_rt_raw(RTS_HUD_UPDATE, 0, 0x1235, hud_payload,
                       sizeof(hud_payload), raw);
    assert(rt_apply(&state, terrain, 10, 20, raw, len) == RTS_HUD_UPDATE);
    assert(state.hud_hp == 7 && state.hud_max_hp == 12);
    assert(state.hud_level == 3 && state.hud_gold == 0xABCD);
    /* flags byte = 1 (PvP enabled), kills = 2. */
    assert(state.hud_pvp_enabled == 1 && state.hud_pvp_kills == 2);

    len = build_rt_raw(RTS_MESSAGE, 0, 0x1236, message_payload,
                       sizeof(message_payload), raw);
    assert(rt_apply(&state, terrain, 10, 20, raw, len) == RTS_MESSAGE);
    assert(state.message_dirty == 1 && state.message_len == 5);
    assert(strcmp(state.message, "HELLO") == 0);

    len = build_rt_raw(RTS_REMOTE_PLAYERS, 2, 0x1237, remote_payload,
                       sizeof(remote_payload), raw);
    assert(rt_apply(&state, terrain, 10, 20, raw, len) ==
           RTS_REMOTE_PLAYERS);
    assert(state.remote_count == 2);
    assert(state.remotes[0].x == 30 && state.remotes[0].y == 31);
    assert(state.remotes[0].facing == RTS_FACE_LEFT);
    assert((state.remotes[0].state & RTS_REMOTE_ALIVE) != 0);
    assert(state.remotes[1].x == 32 && state.remotes[1].y == 33);
    assert((state.remotes[1].state & RTS_REMOTE_ALIVE) == 0);
    /* First sighting only establishes the fire baseline: no tracer yet. */
    assert(state.tracers[0].active == 0);

    {
        /* Slot 0 keeps its position but its fire bits change: that remote
         * fired, so a cosmetic tracer spawns from its cell and facing. Slot 1
         * is still absent and must not spawn anything. */
        const unsigned char fire_payload[] = {
            30, 31, RTS_FACE_LEFT, RTS_REMOTE_ALIVE | 0x04,
            32, 33, RTS_FACE_RIGHT, 0
        };
        len = build_rt_raw(RTS_REMOTE_PLAYERS, 2, 0x1239, fire_payload,
                           sizeof(fire_payload), raw);
        assert(rt_apply(&state, terrain, 10, 20, raw, len) ==
               RTS_REMOTE_PLAYERS);
        assert(state.tracers[0].active == 1);
        assert(state.tracers[0].x == 30 && state.tracers[0].y == 31);
        assert(state.tracers[0].dir == RTS_FACE_LEFT);
        assert(state.tracers[0].steps == 0);
        assert(state.tracers[1].active == 0);

        /* Re-sending the same fire bits is not a new shot. */
        len = build_rt_raw(RTS_REMOTE_PLAYERS, 2, 0x123A, fire_payload,
                           sizeof(fire_payload), raw);
        assert(rt_apply(&state, terrain, 10, 20, raw, len) ==
               RTS_REMOTE_PLAYERS);
        assert(state.tracers[1].active == 0);
    }

    {
        const unsigned char item_payload[] = {
            40, 50, RTS_ITEM_GOLD, 9,
            41, 52, RTS_ITEM_WARDEN_KEY, 1
        };
        unsigned char item_raw[RTS_MAX_RAW];
        unsigned char item_len = build_rt_raw(RTS_ITEM_DROPS, 2, 0x1238,
                                              item_payload,
                                              sizeof(item_payload), item_raw);
        assert(rt_apply(&state, terrain, 10, 20, item_raw, item_len) ==
               RTS_ITEM_DROPS);
        assert(state.item_count == 2);
        assert(state.items[0].x == 40 && state.items[0].y == 50);
        assert(state.items[0].item_id == RTS_ITEM_GOLD);
        assert(state.items[0].quantity == 9);
        assert(state.items[1].item_id == RTS_ITEM_WARDEN_KEY);
    }

    /* A corrupted CRC must be reported as invalid, not merely unhandled. */
    raw[len - 1] ^= 1;
    assert(rt_apply(&state, terrain, 10, 20, raw, len) == RTS_INVALID);
    raw[len - 1] ^= 1;
    /* A well-formed frame of an unhandled type stays 0, so a corrupted
       reception rate can be measured without counting these. */
    /* INVENTORY_UPDATE: valid on the wire, and still unhandled -- the
       inventory modal is Phase 9. QUEST_UPDATE used to stand in here, until
       the quest HUD line started decoding it. */
    raw[2] = 10;
    raw[len - 2] = (unsigned char)(rt_crc16(raw, len - 2) & 0xFF);
    raw[len - 1] = (unsigned char)(rt_crc16(raw, len - 2) >> 8);
    assert(rt_apply(&state, terrain, 10, 20, raw, len) == 0);
}

/* Byte-for-byte against server/protocol.py's encode_resync_request /
 * encode_cache_step_ack / encode_window_commit for the same field values. */
static void fill_test_terrain(struct bootstrap_state *state)
{
    unsigned char row;
    unsigned char col;

    bootstrap_init(state);
    state->origin_x = 10;
    state->origin_y = 20;
    for (row = 0; row < BOOTSTRAP_WINDOW_H; ++row) {
        for (col = 0; col < BOOTSTRAP_WINDOW_W; ++col) {
            state->terrain[(unsigned)row * BOOTSTRAP_WINDOW_W + col] =
                (unsigned char)(row * 7 + col);
        }
    }
}

static void test_bootstrap_terrain_edge_shifts(void)
{
    struct bootstrap_state state;
    unsigned char tiles[BOOTSTRAP_WINDOW_W];
    unsigned char i;
    signed char result;

    /* LEFT: edge origin_x = active - 1, active origin_y unchanged. */
    fill_test_terrain(&state);
    for (i = 0; i < BOOTSTRAP_WINDOW_H; ++i) {
        tiles[i] = (unsigned char)(200 + i);
    }
    result = bootstrap_apply_terrain_edge(&state, 9, 20, 1, BOOTSTRAP_WINDOW_H,
                                          1, tiles, BOOTSTRAP_WINDOW_H);
    assert(result == BOOTSTRAP_EDGE_APPLIED);
    assert(state.origin_x == 9 && state.origin_y == 20);
    assert(state.revision == 1);
    assert(state.terrain[0] == 200);
    assert(state.terrain[7 * BOOTSTRAP_WINDOW_W] == 207);
    /* old column 0 (value 0) is now column 1; old column 30 dropped. */
    assert(state.terrain[1] == 0);
    assert(state.terrain[BOOTSTRAP_WINDOW_W - 1] == 30);

    /* Duplicate re-delivery of the same revision must not shift again. */
    result = bootstrap_apply_terrain_edge(&state, 9, 20, 1, BOOTSTRAP_WINDOW_H,
                                          1, tiles, BOOTSTRAP_WINDOW_H);
    assert(result == BOOTSTRAP_EDGE_DUPLICATE);
    assert(state.origin_x == 9 && state.revision == 1);
    assert(state.terrain[0] == 200);

    /* A revision that isn't current or current+1 needs a resync. */
    result = bootstrap_apply_terrain_edge(&state, 8, 20, 1, BOOTSTRAP_WINDOW_H,
                                          5, tiles, BOOTSTRAP_WINDOW_H);
    assert(result == BOOTSTRAP_EDGE_RESYNC);
    assert(state.origin_x == 9 && state.revision == 1);

    /* Malformed geometry (not a full row or column strip) is rejected. */
    result = bootstrap_apply_terrain_edge(&state, 9, 20, 2, 2, 2, tiles, 4);
    assert(result == BOOTSTRAP_EDGE_RESYNC);
    assert(state.origin_x == 9 && state.revision == 1);

    /* RIGHT: edge origin_x = active + WINDOW_W. */
    fill_test_terrain(&state);
    for (i = 0; i < BOOTSTRAP_WINDOW_H; ++i) {
        tiles[i] = (unsigned char)(210 + i);
    }
    result = bootstrap_apply_terrain_edge(&state, 42, 20, 1, BOOTSTRAP_WINDOW_H,
                                          1, tiles, BOOTSTRAP_WINDOW_H);
    assert(result == BOOTSTRAP_EDGE_APPLIED);
    assert(state.origin_x == 11 && state.origin_y == 20);
    assert(state.terrain[BOOTSTRAP_WINDOW_W - 1] == 210);
    assert(state.terrain[7 * BOOTSTRAP_WINDOW_W + BOOTSTRAP_WINDOW_W - 1] == 217);
    /* old column 1 (value 1) is now column 0; old column 0 dropped. */
    assert(state.terrain[0] == 1);

    /* UP: edge origin_y = active - 1. */
    fill_test_terrain(&state);
    for (i = 0; i < BOOTSTRAP_WINDOW_W; ++i) {
        tiles[i] = (unsigned char)(220 + i);
    }
    result = bootstrap_apply_terrain_edge(&state, 10, 19, BOOTSTRAP_WINDOW_W, 1,
                                          1, tiles, BOOTSTRAP_WINDOW_W);
    assert(result == BOOTSTRAP_EDGE_APPLIED);
    assert(state.origin_x == 10 && state.origin_y == 19);
    assert(state.terrain[0] == 220 && state.terrain[5] == 225);
    /* old row 0 is now row 1. */
    assert(state.terrain[BOOTSTRAP_WINDOW_W + 3] == 3);

    /* DOWN: edge origin_y = active + WINDOW_H. */
    fill_test_terrain(&state);
    for (i = 0; i < BOOTSTRAP_WINDOW_W; ++i) {
        tiles[i] = (unsigned char)(230 + i);
    }
    result = bootstrap_apply_terrain_edge(&state, 10, 44, BOOTSTRAP_WINDOW_W, 1,
                                          1, tiles, BOOTSTRAP_WINDOW_W);
    assert(result == BOOTSTRAP_EDGE_APPLIED);
    assert(state.origin_x == 10 && state.origin_y == 21);
    assert(state.terrain[(BOOTSTRAP_WINDOW_H - 1) * BOOTSTRAP_WINDOW_W] == 230);
    /* old row 1 is now row 0. */
    assert(state.terrain[3] == (unsigned char)(1 * 7 + 3));
}

static void test_bootstrap_window_fill_and_activate(void)
{
    struct bootstrap_fill fill;
    struct bootstrap_state state;
    unsigned char tiles[BOOTSTRAP_WINDOW_W];
    unsigned char row;
    unsigned char col;
    signed char result;

    bootstrap_fill_init(&fill);
    assert(fill.active == 0);

    for (col = 0; col < BOOTSTRAP_WINDOW_W; ++col) {
        tiles[col] = 10;
    }
    result = bootstrap_fill_apply_row(&fill, 7, 5, 100, 0, tiles);
    assert(result == BOOTSTRAP_FILL_ROW_APPLIED);
    assert(fill.active == 1 && fill.fill_id == 7);
    assert(fill.origin_x == 5 && fill.origin_y == 100);

    /* A duplicate copy of an already-had row is ignored, not re-applied. */
    for (col = 0; col < BOOTSTRAP_WINDOW_W; ++col) {
        tiles[col] = 99;
    }
    result = bootstrap_fill_apply_row(&fill, 7, 5, 100, 0, tiles);
    assert(result == BOOTSTRAP_FILL_DUPLICATE);
    assert(fill.terrain[0] == 10);

    /* Every row but 5, out of order; 23 rows must never report complete. */
    for (row = 23; row > 0; --row) {
        if (row == 5) {
            continue;
        }
        for (col = 0; col < BOOTSTRAP_WINDOW_W; ++col) {
            tiles[col] = (unsigned char)(row + col);
        }
        result = bootstrap_fill_apply_row(&fill, 7, 5, (unsigned char)(100 + row),
                                          row, tiles);
        assert(result == BOOTSTRAP_FILL_ROW_APPLIED);
    }
    assert(fill.rows_have != BOOTSTRAP_ALL_ROWS);

    for (col = 0; col < BOOTSTRAP_WINDOW_W; ++col) {
        tiles[col] = (unsigned char)(5 + col);
    }
    result = bootstrap_fill_apply_row(&fill, 7, 5, 105, 5, tiles);
    assert(result == BOOTSTRAP_FILL_COMPLETE);
    assert(fill.rows_have == BOOTSTRAP_ALL_ROWS);
    assert(fill.terrain[10 * BOOTSTRAP_WINDOW_W + 7] == 17);

    bootstrap_init(&state);
    bootstrap_fill_activate(&fill, &state);
    assert(fill.active == 0);
    assert(state.origin_x == 5 && state.origin_y == 100);
    assert(state.terrain[10 * BOOTSTRAP_WINDOW_W + 7] == 17);
    assert(state.revision_trust_next == 1);
    assert(state.commit_pending == 1 && state.commit_fill_id == 7);

    assert(bootstrap_commit_ack_matches(&state, 7, 5, 100) == 1);
    assert(bootstrap_commit_ack_matches(&state, 8, 5, 100) == 0);
    assert(bootstrap_commit_ack_matches(&state, 7, 6, 100) == 0);
    state.commit_pending = 0;
    assert(bootstrap_commit_ack_matches(&state, 7, 5, 100) == 0);

    /* A mismatched fill_id/origin supersedes whatever was in progress. */
    bootstrap_fill_init(&fill);
    bootstrap_fill_apply_row(&fill, 7, 5, 100, 0, tiles);
    result = bootstrap_fill_apply_row(&fill, 8, 9, 200, 0, tiles);
    assert(result == BOOTSTRAP_FILL_ROW_APPLIED);
    assert(fill.fill_id == 8 && fill.origin_x == 9 && fill.origin_y == 200);
    assert(fill.rows_have == 1UL);
}

static void test_bootstrap_revision_trust_next(void)
{
    struct bootstrap_state state;
    unsigned char tiles[BOOTSTRAP_WINDOW_H];
    unsigned char i;
    signed char result;

    /* Simulate the state right after a full-window activation: revision 0,
     * origin (5,100), trust_next set. */
    bootstrap_init(&state);
    state.origin_x = 5;
    state.origin_y = 100;
    state.revision_trust_next = 1;

    /* Malformed geometry is still rejected and does not consume the
     * one-shot trust token. */
    result = bootstrap_apply_terrain_edge(&state, 5, 100, 2, 2, 4321, tiles, 4);
    assert(result == BOOTSTRAP_EDGE_RESYNC);
    assert(state.revision_trust_next == 1);

    /* A geometrically-adjacent RIGHT edge with an arbitrary (non-next)
     * revision is trusted as the new baseline once. */
    for (i = 0; i < BOOTSTRAP_WINDOW_H; ++i) {
        tiles[i] = (unsigned char)(50 + i);
    }
    result = bootstrap_apply_terrain_edge(&state, 37, 100, 1, BOOTSTRAP_WINDOW_H,
                                          9999, tiles, BOOTSTRAP_WINDOW_H);
    assert(result == BOOTSTRAP_EDGE_APPLIED);
    assert(state.origin_x == 6 && state.revision == 9999);
    assert(state.revision_trust_next == 0);

    /* Strict adjacency resumes: a non-adjacent revision now needs resync. */
    result = bootstrap_apply_terrain_edge(&state, 38, 100, 1, BOOTSTRAP_WINDOW_H,
                                          123, tiles, BOOTSTRAP_WINDOW_H);
    assert(result == BOOTSTRAP_EDGE_RESYNC);
    assert(state.revision == 9999);
}

static void test_predict_blocking_matches_server(void)
{
    /* Server world.py tile ids: the cave ENTRANCE (13) is walkable -- it is
       the door that triggers the map change -- and must not block, or the
       dungeon is unreachable. The solid wall is 16, and the exit (17) is
       walkable too so the player can leave. */
    assert(predict_tile_blocks(13) == 0);   /* CAVE_ENTRANCE */
    assert(predict_tile_blocks(17) == 0);   /* CAVE_EXIT */
    assert(predict_tile_blocks(15) == 0);   /* CAVE_FLOOR */
    assert(predict_tile_blocks(16) != 0);   /* CAVE_WALL */
    assert(predict_tile_blocks(0) == 0);    /* GRASS */
    assert(predict_tile_blocks(2) != 0);    /* TREE_FULL */
    assert(predict_tile_blocks(11) != 0);   /* WATER */
    assert(predict_tile_blocks(12) != 0);   /* BUILDING */
}

static void test_predict_basic_and_replay(void)
{
    unsigned char terrain[RTS_WINDOW_W * RTS_WINDOW_H];
    struct rt_state world;
    struct predict_state ps;
    unsigned char result;

    memset(terrain, 0, sizeof(terrain));
    rt_state_init(&world);

    /* Fully acknowledged moves drain to the server position without a
     * visible rollback (the server position matches what was displayed). */
    predict_init(&ps, 15, 25);
    assert(predict_move(&ps, 1, 16, 25, terrain, 10, 20, &world) == 1);
    assert(predict_move(&ps, 2, 17, 25, terrain, 10, 20, &world) == 1);
    result = predict_reconcile(&ps, 17, 25, 0, 2, terrain, 10, 20, &world);
    assert(result == 0);
    assert(ps.count == 0 && ps.x == 17 && ps.y == 25);

    /* Unacknowledged moves replay over the newer authoritative position. */
    predict_init(&ps, 15, 25);
    assert(predict_move(&ps, 1, 16, 25, terrain, 10, 20, &world) == 1);
    assert(predict_move(&ps, 2, 17, 25, terrain, 10, 20, &world) == 1);
    assert(predict_move(&ps, 3, 18, 25, terrain, 10, 20, &world) == 1);
    result = predict_reconcile(&ps, 16, 25, 0, 1, terrain, 10, 20, &world);
    assert(result == 0);
    assert(ps.count == 2 && ps.x == 18 && ps.y == 25);

    /* An impossible replay (the target tile is no longer walkable) forces
     * a hard snap to the server position. */
    predict_init(&ps, 15, 25);
    assert(predict_move(&ps, 1, 16, 25, terrain, 10, 20, &world) == 1);
    assert(predict_move(&ps, 2, 17, 25, terrain, 10, 20, &world) == 1);
    terrain[5 * RTS_WINDOW_W + 7] = PREDICT_TILE_WATER; /* (17,25) blocked */
    result = predict_reconcile(&ps, 16, 25, 0, 1, terrain, 10, 20, &world);
    assert(result == 1);
    assert(ps.count == 0 && ps.x == 16 && ps.y == 25);
    terrain[5 * RTS_WINDOW_W + 7] = 0;
}

static void test_predict_correction_overflow_and_wrap(void)
{
    unsigned char terrain[RTS_WINDOW_W * RTS_WINDOW_H];
    struct rt_state world;
    struct predict_state ps;
    unsigned char i;
    unsigned char result;

    memset(terrain, 0, sizeof(terrain));
    rt_state_init(&world);

    /* correction_flags forces a hard snap regardless of pending moves. */
    predict_init(&ps, 15, 25);
    assert(predict_move(&ps, 1, 16, 25, terrain, 10, 20, &world) == 1);
    result = predict_reconcile(&ps, 5, 5, 1, 1, terrain, 10, 20, &world);
    assert(result == 1);
    assert(ps.count == 0 && ps.x == 5 && ps.y == 5);

    /* A queue at capacity refuses the next move as backpressure: the queue
     * and displayed position are left intact (no backward snap), and an
     * acknowledging WORLD_STATE frees room again. */
    predict_init(&ps, 15, 25);
    for (i = 0; i < PREDICT_MAX_PENDING; ++i) {
        result = predict_move(&ps, i + 1, (unsigned char)(16 + i), 25,
                              terrain, 10, 20, &world);
        assert(result == 1);
    }
    assert(ps.count == PREDICT_MAX_PENDING && ps.x == 23);
    result = predict_move(&ps, PREDICT_MAX_PENDING + 1, 24, 25, terrain, 10,
                          20, &world);
    assert(result == 0);
    assert(ps.count == PREDICT_MAX_PENDING && ps.x == 23 && ps.y == 25);

    /* Draining one entry re-opens exactly one slot, and the replay of the
     * still-pending moves keeps the displayed position where it was. */
    result = predict_reconcile(&ps, 16, 25, 0, 1, terrain, 10, 20, &world);
    assert(result == 0);
    assert(ps.count == PREDICT_MAX_PENDING - 1 && ps.x == 23 && ps.y == 25);
    result = predict_move(&ps, PREDICT_MAX_PENDING + 2, 24, 25, terrain, 10,
                          20, &world);
    assert(result == 1);
    assert(ps.x == 24 && ps.y == 25);

    /* 16-bit sequence wrap: entries at/before the echoed seq drop even when
     * their raw numeric value is smaller due to wraparound. */
    predict_init(&ps, 15, 25);
    assert(predict_move(&ps, 0xFFFE, 16, 25, terrain, 10, 20, &world) == 1);
    assert(predict_move(&ps, 0xFFFF, 17, 25, terrain, 10, 20, &world) == 1);
    assert(predict_move(&ps, 0x0000, 18, 25, terrain, 10, 20, &world) == 1);
    assert(predict_move(&ps, 0x0001, 19, 25, terrain, 10, 20, &world) == 1);
    result = predict_reconcile(&ps, 17, 25, 0, 0xFFFF, terrain, 10, 20,
                               &world);
    assert(result == 0);
    assert(ps.count == 2 && ps.x == 19 && ps.y == 25);
}

static void test_rt_phase7_outgoing_vectors(void)
{
    const unsigned char expected_resync[] = {
        0x04, 0x09, 0x03, 0x0F, 0x02, 0x03, 0x07, 0x0A, 0x14, 0x0A,
        0x14, 0xCD, 0xAB, 0x05, 0x07, 0x01, 0x46, 0xAE, 0x00
    };
    const unsigned char expected_step_ack[] = {
        0x04, 0x04, 0x03, 0x15, 0x02, 0x04, 0x07, 0x02, 0x01, 0x0B,
        0x14, 0xF4, 0x46, 0x00
    };
    const unsigned char expected_commit[] = {
        0x04, 0x05, 0x03, 0x14, 0x02, 0x05, 0x04, 0x07, 0x09, 0x13,
        0x04, 0x01, 0xC9, 0xC4, 0x00
    };
    unsigned char out[RTS_MAX_RAW + 2];
    unsigned char len;

    len = rt_build_resync_request(out, 3, 10, 20, 10, 20, 0xABCDUL, 7, 1);
    assert(len == sizeof(expected_resync));
    assert(memcmp(out, expected_resync, sizeof(expected_resync)) == 0);

    len = rt_build_cache_step_ack(out, 4, 0x0102, 11, 20);
    assert(len == sizeof(expected_step_ack));
    assert(memcmp(out, expected_step_ack, sizeof(expected_step_ack)) == 0);

    len = rt_build_window_commit(out, 5, 7, 9, 19, 0, 1);
    assert(len == sizeof(expected_commit));
    assert(memcmp(out, expected_commit, sizeof(expected_commit)) == 0);
}

static void test_rt_map_transition(void)
{
    /* Byte-for-byte against protocol.py encode_map_ready for the same
       fields (seq 9, map 1, origin 10,20). */
    const unsigned char expected_ready[] = {
        0x04, 0x03, 0x03, 0x13, 0x02, 0x09, 0x06, 0x01, 0x0A, 0x14,
        0x88, 0x30, 0x00
    };
    const unsigned char change_payload[] = { 1, 40, 50, 1, 1, 1 };
    unsigned char out[RTS_MAX_RAW + 2];
    unsigned char raw[RTS_MAX_RAW];
    unsigned char len;
    struct rt_state state;

    len = rt_build_map_ready(out, 9, 1, 10, 20);
    assert(len == sizeof(expected_ready));
    assert(memcmp(out, expected_ready, sizeof(expected_ready)) == 0);

    rt_state_init(&state);
    len = build_rt_raw(RTS_MAP_CHANGE, 0, 0x0007, change_payload,
                       sizeof(change_payload), raw);
    assert(rt_apply(&state, 0, 0, 0, raw, len) == RTS_MAP_CHANGE);
    assert(state.map_change.map_id == 1);
    assert(state.map_change.spawn_x == 40 && state.map_change.spawn_y == 50);
    assert(state.map_change.tileset_id == 1);
    assert(state.map_change.palette_id == 1);
    assert(state.map_change.flags == 1);
}

static void test_rt_phase7_incoming_packets(void)
{
    const unsigned char edge_payload[] = {
        41, 5, 2, 2, 0x03, 0x02, 10, 11, 12, 13
    };
    unsigned char row_payload[36];
    const unsigned char commit_ack_payload[] = { 7, 9, 19 };
    unsigned char raw[RTS_MAX_RAW];
    unsigned char len;
    unsigned char i;
    struct rt_state state;

    rt_state_init(&state);

    len = build_rt_raw(RTS_TERRAIN_EDGE, sizeof(edge_payload) - 6, 0x2000,
                       edge_payload, sizeof(edge_payload), raw);
    assert(rt_apply(&state, 0, 0, 0, raw, len) == RTS_TERRAIN_EDGE);
    assert(state.edge.origin_x == 41 && state.edge.origin_y == 5);
    assert(state.edge.width == 2 && state.edge.height == 2);
    assert(state.edge.revision == 0x0203);
    assert(state.edge.tile_count == 4);
    assert(state.edge.tiles[0] == 10 && state.edge.tiles[3] == 13);

    row_payload[0] = 10;
    row_payload[1] = 44;
    row_payload[2] = 5;
    row_payload[3] = 7;
    for (i = 0; i < RTS_WINDOW_W; ++i) {
        row_payload[4 + i] = (unsigned char)(100 + i);
    }
    len = build_rt_raw(RTS_WINDOW_ROW, RTS_WINDOW_W, 0x3000, row_payload,
                       sizeof(row_payload), raw);
    assert(rt_apply(&state, 0, 0, 0, raw, len) == RTS_WINDOW_ROW);
    assert(state.window_row.origin_x == 10 && state.window_row.origin_y == 44);
    assert(state.window_row.row_index == 5 && state.window_row.fill_id == 7);
    assert(state.window_row.tiles[0] == 100 &&
           state.window_row.tiles[RTS_WINDOW_W - 1] == 131);

    len = build_rt_raw(RTS_WINDOW_COMMIT_ACK, 0, 0x4000, commit_ack_payload,
                       sizeof(commit_ack_payload), raw);
    assert(rt_apply(&state, 0, 0, 0, raw, len) == RTS_WINDOW_COMMIT_ACK);
    assert(state.window_commit_ack.fill_id == 7);
    assert(state.window_commit_ack.origin_x == 9);
    assert(state.window_commit_ack.origin_y == 19);
}

static void test_camera_and_hud_text(void)
{
    unsigned char sprite[HUD_TEXT_SPRITE_BYTES];
    char text[8];
    unsigned char len = 0;

    /* Derived from VIEW_COLS rather than hardcoded, so changing the
       viewport does not require editing the expectations. */
    {
        unsigned char half = VIEW_COLS / 2;
        unsigned char max_cam = RTS_WINDOW_W - VIEW_COLS;
        unsigned char mid = RTS_WINDOW_W / 2;
        unsigned char expect = mid - half;

        assert(rt_camera(0, RTS_WINDOW_W, VIEW_COLS) == 0);
        assert(rt_camera(half, RTS_WINDOW_W, VIEW_COLS) == 0);
        assert(rt_camera(RTS_WINDOW_W - 1, RTS_WINDOW_W, VIEW_COLS) ==
               max_cam);
        if (expect > max_cam) {
            expect = max_cam;
        }
        assert(rt_camera(mid, RTS_WINDOW_W, VIEW_COLS) == expect);
    }

    /* Hysteretic camera: holds inside the band, follows the least amount at
       the edges, clamps to the window, and never moves for a step that keeps
       the player inside the band. */
    {
        unsigned char margin = 3;
        unsigned char view = VIEW_COLS;         /* 20 */
        unsigned char span = RTS_WINDOW_W;      /* 32 */
        unsigned char max_cam = span - view;    /* 12 */
        unsigned char cam = 5;

        /* Player well inside [cam+margin, cam+view-1-margin] -> no move. */
        assert(rt_camera_track(cam, cam + margin, span, view, margin) == cam);
        assert(rt_camera_track(cam, cam + view - 1 - margin, span, view,
                               margin) == cam);
        /* Two steps that stay in the band do not scroll. */
        assert(rt_camera_track(cam, cam + margin + 1, span, view, margin)
               == cam);
        /* Pushing past the near edge pulls the camera left by exactly one. */
        assert(rt_camera_track(cam, cam + margin - 1, span, view, margin)
               == cam - 1);
        /* Pushing past the far edge pushes it right by exactly one. */
        assert(rt_camera_track(cam, cam + view - margin, span, view, margin)
               == cam + 1);
        /* Against the cache edge the camera clamps and the player leaves the
           band toward the screen edge. */
        assert(rt_camera_track(max_cam, span - 1, span, view, margin)
               == max_cam);
        assert(rt_camera_track(0, 0, span, view, margin) == 0);
    }

    hud_text_init(sprite);
    hud_text_render(sprite, "A", 1, 15);
    assert(sprite[0] == HUD_TEXT_ROW_BYTES + 1);
    assert(sprite[1] == 0x0F && sprite[2] == 0xF0);
    assert(sprite[HUD_TEXT_SPRITE_BYTES - 1] == 0);
    len = fmt_u16(text, len, 65535);
    text[len] = 0;
    assert(strcmp(text, "65535") == 0);

    /* Phase 61 grew the logical tile allocation to 52 (atari8-client/art/
       PHASE_61_TILE_ALLOCATION.md). Anything short of that clamps the new
       NPC and Floodworks ids to TILE_BORDER in the terrain blitter. */
    assert(ART_TILE_COUNT == 52 && ART_PLAYER_FRAMES == 12);
    /* 8x8 sprite: 8 scanlines of (count + 4 pixel bytes + the pad byte Suzy
       requires after byte-aligned literal data), then a sprite terminator.
       Entities, players and the bullet still go through Suzy. */
    assert(ART_SPRITE_BYTES == 6 * 8 + 1);
    assert(art_player[0][0] == 6);
    assert(art_player[0][5] == 0);
    assert(art_player[0][ART_SPRITE_BYTES - 1] == 0);
    /* Terrain is a flat framebuffer copy: 8 rows x 4 bytes, no framing. */
    assert(ART_TILE_RAW_BYTES == 8 * 4);
}

/* Build one DIALOGUE_PAGE chunk. Field order is byte-for-byte
 * REALTIME_DIALOGUE_HEAD_STRUCT from server/protocol.py:530; the canonical
 * frame for (dlg 3, speaker 5, page 1/4, flags LAST|END, chunk 2, "HELLO
 * WORLD") COBS-encodes to 04120318174012030501040c020b48454c4c4f20574f524c44f0cf00. */
static unsigned char build_dialogue_chunk(unsigned char *raw,
                                          unsigned char dialogue_id,
                                          unsigned char speaker,
                                          unsigned char page_index,
                                          unsigned char page_count,
                                          unsigned char flags,
                                          unsigned char chunk_index,
                                          const char *text)
{
    unsigned char payload[RTS_MAX_RAW];
    unsigned char len = (unsigned char)strlen(text);
    unsigned char i;

    payload[0] = dialogue_id;
    payload[1] = speaker;
    payload[2] = page_index;
    payload[3] = page_count;
    payload[4] = flags;
    payload[5] = chunk_index;
    payload[6] = len;
    for (i = 0; i < len; ++i) {
        payload[7 + i] = (unsigned char)text[i];
    }
    return build_rt_raw(RTS_DIALOGUE_PAGE, 0, 0x1240, payload,
                        (unsigned char)(7 + len), raw);
}

/* The reassembly contract from fujirealm.asm:9781. Each block here maps to
 * one of the four ordered rules in apply_dialogue_page. */
static void test_rt_dialogue_page(void)
{
    /* A canary immediately after the state catches a page overrun writing
       past text[]; struct order makes dlg the last member. */
    struct {
        struct rt_state state;
        unsigned char canary;
    } guard;
    struct rt_state *state = &guard.state;
    unsigned char raw[RTS_MAX_RAW];
    unsigned char len;
    char long_chunk[RTS_DLG_CHUNK_MAX + 1];
    unsigned char i;

    rt_state_init(state);
    guard.canary = 0xA5;

    /* Two chunks; only the second carries CHUNK_END. */
    len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_WILHELM, 0, 2, 0, 0,
                               "THE BRIDGE IS OUT ");
    assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    /* Nothing renders yet: the page is incomplete. */
    assert(state->dlg.dirty == 0 && state->dlg.request == 0);
    assert(state->dlg.next_chunk == 1);

    len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_WILHELM, 0, 2,
                               RTS_DLG_FLAG_CHUNK_END, 1,
                               "AND THE WATER IS RISING.");
    assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    assert(strcmp(state->dlg.text,
                  "THE BRIDGE IS OUT AND THE WATER IS RISING.") == 0);
    assert(state->dlg.len == 42);
    assert(state->dlg.speaker == RTS_SPEAKER_WILHELM);
    assert(state->dlg.page_count == 2);
    assert(state->dlg.flags == RTS_DLG_FLAG_CHUNK_END);
    assert(state->dlg.dirty == 1 && state->dlg.request == 1);

    /* Rule 2: a gap drops the chunk and leaves the assembled page alone, so
       the modal keeps showing the current page until the resend arrives. */
    state->dlg.dirty = 0;
    len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_WILHELM, 1, 2, 0, 0, "AAA");
    assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_WILHELM, 1, 2,
                               RTS_DLG_FLAG_CHUNK_END, 2, "CCC");
    assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    assert(strcmp(state->dlg.text, "AAA") == 0);
    assert(state->dlg.len == 3);
    assert(state->dlg.next_chunk == 1);
    assert(state->dlg.dirty == 0);

    /* Rule 1: chunk 0 restarts the page even mid-assembly. */
    len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_WILHELM, 1, 2,
                               RTS_DLG_FLAG_CHUNK_END | RTS_DLG_FLAG_LAST_PAGE |
                               RTS_DLG_FLAG_QUEST_OFFER, 0, "WILL YOU HELP");
    assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    assert(strcmp(state->dlg.text, "WILL YOU HELP") == 0);
    assert(state->dlg.flags == (RTS_DLG_FLAG_CHUNK_END | RTS_DLG_FLAG_LAST_PAGE |
                                RTS_DLG_FLAG_QUEST_OFFER));

    /* Rule 4, the quest-freeze guard: a retransmit's chunk 0 carries no
       LAST_PAGE and no CHUNK_END, and must not clear the committed flags --
       otherwise the accept/decline prompt vanishes mid-offer. */
    len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_WILHELM, 1, 2, 0, 0,
                               "WILL YOU HELP");
    assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    assert(state->dlg.flags == (RTS_DLG_FLAG_CHUNK_END | RTS_DLG_FLAG_LAST_PAGE |
                                RTS_DLG_FLAG_QUEST_OFFER));

    /* Replaying a whole page is byte-identical: the server retransmits up to
       six times while waiting for an ack. */
    len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_WILHELM, 1, 2,
                               RTS_DLG_FLAG_CHUNK_END, 0, "WILL YOU HELP");
    assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    assert(strcmp(state->dlg.text, "WILL YOU HELP") == 0);
    assert(state->dlg.len == 13);
    assert(state->dlg.page_index == 1);

    /* text_len over the per-chunk cap clamps rather than reading past the
       frame; 4 full chunks then cap the page at RTS_DLG_PAGE_MAX. */
    for (i = 0; i < RTS_DLG_CHUNK_MAX; ++i) {
        long_chunk[i] = 'X';
    }
    long_chunk[RTS_DLG_CHUNK_MAX] = 0;
    for (i = 0; i < 4; ++i) {
        len = build_dialogue_chunk(raw, 3, RTS_SPEAKER_NONE, 2, 3,
                                   i == 3 ? RTS_DLG_FLAG_CHUNK_END : 0, i,
                                   long_chunk);
        /* 7 header + 47 text = 54 payload = the v3 maximum, so this frame is
           exactly RTS_MAX_RAW bytes and must not be rejected as oversize. */
        assert(len == RTS_MAX_RAW);
        assert(rt_apply(state, 0, 0, 0, raw, len) == RTS_DIALOGUE_PAGE);
    }
    assert(state->dlg.len == RTS_DLG_PAGE_MAX);
    assert(state->dlg.text[RTS_DLG_PAGE_MAX] == 0);
    assert(guard.canary == 0xA5);
}

static void test_rt_dialogue_ack_vector(void)
{
    unsigned char out[RTS_MAX_RAW + 2];
    unsigned char plain[RTS_MAX_RAW + 2];
    unsigned char len;
    unsigned char plain_len;

    /* The decline answer rides the buttons byte of the same PLAYER_STATE that
       bumps the pickup counter -- payload byte +3, alongside the fire bit. */
    len = rt_build_player_state(out, 7, 40, 50, RTS_FACE_UP,
                                RTS_BUTTON_DIALOGUE_DECLINE, 2, 5, 0x1234, 0);
    plain_len = rt_build_player_state(plain, 7, 40, 50, RTS_FACE_UP, 0, 2, 5,
                                      0x1234, 0);
    /* Same length, and the only difference is the buttons byte: nothing else
       in the frame shifts when the bit is set. */
    assert(len == plain_len);
    assert(memcmp(out, plain, len) != 0);
    assert(RTS_BUTTON_DIALOGUE_DECLINE == 0x02);
    /* Fire and decline are independent bits and must not alias. */
    assert((RTS_BUTTON_FIRE & RTS_BUTTON_DIALOGUE_DECLINE) == 0);
}

static void test_rt_quest_and_message(void)
{
    struct rt_state state;
    unsigned char raw[RTS_MAX_RAW];
    unsigned char len;
    const unsigned char quest_payload[] = {
        4, 1, 11, 'B', 'L', 'A', 'C', 'K', 'W', 'A', 'T', 'E', 'R', '!'
    };
    /* message_id 0 (server MSG_NONE) with real text: the exact shape that made
       the Atari client drop bat-attack and kill lines. */
    const unsigned char message_payload[] = {
        0, 12, 'A', ' ', 'B', 'A', 'T', ' ', 'B', 'I', 'T', 'E', 'S', '!'
    };

    rt_state_init(&state);
    len = build_rt_raw(RTS_QUEST_UPDATE, 0, 0x1300, quest_payload,
                       sizeof(quest_payload), raw);
    assert(rt_apply(&state, 0, 0, 0, raw, len) == RTS_QUEST_UPDATE);
    assert(state.quest_id == 4 && state.quest_state == 1);
    assert(state.quest_seen == 1 && state.quest_dirty == 1);
    assert(strcmp(state.quest_text, "BLACKWATER!") == 0);

    /* quest_id 0 arrives mid-campaign once a chain completes; the line must
       clear rather than keep the last quest's text forever. */
    {
        const unsigned char cleared[] = { 0, 0, 0 };

        len = build_rt_raw(RTS_QUEST_UPDATE, 0, 0x1301, cleared,
                           sizeof(cleared), raw);
        assert(rt_apply(&state, 0, 0, 0, raw, len) == RTS_QUEST_UPDATE);
        assert(state.quest_id == 0 && state.quest_len == 0);
        assert(state.quest_text[0] == 0);
        assert(state.quest_seen == 1);
    }

    assert(state.message_seen == 0);
    len = build_rt_raw(RTS_MESSAGE, 0, 0x1302, message_payload,
                       sizeof(message_payload), raw);
    assert(rt_apply(&state, 0, 0, 0, raw, len) == RTS_MESSAGE);
    assert(state.message_seen == 1 && state.message_dirty == 1);
    assert(strcmp(state.message, "A BAT BITES!") == 0);
}

static void test_rt_enemy_kind_and_items(void)
{
    struct rt_state state;
    unsigned char terrain[RTS_WINDOW_W * RTS_WINDOW_H];
    unsigned char raw[RTS_MAX_RAW];
    unsigned char len;
    /* WORLD_STATE payload: px, py, hp, corr, echo(2), tile, tx, ty, then the
       4-byte entity records. The entity count rides the frame's status byte,
       not the payload. A slime with the hit pulse set, then the two Wilhelm
       NPC kinds that now share the entity slots. */
    const unsigned char world_payload[] = {
        44, 60, 100, 0, 0x39, 0x00,
        0, 42, 55,
        45, 56, 12, RTS_KIND_HIT_PULSE | RTS_KIND_SLIME,
        46, 57, 30, RTS_KIND_WILHELM,
        47, 58, 30, RTS_KIND_WILHELM_WORKING
    };

    memset(terrain, 0, sizeof(terrain));
    rt_state_init(&state);
    len = build_rt_raw(RTS_WORLD_STATE, 3, 0x1400, world_payload,
                       sizeof(world_payload), raw);
    assert(rt_apply(&state, terrain, 40, 50, raw, len) == RTS_WORLD_STATE);
    assert(state.beaver_count == 3);
    /* The pulse bit is stripped from the species and turned into a local
       blink; a switch on the raw byte would draw nothing here. */
    assert(state.beavers[0].kind == RTS_KIND_SLIME);
    assert(state.beavers[0].hit_timer == RTS_HIT_FLASH_FRAMES);
    assert(state.beavers[1].kind == RTS_KIND_WILHELM);
    assert(state.beavers[1].hit_timer == 0);
    assert(state.beavers[2].kind == RTS_KIND_WILHELM_WORKING);
    assert(RTS_KIND_WILHELM_WORKING == RTS_KIND_MAX);

    assert(rt_item_art_index(0) == RTS_ART_ITEM_NONE);
    assert(rt_item_art_index(RTS_ITEM_GOLD) == RTS_ART_ITEM_GOLD);
    assert(rt_item_art_index(RTS_ITEM_STICKS) == RTS_ART_ITEM_STICKS);
    assert(rt_item_art_index(RTS_ITEM_HERB) == RTS_ART_ITEM_HERB);
    assert(rt_item_art_index(RTS_ITEM_POTION) == RTS_ART_ITEM_POTION);
    assert(rt_item_art_index(RTS_ITEM_WARDEN_KEY) == RTS_ART_ITEM_KEY);
    /* The two sample items have no art yet, so they show as sticks rather
       than vanishing -- same fallback the Atari client uses. */
    assert(rt_item_art_index(RTS_ITEM_OIL_SAMPLE) == RTS_ART_ITEM_STICKS);
    assert(rt_item_art_index(RTS_ITEM_RUST_SAMPLE) == RTS_ART_ITEM_STICKS);
    assert(rt_item_art_index(200) == RTS_ART_ITEM_STICKS);
}

/* The 8-way shot stepper and its closed-corner rule
 * (fujirealm.asm:10932, server game.py:1504). */
static void test_shot_step_eight_way(void)
{
    unsigned char terrain[RTS_WINDOW_W * RTS_WINDOW_H];
    unsigned char x;
    unsigned char y;
    unsigned char steps;
    /* Window origin chosen so the tested cells sit well inside the cache. */
    const unsigned origin_x = 40;
    const unsigned origin_y = 50;

    memset(terrain, 0, sizeof(terrain));

    assert(predict_shot_dx[RTS_FACE_UP] == 0 && predict_shot_dy[RTS_FACE_UP] == -1);
    assert(predict_shot_dx[RTS_FACE_DOWN] == 0 && predict_shot_dy[RTS_FACE_DOWN] == 1);
    assert(predict_shot_dx[RTS_FACE_LEFT] == -1 && predict_shot_dy[RTS_FACE_LEFT] == 0);
    assert(predict_shot_dx[RTS_FACE_RIGHT] == 1 && predict_shot_dy[RTS_FACE_RIGHT] == 0);
    assert(predict_shot_dx[RTS_FACE_UP_LEFT] == -1 &&
           predict_shot_dy[RTS_FACE_UP_LEFT] == -1);
    assert(predict_shot_dx[RTS_FACE_UP_RIGHT] == 1 &&
           predict_shot_dy[RTS_FACE_UP_RIGHT] == -1);
    assert(predict_shot_dx[RTS_FACE_DOWN_LEFT] == -1 &&
           predict_shot_dy[RTS_FACE_DOWN_LEFT] == 1);
    assert(predict_shot_dx[RTS_FACE_DOWN_RIGHT] == 1 &&
           predict_shot_dy[RTS_FACE_DOWN_RIGHT] == 1);

    /* A facing the server would refuse produces no movement at all. */
    x = 50;
    y = 60;
    assert(predict_shot_step(&x, &y, RTS_FACE_COUNT, terrain, origin_x,
                             origin_y) == 0);
    assert(x == 50 && y == 60);

    /* Clear diagonal: advances one tile on both axes. */
    assert(predict_shot_step(&x, &y, RTS_FACE_DOWN_RIGHT, terrain, origin_x,
                             origin_y) == 1);
    assert(x == 51 && y == 61);

    /* Range: a diagonal reaches PREDICT_SHOT_RANGE columns *and* rows. The
       server does not Euclidean-correct diagonals, so neither do we. */
    x = 50;
    y = 60;
    for (steps = 0; steps < PREDICT_SHOT_RANGE; ++steps) {
        assert(predict_shot_step(&x, &y, RTS_FACE_DOWN_RIGHT, terrain,
                                 origin_x, origin_y) == 1);
    }
    assert(x == 56 && y == 66);

    /* Closed corner: a diagonal is refused when either orthogonal side cell
       blocks, and allowed once both are clear. */
    terrain[(61 - origin_y) * RTS_WINDOW_W + (50 - origin_x)] =
        PREDICT_TILE_TREE_FULL;
    x = 50;
    y = 60;
    assert(predict_shot_step(&x, &y, RTS_FACE_DOWN_RIGHT, terrain, origin_x,
                             origin_y) == 0);
    assert(x == 50 && y == 60);
    /* The same blocker does not affect a cardinal shot across it. */
    assert(predict_shot_step(&x, &y, RTS_FACE_RIGHT, terrain, origin_x,
                             origin_y) == 1);
    assert(x == 51 && y == 60);

    terrain[(61 - origin_y) * RTS_WINDOW_W + (50 - origin_x)] = 0;
    terrain[(60 - origin_y) * RTS_WINDOW_W + (51 - origin_x)] =
        PREDICT_TILE_WATER;
    x = 50;
    y = 60;
    assert(predict_shot_step(&x, &y, RTS_FACE_DOWN_RIGHT, terrain, origin_x,
                             origin_y) == 0);
    terrain[(60 - origin_y) * RTS_WINDOW_W + (51 - origin_x)] = 0;
    assert(predict_shot_step(&x, &y, RTS_FACE_DOWN_RIGHT, terrain, origin_x,
                             origin_y) == 1);

    /* A shot blocker set that is deliberately not the movement set: a shot
       flies over the bullet tile and the static NPCs. */
    assert(predict_shot_blocks(PREDICT_TILE_TREE_FULL));
    assert(predict_shot_blocks(PREDICT_TILE_TREE_DAMAGED));
    assert(predict_shot_blocks(PREDICT_TILE_BORDER));
    assert(predict_shot_blocks(PREDICT_TILE_BEAVER));
    assert(predict_shot_blocks(PREDICT_TILE_WATER));
    assert(predict_shot_blocks(PREDICT_TILE_BUILDING));
    assert(predict_shot_blocks(PREDICT_TILE_CAVE_WALL));
    assert(!predict_shot_blocks(PREDICT_TILE_BULLET));
    assert(!predict_shot_blocks(PREDICT_TILE_SNAKE));
    assert(!predict_shot_blocks(PREDICT_TILE_WILHELM));
    assert(!predict_shot_blocks(0));

    /* World edge: the server clamps a shot to 1 <= x < 127, 1 <= y < 95. Test
       the low edge, which the 32x24 window can actually cover. */
    {
        unsigned char edge[RTS_WINDOW_W * RTS_WINDOW_H];

        memset(edge, 0, sizeof(edge));
        x = PREDICT_SHOT_MIN;
        y = 10;
        assert(predict_shot_step(&x, &y, RTS_FACE_LEFT, edge, 0, 0) == 0);
        assert(x == PREDICT_SHOT_MIN);
        x = 10;
        y = PREDICT_SHOT_MIN;
        assert(predict_shot_step(&x, &y, RTS_FACE_UP, edge, 0, 0) == 0);
        assert(y == PREDICT_SHOT_MIN);
        /* Away from the edge it still moves. */
        assert(predict_shot_step(&x, &y, RTS_FACE_DOWN, edge, 0, 0) == 1);
        assert(y == PREDICT_SHOT_MIN + 1);
    }
}

/* Diagonal movement must obey the same corner rule the server applies in
 * _player_destination_allowed, or every corner cut snaps back. */
static void test_predict_diagonal_corner(void)
{
    unsigned char terrain[RTS_WINDOW_W * RTS_WINDOW_H];
    struct rt_state world;
    struct predict_state ps;
    const unsigned origin_x = 40;
    const unsigned origin_y = 50;

    memset(terrain, 0, sizeof(terrain));
    rt_state_init(&world);

    /* Open ground: the diagonal is legal. */
    assert(predict_can_step(50, 60, 51, 61, terrain, origin_x, origin_y,
                            &world) == 1);

    /* Block one side cell: destination is still clear, but the corner is not. */
    terrain[(61 - origin_y) * RTS_WINDOW_W + (50 - origin_x)] =
        PREDICT_TILE_BUILDING;
    assert(predict_can_move(51, 61, terrain, origin_x, origin_y, &world) == 1);
    assert(predict_can_step(50, 60, 51, 61, terrain, origin_x, origin_y,
                            &world) == 0);
    /* Cardinal steps are untouched by the corner rule. */
    assert(predict_can_step(50, 60, 51, 60, terrain, origin_x, origin_y,
                            &world) == 1);
    assert(predict_can_step(50, 60, 50, 61, terrain, origin_x, origin_y,
                            &world) == 0);

    /* Other side cell, same refusal. */
    terrain[(61 - origin_y) * RTS_WINDOW_W + (50 - origin_x)] = 0;
    terrain[(60 - origin_y) * RTS_WINDOW_W + (51 - origin_x)] =
        PREDICT_TILE_BUILDING;
    assert(predict_can_step(50, 60, 51, 61, terrain, origin_x, origin_y,
                            &world) == 0);
    terrain[(60 - origin_y) * RTS_WINDOW_W + (51 - origin_x)] = 0;

    /* predict_move refuses a corner cut before it ever reaches the wire. */
    predict_init(&ps, 50, 60);
    terrain[(61 - origin_y) * RTS_WINDOW_W + (50 - origin_x)] =
        PREDICT_TILE_BUILDING;
    terrain[(60 - origin_y) * RTS_WINDOW_W + (51 - origin_x)] =
        PREDICT_TILE_BUILDING;
    assert(predict_move(&ps, 1, 51, 61, terrain, origin_x, origin_y, &world) == 0);
    assert(ps.count == 0 && ps.x == 50 && ps.y == 60);

    /* A queued diagonal that a newly-arrived blocker has since closed forces
       a hard snap during replay, rather than drifting into the corner. */
    memset(terrain, 0, sizeof(terrain));
    predict_init(&ps, 50, 60);
    assert(predict_move(&ps, 5, 51, 61, terrain, origin_x, origin_y, &world) == 1);
    assert(ps.count == 1);
    terrain[(61 - origin_y) * RTS_WINDOW_W + (50 - origin_x)] =
        PREDICT_TILE_BUILDING;
    terrain[(60 - origin_y) * RTS_WINDOW_W + (51 - origin_x)] =
        PREDICT_TILE_BUILDING;
    assert(predict_reconcile(&ps, 50, 60, 0, 4, terrain, origin_x, origin_y,
                             &world) == 1);
    assert(ps.count == 0 && ps.x == 50 && ps.y == 60);

    /* The named-NPC overlay tiles block movement but are not entities, so
       only the terrain test can catch them. */
    assert(predict_tile_blocks(PREDICT_TILE_DANIEL));
    assert(predict_tile_blocks(PREDICT_TILE_WILHELM));
    assert(predict_tile_blocks(PREDICT_TILE_LUCIAN));
    assert(predict_tile_blocks(PREDICT_TILE_NERISSA));
    assert(predict_tile_blocks(PREDICT_TILE_BULLET));
    assert(predict_tile_blocks(PREDICT_TILE_BEAVER));
    assert(predict_tile_blocks(PREDICT_TILE_SNAKE));
}

static void test_hud_wrap(void)
{
    /* 141 characters, the display-page maximum. */
    const char *page =
        "THE OLD FLOODWORKS BELOW THE DAM HAVE BEEN QUIET FOR YEARS "
        "BUT THE WATER IS RISING AGAIN AND SOMETHING DOWN THERE IS "
        "STILL PUMPING HARD TODAY";
    unsigned char len = (unsigned char)strlen(page);
    unsigned char pos = 0;
    unsigned char start;
    unsigned char line_len;
    unsigned char lines = 0;
    unsigned char emitted = 0;

    assert(len == RTS_DLG_PAGE_MAX);

    while ((line_len = hud_wrap_next(page, len, &pos, HUD_TEXT_COLS, &start))
           != 0) {
        /* Nothing may exceed the sprite width, or hud_text_render silently
           truncates and the reader loses words. */
        assert(line_len <= HUD_TEXT_COLS);
        assert(page[start] != ' ');
        assert(page[start + line_len - 1] != ' ');
        emitted += line_len;
        ++lines;
        assert(lines <= 8);
    }
    /* Every character survives except the consumed separators. */
    assert(emitted == len - (lines - 1));

    /* A word wider than the line is hard-split instead of looping forever. */
    {
        const char *long_word = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
        unsigned char wlen = (unsigned char)strlen(long_word);

        pos = 0;
        assert(hud_wrap_next(long_word, wlen, &pos, HUD_TEXT_COLS, &start) ==
               HUD_TEXT_COLS);
        assert(start == 0 && pos == HUD_TEXT_COLS);
        assert(hud_wrap_next(long_word, wlen, &pos, HUD_TEXT_COLS, &start) ==
               wlen - HUD_TEXT_COLS);
        assert(hud_wrap_next(long_word, wlen, &pos, HUD_TEXT_COLS, &start) == 0);
    }

    /* A word ending exactly at the boundary stays whole. */
    {
        const char *exact = "ABCDE FGHIJ KLMNO PQRST UVWXY Z";
        unsigned char elen = (unsigned char)strlen(exact);

        assert(elen == HUD_TEXT_COLS);
        pos = 0;
        assert(hud_wrap_next(exact, elen, &pos, HUD_TEXT_COLS, &start) == elen);
        assert(hud_wrap_next(exact, elen, &pos, HUD_TEXT_COLS, &start) == 0);
    }

    /* Runs of spaces collapse rather than emitting blank lines. */
    {
        const char *spaced = "ONE     TWO";

        pos = 0;
        assert(hud_wrap_next(spaced, 11, &pos, 5, &start) == 3);
        assert(start == 0);
        assert(hud_wrap_next(spaced, 11, &pos, 5, &start) == 3);
        assert(start == 8);
        assert(hud_wrap_next(spaced, 11, &pos, 5, &start) == 0);
    }
}


/* Drive one modal iteration with no page update pending. */
static unsigned char modal_press(struct dlg_modal *modal, unsigned char buttons,
                                 unsigned char flags)
{
    return dlg_modal_step(modal, 0, modal->shown, flags, buttons);
}

static void test_dlg_input_latch(void)
{
    unsigned char held = 0;

    /* A press is an edge; holding it is not. */
    assert(dlg_input_latch(&held, DLG_BTN_A) == DLG_ACTION_ACCEPT);
    assert(dlg_input_latch(&held, DLG_BTN_A) == DLG_ACTION_NONE);
    assert(dlg_input_latch(&held, 0) == DLG_ACTION_NONE);
    assert(dlg_input_latch(&held, DLG_BTN_A) == DLG_ACTION_ACCEPT);

    /* Rolling from B to A without a full release still registers A. A single
       "some button is held" flag loses this, and that is what made the modal
       need a second press. */
    held = 0;
    assert(dlg_input_latch(&held, DLG_BTN_B) == DLG_ACTION_DECLINE);
    assert(dlg_input_latch(&held, DLG_BTN_B | DLG_BTN_A) == DLG_ACTION_ACCEPT);

    /* Releases are not actions -- a change detector would fire on them. */
    held = DLG_BTN_A;
    assert(dlg_input_latch(&held, 0) == DLG_ACTION_NONE);

    /* Seeding with the button that opened the scene swallows it until it is
       released, so the interact press cannot also answer the first page. */
    held = DLG_BTN_B;
    assert(dlg_input_latch(&held, DLG_BTN_B) == DLG_ACTION_NONE);
    assert(dlg_input_latch(&held, 0) == DLG_ACTION_NONE);
    assert(dlg_input_latch(&held, DLG_BTN_B) == DLG_ACTION_DECLINE);
}

static void test_dlg_modal_pages_and_acks(void)
{
    struct dlg_modal modal;
    unsigned char effects;

    /* Opened by holding B (interact), as the game loop does. */
    dlg_modal_open(&modal, DLG_BTN_B);
    assert(modal.shown == DLG_SHOWN_NONE);

    /* First page arrives: drawn twice, once per alternating framebuffer. */
    effects = dlg_modal_step(&modal, 1, 0, 0, DLG_BTN_B);
    assert(effects == DLG_EFFECT_DRAW);
    assert(modal.shown == 0);
    effects = dlg_modal_step(&modal, 0, 0, 0, 0);
    assert(effects == DLG_EFFECT_DRAW);
    effects = dlg_modal_step(&modal, 0, 0, 0, 0);
    assert(effects == 0);

    /* A advances a non-final page: ack, no close, input held after. */
    effects = modal_press(&modal, DLG_BTN_A, 0);
    assert(effects == DLG_EFFECT_ACK_ACCEPT);
    assert(modal.waiting == 1);
    assert(modal.closing == 0);

    /* Entering the wait must not owe a redraw: a page is eleven text lines
       rendered through the HUD's msg_sprite, and two extra of those while the
       server streams the next page overflow the RX ring -- corrupted HUD,
       black terrain. */
    assert(modal_press(&modal, 0, 0) == 0);

    /* Further presses while the next page is in flight send nothing: one
       press must not advance two pages. */
    assert(modal_press(&modal, DLG_BTN_A, 0) == 0);

    /* The next page clears the hold and is drawn. */
    assert(modal_press(&modal, 0, 0) == 0);
    effects = dlg_modal_step(&modal, 1, 1, 0, 0);
    assert(effects == DLG_EFFECT_DRAW);
    assert(modal.waiting == 0);
    assert(modal_press(&modal, 0, 0) == DLG_EFFECT_DRAW); /* second page */

    /* A press gated by `waiting` must not cost the player their next press:
       once the page lands, the very next press acts. */
    effects = modal_press(&modal, DLG_BTN_A, 0);
    assert(effects == DLG_EFFECT_ACK_ACCEPT);
}

static void test_dlg_modal_last_page_and_decline(void)
{
    struct dlg_modal modal;
    unsigned char effects;

    /* Accepting the final page acks and closes. */
    dlg_modal_open(&modal, 0);
    dlg_modal_step(&modal, 1, 0, RTS_DLG_FLAG_LAST_PAGE, 0);
    modal_press(&modal, 0, RTS_DLG_FLAG_LAST_PAGE); /* drain the second draw */
    effects = modal_press(&modal, DLG_BTN_A, RTS_DLG_FLAG_LAST_PAGE);
    assert(effects == (DLG_EFFECT_ACK_ACCEPT | DLG_EFFECT_CLOSE));
    assert(modal.closing == 1);

    /* B declines and closes, and must carry the decline bit -- a decline that
       reaches the server as a bare ack reads as accept. */
    dlg_modal_open(&modal, 0);
    dlg_modal_step(&modal, 1, 0, RTS_DLG_FLAG_QUEST_OFFER | RTS_DLG_FLAG_LAST_PAGE, 0);
    modal_press(&modal, 0, RTS_DLG_FLAG_QUEST_OFFER | RTS_DLG_FLAG_LAST_PAGE);
    effects = modal_press(&modal, DLG_BTN_B,
                          RTS_DLG_FLAG_QUEST_OFFER | RTS_DLG_FLAG_LAST_PAGE);
    assert(effects == (DLG_EFFECT_ACK_DECLINE | DLG_EFFECT_CLOSE));

    /* B is the escape hatch: it works even while waiting on a page that a
       dead link will never deliver. */
    dlg_modal_open(&modal, 0);
    dlg_modal_step(&modal, 1, 0, 0, 0);
    modal_press(&modal, 0, 0); /* drain the second draw */
    assert(modal_press(&modal, DLG_BTN_A, 0) == DLG_EFFECT_ACK_ACCEPT);
    assert(modal.waiting == 1);
    assert(modal_press(&modal, 0, 0) == 0);
    effects = modal_press(&modal, DLG_BTN_B, 0);
    assert(effects == (DLG_EFFECT_ACK_DECLINE | DLG_EFFECT_CLOSE));
}

static void test_dlg_modal_page_resend_is_not_a_redraw(void)
{
    struct dlg_modal modal;

    dlg_modal_open(&modal, 0);
    assert(dlg_modal_step(&modal, 1, 0, 0, 0) == DLG_EFFECT_DRAW);
    assert(dlg_modal_step(&modal, 0, 0, 0, 0) == DLG_EFFECT_DRAW);
    assert(dlg_modal_step(&modal, 0, 0, 0, 0) == 0);

    /* The server resends an unacked page. Redrawing it, or re-arming input,
       would make a slow ack look like a double advance. */
    assert(dlg_modal_step(&modal, 1, 0, 0, 0) == 0);

    /* ...and a resend must not clear a pending wait either. */
    assert(modal_press(&modal, DLG_BTN_A, 0) == DLG_EFFECT_ACK_ACCEPT);
    assert(modal.waiting == 1);
    assert(dlg_modal_step(&modal, 1, 0, 0, 0) == 0);
    assert(modal.waiting == 1);
}

int main(void)
{
    test_login_request();
    test_hello_checksum();
    test_crc_and_cobs();
    test_initial_player_state_vector();
    test_bf_stream_parser();
    test_bootstrap_window_assembly();
    test_fragmented_bootstrap_stream_with_hello_echo();
    test_bootstrap_restart_adopts_new_generation();
    test_bootstrap_terrain_edge_shifts();
    test_bootstrap_window_fill_and_activate();
    test_bootstrap_revision_trust_next();
    test_predict_blocking_matches_server();
    test_predict_basic_and_replay();
    test_predict_correction_overflow_and_wrap();
    test_rt_outgoing_server_vectors();
    test_rt_state_packets();
    test_rt_phase7_outgoing_vectors();
    test_rt_phase7_incoming_packets();
    test_rt_map_transition();
    test_rt_dialogue_page();
    test_rt_dialogue_ack_vector();
    test_rt_quest_and_message();
    test_rt_enemy_kind_and_items();
    test_shot_step_eight_way();
    test_predict_diagonal_corner();
    test_hud_wrap();
    test_camera_and_hud_text();
    test_dlg_input_latch();
    test_dlg_modal_pages_and_acks();
    test_dlg_modal_last_page_and_decline();
    test_dlg_modal_page_resend_is_not_a_redraw();
    puts("host client tests: ok");
    return 0;
}
