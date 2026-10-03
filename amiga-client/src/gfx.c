#include <string.h>

#include <exec/memory.h>
#include <graphics/gfx.h>
#include <graphics/gfxbase.h>
#include <graphics/rastport.h>
#include <intuition/intuition.h>
#include <intuition/screens.h>
#include <proto/exec.h>
#include <proto/graphics.h>
#include <proto/intuition.h>

#include "amiga_art.h"
#include "gfx.h"

/* Opened here rather than left to libnix's auto-open, so a missing library
 * is reported instead of failing silently at startup. */
struct GfxBase *GfxBase = NULL;
struct IntuitionBase *IntuitionBase = NULL;

#define SCREEN_W 320
#define SCREEN_H 200
#define DEPTH ART_DEPTH
/* Cookie-cut minterm: D = (A & B) | (!A & C), with A the mask. */
#define MINTERM_COOKIE 0xE0
#define MINTERM_COPY 0xC0

static struct Screen *screen;
static struct Window *window;

/* All image memory is chip RAM, where the blitter can reach it. */
struct chip_bitmap {
    struct BitMap bm;
    LONG plane_bytes;
};

static struct chip_bitmap tiles;     /* 16 x (16 * 52) */
static struct chip_bitmap tiles8;    /* 16 x (8 * 52), 8x8 art in the left byte */
static struct chip_bitmap sprites;   /* 16 x (16 * 28) */
static PLANEPTR sprite_mask;         /* one plane, same geometry as sprites */
static struct chip_bitmap terrain;   /* retained 320x160 terrain layer */
static struct chip_bitmap compose;   /* terrain + entities, then to screen */
static struct RastPort compose_rp;

static int alloc_bitmap(struct chip_bitmap *b, int width, int height)
{
    int i;

    InitBitMap(&b->bm, DEPTH, width, height);
    b->plane_bytes = (LONG)b->bm.BytesPerRow * height;
    for (i = 0; i < DEPTH; ++i) {
        b->bm.Planes[i] = AllocMem(b->plane_bytes, MEMF_CHIP | MEMF_CLEAR);
        if (!b->bm.Planes[i])
            return 1;
    }
    return 0;
}

static void free_bitmap(struct chip_bitmap *b)
{
    int i;

    for (i = 0; i < DEPTH; ++i) {
        if (b->bm.Planes[i])
            FreeMem(b->bm.Planes[i], b->plane_bytes);
        b->bm.Planes[i] = NULL;
    }
}

/* Copy one 16x16 planar image into row slot `index` of a 16-wide sheet. */
static void load_cell(struct chip_bitmap *b, int index,
                      const UWORD image[ART_DEPTH][ART_TILE_SIZE])
{
    int p;

    for (p = 0; p < DEPTH; ++p)
        CopyMem((APTR)image[p], (UBYTE *)b->bm.Planes[p] + index * 32, 32);
}

