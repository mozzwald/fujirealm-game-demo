#!/usr/bin/env python3
"""Generate gfx.bas: Intellivision GRAM cards + color tables from the Lynx tileset.

Source of truth is lynx-client/art/lynx_tileset.json (8x8 tiles, 16-color
CLUT). An Intellivision GRAM card is 1bpp with a single foreground color per
BACKTAB word (background = the all-black color stack), so each tile reduces
to (shape mask, one STIC color):

- "field" tiles (full-coverage terrain: grass, road, water, walls...):
  luminance threshold at (min+max)/2; if that sets a minority of pixels the
  mask is inverted so terrain reads as lit ground with dark texture holes.
- everything else ("object" tiles: NPCs, items, trees, props): background
  removal -- the most frequent CLUT index is the ground the object stands
  on; every other pixel is part of the object.

The foreground color is the dominant STIC mapping of the mask pixels
(never black), overridable per tile in OVERRIDES below. The BACKTAB word
carries the color, the GRAM card only the shape -- so player cards are
reused for remote players by recoloring the word.

Usage (from intv-client/):
    python3 tools/convert_tiles.py > gfx.bas
    python3 tools/convert_tiles.py --preview   # ASCII proofs to stderr
"""

import json
import sys
from collections import Counter
from pathlib import Path

TILESET = Path(__file__).resolve().parents[2] / "lynx-client/art/lynx_tileset.json"

# STIC palette (jzIntv RGB approximations), index = Intellivision color 0-15.
STIC = [
    (0x00, 0x00, 0x00), (0x00, 0x2D, 0xFF), (0xFF, 0x3D, 0x10), (0xC9, 0xCF, 0xAB),
    (0x38, 0x6B, 0x3F), (0x00, 0xA7, 0x56), (0xFA, 0xEA, 0x50), (0xFF, 0xFC, 0xFF),
    (0xBD, 0xAC, 0xC8), (0x24, 0xB8, 0xFF), (0xFF, 0xB4, 0x1F), (0x54, 0x6E, 0x00),
    (0xFF, 0x4E, 0x57), (0xA4, 0x96, 0xFF), (0x75, 0xCC, 0x80), (0xB5, 0x1A, 0x58),
]
STIC_NAMES = ["BLACK", "BLUE", "RED", "TAN", "DARKGREEN", "GREEN", "YELLOW", "WHITE",
              "GREY", "CYAN", "ORANGE", "BROWN", "PINK", "LTBLUE", "YELGREEN", "PURPLE"]

# Logical tile ids that actually appear in the terrain stream (docs/TILE_ALLOCATION.md;
# ids 1 and 18-33 are dead legacy slots).
USED_TILES = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
              34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51]

# Full-coverage terrain -> luminance rule; all other used tiles -> object rule.
FIELD_TILES = {0, 7, 10, 11, 12, 13, 15, 16, 17}

# Per-tile hand overrides: fg = STIC color index, invert = flip the mask.
# (The STIC has no dark grey -- #4E4842 maps to DARKGREEN by distance -- so
# stone/metal art needs its color forced.)
OVERRIDES = {
    6:  {"fg": 6},    # bullet: YELLOW for visibility
    11: {"fg": 9},    # water: pale wave pixels; nearest-color picks GREY, want CYAN
    13: {"fg": 3},    # cave entrance: tan rock frame
    14: {"fg": 8},    # grave: grey headstone (dark grey auto-maps to DARKGREEN)
    15: {"fg": 8, "invert": True},  # cave floor: black floor w/ grey speckles, not a lit slab
    17: {"fg": 8},    # cave exit: grey, to read differently from the tan entrance
    34: {"fg": 6},    # gold: force YELLOW
    39: {"fg": 6},    # warden key: YELLOW
}

# Tiles whose Lynx art is a dither pattern that reduces to noise at 1bpp;
# replaced with hand-drawn glyphs.
HAND_TILES = {
    12: ([        # building: a little house; repeated tiles read as a town
        "...##...",
        "..####..",
        ".######.",
        "########",
        ".######.",
        ".##..##.",
        ".##.###.",
        ".######.",
    ], 3),        # TAN
}

# WORLD_STATE entity species -> logical tile id whose card draws it
# (bat/slime animate by swapping to id+1 in the renderer).
KIND_TILE = [0, 8, 9, 46, 44, 36, 48, 41, 51]

