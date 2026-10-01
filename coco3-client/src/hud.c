#include "hud.h"
#include "gime.h"
#include "tiles.h"
#include "controls.h"
#include <cmoc.h>

#define HUD_COLS 40
#define HUD_ROWS 3
#define GLYPH_BYTES 8
#define FONT 0xF09DU /* RAM copy of the HPRINT font: chars 32-127, 8 bytes each */

#define HUD_TEXT_COLOR 3  /* white in every palette */
#define HUD_HEART_COLOR 11 /* red in every palette */
/* Characters past the ROM font, drawn from special[]. */
#define HUD_HEART 0x80
#define HUD_SOUND_ON 0x81
#define HUD_SOUND_OFF 0x82

/* Atari HUD line-1 layout (fujirealm.asm HUD_*_X). */
#define HEART_COUNT 6
#define HUD_HEARTS_X 3
#define HUD_LEVEL_LABEL_X (HUD_HEARTS_X + HEART_COUNT)
#define HUD_GOLD_X (HUD_LEVEL_LABEL_X + 6)
#define HUD_PVP_X (HUD_GOLD_X + 8)

/* Atari line order: stats, quest, message. */
#define ROW_STATS 0
#define ROW_QUEST 1
#define ROW_MESSAGE 2

#define QUEST_STATE_COMPLETE 3
#define MESSAGE_TIMEOUT_TICKS 1800
#define NOTE_TICKS 120
#define WALK_X 32
#define NOTE_X 35
#define QUEST_DONE_TIMEOUT_TICKS 600

static const unsigned char text_y[HUD_ROWS] = { 3, 13, 23 };
static const unsigned char special[3][GLYPH_BYTES] = {
    { 0x6C, 0xFE, 0xFE, 0xFE, 0x7C, 0x38, 0x10, 0x00 }, /* heart */
    { 0x0C, 0x0E, 0x0B, 0x08, 0x08, 0x78, 0xF8, 0x70 }, /* eighth note */
    { 0x8C, 0x4E, 0x2B, 0x18, 0x08, 0x7C, 0xFA, 0x71 }, /* the note, struck */
};
static const unsigned char special_color[3] = {
    HUD_HEART_COLOR, HUD_TEXT_COLOR, HUD_HEART_COLOR
};

static char shown[HUD_ROWS][HUD_COLS];
static unsigned char stats_valid;
static unsigned char stats_hp, stats_max, stats_level, stats_pvp;
static unsigned stats_gold, stats_kills;
static unsigned char message_active;
static unsigned message_clk;
static unsigned char quest_hidden;
static const char *note_text;
static unsigned note_clk;
static unsigned char note_on;
static unsigned char status_walk;
static unsigned char status_sound;
static unsigned quest_clk;

void gfx_copy8(unsigned char *dst, const unsigned char *src,
               unsigned char blocks)
{
    asm {
        pshs y
        ldx :dst
        ldy :src
        ldb :blocks
        pshs b
hud_copy8_loop:
        ldd ,y
        std ,x
        ldd 2,y
        std 2,x
        ldd 4,y
        std 4,x
        ldd 6,y
        std 6,x
        leax 8,x
        leay 8,y
        dec ,s
        bne hud_copy8_loop
        leas 1,s
        puls y
    }
}

static void fetch_glyph(unsigned char c, unsigned char *out)
{
    memcpy(out, (const void *)(FONT + (unsigned)(c - 32) * GLYPH_BYTES),
           GLYPH_BYTES);
}

/* Draws character c at dst in whatever the window maps, 160-byte rows. */
static void glyph_draw(unsigned char *dst, unsigned char c)
{
    unsigned char glyph[GLYPH_BYTES];
    unsigned char tbl[4];
    unsigned char fg = HUD_TEXT_COLOR;
    unsigned char r, g;

    if (c >= HUD_HEART && c <= HUD_SOUND_OFF) {
        memcpy(glyph, special[c - HUD_HEART], GLYPH_BYTES);
        fg = special_color[c - HUD_HEART];
    } else {
        if (c < 32 || c > 127) {
            c = ' ';
        }
        fetch_glyph(c, glyph);
    }
    tbl[0] = 0;
    tbl[1] = fg;
    tbl[2] = (unsigned char)(fg << 4);
    tbl[3] = (unsigned char)((fg << 4) | fg);

    GFX_ENTER();
    for (r = 0; r < GLYPH_BYTES; ++r) {
        g = glyph[r];
        dst[0] = tbl[g >> 6];
        dst[1] = tbl[(g >> 4) & 3];
        dst[2] = tbl[(g >> 2) & 3];
        dst[3] = tbl[g & 3];
        dst += HUD_IMAGE_STRIDE;
    }
    GFX_LEAVE();
}

