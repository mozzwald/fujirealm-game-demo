#include <string.h>

#include "bootstrap.h"

static unsigned char sum8(const unsigned char *buf, unsigned char len)
{
    unsigned char i;
    unsigned char sum = 0;

    for (i = 0; i < len; ++i) {
        sum += buf[i];
    }
    return sum;
}

static unsigned read_u16(const unsigned char *buf)
{
    return (unsigned)buf[0] | ((unsigned)buf[1] << 8);
}

void bf_parser_init(struct bf_parser *parser)
{
    parser->pos = 0;
    parser->want = 4;
    parser->last_error = BF_ERROR_NONE;
}

signed char bf_parser_feed(struct bf_parser *parser, unsigned char byte,
                           struct bf_packet *packet)
{
    unsigned char i;

    if (parser->pos == 0 && byte != BF_MAGIC) {
        return BF_FEED_NONE;
    }

    parser->frame[parser->pos++] = byte;
    if (parser->pos == 2 && parser->frame[1] != BF_VERSION) {
        bf_parser_init(parser);
        parser->last_error = BF_ERROR_VERSION;
        return BF_FEED_ERROR;
    }
    if (parser->pos == 4) {
        if (parser->frame[3] > BF_MAX_PAYLOAD) {
            bf_parser_init(parser);
            parser->last_error = BF_ERROR_LENGTH;
            return BF_FEED_ERROR;
        }
        parser->want = parser->frame[3] + 5;
    }
    if (parser->pos < parser->want) {
        return BF_FEED_NONE;
    }
    if (sum8(parser->frame, parser->want - 1) !=
        parser->frame[parser->want - 1]) {
        bf_parser_init(parser);
        parser->last_error = BF_ERROR_CHECKSUM;
        return BF_FEED_ERROR;
    }

    packet->type = parser->frame[2];
    packet->payload_len = parser->frame[3];
    for (i = 0; i < packet->payload_len; ++i) {
        packet->payload[i] = parser->frame[4 + i];
    }
    bf_parser_init(parser);
    return BF_FEED_PACKET;
}

void bootstrap_init(struct bootstrap_state *state)
{
    unsigned i;

    state->got_welcome = 0;
    state->player_id = 0;
    state->seed = 0;
    state->max_beavers = 0;
    state->protocol_version = 0;
    state->tick = 0;
    state->origin_x = 0;
    state->origin_y = 0;
    state->rows_received = 0;
    state->error_code = BOOT_ERROR_NONE;
    for (i = 0; i < BOOTSTRAP_TERRAIN_SIZE; ++i) {
        state->terrain[i] = 0;
    }
    state->revision = 0;
    state->revision_trust_next = 0;
    state->commit_pending = 0;
    state->commit_fill_id = 0;
}

static signed char apply_welcome(struct bootstrap_state *state,
                                 const struct bf_packet *packet)
{
    if (packet->payload_len != 5) {
        state->error_code = BOOT_ERROR_WELCOME_LENGTH;
        return BOOTSTRAP_ERROR;
    }
    state->player_id = packet->payload[0];
    state->seed = read_u16(&packet->payload[1]);
    state->max_beavers = packet->payload[3];
    state->protocol_version = packet->payload[4];
    if (state->protocol_version != BF_VERSION) {
        state->error_code = BOOT_ERROR_WELCOME_VERSION;
        return BOOTSTRAP_ERROR;
    }
    state->got_welcome = 1;
    return state->rows_received == BOOTSTRAP_ALL_ROWS ?
        BOOTSTRAP_COMPLETE : BOOTSTRAP_WELCOME;
}

