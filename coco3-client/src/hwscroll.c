#include "hwscroll.h"
#include "gime.h"
#include "tiles.h"
#include "player.h"
#include "terrain.h"
#include "hud.h"
#include "controls.h"
#include "ovl_api.h"
#include "art.h"
#include <coco.h>
#include <cmoc.h>

/* Two virtual screens (rings), each 15 physical blocks (464 lines of 256)
 * from its base block. Each step paints the hidden ring, HUD included, then
 * flips to it at vertical blank, so nothing is drawn on screen. */
#define RING_A_BLOCK 8
#define RING_B_BLOCK 23
#define RING_ROWS 15
#define RING_LINES (RING_ROWS * TILE_H)  /* 240 */
#define MIRROR_ROWS 14                   /* ring rows 0..13 are mirrored */
#define MIRROR_LINES (MIRROR_ROWS * TILE_H) /* 224 */
#define FRAME_HUD_TOP PLAYFIELD_LINES

#define MAX_STALE 4

struct cell {
    unsigned char x;
    unsigned char y;
};

/* What one ring shows: it lags the other by a step, so each keeps its own
 * record. Only cells whose markers or terrain changed are repainted. */
struct ring {
    unsigned char base;
    unsigned char have;              /* painted at least once since hw_init */
    unsigned vx, vy;                 /* view it last showed */
    struct sprite marks[MAX_SPRITES];
    unsigned char nmarks;
    unsigned hud_line;               /* where its HUD was stamped */
    unsigned char hud_hoff;
    unsigned char hud_stale;         /* HUD text changed since stamped */
    unsigned char nstale;            /* terrain changed here; > MAX_STALE: all */
    struct cell stale[MAX_STALE];
};

static struct ring rings[2];
static struct ring *cur;             /* the hidden ring being painted */
static unsigned char front;          /* index of the ring on screen */

/* Each 8K block holds 32 lines, and a tile row (16 lines) never straddles a
 * block, so painting a tile or a line needs exactly one window mapping. */
static void map_block(unsigned line)
{
    *(unsigned char *)0xFFAC = (unsigned char)(cur->base + (line >> 5));
}

/* The art is in slot 5, beside the ring block in slot 4. */
static void put_tile(unsigned line, unsigned char col, unsigned char id)
{
    map_block(line);
    *(unsigned char *)0xFFAD = ART_BLOCK;
    GFX_ENTER();
    copy_tile(GFX_WINDOW + (line & 31) * 256 + col * (TILE_W / 2),
              ART_TILE_IMAGE(GFX_WINDOW + 0x2000, id), 256);
    GFX_LEAVE();
}

/* Cells outside the cached window draw as grass. */
static unsigned char tile_id(const unsigned char *terrain, unsigned ox,
                             unsigned oy, unsigned wx, unsigned wy)
{
    unsigned rx = wx - ox;
    unsigned ry = wy - oy;

    if (rx >= BOOTSTRAP_WINDOW_W || ry >= BOOTSTRAP_WINDOW_H) {
        return 0;
    }
    return terrain[ry * BOOTSTRAP_WINDOW_W + rx];
}

static void paint_tile(unsigned wx, unsigned wy, unsigned char id)
{
    unsigned char row = (unsigned char)(wy % RING_ROWS);
    unsigned char col = (unsigned char)(wx & 31);
    unsigned line = (unsigned)row * TILE_H;

    put_tile(line, col, id);
    if (row < MIRROR_ROWS) {
        put_tile(line + RING_LINES, col, id);
    }
}

static unsigned char blast_n;
static unsigned blast_s;

/* Copies len bytes (a multiple of 4) from src to dst, twelve at a time
 * through the stack pointer, back to front. Inside the GFX bracket. */
static void blast(unsigned char *dst, const unsigned char *src,
                  unsigned char len)
{
    asm {
        pshs u,y
        ldx :dst
        ldy :src
        lda :len
        clrb
blast_div:
        cmpa #12
        blo blast_rem
        suba #12
        incb
        bra blast_div
blast_rem:
        tsta
        beq blast_chunks
blast_rloop:
        ldu ,y++
        stu ,x++
        suba #2
        bne blast_rloop
blast_chunks:
        tstb
        beq blast_done
        stb :blast_n
        lda #12
        mul
        leax d,x
        leay d,y
        sts :blast_s
        leau -6,y
        tfr x,s
blast_loop:
        pulu d,x,y
        pshs d,x,y
        leau -12,u
        pulu d,x,y
        pshs d,x,y
        leau -12,u
        dec :blast_n
        bne blast_loop
        lds :blast_s
blast_done:
        puls u,y
    }
}

/* Stamps the HUD into the hidden ring below the frame whose top-left is
 * world (vx, vy), writing only the copy of each line that frame shows. Only
 * text lines (hud.c rows at 3, 13, 23) move with a sideways scroll; blanks
 * != 0 also clears the empty lines (across the whole 256-byte row), needed
 * when the frame moved vertically. The image is in slot 4; the HUD's 33 ring
 * lines span at most two blocks, mapped in slots 5 and 6. */
