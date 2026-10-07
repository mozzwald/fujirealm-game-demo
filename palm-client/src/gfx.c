#include <PalmOS.h>

#include "gfx.h"

/* GFX_DEPTH (from the Makefile) picks the art: 1 draws the hand-made 1-bit
 * tileset on the default black-and-white screen; 2 switches the screen to
 * four greys and draws the grey tileset; 8 switches a colour Palm (OS 3.5
 * and later) to 256 colours and draws the Lynx art itself. Every depth
 * composes the view in one buffer and draws it with a single WinDrawBitmap.
 * At 1 and 2 bpp the buffer holds one Row per tile column per pixel row (8
 * pixels, leftmost in the top bits, which is also a Palm bitmap's byte
 * order), and since every sprite sits on the tile grid, composing is
 * whole-row masking. At 8 bpp it is one byte per pixel. */
#ifndef GFX_DEPTH
#define GFX_DEPTH 1
#endif

/* The art is compiled into this file, not linked: see palm_art.h. */
#if GFX_DEPTH == 8
#define ART_COLOUR
#elif GFX_DEPTH == 2
#define ART_GREY
#else
#define ART_MONO
#endif
#include "palm_art.c"

#if GFX_DEPTH == 8
typedef UInt8 Row;          /* one pixel */
#define VIEW_ROW_UNITS VIEW_W
#define SMALL_ROW_BYTES 16
#elif GFX_DEPTH == 2
typedef UInt16 Row;
#define TILES art_tiles
#define SPRITES art_sprites
#define MASKS art_masks
#else
typedef UInt8 Row;
#define TILES art_tiles1
#define SPRITES art_sprites1
#define MASKS art_masks1
#endif
#ifndef VIEW_ROW_UNITS
#define VIEW_ROW_UNITS VIEW_COLS
#define SMALL_ROW_BYTES (2 * GFX_DEPTH)
#endif

typedef struct {
    BitmapType hdr;
    Row bits[VIEW_H * VIEW_ROW_UNITS];
} ViewBitmap;

/* One sprite doubled to 16x16, for the title screen. */
typedef struct {
    BitmapType hdr;
    UInt8 bits[16 * SMALL_ROW_BYTES];
} SmallBitmap;

static ViewBitmap *view;
static SmallBitmap small;
static UInt8 depth = GFX_DEPTH;

#if GFX_DEPTH == 8
/* Lynx pen -> this screen's palette index, for the current map's tint. */
static UInt8 pen_index[16];
static UInt8 white_index;

/* The art expanded to this screen's palette indices for the current tint,
 * rebuilt by gfx_set_palette: drawing is then long-word copies, not a nibble
 * unpack and a palette lookup per pixel (which cost the colour build half
 * its frame rate on a 20 MHz Dragonball). sprite_mask has a bit per opaque
 * pixel, bit 7 leftmost. */
typedef struct {
    UInt8 tiles[ART_TILE_COUNT][64];
    UInt8 sprites[ART_SPRITE_COUNT][64];
    UInt8 sprite_mask[ART_SPRITE_COUNT][8];
} ColourCache;
static ColourCache *cache8;

static void expand(const UInt8 *packed, UInt8 *out, UInt8 *mask)
{
    UInt8 i;

    for (i = 0; i < 64; ++i) {
        UInt8 pen = (i & 1) ? (packed[i >> 1] & 15) : (packed[i >> 1] >> 4);

        out[i] = pen_index[pen];
        if (mask && pen)
            mask[i >> 3] |= (UInt8)(0x80 >> (i & 7));
    }
}

void gfx_set_palette(unsigned char palette_id)
{
    RGBColorType rgb;
    UInt8 i;

    if (palette_id >= ART_PALETTE_COUNT)
        palette_id = 0;
    for (i = 0; i < 16; ++i) {
        rgb.index = 0;
        rgb.r = art_palettes[palette_id][i][0];
        rgb.g = art_palettes[palette_id][i][1];
        rgb.b = art_palettes[palette_id][i][2];
        pen_index[i] = WinRGBToIndex(&rgb);
    }
    rgb.r = rgb.g = rgb.b = 255;
    white_index = WinRGBToIndex(&rgb);
    if (!cache8)
        return;
    MemSet(cache8->sprite_mask, sizeof cache8->sprite_mask, 0);
    for (i = 0; i < ART_TILE_COUNT; ++i)
        expand(art_tiles8[i], cache8->tiles[i], NULL);
    for (i = 0; i < ART_SPRITE_COUNT; ++i)
        expand(art_sprites8[i], cache8->sprites[i], cache8->sprite_mask[i]);
}
#else
void gfx_set_palette(unsigned char palette_id)
{
    (void)palette_id;
}
#endif

