#include <stddef.h>

#include <lynx.h>
#include <tgi.h>

#include "render.h"
#include "../art/lynx_art.h"

/* Suzy sprite control block: reload hpos/vpos/hsize/vsize + palette.
 * SPRCTL0: bits 7-6 BPP (11 = 4bpp), bits 2-0 sprite type.
 * SPRCTL1: bit 7 totally literal, bits 5-4 reload depth (01 = HV size). */
#define SPRCTL0_TERRAIN (BPP_4 | TYPE_BACKNONCOLL)
#define SPRCTL0_ENTITY (BPP_4 | TYPE_NONCOLL)
#define SPRCTL1_LITERAL_HV (LITERAL | REHV)
#define SPRCOLL_OFF NO_COLLIDE

static SCB_REHV_PAL scb = {
    SPRCTL0_TERRAIN,
    SPRCTL1_LITERAL_HV,
    SPRCOLL_OFF,
    0,
    0,
    0, 0,
    0x0100, 0x0100,
    { 0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF }
};

/* Leftmost column each row must be repainted from, per page, recording
 * where entities were the last time that page was drawn. 0xFF means the
 * row is clean.
 *
 * A row is repainted as a run from that column to the right edge rather
 * than cell by cell, because a tile paints 18 pixels into a 16 pixel cell:
 * each scanline is a count byte, 8 pixel bytes, and a zero pad byte that
 * Suzy requires but also renders, spilling 2 pixels of pen 0 into the next
 * cell. A full redraw hides that because the next tile immediately covers
 * it, but an isolated repaint leaves a black column. Painting left to right
 * to the edge means every spill is covered by the following tile, and the
 * last one falls off screen. */
#define PATCH_NONE 0xFF
static unsigned char patch_from[2][VIEW_ROWS];
/* Which half of patch_from describes the buffer being drawn this frame.
 * Derived from the hardware page in render_frame, never toggled. */
static unsigned char patch_page;

/* CPU tile blitter. Terrain is copied straight into the back framebuffer by the
 * CPU instead of one Suzy blit per cell, because the per-blit Suzy overhead --
 * not the pixels -- dominates a full-viewport repaint. Entities and the HUD keep
 * drawing through Suzy into the same buffer, on top of the copied terrain.
 *
 * The page addresses are the constants the cc65 Lynx TGI driver itself uses:
 * page 0 at $E018, page 1 at $C038 (SETVIEWPAGE/SETDRAWPAGE in
 * libsrc/lynx/tgi/lynx-160-102-16.s).
 *
 * They are hardcoded because they cannot be discovered. This code used to read
 * them back from Mikey's display-address register at $FD94, which is
 * WRITE-ONLY on hardware: the read returns bus noise ($FDFD, an echo of the
 * address). Both "discovered" pages came out identical, so the terrain layer
 * either wrote to garbage or -- once a sanity check rejected them -- switched
 * itself off. Either way it never drew on hardware, nothing erased the previous
 * frame, and every sprite smeared a trail. The frame rates that appeared to
 * validate this path were high precisely because no terrain was being drawn.
 *
 * There is no Suzy fallback any more; it cost 2548 bytes of tile sprites in a
 * segment that ran out while adding the dialogue modal.
 *
 * The draw page is tracked locally: the driver starts on page 0 and its VBL
 * handler flips on each swap, so counting our own tgi_updatedisplay() calls
 * tracks it -- provided every swap goes through this file. Nothing else in the
 * client swaps once the game loop is running. */
#define FB_STRIDE 80          /* 160 px * 4bpp / 8 = 80 bytes per scanline */
#define FB_TILE_ROW (8 * FB_STRIDE)
#define FB_BYTES (102 * FB_STRIDE)
/* Overridable so the host tests can point these at ordinary allocations. */
#ifndef FB_PAGE_0
#define FB_PAGE_0 ((unsigned char *)0xE018)
#endif
#ifndef FB_PAGE_1
#define FB_PAGE_1 ((unsigned char *)0xC038)
#endif
static unsigned char *fb_page[2];
/* Index into fb_page[] that Suzy and the blitter draw into this frame. */
static unsigned char draw_index;
/* Set once the starting parity has been confirmed by experiment. */
static unsigned char blitter_ok;

/* Called once per terrain row during a repaint to drain the serial RX ring
 * (see render_set_rx_pump). Without it, the ~90-120 ms full repaint leaves the
 * driver's 256-byte ring un-emptied long enough to overflow at the Lynx rate. */
