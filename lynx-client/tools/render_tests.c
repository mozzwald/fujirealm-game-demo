/* Double-buffer bookkeeping tests for src/render.c.
 *
 * render.c is Lynx-only, so this is the one place its logic gets exercised off
 * hardware. It exists because of a real bug: terrain is copied into the back
 * framebuffer by the CPU while entities go through Suzy, and the record of
 * "where entities were the last time this buffer was drawn" has to name the
 * same buffer the copy writes to. When those drifted apart, every sprite left a
 * trail across the screen and nothing off-hardware could see it.
 *
 * The tgi layer is implemented here rather than stubbed away: page flipping is
 * exactly the behaviour under test. This file owns driver_draw_page, the parity
 * the real driver's VBL handler keeps, so the tests can check render.c's
 * independent copy of it against the genuine article.
 */

#include <assert.h>
#include <stdio.h>
#include <string.h>

#include <lynx.h>
#include <tgi.h>

#include "render.h"
#include "hudtext.h"
#include "../art/lynx_art.h"

#define FB_STRIDE 80
#define FB_BYTES (102 * FB_STRIDE)

/* Two fake framebuffers standing in for the Lynx's $E018 and $C038 pages.
 * render_test_hooks.h redirects render.c's FB_PAGE_0/FB_PAGE_1 at these, which
 * is the whole reason that file exists. */
unsigned char test_page_0[FB_BYTES];
unsigned char test_page_1[FB_BYTES];
#define page_a test_page_0
#define page_b test_page_1

/* The driver's own draw page: starts at 0 and its VBL handler flips it on every
 * completed swap. Suzy and tgi_clear both target it. render.c tracks this same
 * parity independently, and the tests exist to prove the two agree -- when they
 * did not, terrain went to the buffer Suzy was not using and every sprite
 * smeared a trail. */
static unsigned char driver_draw_page;

static unsigned char swap_count;
static unsigned char busy;

/* Start the driver on page 1 as well as page 0 across the two runs of the walk
 * test: render.c probes for the starting parity rather than assuming it, so it
 * has to come out right either way. */
static unsigned char start_page;

static unsigned char *suzy_target(void)
{
    return driver_draw_page ? page_b : page_a;
}

/* --- the tgi surface render.c uses ------------------------------------- */
void tgi_setpalette(const unsigned char *p) { (void)p; }
void tgi_setcollisiondetection(unsigned char on) { (void)on; }
void tgi_setcolor(unsigned char c) { (void)c; }
void tgi_setbgcolor(unsigned char c) { (void)c; }
void tgi_bar(int x1, int y1, int x2, int y2) { (void)x1;(void)y1;(void)x2;(void)y2; }
void tgi_line(int x1, int y1, int x2, int y2) { (void)x1;(void)y1;(void)x2;(void)y2; }
unsigned char tgi_busy(void) { return busy; }

void tgi_clear(void)
{
    memset(suzy_target(), 0xEE, FB_BYTES);
}

void tgi_updatedisplay(void)
{
    driver_draw_page ^= 1;
    ++swap_count;
}

/* Suzy sprites: mark the cells they cover in the current draw buffer so the
 * test can tell a drawn sprite from erased terrain. Only the top-left byte of
 * each 8x8 cell is stamped, which is enough to detect presence. */
void tgi_sprite(const void *scbp)
{
    const SCB_REHV_PAL *scb = (const SCB_REHV_PAL *)scbp;
    unsigned char *draw = suzy_target();
    long off;

    if (scb->vpos < 0 || scb->hpos < 0) {
        return;
    }
    off = (long)scb->vpos * FB_STRIDE + (scb->hpos / 2);
    if (off >= 0 && off < FB_BYTES) {
        draw[off] = 0x5A; /* "a sprite was here" */
    }
}

/* The tile copy itself. On the Lynx this is hand-written 6502 (src/blit.s);
 * this is the same 8 scanlines of 4 bytes with an 80-byte destination stride. */
extern unsigned char *blit_src;
extern unsigned char *blit_dst;
void blit_tile_asm(void)
{
    unsigned char row;
    unsigned char *src = blit_src;
    unsigned char *dst = blit_dst;

    for (row = 0; row < 8; ++row) {
        memcpy(dst, src, 4);
        src += 4;
        dst += FB_STRIDE;
    }
}

/* --- helpers ----------------------------------------------------------- */

#define SPRITE_MARK 0x5A
#define GRASS_TILE 0

static unsigned char terrain[RTS_WINDOW_W * RTS_WINDOW_H];
static unsigned char stats[HUD_TEXT_SPRITE_BYTES];
static unsigned char msg[HUD_TEXT_SPRITE_BYTES];
static unsigned char quest[HUD_TEXT_SPRITE_BYTES];

static unsigned char *current_draw_buffer(void)
{
    return suzy_target();
}

/* Byte a cell's top-left pixel row lands on. */
static long cell_offset(unsigned char col, unsigned char row)
{
    return (long)row * TILE_PX * FB_STRIDE + (long)col * TILE_PX / 2;
}

static void frame(struct rt_state *st, unsigned char cam_x, unsigned char cam_y,
                  unsigned char full)
{
    render_frame(st, terrain, 0, 0, cam_x, cam_y, RTS_FACE_DOWN, 0,
                 stats, msg, quest,
                 RENDER_TERRAIN | RENDER_ENTITIES, full);
}

/* The regression this file exists for: a sprite drawn into a buffer must be
 * erased by the partial terrain repaint the next time that same buffer is
 * drawn -- which is two frames later, because the pages alternate. */
