#include "hudtext.h"
#include "../art/lynx_art.h"

void hud_text_init(unsigned char *buf)
{
    unsigned char row;
    unsigned pos = 0;

    for (row = 0; row < 5; ++row) {
        buf[pos] = HUD_TEXT_ROW_BYTES + 1;
        ++pos;
        pos += HUD_TEXT_ROW_BYTES;
    }
    buf[pos] = 0;
}

static void put_pixel(unsigned char *buf, unsigned char x, unsigned char row,
                      unsigned char ink)
{
    unsigned pos = (unsigned)row * (HUD_TEXT_ROW_BYTES + 1) + 1 + (x >> 1);

    if (x & 1) {
        buf[pos] = (buf[pos] & 0xF0) | ink;
    } else {
        buf[pos] = (buf[pos] & 0x0F) | (ink << 4);
    }
}

void hud_text_render(unsigned char *buf, const char *text, unsigned char len,
                     unsigned char ink)
{
    unsigned char index;
    unsigned char row;
    unsigned char col;
    unsigned char code;
    unsigned char bits;
    unsigned pos;

    for (row = 0; row < 5; ++row) {
        pos = (unsigned)row * (HUD_TEXT_ROW_BYTES + 1) + 1;
        for (col = 0; col < HUD_TEXT_ROW_BYTES; ++col) {
            buf[pos + col] = 0;
        }
    }
    if (len > HUD_TEXT_COLS) {
        len = HUD_TEXT_COLS;
    }
    for (index = 0; index < len; ++index) {
        code = (unsigned char)text[index];
        if (code >= 'a' && code <= 'z') {
            code -= 32;
        }
        if (code < 32 || code > 95) {
            code = '?';
        }
        for (row = 0; row < 5; ++row) {
            bits = art_font4x5[(code - 32) * 5 + row];
            for (col = 0; col < 4; ++col) {
                if (bits & (8 >> col)) {
                    put_pixel(buf, index * 5 + col, row, ink);
                }
            }
        }
    }
}

unsigned char fmt_hex16(char *out, unsigned char pos, unsigned val)
{
    unsigned char shift = 12;

    for (;;) {
        unsigned char nib = (unsigned char)((val >> shift) & 0x0F);

        out[pos++] = (char)(nib < 10 ? ('0' + nib) : ('A' + nib - 10));
        if (shift == 0) {
            break;
        }
        shift -= 4;
    }
    return pos;
}

unsigned char hud_wrap_next(const char *text, unsigned char len,
                            unsigned char *pos, unsigned char width,
                            unsigned char *out_start)
{
    unsigned char at = *pos;
    unsigned char start;
    unsigned char end;
    unsigned char scan;
    unsigned char last_space;

    while (at < len && text[at] == ' ') {
        ++at;
    }
    *out_start = at;
    if (at >= len) {
        *pos = at;
        return 0;
    }

    start = at;
    if ((unsigned char)(len - start) <= width) {
        /* The whole remainder fits. */
        end = len;
        *pos = len;
    } else {
        /* Break at the last space inside the width. Scanning one position past
           the width lets a word that ends exactly at the boundary stay whole. */
        last_space = 0;
        for (scan = start; scan <= start + width && scan < len; ++scan) {
            if (text[scan] == ' ') {
                last_space = scan;
            }
        }
        if (last_space > start) {
            end = last_space;
            *pos = last_space;
        } else {
            /* One word wider than the line: hard-split it. */
            end = start + width;
            *pos = end;
        }
    }

    /* Drop trailing spaces so a run of separators does not eat into the line
       (and so the caller can right-align or centre what it gets back). */
    while (end > start && text[end - 1] == ' ') {
        --end;
    }
    return end - start;
}

unsigned char fmt_u16(char *out, unsigned char pos, unsigned val)
{
    char digits[5];
    unsigned char count = 0;

    do {
        digits[count++] = (char)('0' + val % 10);
        val /= 10;
    } while (val != 0);
    while (count != 0) {
        out[pos++] = digits[--count];
    }
    return pos;
}
