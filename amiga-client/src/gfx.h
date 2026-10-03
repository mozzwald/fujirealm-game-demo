#ifndef FUJIREALM_AMIGA_GFX_H
#define FUJIREALM_AMIGA_GFX_H

#include "rt_state.h"

/* 320x200 lores, 16 colours: a 20x10 viewport of 16x16 tiles (the Lynx
 * client's view, at twice the scale) over a 40-line HUD. Text uses the ROM
 * topaz 8 font on a 40x25 character grid. */
#define VIEW_COLS 20
#define VIEW_ROWS 10
#define TILE_PX 16
#define VIEW_W (VIEW_COLS * TILE_PX)
#define VIEW_H (VIEW_ROWS * TILE_PX)
#define TEXT_COLS 40
#define TEXT_ROWS 25
#define HUD_ROW 20              /* first text row below the viewport */

/* Workbench-1.3-style pens in the art palette. */
#define PEN_BLACK 0
#define PEN_NAVY 8
#define PEN_BLUE 9
#define PEN_SKY 10
#define PEN_GREY 11
#define PEN_RED 13
#define PEN_GOLD 14
#define PEN_WHITE 15

struct Window;

int gfx_open(void);             /* 0 on success */
void gfx_close(void);
struct Window *gfx_window(void);
void gfx_set_palette(unsigned char palette_id);

/* Whole-screen text drawing, for boot, name entry and dialogue. */
void gfx_clear(unsigned char pen);
void gfx_fill_rows(unsigned char row, unsigned char count, unsigned char pen);
void gfx_text(unsigned char col, unsigned char row, unsigned char ink,
              unsigned char paper, const char *text, unsigned char len);

/* The live view. terrain/origin describe the 32x24 window cache; cam is the
 * viewport's offset inside it. repaint_terrain forces all 200 cells to be
 * redrawn (camera/origin moved, or a cell changed); otherwise the retained
 * terrain buffer is reused and only the entities are recomposited. */
void gfx_render_world(const struct rt_state *state, const unsigned char *terrain,
                      unsigned origin_x, unsigned origin_y,
                      unsigned char cam_x, unsigned char cam_y,
                      unsigned char facing, unsigned char anim,
                      unsigned char repaint_terrain);

/* One HUD text line (0..3) below the viewport, padded to the full width. */
void gfx_hud_line(unsigned char line, unsigned char ink, const char *text);
void gfx_hud_frame(void);

/* Splash screen drawing: 8x8 tile cells on the 40x25 grid, masked sprites
 * at pixel positions, and one palette entry (0x0RGB) for colour cycling. */
void gfx_cell8(unsigned char col, unsigned char row, unsigned char tile);
void gfx_sprite_at(int x, int y, unsigned char sprite);
void gfx_set_color(unsigned char pen, unsigned short rgb4);

#endif