TOTAL_TILE_CARDS = len(USED_TILES)          # 35
CARD_PLY_FRONT = TOTAL_TILE_CARDS           # players[0]
CARD_PLY_RIGHT = TOTAL_TILE_CARDS + 1       # players[2]
CARD_PLY_LEFT = TOTAL_TILE_CARDS + 2        # players[4]
CARD_POTION = TOTAL_TILE_CARDS + 3          # entities[14] item_potion
CARD_HEART = TOTAL_TILE_CARDS + 4           # hand-drawn HUD glyph
TOTAL_CARDS = TOTAL_TILE_CARDS + 5          # 40

HEART_ROWS = [
    ".##..##.",
    "########",
    "########",
    "########",
    ".######.",
    "..####..",
    "...##...",
    "........",
]

COLOR_LOCAL = 7    # WHITE  -- local player card color
COLOR_REMOTE = 10  # ORANGE -- remote players, same cards recolored
COLOR_HEART = 2    # RED

# facing 0-7 (up,down,left,right,ul,ur,dl,dr) -> player card, mirroring the
# Lynx facing_frame table (no back art; up shares the front card).
FACING_CARD = [CARD_PLY_FRONT, CARD_PLY_FRONT, CARD_PLY_LEFT, CARD_PLY_RIGHT,
               CARD_PLY_LEFT, CARD_PLY_RIGHT, CARD_PLY_LEFT, CARD_PLY_RIGHT]


def lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def nearest_stic(rgb, allow_black=False):
    best, best_d = 7, 1 << 30
    for i, s in enumerate(STIC):
        if i == 0 and not allow_black:
            continue
        d = sum((a - b) ** 2 for a, b in zip(rgb, s))
        if d < best_d:
            best, best_d = i, d
    return best


def tile_pixels(entry):
    return [[int(c, 16) for c in row] for row in entry["rows"]]


def dominant_fg(flat, mask, palette):
    fg_counts = Counter()
    for p, m in zip(flat, mask):
        if m:
            fg_counts[nearest_stic(palette[p])] += 1
    return fg_counts.most_common(1)[0][0] if fg_counts else 7


def convert(pixels, palette, rule, bg_index=None, invert=False):
    """-> (mask rows of bool, fg STIC color)."""
    flat = [p for row in pixels for p in row]
    if rule == "field":
        lums = [lum(palette[p]) for p in flat]
        lo, hi = min(lums), max(lums)
        if hi - lo < 8:
            mask = [True] * 64
        else:
            thr = (lo + hi) / 2
            mask = [v >= thr for v in lums]
            if sum(mask) < 32:
                mask = [not m for m in mask]
    else:
        if bg_index is not None:
            bg = bg_index
        else:
            # The ground the object stands on shows at the tile's corners;
            # global frequency is wrong for objects covering > half the tile.
            corners = [flat[0], flat[7], flat[56], flat[63]]
            bg = Counter(corners).most_common(1)[0][0]
        mask = [p != bg for p in flat]
    if invert:
        mask = [not m for m in mask]
    fg = dominant_fg(flat, mask, palette)
    return [mask[r * 8:(r + 1) * 8] for r in range(8)], fg


def word(card, color):
    w = 0x0800 + card * 8 + (color & 7)
    if color >= 8:
        w += 0x1000
    return w


def emit_bitmap(out, mask_rows):
    for row in mask_rows:
        out.append("    BITMAP \"%s\"" % "".join("#" if m else "." for m in row))