static signed char apply_window(struct bootstrap_state *state,
                                const struct bf_packet *packet)
{
    const unsigned char *payload = packet->payload;
    unsigned tick;
    unsigned origin_x;
    unsigned origin_y;
    unsigned tile_count;
    unsigned char width;
    unsigned char height;
    unsigned char chunk_y;
    unsigned char chunk_h;
    unsigned char row;
    unsigned char column;
    unsigned src;
    unsigned dst;

    if (packet->payload_len < 12) {
        state->error_code = BOOT_ERROR_WINDOW_SHORT;
        return BOOTSTRAP_ERROR;
    }
    tick = read_u16(&payload[0]);
    origin_x = read_u16(&payload[2]);
    origin_y = read_u16(&payload[4]);
    width = payload[6];
    height = payload[7];
    chunk_y = payload[8];
    chunk_h = payload[9];
    tile_count = read_u16(&payload[10]);

    if (width != BOOTSTRAP_WINDOW_W || height != BOOTSTRAP_WINDOW_H ||
        chunk_h == 0 || chunk_y + chunk_h > height) {
        state->error_code = BOOT_ERROR_WINDOW_GEOMETRY;
        return BOOTSTRAP_ERROR;
    }
    if (tile_count != (unsigned)width * chunk_h ||
        packet->payload_len != 12 + tile_count) {
        state->error_code = BOOT_ERROR_WINDOW_COUNT;
        return BOOTSTRAP_ERROR;
    }
    if (state->rows_received != 0 &&
        (state->tick != tick || state->origin_x != origin_x ||
         state->origin_y != origin_y)) {
        /* A re-sent HELLO makes the server restart the bootstrap at a new
           tick; adopt the new generation and drop the partial old rows. */
        state->rows_received = 0;
    }
    state->tick = tick;
    state->origin_x = origin_x;
    state->origin_y = origin_y;

    src = 12;
    for (row = 0; row < chunk_h; ++row) {
        dst = (unsigned)(chunk_y + row) * BOOTSTRAP_WINDOW_W;
        for (column = 0; column < width; ++column) {
            state->terrain[dst + column] = payload[src++];
        }
        state->rows_received |= 1UL << (chunk_y + row);
    }

    return state->got_welcome &&
           state->rows_received == BOOTSTRAP_ALL_ROWS ?
        BOOTSTRAP_COMPLETE : BOOTSTRAP_WINDOW;
}

signed char bootstrap_apply(struct bootstrap_state *state,
                            const struct bf_packet *packet)
{
    if (packet->type == BF_WELCOME) {
        return apply_welcome(state, packet);
    }
    if (packet->type == BF_WINDOW) {
        return apply_window(state, packet);
    }
    return BOOTSTRAP_IGNORED;
}

static unsigned next_cache_revision(unsigned revision)
{
    unsigned next = (revision + 1) & 0xFFFFU;

    return next == 0 ? 1 : next;
}

static signed char apply_edge_column(struct bootstrap_state *state,
                                     unsigned char origin_x,
                                     unsigned char origin_y,
                                     const unsigned char *tiles)
{
    unsigned char row;
    unsigned char *line;

    if (origin_y != state->origin_y) {
        return BOOTSTRAP_EDGE_RESYNC;
    }
    /* memmove rather than per-byte loops: this runs on every cache step,
       about ten times a second while walking, and the byte-at-a-time form
       was a measurable share of the per-second cost of moving. */
    if (origin_x == state->origin_x - 1) {
        for (row = 0; row < BOOTSTRAP_WINDOW_H; ++row) {
            line = &state->terrain[(unsigned)row * BOOTSTRAP_WINDOW_W];
            memmove(line + 1, line, BOOTSTRAP_WINDOW_W - 1);
            line[0] = tiles[row];
        }
        --state->origin_x;
        return BOOTSTRAP_EDGE_APPLIED;
    }
    if ((unsigned)origin_x == state->origin_x + BOOTSTRAP_WINDOW_W) {
        for (row = 0; row < BOOTSTRAP_WINDOW_H; ++row) {
            line = &state->terrain[(unsigned)row * BOOTSTRAP_WINDOW_W];
            memmove(line, line + 1, BOOTSTRAP_WINDOW_W - 1);
            line[BOOTSTRAP_WINDOW_W - 1] = tiles[row];
        }
        ++state->origin_x;
        return BOOTSTRAP_EDGE_APPLIED;
    }
    return BOOTSTRAP_EDGE_RESYNC;
}

static signed char apply_edge_row(struct bootstrap_state *state,
                                  unsigned char origin_x,
                                  unsigned char origin_y,
                                  const unsigned char *tiles)
{

    if (origin_x != state->origin_x) {
        return BOOTSTRAP_EDGE_RESYNC;
    }
    /* Rows are contiguous, so the whole block shifts in a single memmove
       instead of 23 nested loops over 736 bytes. */
    if (origin_y == state->origin_y - 1) {
        memmove(&state->terrain[BOOTSTRAP_WINDOW_W], &state->terrain[0],
                (unsigned)(BOOTSTRAP_WINDOW_H - 1) * BOOTSTRAP_WINDOW_W);
        memcpy(&state->terrain[0], tiles, BOOTSTRAP_WINDOW_W);
        --state->origin_y;
        return BOOTSTRAP_EDGE_APPLIED;
    }
    if ((unsigned)origin_y == state->origin_y + BOOTSTRAP_WINDOW_H) {
        memmove(&state->terrain[0], &state->terrain[BOOTSTRAP_WINDOW_W],
                (unsigned)(BOOTSTRAP_WINDOW_H - 1) * BOOTSTRAP_WINDOW_W);
        memcpy(&state->terrain[(unsigned)(BOOTSTRAP_WINDOW_H - 1) *
                               BOOTSTRAP_WINDOW_W],
               tiles, BOOTSTRAP_WINDOW_W);
        ++state->origin_y;
        return BOOTSTRAP_EDGE_APPLIED;
    }
    return BOOTSTRAP_EDGE_RESYNC;
}

