#include "sound.h"
#include <coco.h>
#include <cmoc.h>

/* Sound test: plays each game effect on a key. Boots from its own disk
 * (SNDTEST.dsk). */

static const char *names[SND_COUNT] = {
    0, "Shoot    ", "Hurt     ", "Death    ", "Kill     ", "Level up "
};
static const char *uses[SND_COUNT] = {
    0, "you fire", "you lose health", "you die", "a creature you hit dies",
    "you gain a level"
};
/* Keys 1-5 share KEY_BIT_1. */
static const unsigned char probes[SND_COUNT] = {
    0, KEY_PROBE_1, KEY_PROBE_2, KEY_PROBE_3, KEY_PROBE_4, KEY_PROBE_5
};

#define STATUS_ROW 8

static void show_status(void)
{
    locate(1, STATUS_ROW);
    printf("F2     sound %s", sound_on ? "on " : "off");
}

/* A warm start to BASIC's OK prompt: the loaded program overwrote the BASIC
 * program area, so that is emptied first. */
static void exit_to_basic(void)
{
    unsigned txttab = *(unsigned *)0x19;

    sound_shutdown();
    *(unsigned *)txttab = 0;
    *(unsigned *)0x1B = txttab + 2; /* VARTAB */
    *(unsigned *)0x1D = txttab + 2; /* ARYTAB */
    *(unsigned *)0x1F = txttab + 2; /* ARYEND */
    asm {
        orcc #$50
        jmp [$FFFE]
    }
}

int main(void)
{
    unsigned char i;
    unsigned char down;
    unsigned char was = 0;

    initCoCoSupport();
    *(unsigned char *)0xFFD9 = 0; /* 1.79 MHz */
    width(40);
    printf("FUJIREALM SOUND TEST\n\n");
    for (i = 1; i < SND_COUNT; ++i) {
        printf(" %u     %s %s\n", i, names[i], uses[i]);
    }
    show_status();
    locate(1, STATUS_ROW + 1);
    printf("BREAK  quit");
    sound_init();

    for (;;) {
        down = 0;
        for (i = 1; i < SND_COUNT; ++i) {
            if (isKeyPressed(probes[i], KEY_BIT_1)) {
                down = i;
            }
        }
        if (isKeyPressed(KEY_PROBE_F2, KEY_BIT_F2)) {
            down = 0x80;
        }
        if (isKeyPressed(KEY_PROBE_BREAK, KEY_BIT_BREAK)) {
            exit_to_basic();
        }
        if (down != was) {
            if (down == 0x80) {
                sound_on ^= 1;
                show_status();
            } else if (down != 0) {
                sound_play(down);
            }
            was = down;
        }
    }
    return 0;
}
