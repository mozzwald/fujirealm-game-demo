#ifndef FUJIREALM_HUDTEXT_H
#define FUJIREALM_HUDTEXT_H

/* Rasterize HUD text into a totally-literal 4bpp Suzy sprite (host-testable;
 * the font comes from art/lynx_art.c). Sprite is HUD_TEXT_COLS glyphs of
 * 4x5 pixels with 1px spacing: 155px wide, 5 rows. Pen 0 is transparent. */

#define HUD_TEXT_COLS 31
#define HUD_TEXT_W (HUD_TEXT_COLS * 5)
#define HUD_TEXT_ROW_BYTES ((HUD_TEXT_W + 1) / 2)
#define HUD_TEXT_SPRITE_BYTES ((HUD_TEXT_ROW_BYTES + 1) * 5 + 1)

/* Set up the per-row offset bytes and terminator; call once per buffer. */
void hud_text_init(unsigned char *buf);

/* Clear the sprite and draw text (ASCII 32..95; lowercase is folded) in the
 * given CLUT pen. Text longer than HUD_TEXT_COLS is truncated. */
void hud_text_render(unsigned char *buf, const char *text, unsigned char len,
                     unsigned char ink);

/* Append val as decimal digits to out; returns new length. */
unsigned char fmt_u16(char *out, unsigned char pos, unsigned val);

/* Append val as exactly four uppercase hex digits; returns new length. Used for
 * addresses on the video diagnostics page, where leading zeros matter. */
unsigned char fmt_hex16(char *out, unsigned char pos, unsigned val);

/* Greedy word wrap over text[0..len), one line per call. *pos is the in/out
 * cursor; start it at 0. Writes the line's first index to *out_start and
 * returns its length, or 0 once the text is exhausted.
 *
 * Leading spaces are skipped, so no line starts blank and the separator is
 * consumed rather than counted. A single word longer than width is hard-split
 * at width -- dialogue text is server-authored and sanitized, but a wrap that
 * can loop forever on one long token is not worth the risk. */
unsigned char hud_wrap_next(const char *text, unsigned char len,
                            unsigned char *pos, unsigned char width,
                            unsigned char *out_start);

#endif
