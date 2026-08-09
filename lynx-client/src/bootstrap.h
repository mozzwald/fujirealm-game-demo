#ifndef FUJIREALM_BOOTSTRAP_H
#define FUJIREALM_BOOTSTRAP_H

#define BF_MAGIC 0xBF
#define BF_VERSION 1
#define BF_WELCOME 0x81
#define BF_WINDOW 0x80

#define BF_MAX_PAYLOAD 108
#define BF_MAX_FRAME (BF_MAX_PAYLOAD + 5)

#define BOOTSTRAP_WINDOW_W 32
#define BOOTSTRAP_WINDOW_H 24
#define BOOTSTRAP_WINDOW_CHUNK_ROWS 3
#define BOOTSTRAP_WINDOW_CHUNKS 8
#define BOOTSTRAP_TERRAIN_SIZE (BOOTSTRAP_WINDOW_W * BOOTSTRAP_WINDOW_H)
#define BOOTSTRAP_ALL_ROWS 0x00FFFFFFUL
#define BOOTSTRAP_WELCOME_FRAME_SIZE 10
#define BOOTSTRAP_WINDOW_FRAME_SIZE 113
#define BOOTSTRAP_HELLO_FRAME_SIZE 12
#define BOOTSTRAP_EXPECTED_BYTES \
    (BOOTSTRAP_WELCOME_FRAME_SIZE + \
     BOOTSTRAP_WINDOW_CHUNKS * BOOTSTRAP_WINDOW_FRAME_SIZE)

#define BF_FEED_ERROR (-1)
#define BF_FEED_NONE 0
#define BF_FEED_PACKET 1

#define BF_ERROR_NONE 0
#define BF_ERROR_VERSION 1
#define BF_ERROR_LENGTH 2
#define BF_ERROR_CHECKSUM 3

#define BOOTSTRAP_IGNORED 0
#define BOOTSTRAP_WELCOME 1
#define BOOTSTRAP_WINDOW 2
#define BOOTSTRAP_COMPLETE 3
#define BOOTSTRAP_ERROR (-1)

#define BOOT_ERROR_NONE 0
#define BOOT_ERROR_WELCOME_LENGTH 1
#define BOOT_ERROR_WELCOME_VERSION 2
#define BOOT_ERROR_WINDOW_SHORT 3
#define BOOT_ERROR_WINDOW_GEOMETRY 4
#define BOOT_ERROR_WINDOW_COUNT 5

/* bootstrap_apply_terrain_edge() outcomes. Applied shifts the active 32x24
 * cache in place; a duplicate re-delivery (the server's go-back-N retransmit
 * after a lost CACHE_STEP_ACK) is re-acknowledged without shifting; anything
 * else (non-adjacent revision/origin, bad geometry) needs a full resync. */
#define BOOTSTRAP_EDGE_APPLIED 10
#define BOOTSTRAP_EDGE_DUPLICATE 11
#define BOOTSTRAP_EDGE_RESYNC 12

/* bootstrap_fill_apply_row() outcomes. */
#define BOOTSTRAP_FILL_IGNORED 0
#define BOOTSTRAP_FILL_ROW_APPLIED 20
#define BOOTSTRAP_FILL_DUPLICATE 21
#define BOOTSTRAP_FILL_COMPLETE 22

struct bf_packet {
    unsigned char type;
    unsigned char payload_len;
    unsigned char payload[BF_MAX_PAYLOAD];
};

struct bf_parser {
    unsigned char frame[BF_MAX_FRAME];
    unsigned char pos;
    unsigned char want;
    unsigned char last_error;
};

struct bootstrap_state {
    unsigned char got_welcome;
    unsigned char player_id;
    unsigned seed;
    unsigned char max_beavers;
    unsigned char protocol_version;
    unsigned tick;
    unsigned origin_x;
    unsigned origin_y;
    unsigned long rows_received;
    unsigned char error_code;
    unsigned char terrain[BOOTSTRAP_TERRAIN_SIZE];
    /* Active terrain-cache revision. 0 means "at the bootstrap window, no
     * TERRAIN_EDGE applied yet"; the server's first edge after bootstrap is
     * always revision 1 (16-bit, wraps 0xFFFF -> 1, never back to 0). */
    unsigned revision;
    /* The server's cache-step revision counter is never rewound by a
     * resync (gap-replay or full fill), so the edge right after one can
     * legitimately arrive with any revision number. Set whenever a resync
     * is requested or a fill activates; the next geometrically-adjacent
     * edge is trusted as the new baseline instead of requiring
     * revision == active_revision + 1. */
    unsigned char revision_trust_next;
    /* Set by bootstrap_fill_activate(); cleared once an incoming
     * WINDOW_COMMIT_ACK matches (see bootstrap_commit_ack_matches()). The
     * caller is responsible for the retry timer and re-sending
     * rt_build_window_commit() while this stays set. */
    unsigned char commit_pending;
    unsigned char commit_fill_id;
};

/* Assembly buffer for an in-progress WINDOW_ROW full-window fill. Kept
 * separate from struct bootstrap_state's active terrain/origin so a
 * partial fill is never visible to rendering or collision. */
struct bootstrap_fill {
    unsigned char active;
    unsigned char fill_id;
    unsigned origin_x;
    unsigned origin_y;
    unsigned long rows_have;
    unsigned char terrain[BOOTSTRAP_TERRAIN_SIZE];
};

void bf_parser_init(struct bf_parser *parser);
signed char bf_parser_feed(struct bf_parser *parser, unsigned char byte,
                           struct bf_packet *packet);
void bootstrap_init(struct bootstrap_state *state);
signed char bootstrap_apply(struct bootstrap_state *state,
                            const struct bf_packet *packet);

/* Apply one TERRAIN_EDGE strip (a decoded struct rt_terrain_edge's fields)
 * to the active cache. width/height/tile_count identify a column
 * (1 x BOOTSTRAP_WINDOW_H) or row (BOOTSTRAP_WINDOW_W x 1) strip; direction
 * is inferred by comparing origin_x/origin_y to the active origin. */
signed char bootstrap_apply_terrain_edge(struct bootstrap_state *state,
                                         unsigned char origin_x,
                                         unsigned char origin_y,
                                         unsigned char width,
                                         unsigned char height,
                                         unsigned revision,
                                         const unsigned char *tiles,
                                         unsigned char tile_count);

void bootstrap_fill_init(struct bootstrap_fill *fill);

/* Apply one WINDOW_ROW. origin_x/abs_origin_y/row_index/tiles are the wire
 * fields as received (absolute row origin, not the fill's window origin --
 * see struct rt_window_row). A fill_id/origin mismatch against whatever is
 * in progress starts a fresh assembly, superseding the old one. */
signed char bootstrap_fill_apply_row(struct bootstrap_fill *fill,
                                     unsigned char fill_id,
                                     unsigned char origin_x,
                                     unsigned char abs_origin_y,
                                     unsigned char row_index,
                                     const unsigned char *tiles);

/* Atomically copy a BOOTSTRAP_FILL_COMPLETE fill into the active cache,
 * mark a WINDOW_COMMIT as owed, and set revision_trust_next (a fresh window
 * has no edge-revision history to continue). Resets fill->active so the
 * buffer is free for the next resync. */
void bootstrap_fill_activate(struct bootstrap_fill *fill,
                             struct bootstrap_state *state);

unsigned char bootstrap_commit_ack_matches(const struct bootstrap_state *state,
                                           unsigned char fill_id,
                                           unsigned char origin_x,
                                           unsigned char origin_y);

#endif