static void init_header(BitmapType *hdr, Int16 w, Int16 h, UInt16 row_bytes,
                        UInt8 pixel_size)
{
    MemSet(hdr, sizeof(*hdr), 0);
    hdr->width = w;
    hdr->height = h;
    hdr->rowBytes = row_bytes;
    hdr->pixelSize = pixel_size;
    hdr->version = 1;
}

int gfx_open(void)
{
#if GFX_DEPTH > 1
    UInt32 want = GFX_DEPTH, got = 1;

    /* Believe only what the screen reports after the request. */
    WinScreenMode(winScreenModeSet, NULL, NULL, &want, NULL);
    if (WinScreenMode(winScreenModeGet, NULL, NULL, &got, NULL) != errNone ||
        got != GFX_DEPTH)
        return 1;
#endif
#if GFX_DEPTH == 8
    cache8 = MemPtrNew(sizeof(ColourCache));
    if (!cache8)
        return 1;
    gfx_set_palette(0);
#endif
    view = MemPtrNew(sizeof(ViewBitmap));
    if (!view)
        return 1;
    init_header(&view->hdr, VIEW_W, VIEW_H, VIEW_ROW_UNITS * sizeof(Row), depth);
    return 0;
}

unsigned char gfx_depth(void)
{
    return depth;
}

void gfx_close(void)
{
    if (view)
        MemPtrFree(view);
    view = NULL;
#if GFX_DEPTH == 8
    if (cache8)
        MemPtrFree(cache8);
    cache8 = NULL;
#endif
#if GFX_DEPTH > 1
    WinScreenMode(winScreenModeSetToDefaults, NULL, NULL, NULL, NULL);
#endif
}

/* ------------------------------------------------------------------ */

/* Species (kind & RTS_KIND_MASK) -> sprite, with a second frame for the
 * animated ones. Same tables as the Lynx and Amiga renderers. */
static const UInt8 enemy_art[RTS_KIND_MAX + 1] = {
    ART_SPRITE_BEAVER, ART_SPRITE_BEAVER, ART_SPRITE_SNAKE, ART_SPRITE_BAT0,
    ART_SPRITE_SLIME0, ART_SPRITE_GOBLIN, ART_SPRITE_GORVAK, ART_SPRITE_WILHELM,
    ART_SPRITE_WILHELM
};
static const UInt8 enemy_art_alt[RTS_KIND_MAX + 1] = {
    0, 0, 0, ART_SPRITE_BAT1, ART_SPRITE_SLIME1, 0, 0, 0,
    ART_SPRITE_WILHELM_WORKING
};
static const UInt8 item_art[] = {
    0, ART_SPRITE_ITEM_GOLD, ART_SPRITE_ITEM_STICKS, ART_SPRITE_ITEM_HERB,
    ART_SPRITE_ITEM_POTION, ART_SPRITE_ITEM_KEY
};
/* RTS_FACE_* -> first of two player frames (diagonals use the side view). */
static const UInt8 facing_frame[RTS_FACE_COUNT] = {0, 0, 4, 2, 4, 2, 4, 2};
static const UInt8 remote_facing_frame[RTS_FACE_COUNT] = {6, 6, 10, 8, 10, 8, 10, 8};

#if GFX_DEPTH == 8
static void draw_tile(UInt8 col, UInt8 row, UInt8 id)
{
    const UInt32 *src;
    UInt32 *dst = (UInt32 *)(view->bits + (UInt16)row * TILE_PX * VIEW_W + col * TILE_PX);
    UInt8 y;

    if (id >= ART_TILE_COUNT)
        id = 0;
    src = (const UInt32 *)cache8->tiles[id];
    for (y = 0; y < TILE_PX; ++y, dst += VIEW_W / 4) {
        dst[0] = *src++;
        dst[1] = *src++;
    }
}

