#include "gime.h"
#include <cmoc.h>

/* Task1's MMU block table ($FFA8-$FFAF). Slots 0-3 are hardcoded to
 * 56-59 -- the top-4-of-64-blocks default a 512K CoCo3 has at cold boot.
 * GIME MMU registers are WRITE-ONLY on real hardware (reads return
 * open-bus garbage), so this can never be read back and verified at
 * runtime; it has to be a known-correct constant, matching how
 * fujinet-battleship/fujinet-fujitzee do it. It is ALSO correct on a 128K
 * (16-block) machine: a 128K GIME can only decode 4 bits of block number,
 * so 56-59 alias to 8-11 -- exactly that machine's own top-8 default.
 * Slots 4-7 are the graphics window, filled at runtime by map_window(). */
static unsigned char task1_blocks[8] = {
    56, 57, 58, 59,
    0, 0, 0, 0
};

/* 5 consecutive blocks per buffer. 128K has only 16 blocks total; 8-15
 * are that machine's own top-8 default (aliased with the hardcoded
 * 56-59 above), leaving just 0-7 genuinely free -- enough for ONE buffer,
 * hence single-buffering on 128K. 512K has 56 blocks free below its own
 * top-8 default (56-63), enough for two 5-block buffers. */
#define BUFFER_BASE_128K 0
#define BUFFER_BASE_512K_A 8
#define BUFFER_BASE_512K_B 13

static unsigned char buffer_base[2];
static unsigned char double_buffered;
static unsigned char draw_idx;

static void map_window(unsigned char first_block)
{
    unsigned char i;

    for (i = 0; i < 4; ++i) {
        task1_blocks[4 + i] = (unsigned char)(first_block + i);
    }
    memcpy((void *)0xFFAC, &task1_blocks[4], 4);
}

void gime_window_playfield(void)
{
    map_window(buffer_base[draw_idx]);
}

unsigned char gime_draw_block(void)
{
    return buffer_base[draw_idx];
}

void gime_window_hud(void)
{
    map_window((unsigned char)(buffer_base[draw_idx] + 1));
}

unsigned char gime_window_hud_shown(void)
{
    if (!double_buffered) {
        return 0;
    }
    map_window((unsigned char)(buffer_base[draw_idx ^ 1] + 1));
    return 1;
}

static void select_draw_buffer(unsigned char idx)
{
    draw_idx = idx;
    gime_window_playfield();
}

static void show_buffer(unsigned char idx)
{
    unsigned int video_addr = (unsigned int)((unsigned long)buffer_base[idx] << 10);
    *(unsigned int *)0xFF9D = video_addr;
}

void gime_init_task1(void)
{
    memcpy((void *)0xFFA8, task1_blocks, 4); /* low-4 only; no buffer chosen yet */
}

void gime_init_mode(void)
{
    INTS_OFF();

    gime_init_task1();

    asm { sync } /* wait for vsync before switching modes */

    *(unsigned char *)0xFF90 = 0x5C; /* INIT0: not CoCo-1/2 mode; FIRQ on */
    *(unsigned char *)0xFF98 = 0x80; /* VMODE: graphics mode on */
    *(unsigned char *)0xFF99 = 0x7E; /* VRES: 225 lines, 160 B/row, 16 colors */
    *(unsigned char *)0xFF9A = 0;    /* border: palette index 0 */

    INTS_RESTORE();
}

void gime_select_buffers(unsigned char is_512k)
{
    if (is_512k) {
        buffer_base[0] = BUFFER_BASE_512K_A;
        buffer_base[1] = BUFFER_BASE_512K_B;
        double_buffered = 1;
    } else {
        buffer_base[0] = BUFFER_BASE_128K;
        buffer_base[1] = BUFFER_BASE_128K;
        double_buffered = 0;
    }

    select_draw_buffer(0);
    show_buffer(0);
}

void gime_flip_display(void)
{
    if (!double_buffered)
        return;

    show_buffer(draw_idx);
    select_draw_buffer((unsigned char)(draw_idx ^ 1));
}

void gime_set_palette(const unsigned char *clut16)
{
    memcpy((void *)0xFFB0, clut16, 16);
}
