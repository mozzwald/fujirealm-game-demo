#include "dlgmodal.h"
#include "rt_state.h"

unsigned char dlg_input_latch(unsigned char *held, unsigned char buttons)
{
    unsigned char pressed = (unsigned char)(buttons & ~*held);

    *held = buttons;
    if (pressed & DLG_BTN_A) {
        return DLG_ACTION_ACCEPT;
    }
    if (pressed & DLG_BTN_B) {
        return DLG_ACTION_DECLINE;
    }
    return DLG_ACTION_NONE;
}

void dlg_modal_open(struct dlg_modal *modal, unsigned char buttons_held)
{
    modal->shown = DLG_SHOWN_NONE;
    modal->waiting = 0;
    modal->closing = 0;
    modal->pages_owed = 0;
    modal->held = buttons_held;
}

unsigned char dlg_modal_step(struct dlg_modal *modal, unsigned char page_dirty,
                             unsigned char page_index, unsigned char page_flags,
                             unsigned char buttons)
{
    unsigned char effects = 0;
    unsigned char action;

    if (page_dirty) {
        /* A resend of the page already on screen must not redraw it or re-arm
           input, or a slow ack looks like a double advance. */
        if (page_index != modal->shown) {
            modal->shown = page_index;
            modal->waiting = 0;
            modal->pages_owed = 2; /* both alternating pages */
        }
    }
    if (modal->pages_owed) {
        --modal->pages_owed;
        effects |= DLG_EFFECT_DRAW;
    }

    action = dlg_input_latch(&modal->held, buttons);

    if (action == DLG_ACTION_DECLINE) {
        /* B is honoured even while waiting: a dead link must not be able to
           trap the player inside a modal. Closing is local, so it needs
           nothing back from the server. */
        modal->closing = 1;
        return (unsigned char)(effects | DLG_EFFECT_ACK_DECLINE |
                               DLG_EFFECT_CLOSE);
    }
    if (action == DLG_ACTION_ACCEPT && !modal->waiting) {
        effects |= DLG_EFFECT_ACK_ACCEPT;
        if (page_flags & RTS_DLG_FLAG_LAST_PAGE) {
            modal->closing = 1;
            effects |= DLG_EFFECT_CLOSE;
        } else {
            /* Hold input until the next page actually arrives, so one press
               cannot advance two pages.

               Tempting to owe a redraw here so the prompt can show the press
               was taken -- but a page is eleven text lines of ~600 put_pixel
               calls each, rendered through the HUD's own msg_sprite, and the
               blit wait between them is time the ComLynx driver spends deaf.
               Two extra page draws land exactly while the server is streaming
               the next page in 47-byte chunks, and the 256-byte RX ring does
               not survive it: the HUD comes back corrupted and the terrain
               repaints black. Feedback has to cost less than this. */
            modal->waiting = 1;
        }
    }
    return effects;
}
