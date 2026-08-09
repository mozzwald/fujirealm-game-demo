#include "predict.h"

void predict_init(struct predict_state *ps, unsigned char x, unsigned char y)
{
    ps->x = x;
    ps->y = y;
    ps->count = 0;
}

const signed char predict_shot_dx[RTS_FACE_COUNT] = { 0, 0, -1, 1, -1, 1, -1, 1 };
const signed char predict_shot_dy[RTS_FACE_COUNT] = { -1, 1, 0, 0, -1, -1, 1, 1 };

unsigned char predict_tile_blocks(unsigned char tile)
{
    return tile == PREDICT_TILE_TREE_FULL || tile == PREDICT_TILE_TREE_DAMAGED ||
           tile == PREDICT_TILE_BULLET || tile == PREDICT_TILE_BORDER ||
           tile == PREDICT_TILE_BEAVER || tile == PREDICT_TILE_SNAKE ||
           tile == PREDICT_TILE_WATER || tile == PREDICT_TILE_BUILDING ||
           tile == PREDICT_TILE_CAVE_WALL || tile == PREDICT_TILE_FARMER ||
           tile == PREDICT_TILE_GOBLIN_NPC || tile == PREDICT_TILE_DANIEL ||
           tile == PREDICT_TILE_WILHELM || tile == PREDICT_TILE_LUCIAN ||
           tile == PREDICT_TILE_NERISSA;
}

unsigned char predict_shot_blocks(unsigned char tile)
{
    return tile == PREDICT_TILE_TREE_FULL || tile == PREDICT_TILE_TREE_DAMAGED ||
           tile == PREDICT_TILE_BORDER || tile == PREDICT_TILE_BEAVER ||
           tile == PREDICT_TILE_WATER || tile == PREDICT_TILE_BUILDING ||
           tile == PREDICT_TILE_CAVE_WALL;
}

/* Shot line-of-sight test for one absolute cell. A cell outside the terrain
 * cache is treated as blocking: we cannot know what is there, and letting a
 * tracer fly through unknown ground looks worse than stopping it short. */
static unsigned char shot_cell_blocks(unsigned char x, unsigned char y,
                                      const unsigned char *terrain,
                                      unsigned origin_x, unsigned origin_y)
{
    unsigned rel_x;
    unsigned rel_y;

    if ((unsigned)x < origin_x || (unsigned)y < origin_y) {
        return 1;
    }
    rel_x = (unsigned)x - origin_x;
    rel_y = (unsigned)y - origin_y;
    if (rel_x >= RTS_WINDOW_W || rel_y >= RTS_WINDOW_H) {
        return 1;
    }
    return predict_shot_blocks(terrain[rel_y * RTS_WINDOW_W + rel_x]);
}

unsigned char predict_shot_step(unsigned char *x, unsigned char *y,
                                unsigned char dir,
                                const unsigned char *terrain,
                                unsigned origin_x, unsigned origin_y)
{
    int nx;
    int ny;

    if (dir >= RTS_FACE_COUNT) {
        return 0;
    }
    nx = (int)*x + predict_shot_dx[dir];
    ny = (int)*y + predict_shot_dy[dir];

    /* Closed corner: a diagonal cannot squeeze between two blockers. */
    if (dir >= RTS_FACE_FIRST_DIAGONAL &&
        (shot_cell_blocks((unsigned char)nx, *y, terrain, origin_x, origin_y) ||
         shot_cell_blocks(*x, (unsigned char)ny, terrain, origin_x, origin_y))) {
        return 0;
    }
    if (nx < PREDICT_SHOT_MIN || nx >= PREDICT_SHOT_LIMIT_X ||
        ny < PREDICT_SHOT_MIN || ny >= PREDICT_SHOT_LIMIT_Y) {
        return 0;
    }
    if (shot_cell_blocks((unsigned char)nx, (unsigned char)ny, terrain,
                         origin_x, origin_y)) {
        return 0;
    }
    *x = (unsigned char)nx;
    *y = (unsigned char)ny;
    return 1;
}