static void (*rx_pump)(void);

void render_set_rx_pump(void (*fn)(void))
{
    rx_pump = fn;
}

/* facing -> player frame base; +1 is the walk frame. There is no diagonal art,
 * so the four diagonals borrow the side-facing frames by parity: an odd facing
 * aims right, an even one left (RTS_FACE_UP_LEFT 4, UP_RIGHT 5, DOWN_LEFT 6,
 * DOWN_RIGHT 7). Same rule as select_remote_facing_base on the Atari. */
static const unsigned char facing_frame[RTS_FACE_COUNT] = {
    0, 0, 4, 2, 4, 2, 4, 2
};
static const unsigned char remote_facing_frame[RTS_FACE_COUNT] = {
    6, 6, 10, 8, 10, 8, 10, 8
};

/* Species (kind & RTS_KIND_MASK) -> sprite. Index 0 is unused on the wire but
 * kept so a stray 0 draws something rather than reading off the front. Kinds
 * with two animation frames pick the second one from the local anim counter --
 * the server sends no frame index, it only sends the species. */
static const unsigned char *const enemy_art[RTS_KIND_MAX + 1] = {
    art_beaver,          /* 0 unused */
    art_beaver,          /* 1 beaver */
    art_snake,           /* 2 */
    art_bat0,            /* 3 bat, animated */
    art_slime0,          /* 4 slime, animated */
    art_goblin,          /* 5 */
    art_gorvak,          /* 6 boss */
    art_wilhelm,         /* 7 NPC, idle */
    art_wilhelm          /* 8 NPC, working: alternates with the work frame */
};
static const unsigned char *const enemy_art_alt[RTS_KIND_MAX + 1] = {
    0, 0, 0,
    art_bat1,            /* 3 */
    art_slime1,          /* 4 */
    0, 0, 0,
    art_wilhelm_working  /* 8 */
};

/* Item drop art, indexed by rt_item_art_index(). */
static const unsigned char *const item_art_table[] = {
    0,                   /* RTS_ART_ITEM_NONE */
    art_item_gold,
    art_item_sticks,
    art_item_herb,
    art_item_potion,
    art_item_key
};

static void draw_sprite(const unsigned char *data, signed int hpos,
                        signed int vpos);

static void patch_reset(unsigned char page)
{
    unsigned char row;

    for (row = 0; row < VIEW_ROWS; ++row) {
        patch_from[page][row] = PATCH_NONE;
    }
}

/* Confirm which fb_page[] index Suzy is currently drawing into, by experiment.
 *
 * The driver starts on page 0 and we track flips ourselves, so this only has to
 * establish the starting parity -- but it has to establish it, not assume it.
 * Getting it backwards puts terrain in the buffer Suzy is not using, which is
 * invisible on a still screen and smears a trail behind everything that moves.
 *
 * Stamp a marker into both pages, have Suzy draw one sprite, see which page
 * changed. draw_sprite does not return until Suzy is done. */
#define PROBE_MARKER 0x11
#define PROBE_ROWS 8
#define PROBE_BYTES 4

static unsigned char probe_touched(const unsigned char *page)
{
    unsigned char row;
    unsigned char col;

    for (row = 0; row < PROBE_ROWS; ++row) {
        for (col = 0; col < PROBE_BYTES; ++col) {
            if (page[(unsigned)row * FB_STRIDE + col] != PROBE_MARKER) {
                return 1;
            }
        }
    }
    return 0;
}

static void probe_stamp(unsigned char *page)
{
    unsigned char row;
    unsigned char col;

    for (row = 0; row < PROBE_ROWS; ++row) {
        for (col = 0; col < PROBE_BYTES; ++col) {
            page[(unsigned)row * FB_STRIDE + col] = PROBE_MARKER;
        }
    }
}

