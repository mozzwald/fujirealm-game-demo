#include "rt_state.h"

/* CRC-16/CCITT-FALSE, byte at a time. The bitwise form cost eight
 * shift/test/xor rounds on a 16-bit value for every byte, which measured as
 * a significant share of the per-second cost of receiving packets. Split
 * into two 256-byte tables so the inner loop is pure 8-bit work with no
 * 16-bit shifts and no index scaling -- both of which the 6502 does badly.
 *
 * Generated for polynomial 0x1021; verified against the bitwise version
 * over random vectors and against the canonical frames in host_tests.c. */
static const unsigned char crc16_hi[256] = {
    0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x81, 0x91, 0xA1, 0xB1,
    0xC1, 0xD1, 0xE1, 0xF1, 0x12, 0x02, 0x32, 0x22, 0x52, 0x42, 0x72, 0x62,
    0x93, 0x83, 0xB3, 0xA3, 0xD3, 0xC3, 0xF3, 0xE3, 0x24, 0x34, 0x04, 0x14,
    0x64, 0x74, 0x44, 0x54, 0xA5, 0xB5, 0x85, 0x95, 0xE5, 0xF5, 0xC5, 0xD5,
    0x36, 0x26, 0x16, 0x06, 0x76, 0x66, 0x56, 0x46, 0xB7, 0xA7, 0x97, 0x87,
    0xF7, 0xE7, 0xD7, 0xC7, 0x48, 0x58, 0x68, 0x78, 0x08, 0x18, 0x28, 0x38,
    0xC9, 0xD9, 0xE9, 0xF9, 0x89, 0x99, 0xA9, 0xB9, 0x5A, 0x4A, 0x7A, 0x6A,
    0x1A, 0x0A, 0x3A, 0x2A, 0xDB, 0xCB, 0xFB, 0xEB, 0x9B, 0x8B, 0xBB, 0xAB,
    0x6C, 0x7C, 0x4C, 0x5C, 0x2C, 0x3C, 0x0C, 0x1C, 0xED, 0xFD, 0xCD, 0xDD,
    0xAD, 0xBD, 0x8D, 0x9D, 0x7E, 0x6E, 0x5E, 0x4E, 0x3E, 0x2E, 0x1E, 0x0E,
    0xFF, 0xEF, 0xDF, 0xCF, 0xBF, 0xAF, 0x9F, 0x8F, 0x91, 0x81, 0xB1, 0xA1,
    0xD1, 0xC1, 0xF1, 0xE1, 0x10, 0x00, 0x30, 0x20, 0x50, 0x40, 0x70, 0x60,
    0x83, 0x93, 0xA3, 0xB3, 0xC3, 0xD3, 0xE3, 0xF3, 0x02, 0x12, 0x22, 0x32,
    0x42, 0x52, 0x62, 0x72, 0xB5, 0xA5, 0x95, 0x85, 0xF5, 0xE5, 0xD5, 0xC5,
    0x34, 0x24, 0x14, 0x04, 0x74, 0x64, 0x54, 0x44, 0xA7, 0xB7, 0x87, 0x97,
    0xE7, 0xF7, 0xC7, 0xD7, 0x26, 0x36, 0x06, 0x16, 0x66, 0x76, 0x46, 0x56,
    0xD9, 0xC9, 0xF9, 0xE9, 0x99, 0x89, 0xB9, 0xA9, 0x58, 0x48, 0x78, 0x68,
    0x18, 0x08, 0x38, 0x28, 0xCB, 0xDB, 0xEB, 0xFB, 0x8B, 0x9B, 0xAB, 0xBB,
    0x4A, 0x5A, 0x6A, 0x7A, 0x0A, 0x1A, 0x2A, 0x3A, 0xFD, 0xED, 0xDD, 0xCD,
    0xBD, 0xAD, 0x9D, 0x8D, 0x7C, 0x6C, 0x5C, 0x4C, 0x3C, 0x2C, 0x1C, 0x0C,
    0xEF, 0xFF, 0xCF, 0xDF, 0xAF, 0xBF, 0x8F, 0x9F, 0x6E, 0x7E, 0x4E, 0x5E,
    0x2E, 0x3E, 0x0E, 0x1E
};