static void draw_char(unsigned char row, unsigned char col, unsigned char c)
{
    *(unsigned char *)0xFFAC = HUD_IMAGE_BLOCK;
    glyph_draw(GFX_WINDOW + (unsigned)text_y[row] * HUD_IMAGE_STRIDE + col * 4, c);
}

void text_draw(unsigned char col, unsigned char row, const char *s)
{
    unsigned char *dst = GFX_WINDOW + (unsigned)row * (8 * BYTES_PER_ROW) + col * 4;

    while (*s) {
        glyph_draw(dst, (unsigned char)*s++);
        dst += 4;
    }
}

/* Draws the cells of line that differ from what is shown. */
static unsigned char put_line(unsigned char row, const char *line)
{
    unsigned char col;
    unsigned char changed = 0;
    char *seen = shown[row];

    for (col = 0; col < HUD_COLS; ++col) {
        if (seen[col] != line[col]) {
            controls_poll();
            seen[col] = line[col];
            draw_char(row, col, (unsigned char)line[col]);
            changed = 1;
        }
    }
    return changed;
}

static unsigned char put_text(unsigned char row, const char *text,
                              unsigned char len)
{
    char line[HUD_COLS];

    memset(line, ' ', HUD_COLS);
    memcpy(line, text, len > HUD_COLS ? HUD_COLS : len);
    return put_line(row, line);
}

/* Zero-padded, clamped to ndigits (Atari hud_draw_two/four_digits). */
static void put_digits(char *p, unsigned value, unsigned char ndigits)
{
    unsigned max = ndigits == 2 ? 99 : 9999;

    if (value > max) {
        value = max;
    }
    while (ndigits != 0) {
        --ndigits;
        p[ndigits] = (char)('0' + value % 10);
        value /= 10;
    }
}

static unsigned char put_stats(void)
{
    char line[HUD_COLS];
    unsigned char full = 0;
    unsigned char i;

    if (stats_max != 0) {
        full = (unsigned char)(((unsigned)stats_hp * HEART_COUNT) / stats_max);
        if (full > HEART_COUNT) {
            full = HEART_COUNT;
        }
    }
    memset(line, ' ', HUD_COLS);
    line[0] = 'H';
    line[1] = 'P';
    for (i = 0; i < full; ++i) {
        line[HUD_HEARTS_X + i] = (char)HUD_HEART;
    }
    line[HUD_LEVEL_LABEL_X + 1] = 'L';
    line[HUD_LEVEL_LABEL_X + 2] = ':';
    put_digits(&line[HUD_LEVEL_LABEL_X + 3], stats_level, 2);
    line[HUD_GOLD_X] = 'G';
    line[HUD_GOLD_X + 1] = ':';
    put_digits(&line[HUD_GOLD_X + 2], stats_gold, 4);
    if (stats_pvp) {
        line[HUD_PVP_X] = 'P';
        line[HUD_PVP_X + 1] = 'V';
        line[HUD_PVP_X + 2] = 'P';
        line[HUD_PVP_X + 3] = ':';
        put_digits(&line[HUD_PVP_X + 4], stats_kills, 4);
    }
    line[WALK_X] = 'V';
    line[WALK_X + 1] = (char)('0' + status_walk);
    if (note_on) {
        memcpy(&line[NOTE_X], note_text, 3);
    } else if (status_sound) {
        line[NOTE_X] = (char)HUD_SOUND_ON;
    } else {
        line[NOTE_X] = (char)HUD_SOUND_OFF;
    }
    return put_line(ROW_STATS, line);
}