static void calibrate_draw_page(void)
{
    unsigned char touched0;
    unsigned char touched1;

    probe_stamp(fb_page[0]);
    probe_stamp(fb_page[1]);

    /* Any sprite will do; a player frame has opaque pixels in its top-left
       cell, and pen 0 is transparent for this sprite type so the marker
       survives wherever the sprite does not cover. */
    scb.sprctl0 = SPRCTL0_ENTITY;
    scb.hsize = TILE_SCALE;
    scb.vsize = TILE_SCALE;
    draw_sprite(art_player[0], 0, 0);
    scb.sprctl0 = SPRCTL0_TERRAIN;

    touched0 = probe_touched(fb_page[0]);
    touched1 = probe_touched(fb_page[1]);

    if (touched0 == touched1) {
        /* Neither or both changed: the probe is inconclusive, so writing 6400
           bytes per frame on the strength of it is not defensible. Fall back to
           the driver's documented starting page and say so, rather than risk
           scribbling over the wrong memory. */
        draw_index = 0;
        blitter_ok = 0;
        return;
    }
    draw_index = touched0 ? 0 : 1;
    blitter_ok = 1;
}

void render_init(void)
{
    patch_reset(0);
    patch_reset(1);

    fb_page[0] = FB_PAGE_0;
    fb_page[1] = FB_PAGE_1;

    tgi_setpalette(art_clut[0]);
    tgi_setcollisiondetection(0);
    tgi_setbgcolor(8);

    /* Clear both alternating pages through completed VBL swaps, so the
       bootstrap status screen is gone from whichever comes up first. */
    while (tgi_busy()) {
    }
    tgi_clear();
    tgi_updatedisplay();
    while (tgi_busy()) {
    }
    tgi_clear();
    tgi_updatedisplay();
    while (tgi_busy()) {
    }
    calibrate_draw_page();
}

void render_video_info(unsigned *page0, unsigned *page1,
                       unsigned char *ok, unsigned char *draw_page)
{
    *page0 = (unsigned)(size_t)fb_page[0];
    *page1 = (unsigned)(size_t)fb_page[1];
    *ok = blitter_ok;
    *draw_page = draw_index;
}

static void draw_sprite(const unsigned char *data, signed int hpos,
                        signed int vpos)
{
    scb.data = (unsigned char *)data;
    scb.hpos = hpos;
    scb.vpos = vpos;
    tgi_sprite(&scb);
}

/* Shared logical tile id (server world.py): what an out-of-range id clamps to. */
#define TILE_BORDER 7

/* Object tiles (herb, grave, the named NPCs, the Floodworks props) need the
 * ground showing through their pen-0 background. That compositing happens
 * offline: tools/import_lynx_art.py bakes each object over the tile it stands
 * on when it emits art_tiles_raw, so the blitter stays one flat copy per cell.
 * OBJECT_TILE_BASE there is the list; nothing is needed here at runtime.
 */

/* Copy one 8x8 raw tile (8 rows x 4 bytes) into the back framebuffer at dst
 * (the cell's top-left byte). Tiles are 8px-aligned, so dst is 4-byte aligned
 * and the copy needs no shifting. The hot loop is in blit.s; the pointers go
 * through globals so each tile is a plain jsr. */
unsigned char *blit_src;
unsigned char *blit_dst;
extern void blit_tile_asm(void);

static void blit_tile(const unsigned char *raw, unsigned char *dst)
{
    blit_src = (unsigned char *)raw;
    blit_dst = dst;
    blit_tile_asm();
}

/* Full 20x10 terrain repaint via the CPU blitter. dst walks the framebuffer
 * incrementally (no per-tile row*640 multiply): +4 per cell, and the row base
 * +640 per tile row. Grass-object tiles are already precomposed opaque in
 * art_tiles_raw, so every cell is one flat copy. */
static void draw_terrain_cpu(const unsigned char *terrain, unsigned char cam_x,
                             unsigned char cam_y, unsigned char *base)
{
    unsigned char row;
    unsigned char col;
    unsigned char tile;
    unsigned tbase;
    unsigned char *dst_row = base;
    unsigned char *dst;

    for (row = 0; row < VIEW_ROWS; ++row) {
        tbase = (unsigned)(cam_y + row) * RTS_WINDOW_W + cam_x;
        dst = dst_row;
        for (col = 0; col < VIEW_COLS; ++col) {
            tile = terrain[tbase + col];
            if (tile >= ART_TILE_COUNT) {
                tile = TILE_BORDER;
            }
            blit_tile(art_tiles_raw[tile], dst);
            dst += 4;
        }
        /* Empty the serial ring into the app buffer between rows so a full
           repaint never sits long enough to overflow it. */
        if (rx_pump) {
            rx_pump();
        }
        dst_row += FB_TILE_ROW;
    }
}

