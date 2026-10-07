#ifndef FUJIREALM_PALM_GFX_H
#define FUJIREALM_PALM_GFX_H

#include "rt_state.h"

/* 160x160: a 20x14 viewport of 8x8 tiles (the Lynx's tile size) over a
 * 48-line HUD of four stdFont lines. Black and white by default; see
 * GFX_DEPTH in gfx.c. */
#define VIEW_COLS 20
#define VIEW_ROWS 14
#define TILE_PX 8
#define VIEW_W (VIEW_COLS * TILE_PX)
#define VIEW_H (VIEW_ROWS * TILE_PX)
#define SCREEN_W 160
#define SCREEN_H 160
#define HUD_Y (VIEW_H + 1)
#define HUD_LINES 4

/* Set up the view (and the screen mode, for greys). 0 on success. */
int gfx_open(void);
void gfx_close(void);
/* Bits per pixel in use: 1 (black and white), 2 (four greys) or 8 (colour). */
unsigned char gfx_depth(void);
/* A map's palette tint (MAP_CHANGE palette_id); only colour uses it. */
void gfx_set_palette(unsigned char palette_id);

/* The live view; see the Amiga client's gfx_render_world. */
void gfx_render_world(const struct rt_state *state, const unsigned char *terrain,
                      unsigned origin_x, unsigned origin_y,
                      unsigned char cam_x, unsigned char cam_y,
                      unsigned char facing, unsigned char anim);

/* Text helpers in screen pixels, black on white. */
void gfx_clear(void);
void gfx_fill(int x, int y, int w, int h, int black);
void gfx_text(int x, int y, const char *text, int bold);
void gfx_text_right(int right, int y, const char *text);
/* Word-wrapped text; returns the y below the last line drawn. */
int gfx_wrap(int x, int y, int width, int max_y, const char *text, unsigned len);
void gfx_frame(int x, int y, int w, int h);

void gfx_hud_frame(void);
/* One HUD line (0..3), cleared to the full width. */
void gfx_hud_line(unsigned char line, const char *text);
/* Lines first..first+count-1 as one word-wrapped block. */
void gfx_hud_wrap(unsigned char first, unsigned char count, const char *text);

/* A sprite at screen pixels, over whatever is there (title screen). */
void gfx_sprite_at(int x, int y, unsigned char sprite);

#endif
