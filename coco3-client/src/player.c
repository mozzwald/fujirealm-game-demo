#include "player.h"
#include "live.h"

/* World limits the server enforces on player steps. */
#define WORLD_MIN 1
#define WORLD_MAX_X 126
#define WORLD_MAX_Y 94
#define VIEW_MAX_X (128 - VIEW_COLS)
#define VIEW_MAX_Y (96 - VIEW_ROWS)

/* Viewport scroll margins, in tiles from the viewport's top-left (Atari:
 * 6/13 across a 20-wide view, 4/6 down a 10-high one). */
#define SCROLL_LEFT_EDGE 6
#define SCROLL_RIGHT_EDGE 13
#define SCROLL_TOP_EDGE 5
#define SCROLL_BOTTOM_EDGE 7

unsigned char player_x;
unsigned char player_y;
unsigned view_x;
unsigned view_y;
unsigned char player_send_pending;
unsigned char player_hit_timer = 0;
unsigned char player_anim = 0;

static unsigned char predicted_pending;
static unsigned predicted_seq = 0;
static unsigned last_state_seq = 0;
static unsigned char corr_pending;
static unsigned char corr_x;
static unsigned char corr_y;

/* Indexed by RTS_FACE_*. */
static const signed char face_dx[8] = { 0, 0, -1, 1, -1, 1, -1, 1 };
static const signed char face_dy[8] = { -1, 1, 0, 0, -1, -1, 1, 1 };

/* The server's PLAYER_BLOCKING tile set (world.py). The Atari's list omits 9
 * and 40-43; predicting into those is a guaranteed snap-back. */
static unsigned char tile_blocks(unsigned char tile)
{
    switch (tile) {
    case 2:  /* tree */
    case 4:  /* damaged tree */
    case 6:  /* bullet */
    case 7:  /* border */
    case 8:  /* beaver */
    case 9:  /* snake */
    case 11: /* water */
    case 12: /* building */
    case 16: /* cave wall */
    case 37: /* farmer */
    case 38: /* goblin npc */
    case 40: /* the Dam Below cast */
    case 41:
    case 42:
    case 43:
        return 1;
    default:
        return 0;
    }
}

static unsigned char entity_at(unsigned char x, unsigned char y)
{
    unsigned char i;

    for (i = 0; i < live_game.beaver_count; ++i) {
        if (live_game.beavers[i].hp != 0 && live_game.beavers[i].x == x &&
            live_game.beavers[i].y == y) {
            return 1;
        }
    }
    for (i = 0; i < live_game.remote_count; ++i) {
        if ((live_game.remotes[i].state & RTS_REMOTE_ALIVE) != 0 &&
            live_game.remotes[i].x == x && live_game.remotes[i].y == y) {
            return 1;
        }
    }
    return 0;
}

/* Outside the cached window counts as blocked: the server slides the window
 * ahead of the player, so a legal step is always inside it. */
static unsigned char cell_blocked(unsigned char x, unsigned char y)
{
    unsigned rx = (unsigned)x - live_terrain.origin_x;
    unsigned ry = (unsigned)y - live_terrain.origin_y;

    if (rx >= RTS_WINDOW_W || ry >= RTS_WINDOW_H) {
        return 1;
    }
    if (tile_blocks(live_terrain.tiles[ry * RTS_WINDOW_W + rx])) {
        return 1;
    }
    return entity_at(x, y);
}

/* Shot line-of-sight blockers (Atari bullet_target_hits_terrain): a shot
 * flies over the bullet tile and over NPCs a player cannot walk through. */
static unsigned char shot_tile_blocks(unsigned char tile)
{
    switch (tile) {
    case 2:  /* tree */
    case 4:  /* damaged tree */
    case 7:  /* border */
    case 8:  /* beaver */
    case 11: /* water */
    case 12: /* building */
    case 16: /* cave wall */
        return 1;
    default:
        return 0;
    }
}

/* A cell outside the cache blocks: we cannot know what is there. */
static unsigned char shot_cell_blocks(unsigned char x, unsigned char y)
{
    unsigned rx = (unsigned)x - live_terrain.origin_x;
    unsigned ry = (unsigned)y - live_terrain.origin_y;

    if (rx >= RTS_WINDOW_W || ry >= RTS_WINDOW_H) {
        return 1;
    }
    return shot_tile_blocks(live_terrain.tiles[ry * RTS_WINDOW_W + rx]);
}

/* Advances a shot one tile. Returns 0 if it dies here: bad direction, world
 * edge, a blocker ahead, or a diagonal squeezing between two blockers. */
static unsigned char shot_step(unsigned char *x, unsigned char *y,
                               unsigned char dir)
{
    int nx;
    int ny;

    if (dir >= RTS_FACE_COUNT) {
        return 0;
    }
    nx = (int)*x + face_dx[dir];
    ny = (int)*y + face_dy[dir];
    if (dir >= RTS_FACE_FIRST_DIAGONAL &&
        (shot_cell_blocks((unsigned char)nx, *y) ||
         shot_cell_blocks(*x, (unsigned char)ny))) {
        return 0;
    }
    if (nx < WORLD_MIN || nx >= WORLD_MAX_X + 1 || ny < WORLD_MIN ||
        ny >= WORLD_MAX_Y + 1) {
        return 0;
    }
    if (shot_cell_blocks((unsigned char)nx, (unsigned char)ny)) {
        return 0;
    }
    *x = (unsigned char)nx;
    *y = (unsigned char)ny;
    return 1;
}