/* Partial CPU repaint: only the cells entities covered last time this page was
 * drawn. Unlike the Suzy path there is no pad-byte spill, so a run from the
 * leftmost dirty column to the edge is still correct (and could later shrink to
 * exact cells). */
static void draw_terrain_patches_cpu(const unsigned char *terrain,
                                     unsigned char cam_x, unsigned char cam_y,
                                     unsigned char page, unsigned char *base)
{
    unsigned char row;
    unsigned char col;
    unsigned char tile;
    unsigned tbase;
    unsigned char *dst_row = base;
    unsigned char *dst;

    for (row = 0; row < VIEW_ROWS; ++row) {
        col = patch_from[page][row];
        if (col != PATCH_NONE) {
            tbase = (unsigned)(cam_y + row) * RTS_WINDOW_W + cam_x;
            dst = dst_row + (unsigned)col * 4;
            for (; col < VIEW_COLS; ++col) {
                tile = terrain[tbase + col];
                if (tile >= ART_TILE_COUNT) {
                    tile = TILE_BORDER;
                }
                blit_tile(art_tiles_raw[tile], dst);
                dst += 4;
            }
            if (rx_pump) {
                rx_pump();
            }
        }
        dst_row += FB_TILE_ROW;
    }
}

static void draw_world_entity(unsigned abs_x, unsigned abs_y,
                              unsigned origin_x, unsigned origin_y,
                              unsigned char cam_x, unsigned char cam_y,
                              const unsigned char *data)
{
    unsigned col;
    unsigned row;

    if (abs_x < origin_x || abs_y < origin_y) {
        return;
    }
    col = abs_x - origin_x;
    row = abs_y - origin_y;
    if (col < cam_x || row < cam_y) {
        return;
    }
    col -= cam_x;
    row -= cam_y;
    if (col >= VIEW_COLS || row >= VIEW_ROWS) {
        return;
    }
    /* Remember how far left this row must be repainted next time. */
    if ((unsigned char)col < patch_from[patch_page][row]) {
        patch_from[patch_page][row] = (unsigned char)col;
    }
    draw_sprite(data, (signed int)col * TILE_PX, (signed int)row * TILE_PX);
}

static const unsigned char *item_art(unsigned char item_id)
{
    /* The id -> art choice lives in rt_state.c so it is host-testable and
       shared with nothing else; here we only turn the index into a pointer. */
    return item_art_table[rt_item_art_index(item_id)];
}

static void draw_entities(const struct rt_state *state, unsigned origin_x,
                          unsigned origin_y, unsigned char cam_x,
                          unsigned char cam_y, unsigned char facing,
                          unsigned char anim)
{
    unsigned char i;
    const struct rt_beaver *beaver;
    const struct rt_remote_player *remote;
    const unsigned char *art;

    scb.sprctl0 = SPRCTL0_ENTITY;
    scb.hsize = TILE_SCALE;
    scb.vsize = TILE_SCALE;
    /* Items sit on the ground, so draw them before the actors that can stand
       over them. */
    for (i = 0; i < state->item_count; ++i) {
        art = item_art(state->items[i].item_id);
        if (art != 0) {
            draw_world_entity(state->items[i].x, state->items[i].y,
                              origin_x, origin_y, cam_x, cam_y, art);
        }
    }
    for (i = 0; i < state->beaver_count; ++i) {
        unsigned char kind;

        beaver = &state->beavers[i];
        /* Hit flash: blink out on alternate frames while the timer runs. This
           replaces the old hp <= 1 "hurt" sprite, whose art the server side
           deleted -- damage now arrives as a one-shot pulse bit, not as a
           state we could read off hp. */
        if (beaver->hit_timer & 1) {
            continue;
        }
        kind = beaver->kind;
        if (kind > RTS_KIND_MAX) {
            kind = RTS_KIND_BEAVER;
        }
        art = enemy_art[kind];
        if ((anim & 1) && enemy_art_alt[kind] != 0) {
            art = enemy_art_alt[kind];
        }
        draw_world_entity(beaver->x, beaver->y, origin_x, origin_y,
                          cam_x, cam_y, art);
    }
    for (i = 0; i < state->remote_count; ++i) {
        remote = &state->remotes[i];
        if ((remote->state & RTS_REMOTE_ALIVE) == 0) {
            continue;
        }
        art = art_player[remote_facing_frame[remote->facing & 7] +
                         (anim & 1)];
        draw_world_entity(remote->x, remote->y, origin_x, origin_y,
                          cam_x, cam_y, art);
    }
    draw_world_entity(state->player_x, state->player_y, origin_x, origin_y,
                      cam_x, cam_y,
                      art_player[facing_frame[facing & 7] + (anim & 1)]);
    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        if (state->tracers[i].active) {
            draw_world_entity(state->tracers[i].x, state->tracers[i].y,
                              origin_x, origin_y, cam_x, cam_y, art_bullet);
        }
    }
}