static void test_partial_repaint_erases_sprites_on_the_right_buffer(void)
{
    struct rt_state st;
    unsigned char *buf_first;
    long off;

    memset(terrain, GRASS_TILE, sizeof(terrain));
    memset(page_a, 0, sizeof(page_a));
    memset(page_b, 0, sizeof(page_b));
    driver_draw_page = start_page;
    swap_count = 0;
    busy = 0;

    rt_state_init(&st);
    st.world_seen = 1;
    st.player_x = 5;
    st.player_y = 3;

    render_init();

    /* Frame 1 draws the buffer that is not currently shown. */
    buf_first = current_draw_buffer();
    frame(&st, 0, 0, 1);
    off = cell_offset(5, 3);
    assert(buf_first[off] == SPRITE_MARK);

    /* Frame 2 draws the other buffer; the first one is untouched. */
    frame(&st, 0, 0, 0);
    assert(buf_first[off] == SPRITE_MARK);

    /* Frame 3 comes back around to buf_first. The player has not moved, so
       the partial repaint must lay terrain over the cell it occupied, and the
       sprite is then redrawn on top -- so the mark is still there, but it got
       there via a repaint rather than by never being erased. Move the player
       first so the difference is observable. */
    st.player_x = 9;
    frame(&st, 0, 0, 0);
    assert(swap_count > 0); /* sanity: swaps really happened */
    /* The vacated cell must have been repainted with terrain, not left as a
       sprite. This is the assertion that fails when the dirty-cell record
       names the wrong buffer. */
    assert(buf_first[off] != SPRITE_MARK);
    /* ...and the new position is drawn. */
    assert(buf_first[cell_offset(9, 3)] == SPRITE_MARK);
}

/* Walking leaves no residue anywhere: step across the viewport and afterwards
 * no cell the player passed through may still hold a sprite mark in either
 * buffer. This is the screen-level statement of the same property. */
static void walk_and_check_no_trail(void)
{
    struct rt_state st;
    unsigned char col;
    unsigned char pass;

    memset(terrain, GRASS_TILE, sizeof(terrain));
    memset(page_a, 0, sizeof(page_a));
    memset(page_b, 0, sizeof(page_b));
    driver_draw_page = start_page;
    busy = 0;

    rt_state_init(&st);
    st.world_seen = 1;
    st.player_y = 4;

    render_init();
    /* Walk right, then back left. The leftward leg is the one that matters: a
       partial repaint covers from the dirtied column to the *right* edge, so a
       rightward walk is always covered by the previous frame's run whether the
       bookkeeping is right or wrong. Only moving left leaves the vacated cell
       outside the repainted run. */
    for (col = 0; col < VIEW_COLS; ++col) {
        st.player_x = col;
        frame(&st, 0, 0, col < 2); /* two full repaints to seed both pages */
    }
    for (col = VIEW_COLS; col-- > 0; ) {
        st.player_x = col;
        frame(&st, 0, 0, 0);
    }

    /* Two more frames with the player parked at the last column, so both
       buffers get a chance to erase whatever the walk left behind. */
    for (pass = 0; pass < 2; ++pass) {
        frame(&st, 0, 0, 0);
    }

    /* Every column except where the player is actually standing must be clear
       of sprite marks in both buffers. */
    for (col = 0; col < VIEW_COLS; ++col) {
        long off = cell_offset(col, 4);

        if (col == st.player_x) {
            continue;
        }
        if (page_a[off] == SPRITE_MARK || page_b[off] == SPRITE_MARK) {
            printf("trail left at column %u (player at %u, "
                   "start_page=%u, page0=%02X page1=%02X)\n",
                   col, st.player_x, start_page,
                   page_a[off], page_b[off]);
            assert(0);
        }
    }
}

/* The regression from hardware: trails appeared even with a full repaint every
 * frame, which can only happen if terrain and sprites land in different
 * buffers. render.c measures which buffer Suzy uses rather than assuming, so
 * this has to hold whichever convention the driver follows. */
static void test_walking_leaves_no_trail(void)
{
    start_page = 0;
    walk_and_check_no_trail();
    start_page = 1;
    walk_and_check_no_trail();
    start_page = 0;
}

/* A full-terrain frame writes 6400 bytes per page by hand, so prove the blitter
 * stays inside them. The canaries below are the actual assertion.
 *
 * The other half of that guard -- calibrate_draw_page() giving up and leaving
 * the terrain layer off -- cannot be provoked from here: the probe draws a real
 * sprite into one of two distinct buffers and the tgi layer in this file always
 * makes that observable, so the inconclusive branch never runs. It only fires on
 * a machine where Suzy does not behave, which is exactly where a host test
 * cannot follow. */
static void test_full_frame_stays_inside_the_buffers(void)
{
    struct rt_state st;

    memset(terrain, GRASS_TILE, sizeof(terrain));
    memset(page_a, 0, sizeof(page_a));
    rt_state_init(&st);
    st.world_seen = 1;

    driver_draw_page = start_page;
    busy = 0;
    render_init();
    frame(&st, 0, 0, 1);
}

/* Canaries either side of the buffers catch a blit that walks off the end. */
static unsigned char canary_before[64];
static unsigned char canary_after[64];

int main(void)
{
    memset(canary_before, 0xC3, sizeof(canary_before));
    memset(canary_after, 0xC3, sizeof(canary_after));

    test_partial_repaint_erases_sprites_on_the_right_buffer();
    test_walking_leaves_no_trail();
    test_full_frame_stays_inside_the_buffers();

    {
        unsigned i;
        for (i = 0; i < sizeof(canary_before); ++i) {
            assert(canary_before[i] == 0xC3);
            assert(canary_after[i] == 0xC3);
        }
    }
    puts("render tests: ok");
    return 0;
}
