#ifndef HWSCROLL_H
#define HWSCROLL_H

#include "rt_state.h"

/* Hardware-scrolled renderer (512K only). The GIME shows a 160-byte-wide
 * window into a virtual screen with 256-byte rows (HVEN), so scrolling is a
 * register write plus painting the few tiles that come into view. Two such
 * screens alternate: each step is painted into the hidden one, then shown.
 *
 * World tile (wx, wy) lives at ring column wx & 31 (8 bytes each: 32 tiles is
 * exactly one 256-byte row, and the hardware wraps within it) and ring row
 * wy % 15 (16 lines each). The ring is 240 lines, followed by a mirror of ring
 * lines 0..223, so a frame that runs off the end of the ring still reads
 * contiguous memory. */

/* Enters the mode: HVEN on, video start on the virtual screen. */
void hw_init(void);

/* Leaves it: HVEN off. The caller re-selects the redraw renderer's buffers. */
void hw_leave(void);

/* Marks the HUD image changed; the next hw_present() stamps it. */
void hw_hud_refresh(void);

/* hw_present() modes. */
#define HW_PRESENT_MOVE 0  /* view, entities and markers only */
#define HW_PRESENT_FULL 1  /* repaint everything: first frame, terrain replaced */
#define HW_PRESENT_TILES 2 /* also repaint terrain cells that changed */

/* Brings the screen up to date with spr_next (tiles.h). view_x/view_y is the
 * viewport's top-left in world tiles. */
void hw_present(const unsigned char *terrain, unsigned origin_x,
                unsigned origin_y, unsigned view_x, unsigned view_y,
                const struct rt_state *st, unsigned char mode);

#endif
