/*
 * Startup splash: "FUJINET / REALMS" spelled in the game's own terrain
 * tiles on a 40x25 grid of 8x8 cells, extruded in 3D (a two-step stone and
 * cave-wall shadow behind each letter), over a meadow with the cast lined
 * up below. The water shimmers by cycling two palette entries, which costs
 * the 68000 nothing, and a bat flaps. Any key, click or fire continues.
 */
#include <string.h>

#include <proto/dos.h>

#include "amiga_art.h"
#include "gfx.h"
#include "input.h"
#include "splash.h"

/* Shared tile ids (docs/TILE_ALLOCATION.md), named for how they look. */
#define T_GRASS 0
#define T_TREE 2
#define T_HERB 3
#define T_ROAD 10
#define T_WATER 11
#define T_STONE 12              /* "Building": grey mossy stone */
#define T_SANDSTONE 13          /* "Cave Entrance": sandstone blocks */
#define T_BLACK 15              /* "Cave Floor": plain black */

#define COLS 40
#define BANNER_ROW 22
#define ROWS 25
#define SPLASH_TIMEOUT_MS 15000L
#define BLINK_TICKS 25          /* 1/50 s */
#define SHIMMER_TICKS 6

/* 4x5 block font, bit 3 = leftmost column. */
struct glyph {
    char ch;
    unsigned char rows[5];
};
static const struct glyph font[] = {
    {'F', {0xF, 0x8, 0xE, 0x8, 0x8}}, {'U', {0x9, 0x9, 0x9, 0x9, 0xF}},
    {'J', {0x1, 0x1, 0x1, 0x9, 0xF}}, {'I', {0xF, 0x6, 0x6, 0x6, 0xF}},
    {'N', {0x9, 0xD, 0xB, 0x9, 0x9}}, {'E', {0xF, 0x8, 0xE, 0x8, 0xF}},
    {'T', {0xF, 0x6, 0x6, 0x6, 0x6}}, {'R', {0xE, 0x9, 0xE, 0xA, 0x9}},
    {'A', {0x6, 0x9, 0xF, 0x9, 0x9}}, {'L', {0x8, 0x8, 0x8, 0x8, 0xF}},
    {'M', {0x9, 0xF, 0xF, 0x9, 0x9}}, {'S', {0xF, 0x8, 0xF, 0x1, 0xF}},
};

static unsigned char bg[ROWS][COLS];

static const struct glyph *glyph_for(char ch)
{
    unsigned i;

    for (i = 0; i < sizeof font / sizeof font[0]; ++i)
        if (font[i].ch == ch)
            return &font[i];
    return NULL;
}

/* Stamp a word into bg[]: extrusion two cells deep (black shadow first,
 * so the nearer grey stone side overlaps it), then the lit face on top. The extrusion
 * falls in the one-cell gaps, which is what keeps the letters apart. */
static void stamp_word(const char *word, int col, int row, unsigned char face)
{
    static const struct { int d; unsigned char tile; } layers[] = {
        {2, T_BLACK}, {1, T_STONE}, {0, 0},
    };
    unsigned l;

    for (l = 0; l < 3; ++l) {
        int d = layers[l].d, c = col;
        const char *p;

        for (p = word; *p; ++p, c += 5) {
            const struct glyph *g = glyph_for(*p);
            int y, x;

            if (!g)
                continue;
            for (y = 0; y < 5; ++y)
                for (x = 0; x < 4; ++x)
                    if (g->rows[y] & (8 >> x))
                        bg[row + y + d][c + x + d] = d ? layers[l].tile : face;
        }
    }
}

static void build_scene(void)
{
    unsigned long seed = 0x46524C4DUL;     /* "FRLM": the same meadow each time */
    int r, c;

    for (r = 0; r < ROWS; ++r) {
        for (c = 0; c < COLS; ++c) {
            unsigned char t = T_GRASS;

            seed = seed * 1103515245UL + 12345UL;
            if (r == 0)
                t = (c & 1) ? T_TREE : T_GRASS;       /* treeline */
            else if (r == ROWS - 1)
                t = T_WATER;                           /* river */
            else if (r == 20)
                t = T_ROAD;                            /* the road the cast stands on */
            else if ((r < 2 || r > 17) || c < 2 || c > 37) {
                unsigned v = (unsigned)(seed >> 16) % 23;

                t = v == 0 ? T_TREE : v == 1 ? T_HERB : T_GRASS;
            }
            bg[r][c] = (unsigned char)t;
        }
    }
    /* FUJINET is 34 cells wide, REALMS 29; both centred with room for the
     * two-cell extrusion. */
    stamp_word("FUJINET", 2, 2, T_WATER);
    stamp_word("REALMS", 5, 10, T_SANDSTONE);
}

