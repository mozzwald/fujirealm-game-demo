#ifndef TILES_H
#define TILES_H

#include "rt_state.h"
#include "gime.h"

#define TILE_ROW_BYTES ((unsigned)TILE_H * BYTES_PER_ROW)

/* Items, creatures, other players, the local player and shots in view. */
#define MAX_SPRITES 32

struct sprite {
    unsigned char x;
    unsigned char y;
    unsigned char img; /* art image number (art.h) */
};

/* Creature animation phase (0 or 1), set by the game loop. */
extern unsigned char sprite_anim;

/* This frame's sprites, in drawing order, and the previous frame's. */
extern struct sprite spr_next[MAX_SPRITES];
extern unsigned char spr_next_n;
extern struct sprite spr_prev[MAX_SPRITES];
extern unsigned char spr_prev_n;

/* Moves spr_next to spr_prev and rebuilds it with what is in the view whose
 * top-left is world (vx, vy); (px, py) and facing are the local player's.
 * Returns 1 if it changed. */
unsigned char sprites_update(const struct rt_state *st, unsigned vx,
                             unsigned vy, unsigned char px, unsigned char py,
                             unsigned char facing);

/* Cells a renderer must repaint. The caller zeroes dirty_n. */
#define MAX_DIRTY 24
extern unsigned char dirty_x[MAX_DIRTY];
extern unsigned char dirty_y[MAX_DIRTY];
extern unsigned char dirty_n;

/* Adds cell (x, y) once. Returns 0 when the list is full. */
unsigned char dirty_add(unsigned char x, unsigned char y);

/* Adds the cells where the sprites in was differ from spr_next. Returns 0
 * when the list is full. */
unsigned char dirty_sprites(const struct sprite *was, unsigned char nwas);

/* The above are in sprites.c, the rest in redraw.c (game only). */

/* Copies a 16x16 art image (8-byte rows) to dst, rows stride bytes apart.
 * Inside the GFX bracket. */
void copy_tile(unsigned char *dst, const unsigned char *src, unsigned stride);

/* As copy_tile, but color 0 pixels leave dst as it was. */
void draw_sprite(unsigned char *dst, const unsigned char *src, unsigned stride);

/* draw_sprite of sprite image img from the art mapped at window address art,
 * in the other-player colors when img has ART_RECOLOR. */
void put_sprite(unsigned char *dst, const unsigned char *art, unsigned char img,
                unsigned stride);

/* Draws the live playfield: a PLAYFIELD_COLS x PLAYFIELD_ROWS viewport whose
 * top-left is (cam_x, cam_y) inside the terrain cache (origin_x/origin_y
 * are the cache's world origin) from the art block, with spr_next. While the
 * view stays put, only cells whose sprites or terrain (st's changed cells)
 * changed are redrawn; full != 0 redraws everything. */
void draw_world(const unsigned char *terrain, unsigned origin_x,
                unsigned origin_y, unsigned char cam_x, unsigned char cam_y,
                const struct rt_state *st, unsigned char full);

#endif
