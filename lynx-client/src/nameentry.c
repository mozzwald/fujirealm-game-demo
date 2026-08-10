#include "nameentry.h"

/* Uppercase and digits only: the 4x5 font (art/lynx_art.h) has no lowercase,
 * and the server rejects a comma outright because the appkey identity record
 * is comma-delimited. Index 0 is the empty slot. */
static const char name_chars[NAME_CHARS] =
    " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

struct name_entry name_state;

void name_entry_init(const char *initial)
{
    unsigned char i = 0;

    if (initial != 0) {
        while (i < NAME_MAX && initial[i] != '\0') {
            name_state.buf[i] = initial[i];
            ++i;
        }
    }
    name_state.buf[i] = '\0';
    name_state.len = i;
    name_state.pick = 0;
    name_state.held = 0;
}

unsigned char name_entry_poll(unsigned char buttons)
{
    unsigned char pressed;

    buttons &= NAME_BTN_MASK;
    pressed = (unsigned char)(buttons & ~name_state.held);
    name_state.held = buttons;
    if (pressed == 0) {
        return NAME_POLL_IDLE;
    }
    if (name_entry_step(pressed)) {
        return NAME_POLL_DONE;
    }
    return NAME_POLL_CHANGED;
}

unsigned char name_entry_step(unsigned char pressed)
{
    /* A full name leaves the cursor parked on the empty slot, so the only
       moves left are accept and backspace. Without this the player can spin
       the wheel on a character that can never be committed. */
    if (name_state.len < NAME_MAX) {
        if (pressed & NAME_BTN_UP) {
            ++name_state.pick;
            if (name_state.pick >= NAME_CHARS) {
                name_state.pick = 0;
            }
        }
        if (pressed & NAME_BTN_DOWN) {
            if (name_state.pick != 0) {
                --name_state.pick;
            } else {
                name_state.pick = NAME_CHARS - 1;
            }
        }
    }

    if (pressed & NAME_BTN_B) {
        /* Backspace off the empty slot first, so a mis-picked character can be
           abandoned without also eating the character before it. */
        if (name_state.pick != 0) {
            name_state.pick = 0;
        } else if (name_state.len != 0) {
            name_state.buf[--name_state.len] = '\0';
        }
    }

    if (pressed & NAME_BTN_A) {
        if (name_state.pick != 0) {
            if (name_state.len < NAME_MAX) {
                name_state.buf[name_state.len++] = name_chars[name_state.pick];
                name_state.buf[name_state.len] = '\0';
            }
            name_state.pick = 0;
        } else if (name_state.len != 0) {
            return 1;
        }
    }
    return 0;
}

unsigned char name_entry_display(char *out)
{
    unsigned char i;

    for (i = 0; i < name_state.len; ++i) {
        out[i] = name_state.buf[i];
    }
    if (name_state.pick != 0) {
        out[i++] = name_chars[name_state.pick];
    } else if (name_state.len < NAME_MAX) {
        /* The empty slot still needs to be visible, or an accept looks like a
           dead button. */
        out[i++] = '_';
    }
    out[i] = '\0';
    return i;
}
