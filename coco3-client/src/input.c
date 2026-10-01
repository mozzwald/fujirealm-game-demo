#include "input.h"
#include <coco.h>

/* CMOC/Color BASIC key codes (see ~/fujinet-config/src/key_codes.h's
 * _CMOC_VERSION_ branch -- not part of <coco.h> itself). */
#define KEY_LEFT_ARROW 0x08
#define KEY_RIGHT_ARROW 0x09
#define KEY_ENTER 0x0D
#define KEY_BREAK 0x03

static unsigned char caps_on = 0;
static unsigned char flag_seen = 0;
static unsigned char flag_seen_set = 0;

/* Folds a SHIFT-0 into caps_on: the ROM flips $011A and swallows the key.
 * Only changes to the flag matter, never its value. */
static void caps_sync(void)
{
    unsigned char flag;

    asm {
        lda $011A
        sta :flag
    }
    if (!flag_seen_set) {
        flag_seen = flag;
        flag_seen_set = 1;
    } else if (flag != flag_seen) {
        flag_seen = flag;
        caps_on ^= 1;
    }
}

unsigned char input_caps_locked(void)
{
    caps_sync();
    return caps_on;
}

void input_caps_indicator(unsigned char col, unsigned char row)
{
    locate(col, row);
    printf("%s", input_caps_locked() ? "ABC" : "abc");
}

/* readline()/waitkey() force uppercase, and inkey() reports letter case per
 * the ROM's $011A flag, so letters are normalized to uppercase and re-cased
 * here as SHIFT xor caps lock (fujinet-config's input() does the SHIFT part).
 * Returns 0 when SHIFT-0 toggles the lock, which inkey() swallows. */
static unsigned char input_key(void)
{
    unsigned char k;
    unsigned char was = input_caps_locked();
    unsigned char shifted;

    for (;;) {
        caps_sync();
        if (caps_on != was) {
            return 0;
        }
        k = inkey();
        if (k >= 'a' && k <= 'z') {
            k = (unsigned char)(k - 0x20);
        }
        if (k > '@' && k < '[') {
            shifted = isKeyPressed(KEY_PROBE_SHIFT, KEY_BIT_SHIFT) != 0;
            if (shifted != caps_on) {
                return k;
            }
            return (unsigned char)(k + 0x20);
        }
        if (k) {
            return k;
        }
    }
}

unsigned char input_line(unsigned char col, unsigned char row, char *buf,
                         unsigned char max)
{
    unsigned char x = col;
    char *c = buf;
    unsigned char k;

    locate(col, row);
    while (*c) {
        putchar(*c);
        ++c;
        ++x;
    }

    for (;;) {
        input_caps_indicator(col, (unsigned char)(row + 1));
        locate(x, row);

        k = input_key();

        if (k == 0) {
            continue;
        }
        if (k == KEY_ENTER) {
            return 1;
        }
        if (k == KEY_BREAK) {
            return 0;
        }
        if (k == KEY_LEFT_ARROW) {
            if (c > buf) {
                --c;
                --x;
                *c = 0;
                locate(x, row);
                putchar(' ');
            }
            continue;
        }
        if (k == KEY_RIGHT_ARROW) {
            if (*c) {
                putchar(*c);
                ++c;
                ++x;
            }
            continue;
        }
        if (k < 0x20 || k > 0x7E) {
            continue;
        }
        if ((unsigned char)(c - buf) >= max) {
            continue;
        }

        putchar(k);
        *c = (char)k;
        ++c;
        ++x;
        *c = 0;
    }
}

#define NAME_PROMPT "Enter your name: "
#define NAME_COL 17 /* strlen(NAME_PROMPT) */

unsigned char input_name_entry(char *buf, unsigned char max, const char *note)
{
    unsigned char ok;
    const char *n;

    buf[0] = 0;

    cls(255);
    locate(0, 0);
    printf(NAME_PROMPT);
    if (note) {
        locate(0, 3);
        printf("%s", note);
    }

    do {
        ok = input_line(NAME_COL, 0, buf, max);
    } while (ok && buf[0] == 0);

    locate(NAME_COL, 1);
    printf("   ");
    if (note) {
        locate(0, 3);
        for (n = note; *n; ++n) {
            putchar(' ');
        }
    }
    locate(0, 2);
    return ok;
}