def main():
    preview = "--preview" in sys.argv
    data = json.loads(TILESET.read_text())
    palette = [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in data["palette"]]

    cards = [None] * TOTAL_CARDS   # (mask_rows, fg, comment)
    tile_fg = {}

    for slot, tid in enumerate(USED_TILES):
        entry = data["tiles"][tid]
        ov = OVERRIDES.get(tid, {})
        if tid in HAND_TILES:
            rows, fg = HAND_TILES[tid]
            mask = [[c == "#" for c in row] for row in rows]
            rule = "hand"
        else:
            rule = "field" if tid in FIELD_TILES else "object"
            mask, fg = convert(tile_pixels(entry), palette, rule, invert=ov.get("invert", False))
        fg = ov.get("fg", fg)
        tile_fg[tid] = fg
        cards[slot] = (mask, fg, "tile %d %s (%s, fg %s)" % (tid, entry["name"], rule, STIC_NAMES[fg]))

    players = {p["index"]: p for p in data["players"]}
    for card, frame, name in ((CARD_PLY_FRONT, 0, "player front"),
                              (CARD_PLY_RIGHT, 2, "player right"),
                              (CARD_PLY_LEFT, 4, "player left")):
        mask, _ = convert(tile_pixels(players[frame]), palette, "object", bg_index=0)
        cards[card] = (mask, COLOR_LOCAL, name)

    potion = next(e for e in data["entities"] if e["name"] == "item_potion")
    mask, fg = convert(tile_pixels(potion), palette, "object", bg_index=0)
    cards[CARD_POTION] = (mask, fg, "item potion")

    cards[CARD_HEART] = ([[c == "#" for c in row] for row in HEART_ROWS], COLOR_HEART, "HUD heart")

    if preview:
        for i, (mask, fg, comment) in enumerate(cards):
            print("GRAM %2d %s" % (i, comment), file=sys.stderr)
            for row in mask:
                print("   " + "".join("#" if m else "." for m in row), file=sys.stderr)

    out = []
    out.append("' gfx.bas -- GRAM cards + color tables (GENERATED FILE, hand-tweakable via")
    out.append("' tools/convert_tiles.py OVERRIDES; regenerate: python3 tools/convert_tiles.py > gfx.bas)")
    out.append("' Source art: lynx-client/art/lynx_tileset.json. %d GRAM cards used." % TOTAL_CARDS)
    out.append("")
    out.append("' gfx_init: one-time GRAM load. Each DEFINE takes effect on the next video")
    out.append("' frame, so every DEFINE is followed by WAIT (max 16 cards per DEFINE).")
    out.append("gfx_init: PROCEDURE")
    for base in range(0, TOTAL_CARDS, 16):
        n = min(16, TOTAL_CARDS - base)
        out.append("    DEFINE %d, %d, gfx_b%d : WAIT" % (base, n, base))
    out.append("END")
    out.append("")
    for i, (mask, fg, comment) in enumerate(cards):
        if i % 16 == 0:
            out.append("gfx_b%d:" % i)
        out.append("' GRAM %d <- %s" % (i, comment))
        emit_bitmap(out, mask)
    out.append("")

    out.append("' tile_word: BACKTAB word (GRAM card + fg color, color-stack mode) per")
    out.append("' logical tile id 0-51. Unused/legacy ids render as blank (word 0).")
    out.append("tile_word:")
    words = []
    for tid in range(52):
        if tid in tile_fg:
            words.append(word(USED_TILES.index(tid), tile_fg[tid]))
        else:
            words.append(0)
    for row in range(0, 52, 8):
        chunk = words[row:row + 8]
        out.append("    DATA %s\t' ids %d-%d" %
                   (",".join("$%04X" % w for w in chunk), row, min(row + 7, 51)))
    out.append("")

    out.append("' ply_word/rem_word: facing 0-7 -> player BACKTAB word (local white,")
    out.append("' remote orange; same GRAM cards, recolored via the word).")
    out.append("ply_word:")
    out.append("    DATA %s" % ",".join("$%04X" % word(c, COLOR_LOCAL) for c in FACING_CARD))
    out.append("rem_word:")
    out.append("    DATA %s" % ",".join("$%04X" % word(c, COLOR_REMOTE) for c in FACING_CARD))
    out.append("")

    out.append("' kind_tile: WORLD_STATE entity species 1-8 -> tile id for its card")
    out.append("' (index 0 unused; bat/slime renderers add the FRAME anim bit).")
    out.append("kind_tile:")
    out.append("    DATA %s" % ",".join(str(t) for t in KIND_TILE))
    out.append("")

    out.append("' item_word: ITEM_DROPS item_id 0-7 -> BACKTAB word.")
    out.append("' 1 gold, 2 sticks, 3 herb, 4 potion, 5 warden key, 6 oil sample, 7 rust sample.")
    item_words = [0,
                  words[34], words[35], words[3],
                  word(CARD_POTION, cards[CARD_POTION][1]),
                  words[39],
                  word(CARD_POTION, 10),   # oil sample: potion card, orange
                  word(CARD_POTION, 8)]    # rust sample: potion card, grey
    out.append("item_word:")
    out.append("    DATA %s" % ",".join("$%04X" % w for w in item_words))
    out.append("")
    out.append("' hud_word: HUD glyph words (index 0 = heart). A DATA table rather than a")
    out.append("' CONST so files compiled before this one can reference it.")
    out.append("hud_word:")
    out.append("    DATA $%04X" % word(CARD_HEART, COLOR_HEART))
    out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main()
