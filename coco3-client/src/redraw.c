#include "tiles.h"
#include "gime.h"
#include "terrain.h"
#include "controls.h"
#include "ovl_api.h"
#include "art.h"

void ovl_region_start(void)
{
}

static unsigned char spr_rows;
static unsigned spr_skip;
static unsigned char recolor_buf[ART_IMAGE_BYTES];
/* Other players: the light blue tunic (12) turns red (11), its dark blue
 * trim (10) maroon (7). */
static const unsigned char remote_color[16] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 7, 11, 11, 13, 14, 15
};

/* ART_RECOLOR images go through recolor_buf, with remote_color. */
void put_sprite(unsigned char *dst, const unsigned char *art,
                       unsigned char img, unsigned stride)
{
    const unsigned char *src = ART_IMAGE(art, img);
    unsigned char i;
    unsigned char b;

    if (img & ART_RECOLOR) {
        for (i = 0; i < ART_IMAGE_BYTES; ++i) {
            b = src[i];
            recolor_buf[i] = (unsigned char)((remote_color[b >> 4] << 4) |
                                             remote_color[b & 0x0F]);
        }
        src = recolor_buf;
    }
    draw_sprite(dst, src, stride);
}

void draw_sprite(unsigned char *dst, const unsigned char *src, unsigned stride)
{
    spr_skip = stride - 8;
    asm {
        pshs y
        ldx :src
        ldy :dst
        lda #16
        sta :spr_rows
spr_row
        ldb #8
spr_byte
        lda ,x+
        beq spr_adv
        bita #$F0
        beq spr_low
        bita #$0F
        beq spr_high
        sta ,y
        bra spr_adv
spr_low
        pshs a
        lda ,y
        anda #$F0
        ora ,s+
        sta ,y
        bra spr_adv
spr_high
        pshs a
        lda ,y
        anda #$0F
        ora ,s+
        sta ,y
spr_adv
        leay 1,y
        decb
        bne spr_byte
        ldd :spr_skip
        leay d,y
        dec :spr_rows
        bne spr_row
        puls y
    }
}

static unsigned char copy_n;

void copy_tile(unsigned char *dst, const unsigned char *src, unsigned stride)
{
    asm {
        pshs y
        ldx :src
        ldy :dst
        lda #16
        sta :copy_n
copy_row
        ldd ,x
        std ,y
        ldd 2,x
        std 2,y
        ldd 4,x
        std 4,y
        ldd 6,x
        std 6,y
        leax 8,x
        ldd :stride
        leay d,y
        dec :copy_n
        bne copy_row
        puls y
    }
}

/* The view the screen shows. */
static unsigned drawn_vx;
static unsigned drawn_vy;

/* This frame, for paint_span. */
static const unsigned char *pt_terrain;
static unsigned char pt_cam_x;
static unsigned char pt_cam_y;
static unsigned pt_vx;
static unsigned pt_vy;
static unsigned char pt_base;

/* Draws ncols tiles of screen row row from col, then the sprites on them.
 * The row's screen lines span at most two blocks: those go in slots 4 and 5,
 * the art in slot 6. One bracket per call keeps interrupts masked well under
 * a 60 Hz tick, so the timer the walk cadence counts is not starved. */
static void paint_span(unsigned char row, unsigned char col,
                       unsigned char ncols)
{
    const unsigned char *src =
        &pt_terrain[(unsigned)(pt_cam_y + row) * BOOTSTRAP_WINDOW_W +
                    pt_cam_x + col];
    unsigned ofs = (unsigned)row * TILE_ROW_BYTES;
    unsigned char block = (unsigned char)(pt_base + (ofs >> 13));
    unsigned char *row_start = GFX_WINDOW + (ofs & 0x1FFF);
    unsigned char *dst = row_start + col * (TILE_W / 2);
    unsigned char row_y = (unsigned char)(pt_vy + row);
    unsigned char i;

    *(unsigned char *)0xFFAC = block;
    *(unsigned char *)0xFFAD = (unsigned char)(block + 1);
    *(unsigned char *)0xFFAE = ART_BLOCK;
    GFX_ENTER();
    for (i = 0; i < ncols; ++i, dst += TILE_W / 2) {
        copy_tile(dst, ART_TILE_IMAGE(GFX_WINDOW + 0x4000, src[i]),
                  BYTES_PER_ROW);
    }
    for (i = 0; i < spr_next_n; ++i) {
        if (spr_next[i].y == row_y &&
            (unsigned)(spr_next[i].x - pt_vx) - col < ncols) {
            put_sprite(row_start + (spr_next[i].x - pt_vx) * (TILE_W / 2),
                       GFX_WINDOW + 0x4000, spr_next[i].img, BYTES_PER_ROW);
        }
    }
    GFX_LEAVE();
}

/* Collects the cells to repaint while the view stays put: sprites that
 * appeared, left or changed since spr_prev, and terrain the server changed.
 * Returns 0 if a full redraw is needed instead. */
static unsigned char find_dirty(const struct rt_state *st)
{
    unsigned char i;
    unsigned char x;
    unsigned char y;

    dirty_n = 0;
    if (st->changed_n > RTS_MAX_CHANGED ||
        !dirty_sprites(spr_prev, spr_prev_n)) {
        return 0;
    }
    for (i = 0; i < st->changed_n; ++i) {
        x = st->changed_x[i];
        y = st->changed_y[i];
        if ((unsigned)(x - pt_vx) < PLAYFIELD_COLS &&
            (unsigned)(y - pt_vy) < PLAYFIELD_ROWS && !dirty_add(x, y)) {
            return 0;
        }
    }
    return 1;
}

void draw_world(const unsigned char *terrain, unsigned origin_x,
                unsigned origin_y, unsigned char cam_x, unsigned char cam_y,
                const struct rt_state *st, unsigned char full)
{
    unsigned char i;

    pt_terrain = terrain;
    pt_cam_x = cam_x;
    pt_cam_y = cam_y;
    pt_vx = origin_x + cam_x;
    pt_vy = origin_y + cam_y;
    pt_base = gime_draw_block();

    if (!full && pt_vx == drawn_vx && pt_vy == drawn_vy && find_dirty(st)) {
        for (i = 0; i < dirty_n; ++i) {
            paint_span((unsigned char)(dirty_y[i] - pt_vy),
                       (unsigned char)(dirty_x[i] - pt_vx), 1);
        }
    } else {
        /* Each row's sprites follow its tiles at once, so on the single 128K
         * buffer they are not seen missing. */
        for (i = 0; i < PLAYFIELD_ROWS; ++i) {
            controls_poll();
            paint_span(i, 0, PLAYFIELD_COLS);
        }
    }
    drawn_vx = pt_vx;
    drawn_vy = pt_vy;
    gime_window_playfield();
}
