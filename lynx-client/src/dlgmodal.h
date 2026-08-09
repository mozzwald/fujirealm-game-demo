#ifndef FUJIREALM_DLGMODAL_H
#define FUJIREALM_DLGMODAL_H

/* The dialogue modal's decision logic, with no I/O in it.
 *
 * main.c owns the joystick, the renderer and the link; this owns what the
 * modal *decides* -- which page is on screen, whether input is held while the
 * next one is in flight, and what a button press means. That split exists
 * because every Lynx bug found on hardware so far has been in main.c, the one
 * file a host test cannot execute. This part can be, and is: see
 * tools/host_tests.c.
 */

/* Buttons, as a mask so a press can be seen while another is still held. */
#define DLG_BTN_A 0x01
#define DLG_BTN_B 0x02

/* What a press meant, if anything. */
#define DLG_ACTION_NONE 0
#define DLG_ACTION_ACCEPT 1  /* A: advance, or accept a quest offer */
#define DLG_ACTION_DECLINE 2 /* B: decline, and the local escape hatch */

/* What the caller must do this iteration. */
#define DLG_EFFECT_DRAW 0x01
#define DLG_EFFECT_ACK_ACCEPT 0x02
#define DLG_EFFECT_ACK_DECLINE 0x04
#define DLG_EFFECT_CLOSE 0x08

#define DLG_SHOWN_NONE 0xFF

struct dlg_modal {
    unsigned char shown;      /* page_index last drawn, or DLG_SHOWN_NONE */
    unsigned char waiting;    /* advance acked; next page still in flight */
    unsigned char closing;    /* leave after this iteration's effects */
    unsigned char pages_owed; /* redraws still owed (one per alternating page) */
    unsigned char held;       /* buttons down at the previous poll */
};

/* Rising-edge latch over a button *mask*.
 *
 * Deliberately not a "some button is held" flag, and not a change detector.
 * A single held-flag loses a roll from B to A -- pressing A without first
 * releasing the B that opened the scene reads as "still held" and is
 * discarded, which is what made the modal need a second press. A change
 * detector is worse still: it fires on releases and swallows the first press
 * when seeded. Tracking the mask makes each button's own press an edge.
 *
 * A press that the caller then discards (see dlg_modal_step's waiting gate)
 * does not cost the player their next press: that one is a fresh edge.
 */
unsigned char dlg_input_latch(unsigned char *held, unsigned char buttons);

/* Seed the modal. buttons_held is whatever is down right now, so the press
 * that opened the scene is swallowed rather than acted on twice. */
void dlg_modal_open(struct dlg_modal *modal, unsigned char buttons_held);

/* One iteration. page_dirty/page_index/page_flags come from the last
 * DIALOGUE_PAGE applied; buttons is the current mask. Returns DLG_EFFECT_*. */
unsigned char dlg_modal_step(struct dlg_modal *modal, unsigned char page_dirty,
                             unsigned char page_index, unsigned char page_flags,
                             unsigned char buttons);

#endif
