#ifndef FUJIREALM_NAMEENTRY_H
#define FUJIREALM_NAMEENTRY_H

/* The name picker's decision logic, with no I/O in it.
 *
 * Split from main.c for the same reason dlgmodal.c is: main.c is the one file
 * a host test cannot execute, so everything that can be decided without the
 * joystick or the renderer is decided here and tested in tools/host_tests.c.
 *
 * The picker is a slot machine rather than an on-screen alphabet grid because
 * MAIN has about 1.3 KB left: one cursor, one index, no layout.
 */

/* The server allows 10 (server/protocol.py USERNAME_MAX_LEN), but 8 keeps the
 * login payload and the appkey record at the sizes they already are, and the
 * name has to share a 155px text sprite with its prompt. */
#define NAME_MAX 8

/* Buttons, as a mask.
 *
 * Deliberately the Lynx's own JOY_*_MASK bit positions (cc65 lynx.h), so the
 * caller hands joy_read() straight through with one AND instead of four tests.
 * cc65 charges real bytes for each of those, and this segment has none spare. */
#define NAME_BTN_UP 0x80
#define NAME_BTN_DOWN 0x40
#define NAME_BTN_A 0x01
#define NAME_BTN_B 0x02
#define NAME_BTN_MASK 0xC3

/* Index 0 of the character table is the empty slot, so A on it means "done"
 * and there is no separate confirm button to explain. */
#define NAME_CHARS 37

/* What name_entry_poll() wants the caller to do next. */
#define NAME_POLL_IDLE 0
#define NAME_POLL_CHANGED 1 /* redraw */
#define NAME_POLL_DONE 2    /* the name is accepted; leave the screen */

struct name_entry {
    char buf[NAME_MAX + 1]; /* NUL-terminated name so far */
    unsigned char len;
    unsigned char pick; /* index into the character table; 0 = empty slot */
    unsigned char held; /* buttons down at the previous poll */
};

/* One picker, at a fixed address. There is only ever one on screen, and cc65
 * generates markedly smaller code for a global than for the same fields
 * reached through a pointer parameter. Exposed so host tests can inspect it. */
extern struct name_entry name_state;

/* Seed the picker. initial may be 0 or empty; anything past NAME_MAX is
 * dropped, which is what a longer name from an older appkey record does. */
void name_entry_init(const char *initial);

/* One iteration, from the raw pad mask. Rising edges only: holding a
 * direction must not spin the wheel, and the button that ends the screen must
 * not be seen again by whatever comes next. Returns a NAME_POLL_* code.
 *
 * The latch lives here rather than in main.c because main.c is the file host
 * tests cannot execute -- and the first version of this screen, which latched
 * in main.c through dlg_input_latch(), was dead on hardware: that function
 * returns a DLG_ACTION_*, not the pressed mask, so the D-pad never reached
 * the picker at all. */
unsigned char name_entry_poll(unsigned char buttons);

/* One iteration from an already edge-latched mask. Returns 1 once the player
 * has accepted a non-empty name (A on the empty slot). */
unsigned char name_entry_step(unsigned char pressed);

/* Render the editable line -- the name so far plus the slot under the cursor --
 * into out, which must hold NAME_MAX + 2 bytes. Returns its length. */
unsigned char name_entry_display(char *out);

#endif