void player_tracers_step(void)
{
    unsigned char i;
    struct rt_tracer *t;
    unsigned char nx;
    unsigned char ny;

    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        t = &live_game.tracers[i];
        if (!t->active) {
            continue;
        }
        nx = t->x;
        ny = t->y;
        if (t->steps >= RTS_BULLET_RANGE || !shot_step(&nx, &ny, t->dir)) {
            t->active = 0;
            continue;
        }
        /* A shot halts on contact with an actor rather than overlapping it. */
        if ((nx == player_x && ny == player_y) || entity_at(nx, ny)) {
            t->active = 0;
            continue;
        }
        t->x = nx;
        t->y = ny;
        ++t->steps;
    }
}

void player_fire(unsigned char dir)
{
    rt_spawn_tracer(&live_game, player_x, player_y, dir);
    player_tracers_step();
}

unsigned char player_try_move(unsigned char dir)
{
    signed char dx = face_dx[dir];
    signed char dy = face_dy[dir];
    unsigned char nx, ny;

    if ((dx < 0 && player_x <= WORLD_MIN) ||
        (dx > 0 && player_x >= WORLD_MAX_X) ||
        (dy < 0 && player_y <= WORLD_MIN) ||
        (dy > 0 && player_y >= WORLD_MAX_Y)) {
        return 0;
    }
    nx = (unsigned char)(player_x + dx);
    ny = (unsigned char)(player_y + dy);
    if (cell_blocked(nx, ny)) {
        return 0;
    }
    /* A diagonal may not cut a closed corner: both side cells must be open. */
    if (dx != 0 && dy != 0 &&
        (cell_blocked(nx, player_y) || cell_blocked(player_x, ny))) {
        return 0;
    }

    player_x = nx;
    player_y = ny;
    player_anim ^= 1;
    corr_pending = 0;
    player_send_pending = 1;
    return 1;
}

void player_note_sent(unsigned seq)
{
    last_state_seq = seq;
    if (player_send_pending) {
        player_send_pending = 0;
        predicted_pending = 1;
        predicted_seq = seq;
    }
}

/* Ready to take a correction: no move in flight, or the server has already
 * processed it (wrap-safe 16-bit compare). */
static unsigned char echo_ready(void)
{
    if (!predicted_pending) {
        return 1;
    }
    return (int)(live_game.echo_client_seq - predicted_seq) >= 0;
}

static unsigned char off_by_two(unsigned char a, unsigned char b)
{
    return (a > b ? a - b : b - a) >= 2;
}

static void queue_or_apply_correction(void)
{
    unsigned char sx = live_game.player_x;
    unsigned char sy = live_game.player_y;

    if (off_by_two(sx, player_x) || off_by_two(sy, player_y)) {
        corr_pending = 0;
        predicted_pending = 0;
        player_x = sx;
        player_y = sy;
        return;
    }
    if (!echo_ready()) {
        corr_pending = 0;
        return;
    }
    corr_x = sx;
    corr_y = sy;
    corr_pending = 1;
}

void player_on_world_state(void)
{
    if (live_game.correction_flags != 0) {
        queue_or_apply_correction();
    } else if (live_game.echo_client_seq == last_state_seq) {
        corr_pending = 0;
        player_x = live_game.player_x;
        player_y = live_game.player_y;
    }
}

void player_apply_correction_step(void)
{
    if (!corr_pending) {
        return;
    }
    if (player_x != corr_x) {
        player_x = (unsigned char)(player_x + (player_x < corr_x ? 1 : -1));
    } else if (player_y != corr_y) {
        player_y = (unsigned char)(player_y + (player_y < corr_y ? 1 : -1));
    } else {
        corr_pending = 0;
        predicted_pending = 0;
    }
}

static unsigned clamp_view(unsigned v, unsigned lo, unsigned span)
{
    if (v < lo) {
        return lo;
    }
    if (v > lo + span) {
        return lo + span;
    }
    return v;
}

void player_update_view(void)
{
    unsigned rel;

    if (player_x < view_x || (unsigned)(player_x - view_x) < SCROLL_LEFT_EDGE) {
        if (view_x != 0) {
            --view_x;
        }
    } else {
        rel = (unsigned)player_x - view_x;
        if (rel > SCROLL_RIGHT_EDGE && view_x < VIEW_MAX_X) {
            ++view_x;
        }
    }

    if (player_y < view_y || (unsigned)(player_y - view_y) < SCROLL_TOP_EDGE) {
        if (view_y != 0) {
            --view_y;
        }
    } else {
        rel = (unsigned)player_y - view_y;
        if (rel > SCROLL_BOTTOM_EDGE && view_y < VIEW_MAX_Y) {
            ++view_y;
        }
    }

    view_x = clamp_view(view_x, live_terrain.origin_x, RTS_WINDOW_W - VIEW_COLS);
    view_y = clamp_view(view_y, live_terrain.origin_y, RTS_WINDOW_H - VIEW_ROWS);
}

void player_snap(unsigned char x, unsigned char y)
{
    player_x = x;
    player_y = y;
    corr_pending = 0;
    predicted_pending = 0;
    player_send_pending = 0;
    view_x = clamp_view(x >= VIEW_COLS / 2 ? x - VIEW_COLS / 2 : 0,
                        live_terrain.origin_x, RTS_WINDOW_W - VIEW_COLS);
    view_y = clamp_view(y >= VIEW_ROWS / 2 ? y - VIEW_ROWS / 2 : 0,
                        live_terrain.origin_y, RTS_WINDOW_H - VIEW_ROWS);
}