void hud_note(const char *text, unsigned now)
{
    note_text = text;
    note_clk = now;
    note_on = 1;
    stats_valid = 0;
}

void hud_set_sound(unsigned char on)
{
    if (on != status_sound) {
        status_sound = on;
        stats_valid = 0;
    }
}

void hud_set_walk(unsigned char walk)
{
    if (walk != status_walk) {
        status_walk = walk;
        stats_valid = 0;
    }
}

void hud_init(void)
{
    unsigned char k;

    *(unsigned char *)0xFFAC = HUD_IMAGE_BLOCK;
    for (k = 0; k < 3; ++k) {
        GFX_ENTER();
        memset(GFX_WINDOW + (unsigned)k * 11 * HUD_IMAGE_STRIDE, 0,
               11 * HUD_IMAGE_STRIDE);
        GFX_LEAVE();
    }
    memset(shown, ' ', sizeof(shown));
    stats_valid = 0;
    message_active = 0;
    quest_hidden = 0;
    note_on = 0;
    gime_window_playfield();
}

unsigned char hud_update(struct rt_state *st, unsigned now)
{
    unsigned char changed = 0;
    unsigned char hp = st->hud_seen ? st->hud_hp : st->health;
    unsigned char max = st->hud_seen ? st->hud_max_hp : 0;
    unsigned char level = st->hud_seen ? st->hud_level : 1;

    /* Signed: note_clk can be a tick after now (F1's appkey write). */
    if (note_on && (int)(now - note_clk) >= NOTE_TICKS) {
        note_on = 0;
        stats_valid = 0;
    }

    if (!stats_valid || hp != stats_hp || max != stats_max ||
        level != stats_level || st->hud_gold != stats_gold ||
        st->hud_pvp_enabled != stats_pvp || st->hud_pvp_kills != stats_kills) {
        stats_valid = 1;
        stats_hp = hp;
        stats_max = max;
        stats_level = level;
        stats_gold = st->hud_gold;
        stats_pvp = st->hud_pvp_enabled;
        stats_kills = st->hud_pvp_kills;
        changed |= put_stats();
    }

    /* A completed quest's line stays up for a while, then clears. */
    if (st->quest_dirty) {
        st->quest_dirty = 0;
        quest_hidden = 0;
        quest_clk = now;
        changed |= put_text(ROW_QUEST, st->quest_text, st->quest_len);
    } else if (!quest_hidden && st->quest_state == QUEST_STATE_COMPLETE &&
               (unsigned)(now - quest_clk) >= QUEST_DONE_TIMEOUT_TICKS) {
        quest_hidden = 1;
        changed |= put_text(ROW_QUEST, "", 0);
    }

    if (st->message_dirty) {
        st->message_dirty = 0;
        message_active = 1;
        message_clk = now;
        changed |= put_text(ROW_MESSAGE, st->message, st->message_len);
    } else if (message_active &&
               (unsigned)(now - message_clk) >= MESSAGE_TIMEOUT_TICKS) {
        message_active = 0;
        changed |= put_text(ROW_MESSAGE, "", 0);
    }

    if (changed) {
        gime_window_playfield();
    }
    return changed;
}

/* Copies the image into the HUD strip mapped at HUD_WINDOW, which leaves
 * slot 4 free to hold the image. 11 lines per bracket to keep interrupts
 * masked briefly. */
static void blit_mapped(void)
{
    unsigned char k;
    unsigned off;

    *(unsigned char *)0xFFAC = HUD_IMAGE_BLOCK;
    for (k = 0; k < 3; ++k) {
        off = (unsigned)k * 11 * HUD_IMAGE_STRIDE;
        GFX_ENTER();
        gfx_copy8(HUD_WINDOW + off, GFX_WINDOW + off,
                  11 * HUD_IMAGE_STRIDE / 8);
        GFX_LEAVE();
    }
}

void hud_blit(unsigned char both)
{
    gime_window_hud();
    blit_mapped();
    if (both && gime_window_hud_shown()) {
        blit_mapped();
    }
    gime_window_playfield();
}
