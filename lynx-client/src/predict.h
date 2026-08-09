#ifndef FUJIREALM_PREDICT_H
#define FUJIREALM_PREDICT_H

#include "rt_state.h"

/* Bounded local-movement prediction (Phase 7). The client shows a move the
 * instant input validates locally, then reconciles against each
 * authoritative WORLD_STATE by dropping acknowledged moves and replaying the
 * rest -- instead of the Phase 6 behavior of unconditionally overwriting
 * the displayed position with every server update. */

#define PREDICT_MAX_PENDING 8

/* These mirror the server's PLAYER_BLOCKING set (world.py) plus the static-NPC
 * tiles it blocks as entities. Values are the shared tile ids, so they must
 * match world.py exactly -- CAVE_ENTRANCE (13) is walkable (it is the door that
 * triggers the map change); the solid cave wall is 16. Tile 9 was Beaver Hurt
 * and is now Snake art, but it is still in the server's blocking set. */
#define PREDICT_TILE_TREE_FULL 2
#define PREDICT_TILE_TREE_DAMAGED 4
#define PREDICT_TILE_BULLET 6
#define PREDICT_TILE_BORDER 7
#define PREDICT_TILE_BEAVER 8
#define PREDICT_TILE_SNAKE 9
#define PREDICT_TILE_WATER 11
#define PREDICT_TILE_BUILDING 12
#define PREDICT_TILE_CAVE_WALL 16
#define PREDICT_TILE_FARMER 37
#define PREDICT_TILE_GOBLIN_NPC 38
/* The Dam Below cast, stamped into the terrain stream as a static overlay
 * (server NPC_STATIC_TILES) rather than sent as entities. */
#define PREDICT_TILE_DANIEL 40
#define PREDICT_TILE_WILHELM 41
#define PREDICT_TILE_LUCIAN 42
#define PREDICT_TILE_NERISSA 43

/* Shots step one tile at a time in one of the eight facings; index these by
 * an RTS_FACE_* code. Diagonals are not Euclidean-corrected, so a diagonal
 * shot reaches PREDICT_SHOT_RANGE columns *and* rows, matching the Atari. */
extern const signed char predict_shot_dx[RTS_FACE_COUNT];
extern const signed char predict_shot_dy[RTS_FACE_COUNT];
#define PREDICT_SHOT_RANGE RTS_BULLET_RANGE
/* World edge limits the server enforces on a shot: 1 <= x < 127, 1 <= y < 95. */
#define PREDICT_SHOT_MIN 1
#define PREDICT_SHOT_LIMIT_X 127
#define PREDICT_SHOT_LIMIT_Y 95

struct predict_move {
    unsigned seq;
    unsigned char x;
    unsigned char y;
};

struct predict_state {
    unsigned char x;
    unsigned char y;
    unsigned char count;
    struct predict_move pending[PREDICT_MAX_PENDING];
};

void predict_init(struct predict_state *ps, unsigned char x, unsigned char y);

unsigned char predict_tile_blocks(unsigned char tile);

/* Line-of-sight blockers for a shot, which are not the same set as movement:
 * a shot passes over the bullet tile and the static NPCs a player cannot walk
 * through. Mirrors bullet_target_hits_terrain (fujirealm.asm:7064). */
unsigned char predict_shot_blocks(unsigned char tile);

/* True if (x,y) is inside the active terrain window, walkable, and not
 * occupied by a live beaver or remote player. terrain/origin are the active
 * BOOTSTRAP_WINDOW_W x BOOTSTRAP_WINDOW_H cache (see bootstrap.h). */
unsigned char predict_can_move(unsigned char x, unsigned char y,
                               const unsigned char *terrain,
                               unsigned origin_x, unsigned origin_y,
                               const struct rt_state *world);

/* True if a step from (fx,fy) to (tx,ty) is legal. Identical to
 * predict_can_move for a cardinal step; for a diagonal it additionally
 * requires BOTH orthogonal side cells to be enterable, so the player cannot
 * cut a closed corner. Mirrors _player_destination_allowed (game.py:1425) --
 * predicting a corner cut the server refuses is a guaranteed snap-back. */
unsigned char predict_can_step(unsigned char fx, unsigned char fy,
                               unsigned char tx, unsigned char ty,
                               const unsigned char *terrain,
                               unsigned origin_x, unsigned origin_y,
                               const struct rt_state *world);

/* Advance a shot one tile in dir. Returns 1 with the position moved, or 0 if
 * the shot dies here: dir out of range, a blocker at the destination, a closed
 * corner on a diagonal, or the world edge. Range is the caller's to count.
 * The order of these checks matches shot_step_target (fujirealm.asm:10932),
 * which decides whether a shot fizzles on the wall or one tile short of it. */
unsigned char predict_shot_step(unsigned char *x, unsigned char *y,
                                unsigned char dir,
                                const unsigned char *terrain,
                                unsigned origin_x, unsigned origin_y);

/* Validate (x,y) and, if legal, record it under client sequence seq and
 * update ps->x/y. Returns 1 if applied (caller should send PLAYER_STATE
 * with ps->x/y under seq), 0 if illegal or the pending queue is full.
 * A full queue is backpressure, not an error: the queue is left intact so
 * replay still works and movement simply stalls until a WORLD_STATE drains
 * an entry. (Clearing it here instead would discard still-valid predicted
 * moves and make the next reconcile snap the player backward -- the
 * visible "pause then jump forward" seen on hardware.) The server advances
 * echo_client_seq for any newer PLAYER_STATE whether or not it accepts the
 * move, so a live link always drains this queue. */
unsigned char predict_move(struct predict_state *ps, unsigned seq,
                           unsigned char x, unsigned char y,
                           const unsigned char *terrain,
                           unsigned origin_x, unsigned origin_y,
                           const struct rt_state *world);

/* Reconcile against one authoritative WORLD_STATE. Drops pending moves at
 * or before echo_client_seq (wrap-safe 16-bit compare), then replays the
 * rest from (server_x,server_y) against the current cache/entities.
 * correction_flags != 0 (rejected input, respawn/death) or an impossible
 * replay step forces a hard snap: pending is cleared and ps->x/y becomes
 * the server position. Returns 1 on hard snap, 0 on a clean reconcile. */
unsigned char predict_reconcile(struct predict_state *ps,
                                unsigned char server_x, unsigned char server_y,
                                unsigned char correction_flags,
                                unsigned echo_client_seq,
                                const unsigned char *terrain,
                                unsigned origin_x, unsigned origin_y,
                                const struct rt_state *world);

#endif
