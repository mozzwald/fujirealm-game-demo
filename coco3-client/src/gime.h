#ifndef GIME_H
#define GIME_H

#include <coco.h>

/* 320x225x16, 16x16 tiles: 20x12 playfield (320x192) + 33-line HUD strip.
 * Both share one palette. */
#define TILE_W 16
#define TILE_H 16
#define PLAYFIELD_COLS 20
#define PLAYFIELD_ROWS 12
#define PLAYFIELD_LINES 192
#define HUD_LINES 33
#define SCREEN_LINES (PLAYFIELD_LINES + HUD_LINES)
#define BYTES_PER_ROW 160
#define SCREEN_BYTES ((unsigned int)BYTES_PER_ROW * SCREEN_LINES)

/* Code/data/stack live in slots 0-3 ($0000-$7FFF), per the Makefile's
 * --org/--limit/--initial-s; task1 mirrors them. Task1's slots 4-7
 * ($8000-$FFFF) are the graphics window: 32K, but the buffer is 36000 bytes,
 * so it shows the buffer's first 4 blocks (the playfield) or, shifted up one
 * block, its last 4 (the HUD strip, which starts past the 32K mark).
 * $FF00-$FFFF is I/O, so the top 256 bytes of the window are unusable.
 *
 * Slot 7 ($E000-$FFFF) can NEVER be permanently reassigned in task0: it
 * holds the 6809's hardware interrupt vectors ($FFF0-$FFFF). Doing so once
 * (writing task0's own $FFA3-$FFA7 directly) took the very next timer
 * interrupt through garbage and crashed the whole system back to a DOS/
 * BASIC text screen -- confirmed by testing, not a guess. This is exactly
 * what task1 is for: a BRACKETED alternate mapping, entered only with
 * interrupts disabled and reverted to task0's real vector table before
 * they're re-enabled. Graphics writes must go through the GFX_ENTER/
 * GFX_LEAVE macros below, inlined at the call site (not through a plain
 * function call) so no JSR/RTS pair has its return address pushed under
 * one task and popped under the other. */
#define GFX_WINDOW ((unsigned char *)0x8000U)
#define GFX_BLOCK_BYTES 8192U
#define HUD_WINDOW \
    (GFX_WINDOW + ((unsigned int)PLAYFIELD_LINES * BYTES_PER_ROW - GFX_BLOCK_BYTES))

/* The CoCo 3 runs in all-RAM mode: at cold start its ROM copies BASIC and the
 * cartridge (HDB-DOS) into RAM and never returns to ROM mode. Never write
 * $FFDE -- the interrupt handlers would then run from the ROMs, and on a real
 * CoCo 3 that locked up or crashed the machine. */

/* $FF91 bit 5 keeps the GIME timer at 3.58 MHz for the sound (sound.c). */
#define TASK0() \
    do { \
        asm("ldb", "#$20"); \
        asm("stb", "$FF91"); \
    } while (0)
#define TASK1() \
    do { \
        asm("ldb", "#$21"); \
        asm("stb", "$FF91"); \
    } while (0)

/* Masks IRQ and FIRQ, saving CC on the stack; INTS_RESTORE() puts back
 * exactly what was there (CMOC's enableInterrupts() unmasks both whatever
 * their prior state). Pair them in the same function. */
#define INTS_OFF() \
    do { \
        asm("pshs", "cc"); \
        asm("orcc", "#$50"); \
    } while (0)
#define INTS_RESTORE() asm("puls", "cc")

#define GFX_ENTER() \
    do { \
        INTS_OFF(); \
        TASK1(); \
    } while (0)

#define GFX_LEAVE() \
    do { \
        TASK0(); \
        INTS_RESTORE(); \
    } while (0)

/* Points task1's low four slots at the program, as GFX_ENTER() needs. */
void gime_init_task1(void);

/* Sets up GIME mode registers and task1's low slots. Does not choose a
 * graphics buffer yet -- call gime_select_buffers() after the RAM probe. */
void gime_init_mode(void);

void gime_set_palette(const unsigned char *clut16);

/* Aim the graphics window at the draw buffer's playfield (draw through
 * GFX_WINDOW) or its HUD strip (draw through HUD_WINDOW). Call outside a
 * GFX_ENTER()/GFX_LEAVE() bracket. The playfield is the resting state. */
void gime_window_playfield(void);
void gime_window_hud(void);

/* First physical block of the draw buffer. */
unsigned char gime_draw_block(void);

/* Double-buffered only: maps the DISPLAYED buffer's HUD strip and returns 1;
 * returns 0 (nothing mapped) when single-buffered. */
unsigned char gime_window_hud_shown(void);

/* Chooses the graphics buffer layout for the detected RAM size (1 =
 * 512K/double-buffered, 0 = 128K/single-buffered), and makes buffer 0
 * both the draw target and the displayed buffer. */
void gime_select_buffers(unsigned char is_512k);

/* Double-buffered only: shows the buffer just drawn into and makes the
 * OTHER buffer the new draw target. No-op if gime_select_buffers() chose
 * the single-buffered (128K) layout. */
void gime_flip_display(void);

#endif