int gfx_open(void)
{
    struct NewScreen ns;
    struct NewWindow nw;
    int i;

    GfxBase = (struct GfxBase *)OpenLibrary((UBYTE *)"graphics.library", 33);
    IntuitionBase = (struct IntuitionBase *)OpenLibrary((UBYTE *)"intuition.library", 33);
    if (!GfxBase || !IntuitionBase)
        return 1;

    if (alloc_bitmap(&tiles, 16, 16 * ART_TILE_COUNT) ||
        alloc_bitmap(&tiles8, 16, 8 * ART_TILE_COUNT) ||
        alloc_bitmap(&sprites, 16, 16 * ART_SPRITE_COUNT) ||
        alloc_bitmap(&terrain, VIEW_W, VIEW_H) ||
        alloc_bitmap(&compose, VIEW_W, VIEW_H))
        return 1;
    sprite_mask = AllocMem(sprites.plane_bytes, MEMF_CHIP);
    if (!sprite_mask)
        return 1;
    for (i = 0; i < ART_TILE_COUNT; ++i)
        load_cell(&tiles, i, art_tiles[i]);
    for (i = 0; i < ART_TILE_COUNT; ++i) {
        int p;

        for (p = 0; p < DEPTH; ++p)
            CopyMem((APTR)art_tiles8[i][p], (UBYTE *)tiles8.bm.Planes[p] + i * 16, 16);
    }
    for (i = 0; i < ART_SPRITE_COUNT; ++i) {
        load_cell(&sprites, i, art_sprites[i]);
        CopyMem((APTR)art_masks[i], (UBYTE *)sprite_mask + i * 32, 32);
    }
    InitRastPort(&compose_rp);
    compose_rp.BitMap = &compose.bm;

    memset(&ns, 0, sizeof(ns));
    ns.Width = SCREEN_W;
    ns.Height = SCREEN_H;
    ns.Depth = DEPTH;
    ns.DetailPen = PEN_BLACK;
    ns.BlockPen = PEN_WHITE;
    ns.Type = CUSTOMSCREEN | SCREENQUIET;
    ns.DefaultTitle = (UBYTE *)"FujiRealm";
    screen = OpenScreen(&ns);
    if (!screen)
        return 1;

    memset(&nw, 0, sizeof(nw));
    nw.Width = SCREEN_W;
    nw.Height = SCREEN_H;
    nw.DetailPen = PEN_BLACK;
    nw.BlockPen = PEN_WHITE;
    nw.IDCMPFlags = RAWKEY | MOUSEBUTTONS;
    nw.Flags = BACKDROP | BORDERLESS | ACTIVATE | RMBTRAP | NOCAREREFRESH;
    nw.Screen = screen;
    nw.Type = CUSTOMSCREEN;
    window = OpenWindow(&nw);
    if (!window)
        return 1;
    /* The screen's title bar is a layer in front of backdrop windows even
     * with SCREENQUIET (which only stops the title being drawn), so it hid
     * our top ~10 lines as a black band. Put it behind the backdrop. */
    ShowTitle(screen, FALSE);
    /* The Intuition pointer stays visible for mouse play; give it clear
     * colours (sprite pens 17-19) against grass, stone and water. */
    SetRGB4(&screen->ViewPort, 17, 0xF, 0x3, 0x2);
    SetRGB4(&screen->ViewPort, 18, 0x0, 0x0, 0x0);
    SetRGB4(&screen->ViewPort, 19, 0xF, 0xF, 0xF);
    gfx_set_palette(0);
    SetDrMd(window->RPort, JAM2);
    gfx_clear(PEN_NAVY);
    return 0;
}

void gfx_close(void)
{
    if (window) {
        CloseWindow(window);
        window = NULL;
    }
    if (screen) {
        CloseScreen(screen);
        screen = NULL;
    }
    free_bitmap(&tiles);
    free_bitmap(&tiles8);
    free_bitmap(&sprites);
    free_bitmap(&terrain);
    free_bitmap(&compose);
    if (sprite_mask)
        FreeMem(sprite_mask, sprites.plane_bytes);
    sprite_mask = NULL;
    if (IntuitionBase)
        CloseLibrary((struct Library *)IntuitionBase);
    if (GfxBase)
        CloseLibrary((struct Library *)GfxBase);
    IntuitionBase = NULL;
    GfxBase = NULL;
}

struct Window *gfx_window(void)
{
    return window;
}

void gfx_set_palette(unsigned char palette_id)
{
    if (palette_id >= ART_PALETTE_COUNT)
        palette_id = 0;
    LoadRGB4(&screen->ViewPort, (UWORD *)art_palette[palette_id], 16);
}

void gfx_clear(unsigned char pen)
{
    SetRast(window->RPort, pen);
}

void gfx_fill_rows(unsigned char row, unsigned char count, unsigned char pen)
{
    SetAPen(window->RPort, pen);
    RectFill(window->RPort, 0, row * 8, SCREEN_W - 1, (row + count) * 8 - 1);
}

