#include "ovl_api.h"
#include "rt_state.h"
#include "gime.h"
#include <coco.h>
#include <cmoc.h>

/* Built as its own program at the start of the overlay region (see
 * ovl_api.h). No CMOC startup code: the game calls ovl_entry directly, and
 * zeroes the overlay's variables first. */

unsigned char ovl_entry(const struct ovl_api *api, unsigned char which);
void show_dialogue(const struct ovl_api *api);
void show_quest_offer(const struct ovl_api *api);

/* The linker needs a program_start. */
void ovl_start(void)
{
    asm {
        EXPORT program_start
program_start
        jmp _ovl_entry
    }
}

static unsigned char fire_mask;

/* ENTER, SPACE, or the selected joystick's button 1. */
static unsigned char close_key_down(void)
{
    return (readJoystickButtons() & fire_mask) != fire_mask ||
           isKeyPressed(KEY_PROBE_ENTER, KEY_BIT_ENTER) ||
           isKeyPressed(KEY_PROBE_SPACE, KEY_BIT_SPACE);
}

/* Waits for a press and its release. */
static void wait_close(const struct ovl_api *api)
{
    while (close_key_down()) {
        api->service();
    }
    while (!close_key_down()) {
        api->service();
    }
    while (close_key_down()) {
        api->service();
    }
}

/* Atari help_modal_lines, with the CoCo's keys. */
static void show_help(const struct ovl_api *api)
{
    api->clear();
    api->text(18, 1, "Help");
    api->text(6, 4, "Arrows/WASD - Move");
    api->text(6, 5, "SPACE - Fire");
    api->text(6, 6, "Joystick - Move + fire");
    api->text(6, 7, "ENTER - Interact/accept");
    api->text(6, 8, "H - Help (this screen)");
    api->text(6, 9, "M - Map");
    api->text(6, 10, "I - Inventory");
    api->text(6, 11, "P - Toggle PvP");
    api->text(6, 12, "V - Walk speed");
    api->text(6, 13, "F1 - RGB/composite");
    api->text(6, 14, "F2 - Sound on/off");
    api->text(6, 15, "BREAK - Exit to BASIC");
    api->text(4, 21, "Press ENTER or fire to continue");
    api->show();
    wait_close(api);
}

/* Map layout: each zone is a block 16 bytes (4 characters) wide and 16 lines
 * tall, less a 1-byte, 1-line gap on its right and bottom. */
#define MAP_X 16      /* bytes */
#define MAP_Y 32      /* lines */
#define ZONE_BYTES 16
#define ZONE_LINES 16
#define FONT ((const unsigned char *)0xF09D) /* ROM font copy, chars 32-127 */

/* Palette slots (palette.c roles, the same in every area). */
#define C_BLACK 0
#define C_GRAY 2
#define C_BLUE 12
#define C_YELLOW 14

static void fill(unsigned char x, unsigned char y, unsigned char w,
                 unsigned char h, unsigned char color)
{
    unsigned char *dst = GFX_WINDOW + (unsigned)y * BYTES_PER_ROW + x;

    color = (unsigned char)((color << 4) | color);
    while (h--) {
        GFX_ENTER();
        memset(dst, color, w);
        GFX_LEAVE();
        dst += BYTES_PER_ROW;
    }
}

/* Draws c at byte x, line y in fg on bg. */
static void glyph(unsigned char x, unsigned char y, char c, unsigned char fg,
                  unsigned char bg)
{
    unsigned char g[8];
    unsigned char tbl[4];
    unsigned char *dst = GFX_WINDOW + (unsigned)y * BYTES_PER_ROW + x;
    unsigned char r;
    unsigned char b;

    memcpy(g, FONT + (unsigned)(c - 32) * 8, 8);
    tbl[0] = (unsigned char)((bg << 4) | bg);
    tbl[1] = (unsigned char)((bg << 4) | fg);
    tbl[2] = (unsigned char)((fg << 4) | bg);
    tbl[3] = (unsigned char)((fg << 4) | fg);
    GFX_ENTER();
    for (r = 0; r < 8; ++r) {
        b = g[r];
        dst[0] = tbl[b >> 6];
        dst[1] = tbl[(b >> 4) & 3];
        dst[2] = tbl[(b >> 2) & 3];
        dst[3] = tbl[b & 3];
        dst += BYTES_PER_ROW;
    }
    GFX_LEAVE();
}

/* A zone's letter (0 for none) and block color; unvisited zones stay black. */
static char zone_look(unsigned char cell, unsigned char *color)
{
    *color = C_GRAY;
    if (cell & RTS_MAP_CELL_CURRENT) {
        *color = C_YELLOW;
        return 'P';
    }
    switch (cell & RTS_MAP_MARKER_MASK) {
    case RTS_MAP_MARKER_CAVE:
        return 'C';
    case RTS_MAP_MARKER_GRAVE:
        return 'G';
    case RTS_MAP_MARKER_TOWN:
        return 'T';
    }
    *color = (cell & RTS_MAP_CELL_VISITED) ? C_BLUE : C_BLACK;
    return 0;
}