static void paint_hud(unsigned vx, unsigned vy, unsigned char blanks)
{
    unsigned line = (vy % RING_ROWS) * TILE_H + FRAME_HUD_TOP;
    unsigned char hoff = (unsigned char)((vx & 31) * (TILE_W / 2));
    unsigned room = 256 - (unsigned)hoff;
    unsigned char seg1 = HUD_IMAGE_STRIDE;
    unsigned char block = (unsigned char)(cur->base + (line >> 5));
    unsigned char *row = GFX_WINDOW + 0x2000 + (line & 31) * 256;
    const unsigned char *src = GFX_WINDOW;
    unsigned char i;

    if (room < HUD_IMAGE_STRIDE) { /* not a ternary: CMOC sign-extends 160 */
        seg1 = (unsigned char)room;
    }
    *(unsigned char *)0xFFAC = HUD_IMAGE_BLOCK;
    *(unsigned char *)0xFFAD = block;
    *(unsigned char *)0xFFAE = (unsigned char)(block + 1);
    for (i = 0; i < HUD_LINES; ++i, row += 256, src += HUD_IMAGE_STRIDE) {
        if (i >= 3 && (unsigned char)((i - 3) % 10) < 8) {
            GFX_ENTER();
            blast(row + hoff, src, seg1);
            if (seg1 < HUD_IMAGE_STRIDE) {
                blast(row, src + seg1, (unsigned char)(HUD_IMAGE_STRIDE - seg1));
            }
            GFX_LEAVE();
        } else if (blanks) {
            GFX_ENTER();
            blast(row, GFX_WINDOW, HUD_IMAGE_STRIDE);
            blast(row + HUD_IMAGE_STRIDE, GFX_WINDOW, 256 - HUD_IMAGE_STRIDE);
            GFX_LEAVE();
        }
    }
}

void hw_hud_refresh(void)
{
    rings[0].hud_stale = 1;
    rings[1].hud_stale = 1;
}

static void draw_mark(const struct sprite *m)
{
    unsigned char row = (unsigned char)(m->y % RING_ROWS);
    unsigned line = (unsigned)row * TILE_H;

    for (;;) {
        map_block(line);
        *(unsigned char *)0xFFAD = ART_BLOCK;
        GFX_ENTER();
        put_sprite(GFX_WINDOW + (line & 31) * 256 + (m->x & 31) * (TILE_W / 2),
                   GFX_WINDOW + 0x2000, m->img, 256);
        GFX_LEAVE();
        if (row >= MIRROR_ROWS || line >= RING_LINES) {
            break;
        }
        line += RING_LINES;
    }
}

/* Draws every marker of this frame that sits on cell (x, y), in list order. */
static void draw_cell_marks(unsigned char x, unsigned char y)
{
    unsigned char i;

    for (i = 0; i < spr_next_n; ++i) {
        if (spr_next[i].x == x && spr_next[i].y == y) {
            draw_mark(&spr_next[i]);
        }
    }
}

/* Shows the hidden ring at (view_x, view_y), at vertical blank: the GIME
 * latches the start address at the top of the frame. Only IRQ is masked, so
 * the sound FIRQ keeps playing; it also ends a sync, hence the wait for the
 * PIA's field-sync flag. */
static void set_scroll(unsigned view_x, unsigned view_y)
{
    unsigned start = (view_y % RING_ROWS) * TILE_H;
    unsigned video = ((unsigned)cur->base << 10) + start * 32;
    unsigned char hoff = (unsigned char)((view_x & 31) * 4);

    asm {
        pshs cc
        orcc #$10
        lda $FF92 ; acknowledge a pending GIME IRQ
scroll_wait
        sync
        tst $FF03
        bpl scroll_wait
    }
    *(unsigned *)0xFF9D = video;
    *(unsigned char *)0xFF9F = (unsigned char)(0x80 | hoff);
    asm { puls cc }
}

void hw_init(void)
{
    memset(rings, 0, sizeof(rings));
    rings[0].base = RING_A_BLOCK;
    rings[1].base = RING_B_BLOCK;
    front = 0;
    *(unsigned *)0xFF9D = (unsigned)RING_A_BLOCK << 10;
    *(unsigned char *)0xFF9F = 0x80;
}

void hw_leave(void)
{
    *(unsigned char *)0xFF9F = 0;
}

static void paint_view(const unsigned char *terrain, unsigned ox, unsigned oy,
                       unsigned vx, unsigned vy, unsigned char skip_painted)
{
    unsigned char row, col;
    unsigned wx, wy;

    for (row = 0; row < VIEW_ROWS; ++row) {
        controls_poll();
        wy = vy + row;
        for (col = 0; col < VIEW_COLS; ++col) {
            wx = vx + col;
            if (skip_painted && wx - cur->vx < VIEW_COLS &&
                wy - cur->vy < VIEW_ROWS) {
                continue;
            }
            paint_tile(wx, wy, tile_id(terrain, ox, oy, wx, wy));
        }
    }
}