static void draw_sprite(unsigned x, unsigned y, unsigned origin_x, unsigned origin_y,
                        UInt8 cam_x, UInt8 cam_y, UInt8 sprite)
{
    Int16 col = (Int16)(x - origin_x) - cam_x;
    Int16 row = (Int16)(y - origin_y) - cam_y;
    const UInt8 *src, *mask;
    UInt8 *dst;
    UInt8 i, j;

    if (col < 0 || col >= VIEW_COLS || row < 0 || row >= VIEW_ROWS)
        return;
    src = cache8->sprites[sprite];
    mask = cache8->sprite_mask[sprite];
    dst = view->bits + (UInt16)row * TILE_PX * VIEW_W + col * TILE_PX;
    for (i = 0; i < TILE_PX; ++i, dst += VIEW_W, src += TILE_PX) {
        UInt8 m = mask[i];

        for (j = 0; m; ++j, m <<= 1)
            if (m & 0x80)
                dst[j] = src[j];
    }
}
#else
static void draw_tile(UInt8 col, UInt8 row, UInt8 id)
{
    const Row *src;
    Row *dst = view->bits + (UInt16)row * TILE_PX * VIEW_COLS + col;
    UInt8 y;

    if (id >= ART_TILE_COUNT)
        id = 0;
    src = TILES[id];
    for (y = 0; y < TILE_PX; ++y, dst += VIEW_COLS)
        *dst = src[y];
}

static void draw_sprite(unsigned x, unsigned y, unsigned origin_x, unsigned origin_y,
                        UInt8 cam_x, UInt8 cam_y, UInt8 sprite)
{
    Int16 col = (Int16)(x - origin_x) - cam_x;
    Int16 row = (Int16)(y - origin_y) - cam_y;
    const Row *data, *mask;
    Row *dst;
    UInt8 i;

    if (col < 0 || col >= VIEW_COLS || row < 0 || row >= VIEW_ROWS)
        return;
    data = SPRITES[sprite];
    mask = MASKS[sprite];
    dst = view->bits + (UInt16)row * TILE_PX * VIEW_COLS + col;
    for (i = 0; i < TILE_PX; ++i, dst += VIEW_COLS)
        *dst = (Row)((*dst & ~mask[i]) | data[i]);
}
#endif

void gfx_render_world(const struct rt_state *state, const unsigned char *cache,
                      unsigned origin_x, unsigned origin_y,
                      unsigned char cam_x, unsigned char cam_y,
                      unsigned char facing, unsigned char anim)
{
    UInt8 r, c, i;

    for (r = 0; r < VIEW_ROWS; ++r) {
        const unsigned char *line = cache + (unsigned)(cam_y + r) * RTS_WINDOW_W + cam_x;

        for (c = 0; c < VIEW_COLS; ++c)
            draw_tile(c, r, line[c]);
    }
    /* Items lie on the ground, so they go under everything that walks. */
    for (i = 0; i < state->item_count; ++i) {
        UInt8 art = rt_item_art_index(state->items[i].item_id);

        if (art != RTS_ART_ITEM_NONE && art < sizeof(item_art))
            draw_sprite(state->items[i].x, state->items[i].y, origin_x, origin_y,
                        cam_x, cam_y, item_art[art]);
    }
    for (i = 0; i < state->beaver_count; ++i) {
        const struct rt_beaver *e = &state->beavers[i];
        UInt8 kind = e->kind > RTS_KIND_MAX ? RTS_KIND_BEAVER : e->kind;
        UInt8 art = enemy_art[kind];

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
                    (UInt8)(remote_facing_frame[p->facing & 7] + (anim & 1)));
    }
    draw_sprite(state->player_x, state->player_y, origin_x, origin_y, cam_x, cam_y,
                (UInt8)(facing_frame[facing & 7] + (anim & 1)));
    for (i = 0; i < RTS_MAX_TRACERS; ++i) {
        if (state->tracers[i].active)
            draw_sprite(state->tracers[i].x, state->tracers[i].y, origin_x,
                        origin_y, cam_x, cam_y, ART_SPRITE_BULLET);
    }
    WinDrawBitmap(&view->hdr, 0, 0);
}

/* ------------------------------------------------------------------ */
/* Text                                                                */

void gfx_clear(void)
{
    RectangleType r;

    RctSetRectangle(&r, 0, 0, SCREEN_W, SCREEN_H);
    WinEraseRectangle(&r, 0);
}

void gfx_fill(int x, int y, int w, int h, int black)
{
    RectangleType r;

    RctSetRectangle(&r, x, y, w, h);
    if (black)
        WinDrawRectangle(&r, 0);
    else
        WinEraseRectangle(&r, 0);
}

