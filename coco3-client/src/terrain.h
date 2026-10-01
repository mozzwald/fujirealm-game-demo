#ifndef TERRAIN_H
#define TERRAIN_H

#define BOOTSTRAP_WINDOW_W 32
#define BOOTSTRAP_WINDOW_H 24
#define BOOTSTRAP_TERRAIN_SIZE (BOOTSTRAP_WINDOW_W * BOOTSTRAP_WINDOW_H)

/* Live 32x24 terrain cache: TERRAIN_EDGE strips scroll it one row/column at
 * a time, WINDOW_ROW fills replace it wholesale. Ported from lynx-client's
 * bootstrap.c, whose host tests cover the same logic. */

#define TERRAIN_ALL_ROWS 0x00FFFFFFUL

/* terrain_apply_edge() outcomes. Applied shifts the cache in place; a
 * duplicate (the server's retransmit after a lost CACHE_STEP_ACK) is
 * re-acknowledged without shifting; anything else needs a full resync. */
#define TERRAIN_EDGE_APPLIED 10
#define TERRAIN_EDGE_DUPLICATE 11
#define TERRAIN_EDGE_RESYNC 12

/* terrain_fill_apply_row() outcomes. */
#define TERRAIN_FILL_IGNORED 0
#define TERRAIN_FILL_ROW_APPLIED 20
#define TERRAIN_FILL_DUPLICATE 21
#define TERRAIN_FILL_COMPLETE 22

struct terrain_cache {
    unsigned origin_x;
    unsigned origin_y;
    /* 0 = still at the bootstrap window. The server's first edge is revision
     * 1; the counter wraps 0xFFFF -> 1, never to 0. */
    unsigned revision;
    /* The server never rewinds its revision counter on a resync, so the edge
     * after one may carry any revision: the next adjacent edge is trusted as
     * the new baseline. */
    unsigned char revision_trust_next;
    /* Set when a fill activates; cleared by the matching WINDOW_COMMIT_ACK.
     * The caller re-sends WINDOW_COMMIT while it stays set. */
    unsigned char commit_pending;
    unsigned char commit_fill_id;
    unsigned char tiles[BOOTSTRAP_TERRAIN_SIZE];
};

/* A WINDOW_ROW fill under assembly, kept apart from the cache so a partial
 * fill is never drawn. Its tiles are assembled in TERRAIN_FILL_BLOCK at
 * TERRAIN_FILL_OFS, past the HUD image, to spare low RAM. */
#define TERRAIN_FILL_BLOCK 7
#define TERRAIN_FILL_OFS 0x1D00 /* ends at the block end */

struct terrain_fill {
    unsigned char active;
    unsigned char fill_id;
    unsigned origin_x;
    unsigned origin_y;
    unsigned long rows_have;
};

/* Sets the origin and clears revision state; tiles are left as bootstrap
 * filled them. */
void terrain_init(struct terrain_cache *cache, unsigned origin_x,
                  unsigned origin_y);

signed char terrain_apply_edge(struct terrain_cache *cache,
                               unsigned char origin_x, unsigned char origin_y,
                               unsigned char width, unsigned char height,
                               unsigned revision, const unsigned char *tiles,
                               unsigned char tile_count);

void terrain_fill_init(struct terrain_fill *fill);

/* origin_x/abs_origin_y/row_index/tiles are the WINDOW_ROW wire fields (the
 * row's absolute origin, not the fill's window origin). A fill_id/origin
 * mismatch starts a fresh assembly. */
signed char terrain_fill_apply_row(struct terrain_fill *fill,
                                   unsigned char fill_id,
                                   unsigned char origin_x,
                                   unsigned char abs_origin_y,
                                   unsigned char row_index,
                                   const unsigned char *tiles);

/* Copies a complete fill into the cache, owes a WINDOW_COMMIT, and trusts the
 * next edge's revision. */
void terrain_fill_activate(struct terrain_fill *fill,
                           struct terrain_cache *cache);

unsigned char terrain_commit_ack_matches(const struct terrain_cache *cache,
                                         unsigned char fill_id,
                                         unsigned char origin_x,
                                         unsigned char origin_y);

#endif