void gfx_text(unsigned char col, unsigned char row, unsigned char ink,
              unsigned char paper, const char *text, unsigned char len)
{
    struct RastPort *rp = window->RPort;

    if (col >= TEXT_COLS)
        return;
    if (len > TEXT_COLS - col)
        len = TEXT_COLS - col;
    SetAPen(rp, ink);
    SetBPen(rp, paper);
    Move(rp, col * 8, row * 8 + rp->TxBaseline);
    Text(rp, (STRPTR)text, len);
}

/* ------------------------------------------------------------------ */

/* Species (kind & RTS_KIND_MASK) -> sprite, with a second frame for the
 * animated ones. Same table as the Lynx renderer. */
static const unsigned char enemy_art[RTS_KIND_MAX + 1] = {
    ART_SPRITE_BEAVER, ART_SPRITE_BEAVER, ART_SPRITE_SNAKE, ART_SPRITE_BAT0,
    ART_SPRITE_SLIME0, ART_SPRITE_GOBLIN, ART_SPRITE_GORVAK, ART_SPRITE_WILHELM,
    ART_SPRITE_WILHELM
};
static const unsigned char enemy_art_alt[RTS_KIND_MAX + 1] = {
    0, 0, 0, ART_SPRITE_BAT1, ART_SPRITE_SLIME1, 0, 0, 0,
    ART_SPRITE_WILHELM_WORKING
};
static const unsigned char item_art[] = {
    0, ART_SPRITE_ITEM_GOLD, ART_SPRITE_ITEM_STICKS, ART_SPRITE_ITEM_HERB,
    ART_SPRITE_ITEM_POTION, ART_SPRITE_ITEM_KEY
};
/* RTS_FACE_* -> first of two player frames (diagonals use the side view). */
static const unsigned char facing_frame[RTS_FACE_COUNT] = {0, 0, 4, 2, 4, 2, 4, 2};
static const unsigned char remote_facing_frame[RTS_FACE_COUNT] = {6, 6, 10, 8, 10, 8, 10, 8};

static void draw_tile(unsigned char col, unsigned char row, unsigned char id)
{
    if (id >= ART_TILE_COUNT)
        id = 0;
    BltBitMap(&tiles.bm, 0, id * 16, &terrain.bm, col * 16, row * 16, 16, 16,
              MINTERM_COPY, 0xFF, NULL);
}

static void draw_sprite(unsigned x, unsigned y, unsigned origin_x,
                        unsigned origin_y, unsigned char cam_x,
                        unsigned char cam_y, unsigned char sprite)
{
    int col = (int)(x - origin_x) - cam_x;
    int row = (int)(y - origin_y) - cam_y;

    if (col < 0 || col >= VIEW_COLS || row < 0 || row >= VIEW_ROWS)
        return;
    BltMaskBitMapRastPort(&sprites.bm, 0, sprite * 16, &compose_rp,
                          col * 16, row * 16, 16, 16, MINTERM_COOKIE,
                          sprite_mask);
}

