#ifndef HUD_H
#define HUD_H

#include "rt_state.h"

/* The HUD strip's three text lines, laid out like the Atari's: stats (HP
 * hearts, level, gold, PvP kills), the active quest, the last server message.
 * They are drawn into an image in HUD_IMAGE_BLOCK (160-byte rows, HUD_LINES
 * tall) that each renderer copies onto the screen. Block 7 is free on both
 * RAM sizes (gime.c, ram.c); its tail also holds the 128K renderer save
 * (play.c) and the terrain fill buffer (terrain.h). */
#define HUD_IMAGE_BLOCK 7
#define HUD_IMAGE_STRIDE 160

/* Clears the image and draws the initial lines. After gime_init_mode(). */
void hud_init(void);

/* Redraws whatever changed in st since the last call (now = getTimer()).
 * Returns 1 if the image changed. */
unsigned char hud_update(struct rt_state *st, unsigned now);

/* Stats-line walk speed digit. */
void hud_set_walk(unsigned char walk);

/* Stats-line sound marker, where a note (hud_note) does not cover it. */
void hud_set_sound(unsigned char on);

/* Shows a 3-character note at the right end of the stats line for about two
 * seconds. text must stay valid. */
void hud_note(const char *text, unsigned now);

/* Draws s white on black at character cell (col, row) of the playfield
 * mapped by gime_window_playfield(). */
void text_draw(unsigned char col, unsigned char row, const char *s);

/* Redraw renderer: copies the image into the draw buffer's HUD strip, and
 * with both != 0 also into the displayed buffer's. */
void hud_blit(unsigned char both);

/* Copies blocks * 8 bytes. Inside the GFX bracket; blocks != 0. */
void gfx_copy8(unsigned char *dst, const unsigned char *src,
               unsigned char blocks);

#endif
