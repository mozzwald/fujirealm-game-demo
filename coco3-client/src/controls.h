#ifndef CONTROLS_H
#define CONTROLS_H

/* No direction. Otherwise dir is an RTS_FACE_* code (rt_state.h): held now,
 * or a key tapped since the previous read. */
#define CTL_NONE 0xFF

struct controls {
    unsigned char dir;
    /* Pressed since the previous read. */
    unsigned char fire;
    unsigned char interact;
    unsigned char pvp;
};

/* Polls the keyboard and joysticks.
 *
 *   Move      arrow keys or W/A/S/D (cardinals), or a joystick (8 directions)
 *   Fire      SPACE or joystick button 1
 *   Interact  ENTER (talk / pick up)
 *   PvP       P (toggle)
 *
 * A joystick is ignored until one of its buttons is pressed, then that stick
 * stays selected (same as fujinet-fujirkle): an unplugged stick reads as
 * noise and would otherwise walk the player around on its own. */
void controls_read(struct controls *c);

/* Latches button and direction key presses for the next controls_read().
 * Called between redraw rows and network calls: the CoCo keyboard has no
 * latch, so a tap shorter than one loop pass is otherwise lost. */
void controls_poll(void);

/* The selected stick's button-1 bit in readJoystickButtons() (active low),
 * or 0 when no stick is selected. */
unsigned char controls_fire_mask(void);

/* 0 while a joystick button is held: keyboard reads are unreliable then. */
unsigned char controls_keys_valid(void);

#endif
