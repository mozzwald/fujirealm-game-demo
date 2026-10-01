#include "tiles.h"
#include "player.h"
#include "art.h"
#include <cmoc.h>

unsigned char sprite_anim = 0;
struct sprite spr_next[MAX_SPRITES];
unsigned char spr_next_n = 0;
struct sprite spr_prev[MAX_SPRITES];
unsigned char spr_prev_n = 0;
unsigned char dirty_x[MAX_DIRTY];
unsigned char dirty_y[MAX_DIRTY];
unsigned char dirty_n = 0;

/* Species (rt_state.h RTS_KIND_*) -> entity image; kind_alt is the second
 * animation frame, 0 for none. The Lynx client's enemy_art tables. */
static const unsigned char kind_image[RTS_KIND_MAX + 1] = {
    0, 0, 1, 5, 3, 2, 7, 8, 8
};
static const unsigned char kind_alt[RTS_KIND_MAX + 1] = {
    0, 0, 0, 6, 4, 0, 0, 0, 9
};
/* Facing -> player frame (front 0, right 2, left 4, back 6); +1 is the walk
 * frame. No diagonal art: diagonals face right when odd, left when even
 * (Atari select_remote_facing_base). */
static const unsigned char facing_frame[RTS_FACE_COUNT] = {
    6, 0, 4, 2, 4, 2, 4, 2
};

static unsigned sp_vx;
static unsigned sp_vy;

static void add_sprite(unsigned char x, unsigned char y, unsigned char img)
{
    struct sprite *s;

    if ((unsigned)x - sp_vx >= PLAYFIELD_COLS ||
        (unsigned)y - sp_vy >= PLAYFIELD_ROWS || spr_next_n >= MAX_SPRITES) {
        return;
    }
    s = &spr_next[spr_next_n++];
    s->x = x;
    s->y = y;
    s->img = img;
}

unsigned char sprites_update(const struct rt_state *st, unsigned vx,
                             unsigned vy, unsigned char px, unsigned char py,
                             unsigned char facing)
{
    unsigned char i;
    unsigned char k;
    unsigned char img;

    memcpy(spr_prev, spr_next, sizeof(struct sprite) * spr_next_n);
    spr_prev_n = spr_next_n;
    spr_next_n = 0;
    sp_vx = vx;
    sp_vy = vy;
    /* Items lie on the ground, under whatever stands on them. */
    for (i = 0; i < st->item_count; ++i) {
        k = rt_item_art_index(st->items[i].item_id);
        if (k != RTS_ART_ITEM_NONE) {
            add_sprite(st->items[i].x, st->items[i].y,
                       (unsigned char)(ART_FIRST_ENTITY + ART_ENT_BULLET + k));
        }
    }
    for (i = 0; i < st->beaver_count; ++i) {
        if (st->beavers[i].hp != 0 && !(st->beavers[i].hit_timer & 1)) {
            k = st->beavers[i].kind;
            if (k > RTS_KIND_MAX) {
                k = RTS_KIND_BEAVER;
            }
            img = kind_image[k];
            if (sprite_anim && kind_alt[k] != 0) {
                img = kind_alt[k];
            }
            add_sprite(st->beavers[i].x, st->beavers[i].y,
                       (unsigned char)(ART_FIRST_ENTITY + img));
        }
    }
    for (i = 0; i < st->remote_count; ++i) {
        if (st->remotes[i].state & RTS_REMOTE_ALIVE) {
            add_sprite(st->remotes[i].x, st->remotes[i].y,
                       (unsigned char)(ART_RECOLOR | (ART_FIRST_PLAYER +
                                       facing_frame[st->remotes[i].facing & 7] +
                                       (st->remotes[i].anim & 1))));
        }
    }
    if (st->world_seen && !(player_hit_timer & 1)) {
        add_sprite(px, py,
                   (unsigned char)(ART_FIRST_PLAYER + facing_frame[facing & 7] +
                                   (player_anim & 1)));
    }
    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        if (st->tracers[i].active) {
            add_sprite(st->tracers[i].x, st->tracers[i].y,
                       ART_FIRST_ENTITY + ART_ENT_BULLET);
        }
    }
    return spr_next_n != spr_prev_n ||
           memcmp(spr_next, spr_prev, sizeof(struct sprite) * spr_next_n) != 0;
}

unsigned char dirty_add(unsigned char x, unsigned char y)
{
    unsigned char i;

    for (i = 0; i < dirty_n; ++i) {
        if (dirty_x[i] == x && dirty_y[i] == y) {
            return 1;
        }
    }
    if (dirty_n == MAX_DIRTY) {
        return 0;
    }
    dirty_x[dirty_n] = x;
    dirty_y[dirty_n] = y;
    ++dirty_n;
    return 1;
}

/* Adds the cells of a's sprites that b lacks. */
static unsigned char add_missing(const struct sprite *a, unsigned char na,
                                 const struct sprite *b, unsigned char nb)
{
    unsigned char i;
    unsigned char j;

    for (i = 0; i < na; ++i, ++a) {
        for (j = 0; j < nb; ++j) {
            if (b[j].x == a->x && b[j].y == a->y && b[j].img == a->img) {
                break;
            }
        }
        if (j == nb && !dirty_add(a->x, a->y)) {
            return 0;
        }
    }
    return 1;
}

unsigned char dirty_sprites(const struct sprite *was, unsigned char nwas)
{
    return add_missing(was, nwas, spr_next, spr_next_n) &&
           add_missing(spr_next, spr_next_n, was, nwas);
}