void gfx_render_world(const struct rt_state *state, const unsigned char *cache,
                      unsigned origin_x, unsigned origin_y,
                      unsigned char cam_x, unsigned char cam_y,
                      unsigned char facing, unsigned char anim,
                      unsigned char repaint_terrain)
{
    unsigned char r, c, i;

    if (repaint_terrain) {
        for (r = 0; r < VIEW_ROWS; ++r) {
            const unsigned char *line =
                cache + (unsigned)(cam_y + r) * RTS_WINDOW_W + cam_x;
            for (c = 0; c < VIEW_COLS; ++c)
                draw_tile(c, r, line[c]);
        }
    }
    BltBitMap(&terrain.bm, 0, 0, &compose.bm, 0, 0, VIEW_W, VIEW_H,
              MINTERM_COPY, 0xFF, NULL);

    /* Items lie on the ground, so they go under everything that walks. */
    for (i = 0; i < state->item_count; ++i) {
        unsigned char art = rt_item_art_index(state->items[i].item_id);

        if (art != RTS_ART_ITEM_NONE && art < sizeof(item_art))
            draw_sprite(state->items[i].x, state->items[i].y, origin_x, origin_y,
                        cam_x, cam_y, item_art[art]);
    }
    for (i = 0; i < state->beaver_count; ++i) {
        const struct rt_beaver *e = &state->beavers[i];
        unsigned char kind = e->kind > RTS_KIND_MAX ? RTS_KIND_BEAVER : e->kind;
        unsigned char art = enemy_art[kind];

        if (e->hit_timer & 1)
            continue;               /* blink while a hit lands */
        if ((anim & 1) && enemy_art_alt[kind])
            art = enemy_art_alt[kind];
        draw_sprite(e->x, e->y, origin_x, origin_y, cam_x, cam_y, art);
    }
    for (i = 0; i < state->remote_count; ++i) {
        const struct rt_remote_player *p = &state->remotes[i];

        if (!(p->state & RTS_REMOTE_ALIVE))
            continue;
        draw_sprite(p->x, p->y, origin_x, origin_y, cam_x, cam_y,
                    (unsigned char)(remote_facing_frame[p->facing & 7] + (anim & 1)));
    }
    draw_sprite(state->player_x, state->player_y, origin_x, origin_y, cam_x, cam_y,
                (unsigned char)(facing_frame[facing & 7] + (anim & 1)));
    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        if (state->tracers[i].active)
            draw_sprite(state->tracers[i].x, state->tracers[i].y, origin_x,
                        origin_y, cam_x, cam_y, ART_SPRITE_BULLET);
    }

    /* Start the copy at the top of the frame so the beam trails it. */
    WaitTOF();
    BltBitMapRastPort(&compose.bm, 0, 0, window->RPort, 0, 0, VIEW_W, VIEW_H,
                      MINTERM_COPY);
}

void gfx_hud_frame(void)
{
    struct RastPort *rp = window->RPort;

    SetAPen(rp, PEN_NAVY);
    RectFill(rp, 0, VIEW_H, SCREEN_W - 1, SCREEN_H - 1);
    SetAPen(rp, PEN_GREY);
    Move(rp, 0, VIEW_H);
    Draw(rp, SCREEN_W - 1, VIEW_H);
}

void gfx_hud_line(unsigned char line, unsigned char ink, const char *text)
{
    char padded[TEXT_COLS];
    unsigned n = strlen(text);

    if (n > TEXT_COLS)
        n = TEXT_COLS;
    memcpy(padded, text, n);
    memset(padded + n, ' ', TEXT_COLS - n);
    /* Rows 20..24 of the text grid; line 0 sits a pixel below the rule. */
    gfx_text(0, (unsigned char)(HUD_ROW + 1 + line), ink, PEN_NAVY, padded,
             TEXT_COLS);
}

/* ------------------------------------------------------------------ */
/* Splash screen                                                       */

void gfx_cell8(unsigned char col, unsigned char row, unsigned char tile)
{
    if (tile >= ART_TILE_COUNT)
        tile = 0;
    BltBitMapRastPort(&tiles8.bm, 0, tile * 8, window->RPort, col * 8, row * 8,
                      8, 8, MINTERM_COPY);
}

void gfx_sprite_at(int x, int y, unsigned char sprite)
{
    BltMaskBitMapRastPort(&sprites.bm, 0, sprite * 16, window->RPort, x, y,
                          16, 16, MINTERM_COOKIE, sprite_mask);
}

void gfx_set_color(unsigned char pen, unsigned short rgb4)
{
    SetRGB4(&screen->ViewPort, pen, (rgb4 >> 8) & 15, (rgb4 >> 4) & 15, rgb4 & 15);
}