void gfx_text(int x, int y, const char *text, int bold)
{
    FontID old = FntSetFont(bold ? boldFont : stdFont);

    WinDrawChars(text, StrLen(text), x, y);
    FntSetFont(old);
}

void gfx_text_right(int right, int y, const char *text)
{
    FontID old = FntSetFont(stdFont);
    Int16 len = StrLen(text);

    WinDrawChars(text, len, right - FntCharsWidth(text, len), y);
    FntSetFont(old);
}

int gfx_wrap(int x, int y, int width, int max_y, const char *text, unsigned len)
{
    FontID old = FntSetFont(stdFont);
    Int16 line_h = FntLineHeight();
    char buf[RTS_DLG_PAGE_MAX + 1];
    const char *p;

    if (len > RTS_DLG_PAGE_MAX)
        len = RTS_DLG_PAGE_MAX;
    MemMove(buf, text, len);
    buf[len] = '\0';
    p = buf;
    while (*p && y + line_h <= max_y) {
        UInt16 n = FntWordWrap(p, width);
        UInt16 shown = n;

        if (n == 0)
            break;
        while (shown > 0 && (p[shown - 1] == ' ' || p[shown - 1] == '\n'))
            --shown;
        WinDrawChars(p, shown, x, y);
        p += n;
        y += line_h;
    }
    FntSetFont(old);
    return y;
}

void gfx_frame(int x, int y, int w, int h)
{
    RectangleType r;

    RctSetRectangle(&r, x, y, w, h);
    WinDrawRectangleFrame(rectangleFrame, &r);
}

/* ------------------------------------------------------------------ */
/* HUD                                                                 */

#define HUD_LINE_H 11

void gfx_hud_frame(void)
{
    gfx_fill(0, VIEW_H, SCREEN_W, SCREEN_H - VIEW_H, 0);
    WinDrawLine(0, VIEW_H, SCREEN_W - 1, VIEW_H);
}

void gfx_hud_line(unsigned char line, const char *text)
{
    FontID old = FntSetFont(stdFont);
    Int16 len = StrLen(text), y = HUD_Y + 1 + line * HUD_LINE_H;
    Int16 width = SCREEN_W - 2;
    Boolean fits;

    gfx_fill(0, y, SCREEN_W, HUD_LINE_H, 0);
    FntCharsInWidth(text, &width, &len, &fits);
    WinDrawChars(text, len, 1, y);
    FntSetFont(old);
}

void gfx_hud_wrap(unsigned char first, unsigned char count, const char *text)
{
    Int16 y = HUD_Y + 1 + first * HUD_LINE_H;

    gfx_fill(0, y, SCREEN_W, count * HUD_LINE_H, 0);
    gfx_wrap(1, y, SCREEN_W - 2, y + count * HUD_LINE_H, text, StrLen(text));
}

/* ------------------------------------------------------------------ */

void gfx_sprite_at(int x, int y, unsigned char sprite)
{
    UInt8 r, c;

    if (sprite >= ART_SPRITE_COUNT)
        return;
    init_header(&small.hdr, 16, 16, SMALL_ROW_BYTES, GFX_DEPTH);
    MemSet(small.bits, sizeof small.bits, 0);
    for (r = 0; r < 16; ++r) {
#if GFX_DEPTH == 8
        for (c = 0; c < 16; ++c) {
            UInt8 py = (UInt8)(r >> 1), px = (UInt8)(c >> 1);

            small.bits[r * 16 + c] =
                (cache8->sprite_mask[sprite][py] & (0x80 >> px)) ?
                cache8->sprites[sprite][py * 8 + px] : white_index;
        }
#else
        Row row = SPRITES[sprite][r >> 1];

        for (c = 0; c < 16; ++c) {
#if GFX_DEPTH == 2
            UInt8 grey = (UInt8)((row >> (14 - 2 * (c >> 1))) & 3);

            small.bits[r * 4 + (c >> 2)] |= (UInt8)(grey << (6 - 2 * (c & 3)));
#else
            if (row & (0x80 >> (c >> 1)))
                small.bits[r * 2 + (c >> 3)] |= (UInt8)(0x80 >> (c & 7));
#endif
        }
#endif
    }
    WinDrawBitmap(&small.hdr, x, y);
}