static void legend(unsigned char col, char c, unsigned char color,
                   const struct ovl_api *api, const char *label)
{
    glyph((unsigned char)(col * 4), 18 * 8, c, C_BLACK, color);
    api->text((unsigned char)(col + 2), 18, label);
}

/* Atari show_map_modal, drawn larger: a block per zone inside a border. */
static void show_map(const struct ovl_api *api)
{
    const struct rt_map_summary *m = &api->game->map;
    const unsigned char *cell = m->cells;
    unsigned char w = (unsigned char)(m->width * ZONE_BYTES);
    unsigned char h = (unsigned char)(m->height * ZONE_LINES);
    unsigned char zx;
    unsigned char zy;
    unsigned char x;
    unsigned char y;
    unsigned char color;
    char c;

    api->clear();
    api->text(18, 1, "Map");
    if (m->valid) {
        fill(MAP_X - 2, MAP_Y - 3, (unsigned char)(w + 3), 2, C_GRAY);
        fill(MAP_X - 2, (unsigned char)(MAP_Y + h), (unsigned char)(w + 3), 2,
             C_GRAY);
        fill(MAP_X - 2, MAP_Y - 1, 1, (unsigned char)(h + 1), C_GRAY);
        fill((unsigned char)(MAP_X + w), MAP_Y - 1, 1, (unsigned char)(h + 1),
             C_GRAY);
        for (zy = 0; zy < m->height; ++zy) {
            api->service();
            y = (unsigned char)(MAP_Y + zy * ZONE_LINES);
            for (zx = 0; zx < m->width; ++zx) {
                x = (unsigned char)(MAP_X + zx * ZONE_BYTES);
                c = zone_look(*cell++, &color);
                if (color != C_BLACK) {
                    fill(x, y, ZONE_BYTES - 1, ZONE_LINES - 1, color);
                }
                if (c) {
                    glyph((unsigned char)(x + 6), (unsigned char)(y + 4), c,
                          C_BLACK, color);
                }
            }
        }
        legend(3, 'P', C_YELLOW, api, "Player");
        legend(13, 'T', C_GRAY, api, "Town");
        legend(21, 'C', C_GRAY, api, "Cave");
        legend(29, 'G', C_GRAY, api, "Grave");
    } else {
        api->text(14, 9, "No map data");
    }
    api->text(6, 21, "Press ENTER or fire to close");
    api->show();
    wait_close(api);
}

/* Item ids 2-7 (server items.py), NUL-separated; gold (1) has its own line. */
static const char item_names[] =
    "Sticks\0Herbs\0Potions\0Warden Key\0Oil Sample\0Rust Sample";

static const char *item_name(unsigned char id)
{
    const char *p = item_names;

    while (id-- != 2) {
        p += strlen(p) + 1;
    }
    return p;
}

/* Right-aligns n in 5 columns ending at col 29. */
static void put_number(const struct ovl_api *api, unsigned char row, unsigned n)
{
    char buf[6];
    unsigned char i = 5;

    buf[5] = 0;
    do {
        buf[--i] = (char)('0' + n % 10);
        n /= 10;
    } while (n != 0);
    while (i != 0) {
        buf[--i] = ' ';
    }
    api->text(25, row, buf);
}

/* Atari show_inventory_modal, listing every item the player has carried at
 * least once (a used-up one shows 0). */
static void show_inventory(const struct ovl_api *api)
{
    const struct rt_inventory *inv = &api->game->inv;
    unsigned char row = 6;
    unsigned char bit = 4;
    unsigned char id;
    unsigned char i;
    unsigned n;

    api->clear();
    api->text(15, 1, "Inventory");
    if (inv->valid) {
        api->text(10, 4, "Gold");
        put_number(api, 4, ((unsigned)inv->gold_hi << 8) | inv->gold_lo);
        for (id = 2; id < 8; ++id, bit <<= 1) {
            if (!(inv->seen & bit)) {
                continue;
            }
            n = 0;
            for (i = 0; i < inv->count * 2; i += 2) {
                if (inv->slot[i] == id) {
                    n += inv->slot[i + 1];
                }
            }
            api->text(10, row, item_name(id));
            put_number(api, row, n);
            row += 2;
        }
    } else {
        api->text(11, 9, "No inventory data");
    }
    api->text(6, 21, "Press ENTER or fire to close");
    api->show();
    wait_close(api);
}

unsigned char ovl_entry(const struct ovl_api *api, unsigned char which)
{
    fire_mask = api->fire_mask;
    if (which == OVL_HELP) {
        show_help(api);
    } else if (which == OVL_MAP) {
        show_map(api);
    } else if (which == OVL_INVENTORY) {
        show_inventory(api);
    } else if (which == OVL_DIALOGUE) {
        show_dialogue(api);
    } else if (which == OVL_QUEST_OFFER) {
        show_quest_offer(api);
    }
    return 0;
}
