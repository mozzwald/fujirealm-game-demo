#ifndef FUJIREALM_RENDER_H
#define FUJIREALM_RENDER_H

#include "rt_state.h"

/* 20x10 tile viewport (160x80) + 22px HUD (rows 80..101), on a native 8x8
 * tileset. The Atari client shows 20x12 tiles, so the original 10x5 of
 * 16x16 was showing about a fifth of the world area and the player kept
 * walking into unseen trouble.
 *
 * Horizontal detail is unchanged by the move: the art is authored 8 pixels
 * wide and used to be doubled to 16, so at 8px it maps 1:1. Vertical detail
 * halves, 16 source rows merged to 8 in the importer. Tiles are drawn at
 * 1:1 now, so nothing is scaled at runtime. */
#define VIEW_COLS 20
#define VIEW_ROWS 10
#define TILE_PX 8
#define TILE_SCALE 0x0100
#define VIEW_H (VIEW_ROWS * TILE_PX)
#define HUD_TOP VIEW_H
/* Three 5px text rows on a 6px pitch inside rows 80..101, below the 1px top
 * rule: stats, the server MESSAGE line, and the active quest. The quest line is
 * the third because it is the one that is usually blank. */
#define HUD_STATS_Y (HUD_TOP + 2)
#define HUD_MSG_Y (HUD_TOP + 8)
#define HUD_QUEST_Y (HUD_TOP + 14)

void render_init(void);

/* Re-tint the screen for a map. palette_id comes from MAP_CHANGE (0 overworld,
 * 1 starter cave, 2 PvP realm); out-of-range falls back to the overworld. The
 * tileset_id in the same packet is deliberately ignored -- the Lynx has a
 * single tile table, and the server aliases the PvP tileset to the
 * overworld's. */
void render_set_palette(unsigned char palette_id);

/* The two framebuffer pages, whether render_init() confirmed which one Suzy
 * draws into, and the index of that page -- for the video diagnostics page.
 * The terrain layer depends entirely on that parity being right, and none of it
 * is observable from outside the renderer, which is precisely why a wrong
 * answer took several hardware trips to pin down. */
void render_video_info(unsigned *page0, unsigned *page1,
                       unsigned char *ok, unsigned char *draw_page);

/* Register a callback the CPU tile blitter calls once per terrain row during a
 * repaint, so the app can drain the serial driver's small RX ring into its own
 * larger buffer instead of letting it overflow across the ~90-120 ms a full
 * repaint keeps the CPU busy. Pass 0 to disable. */
void render_set_rx_pump(void (*fn)(void));

/* Draw one full frame: terrain window slice, entities, player, HUD panel
 * plus the two prebuilt text sprites. cam_x/cam_y are tile offsets into the
 * 32x24 window; origin_* are the window's absolute world coords. */
/* draw_flags selects which layers to draw. The HUD panel occupies rows
 * 80..101, which terrain and entities never touch, so RENDER_HUD may be
 * omitted to keep whatever this page already shows -- but it must be set
 * for two consecutive frames after any HUD change, once per alternating
 * page.
 *
 * Omitting RENDER_TERRAIN is a measurement aid only: nothing then erases
 * the previous frame, so entities smear. It exists so the cost of the 50
 * tile blits can be measured by difference against the frame rate.
 *
 * full_terrain redraws all VIEW_COLS*VIEW_ROWS cells. When it is 0 only the
 * cells that entities covered the last time this same page was drawn are
 * repainted, which is enough to erase them. Terrain sprites are opaque
 * (pen 0 is a colour, not transparency, for the BACKGROUND types), so a
 * repainted cell fully erases whatever was over it.
 *
 * The caller must pass 1 for two consecutive frames whenever the camera,
 * the window origin, or a terrain cell changes -- two because the pages
 * alternate and each holds its own stale copy. */
#define RENDER_TERRAIN 0x01
#define RENDER_ENTITIES 0x02
#define RENDER_HUD 0x04
/* RENDER_HALF_TILES (0x08) used to draw terrain at half scale to separate the
 * per-Suzy-call cost from the per-pixel cost. It only ever scaled the Suzy
 * terrain blits, which no longer exist -- the CPU blitter copies whole cells --
 * so the flag was removed rather than left as a no-op. The measurements it was
 * built for are recorded in the project history. */
void render_frame(const struct rt_state *state, const unsigned char *terrain,
                  unsigned origin_x, unsigned origin_y,
                  unsigned char cam_x, unsigned char cam_y,
                  unsigned char facing, unsigned char anim,
                  const unsigned char *stats_sprite,
                  const unsigned char *msg_sprite,
                  const unsigned char *quest_sprite,
                  unsigned char draw_flags,
                  unsigned char full_terrain);

/* Full-screen modal (the dialogue scenes). Begin clears the page, text blits
 * one prebuilt hudtext line at (x, y), End shows it. Text blits are blocking,
 * so the caller can rasterize every line into one shared sprite buffer and blit
 * it immediately rather than holding a sprite per line. */
void render_modal_begin(void);
void render_modal_text(const unsigned char *sprite, signed int x, signed int y);
void render_modal_end(void);

#endif