static const unsigned char crc16_lo[256] = {
    0x00, 0x21, 0x42, 0x63, 0x84, 0xA5, 0xC6, 0xE7, 0x08, 0x29, 0x4A, 0x6B,
    0x8C, 0xAD, 0xCE, 0xEF, 0x31, 0x10, 0x73, 0x52, 0xB5, 0x94, 0xF7, 0xD6,
    0x39, 0x18, 0x7B, 0x5A, 0xBD, 0x9C, 0xFF, 0xDE, 0x62, 0x43, 0x20, 0x01,
    0xE6, 0xC7, 0xA4, 0x85, 0x6A, 0x4B, 0x28, 0x09, 0xEE, 0xCF, 0xAC, 0x8D,
    0x53, 0x72, 0x11, 0x30, 0xD7, 0xF6, 0x95, 0xB4, 0x5B, 0x7A, 0x19, 0x38,
    0xDF, 0xFE, 0x9D, 0xBC, 0xC4, 0xE5, 0x86, 0xA7, 0x40, 0x61, 0x02, 0x23,
    0xCC, 0xED, 0x8E, 0xAF, 0x48, 0x69, 0x0A, 0x2B, 0xF5, 0xD4, 0xB7, 0x96,
    0x71, 0x50, 0x33, 0x12, 0xFD, 0xDC, 0xBF, 0x9E, 0x79, 0x58, 0x3B, 0x1A,
    0xA6, 0x87, 0xE4, 0xC5, 0x22, 0x03, 0x60, 0x41, 0xAE, 0x8F, 0xEC, 0xCD,
    0x2A, 0x0B, 0x68, 0x49, 0x97, 0xB6, 0xD5, 0xF4, 0x13, 0x32, 0x51, 0x70,
    0x9F, 0xBE, 0xDD, 0xFC, 0x1B, 0x3A, 0x59, 0x78, 0x88, 0xA9, 0xCA, 0xEB,
    0x0C, 0x2D, 0x4E, 0x6F, 0x80, 0xA1, 0xC2, 0xE3, 0x04, 0x25, 0x46, 0x67,
    0xB9, 0x98, 0xFB, 0xDA, 0x3D, 0x1C, 0x7F, 0x5E, 0xB1, 0x90, 0xF3, 0xD2,
    0x35, 0x14, 0x77, 0x56, 0xEA, 0xCB, 0xA8, 0x89, 0x6E, 0x4F, 0x2C, 0x0D,
    0xE2, 0xC3, 0xA0, 0x81, 0x66, 0x47, 0x24, 0x05, 0xDB, 0xFA, 0x99, 0xB8,
    0x5F, 0x7E, 0x1D, 0x3C, 0xD3, 0xF2, 0x91, 0xB0, 0x57, 0x76, 0x15, 0x34,
    0x4C, 0x6D, 0x0E, 0x2F, 0xC8, 0xE9, 0x8A, 0xAB, 0x44, 0x65, 0x06, 0x27,
    0xC0, 0xE1, 0x82, 0xA3, 0x7D, 0x5C, 0x3F, 0x1E, 0xF9, 0xD8, 0xBB, 0x9A,
    0x75, 0x54, 0x37, 0x16, 0xF1, 0xD0, 0xB3, 0x92, 0x2E, 0x0F, 0x6C, 0x4D,
    0xAA, 0x8B, 0xE8, 0xC9, 0x26, 0x07, 0x64, 0x45, 0xA2, 0x83, 0xE0, 0xC1,
    0x1F, 0x3E, 0x5D, 0x7C, 0x9B, 0xBA, 0xD9, 0xF8, 0x17, 0x36, 0x55, 0x74,
    0x93, 0xB2, 0xD1, 0xF0
};

unsigned rt_crc16(const unsigned char *data, unsigned char len)
{
    unsigned char i;
    unsigned char index;
    unsigned char hi = 0xFF;
    unsigned char lo = 0xFF;

    for (i = 0; i < len; ++i) {
        index = hi ^ data[i];
        hi = lo ^ crc16_hi[index];
        lo = crc16_lo[index];
    }
    return ((unsigned)hi << 8) | lo;
}