/* Queues st's changed terrain cells for r to repaint. */
static void add_stale(struct ring *r, const struct rt_state *st)
{
    unsigned char i;

    if (st->changed_n > RTS_MAX_CHANGED) {
        r->nstale = MAX_STALE + 1;
        return;
    }
    for (i = 0; i < st->changed_n; ++i) {
        if (r->nstale >= MAX_STALE) {
            r->nstale = MAX_STALE + 1;
            return;
        }
        r->stale[r->nstale].x = st->changed_x[i];
        r->stale[r->nstale].y = st->changed_y[i];
        ++r->nstale;
    }
}

/* Brings the hidden ring up to the view (vx, vy) with spr_next, then shows
 * it. */
static void paint_ring(const unsigned char *terrain, unsigned ox, unsigned oy,
                       unsigned vx, unsigned vy, unsigned char full)
{
    unsigned char i;
    unsigned char ok;
    int ddx;
    int ddy;
    unsigned char x;
    unsigned char y;
    unsigned line = (vy % RING_ROWS) * TILE_H + FRAME_HUD_TOP;
    unsigned char hoff = (unsigned char)((vx & 31) * (TILE_W / 2));

    cur = &rings[front ^ 1];
    ddx = (int)(vx - cur->vx);
    ddy = (int)(vy - cur->vy);
    if (full || !cur->have || cur->nstale > MAX_STALE ||
        ddx >= VIEW_COLS || ddx <= -VIEW_COLS ||
        ddy >= VIEW_ROWS || ddy <= -VIEW_ROWS) {
        paint_view(terrain, ox, oy, vx, vy, 0);
        for (i = 0; i < spr_next_n; ++i) {
            draw_mark(&spr_next[i]);
        }
        paint_hud(vx, vy, 1);
    } else {
        dirty_n = 0;
        ok = dirty_sprites(cur->marks, cur->nmarks);
        paint_view(terrain, ox, oy, vx, vy, 1);
        for (i = 0; ok && i < cur->nstale; ++i) {
            ok = dirty_add(cur->stale[i].x, cur->stale[i].y);
        }
        if (!ok) {
            for (i = 0; i < cur->nstale; ++i) {
                x = cur->stale[i].x;
                y = cur->stale[i].y;
                if ((unsigned)x - vx < VIEW_COLS && (unsigned)y - vy < VIEW_ROWS) {
                    paint_tile(x, y, tile_id(terrain, ox, oy, x, y));
                }
            }
            for (i = 0; i < cur->nmarks; ++i) {
                x = cur->marks[i].x;
                y = cur->marks[i].y;
                if ((unsigned)x - vx < VIEW_COLS && (unsigned)y - vy < VIEW_ROWS) {
                    paint_tile(x, y, tile_id(terrain, ox, oy, x, y));
                }
            }
            for (i = 0; i < spr_next_n; ++i) {
                draw_mark(&spr_next[i]);
            }
        } else {
            for (i = 0; i < dirty_n; ++i) {
                x = dirty_x[i];
                y = dirty_y[i];
                if ((unsigned)x - vx < VIEW_COLS && (unsigned)y - vy < VIEW_ROWS) {
                    paint_tile(x, y, tile_id(terrain, ox, oy, x, y));
                    draw_cell_marks(x, y);
                }
            }
        }
        if (cur->hud_line != line) {
            paint_hud(vx, vy, 1);
        } else if (cur->hud_hoff != hoff || cur->hud_stale) {
            paint_hud(vx, vy, 0);
        }
    }
    cur->vx = vx;
    cur->vy = vy;
    cur->have = 1;
    cur->hud_line = line;
    cur->hud_hoff = hoff;
    cur->hud_stale = 0;
    cur->nstale = 0;
    memcpy(cur->marks, spr_next, sizeof(struct sprite) * spr_next_n);
    cur->nmarks = spr_next_n;

    set_scroll(vx, vy);
    front ^= 1;
}

void hw_present(const unsigned char *terrain, unsigned ox, unsigned oy,
                unsigned vx, unsigned vy, const struct rt_state *st,
                unsigned char mode)
{
    if (mode == HW_PRESENT_TILES) {
        add_stale(&rings[0], st);
        add_stale(&rings[1], st);
    }

    paint_ring(terrain, ox, oy, vx, vy, mode == HW_PRESENT_FULL);
    /* A full repaint does both rings, so the next step is not a full one. */
    if (mode == HW_PRESENT_FULL) {
        paint_ring(terrain, ox, oy, vx, vy, 1);
    }
}

void ovl_region_end(void)
{
}