unsigned char predict_can_move(unsigned char x, unsigned char y,
                               const unsigned char *terrain,
                               unsigned origin_x, unsigned origin_y,
                               const struct rt_state *world)
{
    unsigned char i;
    unsigned rel_x;
    unsigned rel_y;

    if ((unsigned)x < origin_x || (unsigned)y < origin_y) {
        return 0;
    }
    rel_x = (unsigned)x - origin_x;
    rel_y = (unsigned)y - origin_y;
    if (rel_x >= RTS_WINDOW_W || rel_y >= RTS_WINDOW_H ||
        predict_tile_blocks(terrain[rel_y * RTS_WINDOW_W + rel_x])) {
        return 0;
    }
    for (i = 0; i < world->beaver_count; ++i) {
        if (world->beavers[i].hp != 0 && world->beavers[i].x == x &&
            world->beavers[i].y == y) {
            return 0;
        }
    }
    for (i = 0; i < world->remote_count; ++i) {
        if ((world->remotes[i].state & RTS_REMOTE_ALIVE) != 0 &&
            world->remotes[i].x == x && world->remotes[i].y == y) {
            return 0;
        }
    }
    return 1;
}

unsigned char predict_can_step(unsigned char fx, unsigned char fy,
                               unsigned char tx, unsigned char ty,
                               const unsigned char *terrain,
                               unsigned origin_x, unsigned origin_y,
                               const struct rt_state *world)
{
    if (!predict_can_move(tx, ty, terrain, origin_x, origin_y, world)) {
        return 0;
    }
    if (tx == fx || ty == fy) {
        return 1;
    }
    /* Diagonal: the server applies the same full entry test to both side
       cells, so we do too rather than checking terrain alone. */
    return predict_can_move(tx, fy, terrain, origin_x, origin_y, world) &&
           predict_can_move(fx, ty, terrain, origin_x, origin_y, world);
}

unsigned char predict_move(struct predict_state *ps, unsigned seq,
                           unsigned char x, unsigned char y,
                           const unsigned char *terrain,
                           unsigned origin_x, unsigned origin_y,
                           const struct rt_state *world)
{
    if (!predict_can_step(ps->x, ps->y, x, y, terrain, origin_x, origin_y,
                          world)) {
        return 0;
    }
    if (ps->count >= PREDICT_MAX_PENDING) {
        return 0;
    }
    ps->pending[ps->count].seq = seq;
    ps->pending[ps->count].x = x;
    ps->pending[ps->count].y = y;
    ++ps->count;
    ps->x = x;
    ps->y = y;
    return 1;
}

unsigned char predict_reconcile(struct predict_state *ps,
                                unsigned char server_x, unsigned char server_y,
                                unsigned char correction_flags,
                                unsigned echo_client_seq,
                                const unsigned char *terrain,
                                unsigned origin_x, unsigned origin_y,
                                const struct rt_state *world)
{
    unsigned char i;
    unsigned char keep;
    unsigned char x;
    unsigned char y;

    if (correction_flags != 0) {
        ps->count = 0;
        ps->x = server_x;
        ps->y = server_y;
        return 1;
    }

    keep = 0;
    for (i = 0; i < ps->count; ++i) {
        unsigned diff = (ps->pending[i].seq - echo_client_seq) & 0xFFFFU;

        if (diff != 0 && diff < 0x8000U) {
            ps->pending[keep++] = ps->pending[i];
        }
    }
    ps->count = keep;

    x = server_x;
    y = server_y;
    for (i = 0; i < ps->count; ++i) {
        /* Replay from where the previous step left us, so a diagonal in the
           queue is re-checked against the corner rule and not just its
           destination cell. */
        if (!predict_can_step(x, y, ps->pending[i].x, ps->pending[i].y, terrain,
                              origin_x, origin_y, world)) {
            ps->count = 0;
            ps->x = server_x;
            ps->y = server_y;
            return 1;
        }
        x = ps->pending[i].x;
        y = ps->pending[i].y;
    }
    ps->x = x;
    ps->y = y;
    return 0;
}