static void paint_rows(int from, int to)
{
    int r, c;

    for (r = from; r <= to; ++r)
        for (c = 0; c < COLS; ++c)
            gfx_cell8((unsigned char)c, (unsigned char)r, bg[r][c]);
}

static void paint_cast(void)
{
    /* Hero facing right, squaring up to the goblin; beaver and slime
     * behind. 16x16 sprites standing on the road (row 20). */
    gfx_sprite_at(12 * 8, 18 * 8 + 4, 2);                  /* player, right */
    gfx_sprite_at(17 * 8, 18 * 8 + 4, ART_SPRITE_GOBLIN);
    gfx_sprite_at(21 * 8, 18 * 8 + 4, ART_SPRITE_BEAVER);
    gfx_sprite_at(25 * 8, 18 * 8 + 4, ART_SPRITE_SLIME0);
}

static void paint_bat(int frame)
{
    /* Restore the 2x2 cells under the bat, then draw the new frame. */
    gfx_cell8(34, 18, bg[18][34]);
    gfx_cell8(35, 18, bg[18][35]);
    gfx_cell8(34, 19, bg[19][34]);
    gfx_cell8(35, 19, bg[19][35]);
    gfx_sprite_at(34 * 8, 18 * 8, frame ? ART_SPRITE_BAT1 : ART_SPRITE_BAT0);
}

/* The captions sit on a plain navy banner (rows 22-23) so they read
 * cleanly, and the prompt blinks by redrawing one line of text. */
static void paint_prompt(int on)
{
    static const char prompt[] = "PRESS ANY KEY OR CLICK";

    gfx_text((COLS - (sizeof prompt - 1)) / 2, BANNER_ROW + 1,
             on ? PEN_GOLD : PEN_NAVY, PEN_NAVY, prompt, sizeof prompt - 1);
}

static int any_input(void)
{
    int pressed = 0;

    input_poll();
    while (input_char() >= 0)
        pressed = 1;
    return pressed || input_fire() || input_use() || input_quit() ||
           input_mouse_left() || input_mouse_right_click() ||
           input_dir() != INPUT_NONE;
}

void splash_show(void)
{
    /* Water blues (pens 9 and 10), cycled for the shimmer. */
    static const unsigned short blue9[] = {0x37C, 0x48D, 0x59E, 0x48D};
    static const unsigned short blue10[] = {0x9CE, 0xADF, 0xBEF, 0xADF};
    static const char sub[] = "AMIGA  -  FUJINET NIO  -  KICKSTART 1.3";
    long waited = 0;
    int tick = 0, blink = 1, bat = 0, phase = 0;

    gfx_set_palette(0);
    build_scene();
    paint_rows(0, ROWS - 1);
    paint_cast();
    paint_bat(0);
    gfx_fill_rows(BANNER_ROW, 2, PEN_NAVY);
    gfx_text((COLS - (sizeof sub - 1)) / 2, BANNER_ROW, PEN_WHITE, PEN_NAVY,
             sub, sizeof sub - 1);
    paint_prompt(1);

    /* Let go of whatever launched us (a double-click, Return). */
    while (any_input() && waited < 50) {
        Delay(1);
        ++waited;
    }
    for (waited = 0; waited < SPLASH_TIMEOUT_MS / 20; ++waited, ++tick) {
        if (any_input())
            break;
        if (tick % SHIMMER_TICKS == 0) {
            phase = (phase + 1) & 3;
            gfx_set_color(9, blue9[phase]);
            gfx_set_color(10, blue10[phase]);
        }
        if (tick % 10 == 0)
            paint_bat(bat ^= 1);
        if (tick % BLINK_TICKS == 0)
            paint_prompt(blink ^= 1);
        Delay(1);
    }
    gfx_set_palette(0);         /* undo the colour cycling */
    input_flush_chars();
}