static void draw_hud(const unsigned char *stats_sprite,
                     const unsigned char *msg_sprite,
                     const unsigned char *quest_sprite)
{
    tgi_setcolor(8); /* navy panel */
    tgi_bar(0, HUD_TOP, 159, 101);
    tgi_setcolor(11);
    tgi_line(0, HUD_TOP, 159, HUD_TOP);
    scb.sprctl0 = SPRCTL0_ENTITY;
    scb.hsize = 0x0100;
    scb.vsize = 0x0100;
    draw_sprite(stats_sprite, 2, HUD_STATS_Y);
    draw_sprite(msg_sprite, 2, HUD_MSG_Y);
    draw_sprite(quest_sprite, 2, HUD_QUEST_Y);
}

void render_frame(const struct rt_state *state, const unsigned char *terrain,
                  unsigned origin_x, unsigned origin_y,
                  unsigned char cam_x, unsigned char cam_y,
                  unsigned char facing, unsigned char anim,
                  const unsigned char *stats_sprite,
                  const unsigned char *msg_sprite,
                  const unsigned char *quest_sprite,
                  unsigned char draw_flags,
                  unsigned char full_terrain)
{
    unsigned char *back = blitter_ok ? fb_page[draw_index] : 0;

    /* The dirty-cell record is keyed to the buffer this frame draws into: it
       says where entities were the last time this same buffer was drawn, and the
       partial repaint uses it to erase them. Same index, so they cannot drift. */
    patch_page = draw_index;

    if ((draw_flags & RENDER_TERRAIN) && back != 0) {
        if (full_terrain) {
            draw_terrain_cpu(terrain, cam_x, cam_y, back);
        } else {
            draw_terrain_patches_cpu(terrain, cam_x, cam_y, patch_page, back);
        }
    }
    /* Cleared even when terrain was skipped: those rows are either now
       repainted or deliberately stale, and the entities about to be drawn
       are what the next pass over this page must erase. */
    patch_reset(patch_page);
    if (draw_flags & RENDER_ENTITIES) {
        draw_entities(state, origin_x, origin_y, cam_x, cam_y, facing, anim);
    }
    if (draw_flags & RENDER_HUD) {
        draw_hud(stats_sprite, msg_sprite, quest_sprite);
    }
    tgi_updatedisplay();
    /* The driver's VBL handler flips its draw page on this swap; follow it. */
    draw_index ^= 1;
}

/* ------------------------------------------------------------------------- */
/* Full-screen modal. Terrain, entities and the HUD are all skipped; the page
 * is cleared and only text is drawn, so the modal owns the screen. On exit the
 * caller forces a full terrain repaint on both pages to rebuild the game view.
 */

void render_modal_begin(void)
{
    while (tgi_busy()) {
    }
    tgi_clear();
}

void render_modal_text(const unsigned char *sprite, signed int x, signed int y)
{
    scb.sprctl0 = SPRCTL0_ENTITY;
    scb.hsize = TILE_SCALE;
    scb.vsize = TILE_SCALE;
    draw_sprite(sprite, x, y);
    /* Leave the control word on the terrain type, as every other path here
       does, so a later frame does not inherit the entity type. */
    scb.sprctl0 = SPRCTL0_TERRAIN;
}

void render_modal_end(void)
{
    tgi_updatedisplay();
    draw_index ^= 1;
    /* Both pages are now stale as far as the game view is concerned. The
       modal's caller invalidates the camera and terrain, not us. */
    patch_reset(0);
    patch_reset(1);
}

void render_set_palette(unsigned char palette_id)
{
    /* One CLUT, so a map's palette_id re-tints the whole screen. An id we do
       not have falls back to the overworld rather than reading off the end. */
    if (palette_id >= ART_PALETTE_COUNT) {
        palette_id = 0;
    }
    tgi_setpalette(art_clut[palette_id]);
}
