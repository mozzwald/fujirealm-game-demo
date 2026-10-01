#include "controls.h"
#include "rt_state.h"
#include "gime.h"
#include <coco.h>

/* Analog axes read 0-63 with center near 31. */
#define JOY_LOW 15
#define JOY_HIGH 47

static unsigned char left_joy_selected = 0;
static unsigned char right_joy_selected = 0;

static unsigned char key_dir(void)
{
    if (isKeyPressed(KEY_PROBE_UP, KEY_BIT_UP) ||
        isKeyPressed(KEY_PROBE_W, KEY_BIT_W)) {
        return RTS_FACE_UP;
    }
    if (isKeyPressed(KEY_PROBE_DOWN, KEY_BIT_DOWN) ||
        isKeyPressed(KEY_PROBE_S, KEY_BIT_S)) {
        return RTS_FACE_DOWN;
    }
    if (isKeyPressed(KEY_PROBE_LEFT, KEY_BIT_LEFT) ||
        isKeyPressed(KEY_PROBE_A, KEY_BIT_A)) {
        return RTS_FACE_LEFT;
    }
    if (isKeyPressed(KEY_PROBE_RIGHT, KEY_BIT_RIGHT) ||
        isKeyPressed(KEY_PROBE_D, KEY_BIT_D)) {
        return RTS_FACE_RIGHT;
    }
    return CTL_NONE;
}

static unsigned char stick_dir(unsigned char h, unsigned char v)
{
    unsigned char up = v <= JOY_LOW;
    unsigned char down = v >= JOY_HIGH;
    unsigned char left = h <= JOY_LOW;
    unsigned char right = h >= JOY_HIGH;

    if (up && left) {
        return RTS_FACE_UP_LEFT;
    }
    if (up && right) {
        return RTS_FACE_UP_RIGHT;
    }
    if (down && left) {
        return RTS_FACE_DOWN_LEFT;
    }
    if (down && right) {
        return RTS_FACE_DOWN_RIGHT;
    }
    if (up) {
        return RTS_FACE_UP;
    }
    if (down) {
        return RTS_FACE_DOWN;
    }
    if (left) {
        return RTS_FACE_LEFT;
    }
    if (right) {
        return RTS_FACE_RIGHT;
    }
    return CTL_NONE;
}

#define EDGE_FIRE 0x01
#define EDGE_INTERACT 0x02
#define EDGE_PVP 0x04

static unsigned char keys_down = 0; /* EDGE_* held at the last poll */
static unsigned char key_edges = 0; /* EDGE_* pressed since the last read */
static unsigned char dir_down = CTL_NONE;  /* key direction at the last poll */
static unsigned char dir_latch = CTL_NONE; /* first new one since the last read */

/* A held joystick button shares its PIA line with a keyboard row, so every
 * key on that row reads as pressed (right button 1: @ A-G). */
unsigned char controls_keys_valid(void)
{
    return (readJoystickButtons() & 0x0F) == 0x0F;
}

unsigned char controls_fire_mask(void)
{
    if (left_joy_selected) {
        return 0x02;
    }
    if (right_joy_selected) {
        return 0x01;
    }
    return 0;
}

void controls_poll(void)
{
    unsigned char buttons = readJoystickButtons();
    unsigned char keys = (buttons & 0x0F) == 0x0F;
    unsigned char down = 0;
    unsigned char dir = CTL_NONE;

    /* A press on an unselected stick only selects it: counting it as held
     * already means it fires nothing until released and pressed again.
     * Buttons are active low, left 0x02/0x08, right 0x01/0x04 (the masks
     * fujirkle verified; coco.h's JOYSTK_BUTTON_* names do not match). */
    if (!left_joy_selected && (buttons & 0x0A) != 0x0A) {
        left_joy_selected = 1;
        right_joy_selected = 0;
        keys_down |= EDGE_FIRE;
    } else if (!right_joy_selected && (buttons & 0x05) != 0x05) {
        right_joy_selected = 1;
        left_joy_selected = 0;
        keys_down |= EDGE_FIRE;
    }

    if ((keys && isKeyPressed(KEY_PROBE_SPACE, KEY_BIT_SPACE)) ||
        (left_joy_selected && (buttons & 0x02) == 0) ||
        (right_joy_selected && (buttons & 0x01) == 0)) {
        down = EDGE_FIRE;
    }
    if (keys && isKeyPressed(KEY_PROBE_ENTER, KEY_BIT_ENTER)) {
        down |= EDGE_INTERACT;
    }
    if (keys && isKeyPressed(KEY_PROBE_P, KEY_BIT_P)) {
        down |= EDGE_PVP;
    }
    key_edges |= (unsigned char)(down & ~keys_down);
    keys_down = down;
    if (keys) {
        dir = key_dir();
    }
    if (dir != dir_down && dir_latch == CTL_NONE) {
        dir_latch = dir;
    }
    dir_down = dir;
}

/* Joystick reads use the DAC and its mux, so the sound FIRQ is held off and
 * the mux is put back on the DAC after. */
static const unsigned char *read_sticks(void)
{
    const unsigned char *pos;

    INTS_OFF();
    pos = readJoystickPositions();
    *(unsigned char *)0xFF01 &= 0xF7;
    *(unsigned char *)0xFF03 &= 0xF7;
    INTS_RESTORE();
    return pos;
}

void controls_read(struct controls *c)
{
    unsigned char buttons = readJoystickButtons();
    const unsigned char *pos;
    unsigned char joy_dir = CTL_NONE;

    controls_poll();
    if (left_joy_selected) {
        pos = read_sticks();
        joy_dir = stick_dir(pos[JOYSTK_LEFT_HORIZ], pos[JOYSTK_LEFT_VERT]);
    } else if (right_joy_selected) {
        pos = read_sticks();
        joy_dir = stick_dir(pos[JOYSTK_RIGHT_HORIZ], pos[JOYSTK_RIGHT_VERT]);
    }

    c->dir = CTL_NONE;
    if ((buttons & 0x0F) == 0x0F) {
        c->dir = key_dir();
    }
    if (c->dir == CTL_NONE) {
        c->dir = dir_latch;
    }
    if (c->dir == CTL_NONE) {
        c->dir = joy_dir;
    }
    dir_latch = CTL_NONE;
    c->fire = (key_edges & EDGE_FIRE) != 0;
    c->interact = (key_edges & EDGE_INTERACT) != 0;
    c->pvp = (key_edges & EDGE_PVP) != 0;
    key_edges = 0;
}
