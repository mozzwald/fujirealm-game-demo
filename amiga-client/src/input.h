#ifndef FUJIREALM_AMIGA_INPUT_H
#define FUJIREALM_AMIGA_INPUT_H

/* Keyboard (Intuition RAWKEY on our window) plus a joystick in port 2.
 *
 *   Move    cursor keys, keypad 8/2/4/6 (7/9/1/3 diagonal), or joystick
 *   Fire    Space, or the joystick button
 *   Use     Return / keypad Enter (pick up, talk, accept)
 *   PvP     P toggles player-versus-player
 *   Quit    Esc (in a dialogue: decline)
 *   Mouse   left click/hold: walk to the pointer; right click: shoot at it
 */

#define INPUT_NONE 0xFF          /* no direction held (FACE_NONE) */

struct Window;

void input_init(struct Window *window);
/* Drain pending IDCMP messages into the key state. Call once per loop. */
void input_poll(void);

unsigned char input_dir(void);   /* RTS_FACE_* or INPUT_NONE */
unsigned char input_fire(void);
unsigned char input_use(void);
unsigned char input_pvp(void);
unsigned char input_quit(void);

/* Typed characters for text entry: uppercase letters, digits, and
 * '\b' backspace, '\r' return, 0x1B escape. -1 when none are queued. */
int input_char(void);
void input_flush_chars(void);

/* Mouse, in screen pixels (our window covers the screen). */
unsigned char input_mouse_left(void);       /* left button held */
unsigned char input_mouse_right_click(void); /* right press since last call */
void input_mouse_pos(int *x, int *y);

#endif