unsigned char rt_cobs_decode(const unsigned char *in, unsigned char in_len,
                             unsigned char *out)
{
    unsigned char read = 0;
    unsigned char write = 0;
    unsigned char code;
    unsigned char count;

    while (read < in_len) {
        code = in[read++];
        if (code == 0 || (unsigned)read + code - 1 > in_len) {
            return 0;
        }
        count = code - 1;
        while (count-- != 0) {
            out[write++] = in[read++];
        }
        if (code != 0xFF && read < in_len) {
            out[write++] = 0;
        }
    }
    return write;
}

unsigned char rt_cobs_encode(const unsigned char *in, unsigned char in_len,
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

void rt_state_init(struct rt_state *state)
{
    unsigned i;
    unsigned char *bytes = (unsigned char *)state;

    for (i = 0; i < sizeof(struct rt_state); ++i) {
        bytes[i] = 0;
    }
}

static void apply_world_state(struct rt_state *state, unsigned char *terrain,
                              unsigned origin_x, unsigned origin_y,
                              const unsigned char *w)
{
    unsigned char i;
    unsigned char count = w[3];
    unsigned tile_x;
    unsigned tile_y;

    state->world_seen = 1;
    state->last_server_seq = (unsigned)w[4] | ((unsigned)w[5] << 8);
    state->player_x = w[6];
    state->player_y = w[7];
    state->health = w[8];
    state->correction_flags = w[9];
    state->echo_client_seq = (unsigned)w[10] | ((unsigned)w[11] << 8);
    if (count > RTS_MAX_BEAVERS) {
        count = RTS_MAX_BEAVERS;
    }
    state->beaver_count = count;
    for (i = 0; i < count; ++i) {
        unsigned char kind = w[18 + i * 4];

        state->beavers[i].x = w[15 + i * 4];
        state->beavers[i].y = w[16 + i * 4];
        state->beavers[i].hp = w[17 + i * 4];
        /* Bit 7 is a one-shot "damage just landed" pulse, not part of the
           species. The blink it arms is timed locally: the server sends the
           pulse once and never repeats it. */
        state->beavers[i].kind = kind & RTS_KIND_MASK;
        if (kind & RTS_KIND_HIT_PULSE) {
            state->beavers[i].hit_timer = RTS_HIT_FLASH_FRAMES;
        }
    }

    /* Live terrain cell update (chopped tree, item drop, ...). Absolute
     * coordinates; only cells inside the bootstrap window are ours. */
    if (terrain != 0) {
        tile_x = w[13];
        tile_y = w[14];
        if (tile_x >= origin_x && tile_x < origin_x + RTS_WINDOW_W &&
            tile_y >= origin_y && tile_y < origin_y + RTS_WINDOW_H) {
            unsigned offset = (tile_y - origin_y) * RTS_WINDOW_W +
                              (tile_x - origin_x);
            /* Only report a change when the cell really differs: every
               WORLD_STATE carries these fields, and treating each one as a
               change would force a full repaint ten times a second. */
            if (terrain[offset] != w[12]) {
                terrain[offset] = w[12];
                state->tile_changed = 1;
            }
        }
    }
}

static void apply_hud_update(struct rt_state *state, const unsigned char *w)
{
    state->hud_seen = 1;
    state->hud_hp = w[6];
    state->hud_max_hp = w[7];
    state->hud_level = w[8];
    /* Payload: hp, max_hp, level, xp(2), xp_next(2), gold(2), flags, kills(2).
     * gold is w[13..14]; flags w[15]; pvp kills w[16..17]. */
    state->hud_gold = (unsigned)w[13] | ((unsigned)w[14] << 8);
    state->hud_pvp_enabled = (w[15] & RTS_HUD_FLAG_PVP_ENABLED) != 0;
    state->hud_pvp_kills = (unsigned)w[16] | ((unsigned)w[17] << 8);
}

static void apply_message(struct rt_state *state, const unsigned char *w)
{
    unsigned char i;
    unsigned char len = w[7];

    if (len > RTS_TEXT_MAX) {
        len = RTS_TEXT_MAX;
    }
    for (i = 0; i < len; ++i) {
        state->message[i] = (char)w[8 + i];
    }
    state->message[len] = 0;
    state->message_len = len;
    state->message_dirty = 1;
    /* Deliberately not conditional on w[6] (message_id): id 0 is a real
       message. See message_seen in rt_state.h. */
    state->message_seen = 1;
}

static void apply_quest_update(struct rt_state *state, const unsigned char *w)
{
    unsigned char i;
    unsigned char len = w[8];

    if (len > RTS_TEXT_MAX) {
        len = RTS_TEXT_MAX;
    }
    for (i = 0; i < len; ++i) {
        state->quest_text[i] = (char)w[9 + i];
    }
    state->quest_text[len] = 0;
    state->quest_len = len;
    state->quest_id = w[6];
    state->quest_state = w[7];
    state->quest_seen = 1;
    state->quest_dirty = 1;
}

/* Fold one chunk into the pending display page. Mirrors the Atari client's
 * netstream_apply_dialogue_page (fujirealm.asm:9781) exactly; the ordering
 * of these four rules is the contract, not an implementation detail. */
static void apply_dialogue_page(struct rt_state *state, const unsigned char *w)
{
    unsigned char chunk = w[11];
    unsigned char len = w[12];
    unsigned char i;

    /* 1. Chunk 0 restarts the page. This is also how a retransmit arrives, so
          it must be safe to replay a page we have already assembled. */
    if (chunk == 0) {
        state->dlg.len = 0;
        state->dlg.next_chunk = 0;
    }
    /* 2. A gap means we lost a chunk. Drop it silently and wait for the
          server's whole-page resend rather than assembling torn text. */
    if (chunk != state->dlg.next_chunk) {
        return;
    }

    state->dlg.id = w[6];
    state->dlg.speaker = w[7];
    state->dlg.page_index = w[8];
    state->dlg.page_count = w[9];

    /* 3. Append, clamped both per chunk and per page. */
    if (len > RTS_DLG_CHUNK_MAX) {
        len = RTS_DLG_CHUNK_MAX;
    }
    for (i = 0; i < len && state->dlg.len < RTS_DLG_PAGE_MAX; ++i) {
        state->dlg.text[state->dlg.len++] = (char)w[13 + i];
    }
    state->dlg.text[state->dlg.len] = 0;
    ++state->dlg.next_chunk;

    /* 4. Commit the flags only from the chunk that carries CHUNK_END. Every
          earlier chunk of the page repeats a partial flags byte, and a
          retransmit's chunk 0 carries no LAST_PAGE at all -- taking flags from
          those is what froze the Atari client on a quest turn-in, because the
          prompt lost its accept/decline state mid-page. */
    if ((w[10] & RTS_DLG_FLAG_CHUNK_END) == 0) {
        return;
    }
    state->dlg.flags = w[10];
    state->dlg.dirty = 1;
    if (!state->dlg.active) {
        state->dlg.request = 1;
    }
}

unsigned char rt_item_art_index(unsigned char item_id)
{
    switch (item_id) {
    case 0:
        return RTS_ART_ITEM_NONE;
    case RTS_ITEM_GOLD:
        return RTS_ART_ITEM_GOLD;
    case RTS_ITEM_HERB:
        return RTS_ART_ITEM_HERB;
    case RTS_ITEM_POTION:
        return RTS_ART_ITEM_POTION;
    case RTS_ITEM_WARDEN_KEY:
        return RTS_ART_ITEM_KEY;
    default:
        /* Sticks stands in for anything we have no art for yet (oil and rust
           samples today), so an unknown drop is still visible and walkable-
           over rather than invisible. */
        return RTS_ART_ITEM_STICKS;
    }
}

void rt_spawn_tracer(struct rt_state *state, unsigned char x, unsigned char y,
                     unsigned char dir)
{
    unsigned char slot = state->tracer_next;

    state->tracers[slot].active = 1;
    state->tracers[slot].x = x;
    state->tracers[slot].y = y;
    state->tracers[slot].dir = dir;
    state->tracers[slot].steps = 0;
    ++slot;
    if (slot >= RTS_MAX_TRACERS) {
        slot = 0;
    }
    state->tracer_next = slot;
}

static void apply_remote_players(struct rt_state *state,
                                 const unsigned char *w)
{
    unsigned char i;
    unsigned char old_count = state->remote_count;
    unsigned char count = w[3];
    unsigned char nx;
    unsigned char ny;
    unsigned char nfacing;
    unsigned char nstate;
    unsigned char fire;

    if (count > RTS_MAX_REMOTE_PLAYERS) {
        count = RTS_MAX_REMOTE_PLAYERS;
    }
    for (i = 0; i < count; ++i) {
        nx = w[6 + i * 4];
        ny = w[7 + i * 4];
        nfacing = w[8 + i * 4];
        nstate = w[9 + i * 4];
        fire = nstate & RTS_REMOTE_STATE_FIRE_MASK;
        /* A change in the fire bits on a slot that was already occupied means
         * that remote fired: draw a cosmetic tracer from its cell and facing.
         * A freshly occupied slot only establishes a baseline (no tracer).
         * Facings 4-7 are followed too now that the stepper walks diagonals --
         * without that a remote's diagonal shots were silently invisible. */
        if (i < old_count && (state->remotes[i].state & RTS_REMOTE_ALIVE) &&
            (nstate & RTS_REMOTE_ALIVE) &&
            fire != state->remote_prev_fire[i] &&
            nfacing < RTS_FACE_COUNT) {
            rt_spawn_tracer(state, nx, ny, nfacing);
        }
        state->remote_prev_fire[i] = fire;
        state->remotes[i].x = nx;
        state->remotes[i].y = ny;
        state->remotes[i].facing = nfacing;
        state->remotes[i].state = nstate;
    }
    /* Slots that emptied this frame must forget their baseline so the next
     * occupant is treated as new rather than inheriting a stale fire count. */
    for (i = count; i < old_count; ++i) {
        state->remote_prev_fire[i] = 0;
    }
    state->remote_count = count;
}

static void apply_item_drops(struct rt_state *state, const unsigned char *w)
{
    unsigned char i;
    unsigned char count = w[3];

    if (count > RTS_MAX_ITEMS) {
        count = RTS_MAX_ITEMS;
    }
    state->item_count = count;
    for (i = 0; i < count; ++i) {
        state->items[i].x = w[6 + i * 4];
        state->items[i].y = w[7 + i * 4];
        state->items[i].item_id = w[8 + i * 4];
        state->items[i].quantity = w[9 + i * 4];
    }
}

static void apply_terrain_edge(struct rt_state *state, const unsigned char *w)
{
    unsigned char i;
    unsigned char count = w[3];

    if (count > RTS_EDGE_MAX_TILES) {
        count = RTS_EDGE_MAX_TILES;
    }
    state->edge.origin_x = w[6];
    state->edge.origin_y = w[7];
    state->edge.width = w[8];
    state->edge.height = w[9];
    state->edge.revision = (unsigned)w[10] | ((unsigned)w[11] << 8);
    state->edge.tile_count = count;
    for (i = 0; i < count; ++i) {
        state->edge.tiles[i] = w[12 + i];
    }
}

static void apply_window_row(struct rt_state *state, const unsigned char *w)
{
    unsigned char i;

    state->window_row.origin_x = w[6];
    state->window_row.origin_y = w[7];
    state->window_row.row_index = w[8];
    state->window_row.fill_id = w[9];
    for (i = 0; i < RTS_WINDOW_W; ++i) {
        state->window_row.tiles[i] = w[10 + i];
    }
}

static void apply_window_commit_ack(struct rt_state *state,
                                    const unsigned char *w)
{
    state->window_commit_ack.fill_id = w[6];
    state->window_commit_ack.origin_x = w[7];
    state->window_commit_ack.origin_y = w[8];
}

static void apply_map_change(struct rt_state *state, const unsigned char *w)
{
    state->map_change.map_id = w[6];
    state->map_change.spawn_x = w[7];
    state->map_change.spawn_y = w[8];
    state->map_change.tileset_id = w[9];
    state->map_change.palette_id = w[10];
    state->map_change.flags = w[11];
}

unsigned char rt_apply(struct rt_state *state, unsigned char *terrain,
                       unsigned origin_x, unsigned origin_y,
                       const unsigned char *raw, unsigned char raw_len)
{
    static unsigned char w[RTS_WORKSPACE];
    unsigned char i;
    unsigned expected_crc;

    if (raw_len < 8 || raw_len > RTS_MAX_RAW || raw[1] != RTS_VERSION ||
        raw[0] + 8 != raw_len) {
        return RTS_INVALID;
    }
    expected_crc = (unsigned)raw[raw_len - 2] |
                   ((unsigned)raw[raw_len - 1] << 8);
    if (rt_crc16(raw, raw_len - 2) != expected_crc) {
        return RTS_INVALID;
    }
    /* Re-pad the stripped trailing zeros into a fixed workspace. */
    for (i = 0; i < raw_len - 2; ++i) {
        w[i] = raw[i];
    }
    for (i = raw_len - 2; i < RTS_WORKSPACE; ++i) {
        w[i] = 0;
    }

    switch (w[2]) {
    case RTS_WORLD_STATE:
        apply_world_state(state, terrain, origin_x, origin_y, w);
        return RTS_WORLD_STATE;
    case RTS_HUD_UPDATE:
        apply_hud_update(state, w);
        return RTS_HUD_UPDATE;
    case RTS_MESSAGE:
        apply_message(state, w);
        return RTS_MESSAGE;
    case RTS_QUEST_UPDATE:
        apply_quest_update(state, w);
        return RTS_QUEST_UPDATE;
    case RTS_DIALOGUE_PAGE:
        apply_dialogue_page(state, w);
        return RTS_DIALOGUE_PAGE;
    case RTS_REMOTE_PLAYERS:
        apply_remote_players(state, w);
        return RTS_REMOTE_PLAYERS;
    case RTS_ITEM_DROPS:
        apply_item_drops(state, w);
        return RTS_ITEM_DROPS;
    case RTS_TERRAIN_EDGE:
        apply_terrain_edge(state, w);
        return RTS_TERRAIN_EDGE;
    case RTS_WINDOW_ROW:
        apply_window_row(state, w);
        return RTS_WINDOW_ROW;
    case RTS_WINDOW_COMMIT_ACK:
        apply_window_commit_ack(state, w);
        return RTS_WINDOW_COMMIT_ACK;
    case RTS_MAP_CHANGE:
        apply_map_change(state, w);
        return RTS_MAP_CHANGE;
    default:
        return 0;
    }
}

static unsigned char finish_frame(unsigned char *out, unsigned char *raw,
                                  unsigned char payload_len)
{
    unsigned crc;
    unsigned char encoded_len;

    while (payload_len != 0 && raw[5 + payload_len] == 0) {
        --payload_len;
    }
    raw[0] = payload_len;
    crc = rt_crc16(raw, payload_len + 6);
    raw[payload_len + 6] = (unsigned char)(crc & 0xFF);
    raw[payload_len + 7] = (unsigned char)(crc >> 8);
    encoded_len = rt_cobs_encode(raw, payload_len + 8, out);
    out[encoded_len++] = 0;
    return encoded_len;
}

unsigned char rt_build_auth(unsigned char *out, unsigned long token)
{
    unsigned char raw[12];

    raw[1] = RTS_VERSION;
    raw[2] = RTS_AUTH;
    raw[3] = 0;
    raw[4] = 0;
    raw[5] = 0;
    raw[6] = (unsigned char)(token & 0xFF);
    raw[7] = (unsigned char)((token >> 8) & 0xFF);
    raw[8] = (unsigned char)((token >> 16) & 0xFF);
    raw[9] = (unsigned char)((token >> 24) & 0xFF);
    return finish_frame(out, raw, 4);
}

unsigned char rt_build_player_state(unsigned char *out, unsigned seq,
                                    unsigned char x, unsigned char y,
                                    unsigned char facing,
                                    unsigned char buttons,
                                    unsigned char fire_counter,
                                    unsigned char pickup_counter,
                                    unsigned last_server_seq,
                                    unsigned char pvp_toggle_counter)
{
    unsigned char raw[23];

    raw[1] = RTS_VERSION;
    raw[2] = RTS_PLAYER_STATE;
    raw[3] = 0;
    raw[4] = (unsigned char)(seq & 0xFF);
    raw[5] = (unsigned char)(seq >> 8);
    raw[6] = x;
    raw[7] = y;
    raw[8] = facing;
    raw[9] = buttons;
    raw[10] = fire_counter;
    raw[11] = pickup_counter;
    raw[12] = (unsigned char)(last_server_seq & 0xFF);
    raw[13] = (unsigned char)(last_server_seq >> 8);
    raw[14] = 0; /* rx_drops */
    raw[15] = pvp_toggle_counter;
    return finish_frame(out, raw, 10);
}

unsigned char rt_build_resync_request(unsigned char *out, unsigned seq,
                                      unsigned char origin_x,
                                      unsigned char origin_y,
                                      unsigned char fill_origin_x,
                                      unsigned char fill_origin_y,
                                      unsigned long rows_have,
                                      unsigned char fill_id,
                                      unsigned char flags)
{
    unsigned char raw[17];

    raw[1] = RTS_VERSION;
    raw[2] = RTS_RESYNC_REQUEST;
    raw[3] = 0;
    raw[4] = (unsigned char)(seq & 0xFF);
    raw[5] = (unsigned char)(seq >> 8);
    raw[6] = origin_x;
    raw[7] = origin_y;
    raw[8] = fill_origin_x;
    raw[9] = fill_origin_y;
    raw[10] = (unsigned char)(rows_have & 0xFF);
    raw[11] = (unsigned char)((rows_have >> 8) & 0xFF);
    raw[12] = (unsigned char)((rows_have >> 16) & 0xFF);
    raw[13] = fill_id;
    raw[14] = flags;
    return finish_frame(out, raw, 9);
}

unsigned char rt_build_cache_step_ack(unsigned char *out, unsigned seq,
                                      unsigned revision,
                                      unsigned char origin_x,
                                      unsigned char origin_y)
{
    unsigned char raw[12];

    raw[1] = RTS_VERSION;
    raw[2] = RTS_CACHE_STEP_ACK;
    raw[3] = 0;
    raw[4] = (unsigned char)(seq & 0xFF);
    raw[5] = (unsigned char)(seq >> 8);
    raw[6] = (unsigned char)(revision & 0xFF);
    raw[7] = (unsigned char)(revision >> 8);
    raw[8] = origin_x;
    raw[9] = origin_y;
    return finish_frame(out, raw, 4);
}

unsigned char rt_build_window_commit(unsigned char *out, unsigned seq,
                                     unsigned char fill_id,
                                     unsigned char origin_x,
                                     unsigned char origin_y,
                                     unsigned char map_id,
                                     unsigned char flags)
{
    unsigned char raw[13];

    raw[1] = RTS_VERSION;
    raw[2] = RTS_WINDOW_COMMIT;
    raw[3] = 0;
    raw[4] = (unsigned char)(seq & 0xFF);
    raw[5] = (unsigned char)(seq >> 8);
    raw[6] = fill_id;
    raw[7] = origin_x;
    raw[8] = origin_y;
    raw[9] = map_id;
    raw[10] = flags;
    return finish_frame(out, raw, 5);
}

unsigned char rt_build_map_ready(unsigned char *out, unsigned seq,
                                 unsigned char map_id,
                                 unsigned char origin_x,
                                 unsigned char origin_y)
{
    unsigned char raw[11];

    raw[1] = RTS_VERSION;
    raw[2] = RTS_MAP_READY;
    raw[3] = 0;
    raw[4] = (unsigned char)(seq & 0xFF);
    raw[5] = (unsigned char)(seq >> 8);
    raw[6] = map_id;
    raw[7] = origin_x;
    raw[8] = origin_y;
    return finish_frame(out, raw, 3);
}

unsigned char rt_camera(unsigned char pos, unsigned char span,
                        unsigned char view)
{
    unsigned char half = view / 2;

    if (pos <= half) {
        return 0;
    }
    if (pos - half >= span - view) {
        return span - view;
    }
    return pos - half;
}

unsigned char rt_camera_track(unsigned char cam, unsigned char pos,
                              unsigned char span, unsigned char view,
                              unsigned char margin)
{
    unsigned char max_cam = span - view;
    unsigned char span_far = view - 1 - margin; /* 'far' is a cc65 keyword */
    unsigned char low = pos > span_far ? pos - span_far : 0;
    unsigned char high = pos > margin ? pos - margin : 0;

    if (cam < low) {
        cam = low;
    } else if (cam > high) {
        cam = high;
    }
    /* At the cache edge the camera cannot scroll further, so pos leaves the
       band and simply approaches the screen edge -- the same behaviour the
       centering camera already had there. */
    if (cam > max_cam) {
        cam = max_cam;
    }
    return cam;
}