signed char bootstrap_apply_terrain_edge(struct bootstrap_state *state,
                                         unsigned char origin_x,
                                         unsigned char origin_y,
                                         unsigned char width,
                                         unsigned char height,
                                         unsigned revision,
                                         const unsigned char *tiles,
                                         unsigned char tile_count)
{
    signed char result;

    if (revision == state->revision) {
        return BOOTSTRAP_EDGE_DUPLICATE;
    }
    if (!state->revision_trust_next &&
        revision != next_cache_revision(state->revision)) {
        return BOOTSTRAP_EDGE_RESYNC;
    }

    if (width == 1 && height == BOOTSTRAP_WINDOW_H &&
        tile_count == BOOTSTRAP_WINDOW_H) {
        result = apply_edge_column(state, origin_x, origin_y, tiles);
    } else if (height == 1 && width == BOOTSTRAP_WINDOW_W &&
               tile_count == BOOTSTRAP_WINDOW_W) {
        result = apply_edge_row(state, origin_x, origin_y, tiles);
    } else {
        result = BOOTSTRAP_EDGE_RESYNC;
    }

    if (result == BOOTSTRAP_EDGE_APPLIED) {
        state->revision = revision;
        state->revision_trust_next = 0;
    }
    return result;
}

void bootstrap_fill_init(struct bootstrap_fill *fill)
{
    fill->active = 0;
    fill->fill_id = 0;
    fill->origin_x = 0;
    fill->origin_y = 0;
    fill->rows_have = 0;
}

signed char bootstrap_fill_apply_row(struct bootstrap_fill *fill,
                                     unsigned char fill_id,
                                     unsigned char origin_x,
                                     unsigned char abs_origin_y,
                                     unsigned char row_index,
                                     const unsigned char *tiles)
{
    unsigned char col;
    unsigned fill_origin_y;
    unsigned long bit;

    if (row_index >= BOOTSTRAP_WINDOW_H) {
        return BOOTSTRAP_FILL_IGNORED;
    }
    fill_origin_y = (unsigned)abs_origin_y - row_index;

    if (!fill->active || fill->fill_id != fill_id ||
        fill->origin_x != origin_x || fill->origin_y != fill_origin_y) {
        fill->active = 1;
        fill->fill_id = fill_id;
        fill->origin_x = origin_x;
        fill->origin_y = fill_origin_y;
        fill->rows_have = 0;
    }

    bit = 1UL << row_index;
    if (fill->rows_have & bit) {
        return BOOTSTRAP_FILL_DUPLICATE;
    }
    for (col = 0; col < BOOTSTRAP_WINDOW_W; ++col) {
        fill->terrain[(unsigned)row_index * BOOTSTRAP_WINDOW_W + col] =
            tiles[col];
    }
    fill->rows_have |= bit;
    return fill->rows_have == BOOTSTRAP_ALL_ROWS ?
        BOOTSTRAP_FILL_COMPLETE : BOOTSTRAP_FILL_ROW_APPLIED;
}

void bootstrap_fill_activate(struct bootstrap_fill *fill,
                             struct bootstrap_state *state)
{
    unsigned i;

    for (i = 0; i < BOOTSTRAP_TERRAIN_SIZE; ++i) {
        state->terrain[i] = fill->terrain[i];
    }
    state->origin_x = fill->origin_x;
    state->origin_y = fill->origin_y;
    state->revision_trust_next = 1;
    state->commit_pending = 1;
    state->commit_fill_id = fill->fill_id;
    fill->active = 0;
}

unsigned char bootstrap_commit_ack_matches(const struct bootstrap_state *state,
                                           unsigned char fill_id,
                                           unsigned char origin_x,
                                           unsigned char origin_y)
{
    return state->commit_pending && state->commit_fill_id == fill_id &&
           state->origin_x == origin_x && state->origin_y == origin_y;
}
