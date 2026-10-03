#include <exec/ports.h>
#include <intuition/intuition.h>
#include <proto/exec.h>

#include "input.h"
#include "rt_state.h"

/* Joystick in port 2: JOY1DAT and the CIA-A fire bit. Reading them directly
 * is safe on 1.3; nothing else owns port 2 while we run. */
#define JOY1DAT (*(volatile UWORD *)0xDFF00C)
#define CIAA_PRA (*(volatile UBYTE *)0xBFE001)

#define KEY_UP 0x4C
#define KEY_DOWN 0x4D
#define KEY_RIGHT 0x4E
#define KEY_LEFT 0x4F
#define KEY_SPACE 0x40
#define KEY_BACKSPACE 0x41
#define KEY_ENTER 0x43
#define KEY_RETURN 0x44
#define KEY_ESC 0x45
#define KEY_DEL 0x46
#define KEY_P 0x19
#define KP_1 0x1D
#define KP_2 0x1E
#define KP_3 0x1F
#define KP_4 0x2D
#define KP_6 0x2F
#define KP_7 0x3D
#define KP_8 0x3E
#define KP_9 0x3F

static struct MsgPort *port;
static struct Window *win;
static unsigned char mouse_left, mouse_right_clicks;
static unsigned char down[128];

#define QUEUE 16
static char queue[QUEUE];
static unsigned char q_head, q_tail;

/* Raw key -> character for name entry (US layout; letters, digits only). */
static char rawkey_char(UWORD code)
{
    static const char row1[] = "1234567890";     /* 0x01-0x0A */
    static const char row2[] = "QWERTYUIOP";     /* 0x10-0x19 */
    static const char row3[] = "ASDFGHJKL";      /* 0x20-0x28 */
    static const char row4[] = "ZXCVBNM";        /* 0x31-0x37 */

    if (code >= 0x01 && code <= 0x0A)
        return row1[code - 0x01];
    if (code >= 0x10 && code <= 0x19)
        return row2[code - 0x10];
    if (code >= 0x20 && code <= 0x28)
        return row3[code - 0x20];
    if (code >= 0x31 && code <= 0x37)
        return row4[code - 0x31];
    if (code == KEY_BACKSPACE || code == KEY_DEL)
        return '\b';
    if (code == KEY_RETURN || code == KEY_ENTER)
        return '\r';
    if (code == KEY_ESC)
        return 0x1B;
    return 0;
}

void input_init(struct Window *window)
{
    port = window->UserPort;
    win = window;
    q_head = q_tail = 0;
}

void input_poll(void)
{
    struct IntuiMessage *msg;

    while ((msg = (struct IntuiMessage *)GetMsg(port)) != NULL) {
        if (msg->Class == MOUSEBUTTONS) {
            if (msg->Code == SELECTDOWN)
                mouse_left = 1;
            else if (msg->Code == SELECTUP)
                mouse_left = 0;
            else if (msg->Code == MENUDOWN)
                ++mouse_right_clicks;
        } else if (msg->Class == RAWKEY) {
            UWORD code = msg->Code & 0x7F;

            if (msg->Code & IECODE_UP_PREFIX) {
                down[code] = 0;
            } else {
                char ch = rawkey_char(code);

                down[code] = 1;
                if (ch && (unsigned char)(q_tail + 1) % QUEUE != q_head) {
                    queue[q_tail] = ch;
                    q_tail = (unsigned char)((q_tail + 1) % QUEUE);
                }
            }
        }
        ReplyMsg((struct Message *)msg);
    }
}

unsigned char input_dir(void)
{
    UWORD joy = JOY1DAT;
    unsigned char right = (joy >> 1) & 1;
    unsigned char left = (joy >> 9) & 1;
    unsigned char dn = ((joy >> 1) ^ joy) & 1;
    unsigned char up = ((joy >> 9) ^ (joy >> 8)) & 1;

    up |= down[KEY_UP] | down[KP_8];
    dn |= down[KEY_DOWN] | down[KP_2];
    left |= down[KEY_LEFT] | down[KP_4];
    right |= down[KEY_RIGHT] | down[KP_6];
    /* Keypad diagonals. */
    if (down[KP_7]) up = left = 1;
    if (down[KP_9]) up = right = 1;
    if (down[KP_1]) dn = left = 1;
    if (down[KP_3]) dn = right = 1;

    /* Diagonals first, as on the Lynx, so a diagonal never collapses to
     * whichever axis happened to be tested earlier. */
    if (up && left) return RTS_FACE_UP_LEFT;
    if (up && right) return RTS_FACE_UP_RIGHT;
    if (dn && left) return RTS_FACE_DOWN_LEFT;
    if (dn && right) return RTS_FACE_DOWN_RIGHT;
    if (up) return RTS_FACE_UP;
    if (dn) return RTS_FACE_DOWN;
    if (left) return RTS_FACE_LEFT;
    if (right) return RTS_FACE_RIGHT;
    return INPUT_NONE;
}

unsigned char input_fire(void)
{
    return down[KEY_SPACE] || !(CIAA_PRA & 0x80);
}

unsigned char input_use(void)
{
    return down[KEY_RETURN] || down[KEY_ENTER];
}

unsigned char input_pvp(void)
{
    return down[KEY_P];
}

unsigned char input_quit(void)
{
    return down[KEY_ESC];
}

int input_char(void)
{
    char ch;

    if (q_head == q_tail)
        return -1;
    ch = queue[q_head];
    q_head = (unsigned char)((q_head + 1) % QUEUE);
    return (unsigned char)ch;
}

void input_flush_chars(void)
{
    q_head = q_tail;
}

unsigned char input_mouse_left(void)
{
    return mouse_left;
}

unsigned char input_mouse_right_click(void)
{
    unsigned char n = mouse_right_clicks;

    mouse_right_clicks = 0;
    return n != 0;
}

void input_mouse_pos(int *x, int *y)
{
    *x = win->MouseX;
    *y = win->MouseY;
}
