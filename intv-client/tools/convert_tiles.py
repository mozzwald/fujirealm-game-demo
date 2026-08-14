#!/usr/bin/env python3
"""Seed art/intv_cards.json: Intellivision GRAM cards derived from the Lynx tileset.

BOOTSTRAP TOOL -- not part of the build. The Intellivision's source of truth is
art/intv_cards.json, hand-edited in tools/tile-editor/intv.html and compiled to
gfx.bas by tools/gen_gfx.py (that one *is* wired into the Makefile). This script
exists to produce the initial JSON, and to document how the cards that shipped
before the editor existed were arrived at. Re-running it discards hand-drawn art.

The derivation below reads lynx-client/art/lynx_tileset.json (8x8 tiles, 16-color
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
    python3 tools/convert_tiles.py --seed      # (re)write art/intv_cards.json
    python3 tools/convert_tiles.py --preview   # ASCII proofs to stderr
"""

import json
import sys
from collections import Counter
from pathlib import Path

from intv_cards import (
    CARD_HEART, CARD_PLY_FRONT, CARD_PLY_LEFT, CARD_PLY_RIGHT, CARD_POTION,
    COLOR_LOCAL, PROJECT_TYPE, PROJECT_VERSION, STIC, STIC_NAMES, TOTAL_CARDS,
    USED_TILES, bindings, card_record, comment_for,
)

TILESET = Path(__file__).resolve().parents[2] / "lynx-client/art/lynx_tileset.json"
CARDS = Path(__file__).resolve().parents[1] / "art/intv_cards.json"

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

COLOR_HEART = 2    # RED


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


def main():
    preview = "--preview" in sys.argv
    data = json.loads(TILESET.read_text())
    palette = [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in data["palette"]]

    cards = [None] * TOTAL_CARDS   # dicts in the art/intv_cards.json card shape

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
        cards[slot] = card_record(slot, "tile", entry["name"], fg, mask, tile=tid, rule=rule)

    players = {p["index"]: p for p in data["players"]}
    for slot, frame, name in ((CARD_PLY_FRONT, 0, "player front"),
                              (CARD_PLY_RIGHT, 2, "player right"),
                              (CARD_PLY_LEFT, 4, "player left")):
        mask, _ = convert(tile_pixels(players[frame]), palette, "object", bg_index=0)
        cards[slot] = card_record(slot, "player", name, COLOR_LOCAL, mask)

    potion = next(e for e in data["entities"] if e["name"] == "item_potion")
    mask, fg = convert(tile_pixels(potion), palette, "object", bg_index=0)
    cards[CARD_POTION] = card_record(CARD_POTION, "item", "item potion", fg, mask)

    heart = [[c == "#" for c in row] for row in HEART_ROWS]
    cards[CARD_HEART] = card_record(CARD_HEART, "hud", "HUD heart", COLOR_HEART, heart)

    if preview:
        for card in cards:
            print("GRAM %2d %s" % (card["index"], comment_for(card)), file=sys.stderr)
            for row in card["rows"]:
                print("   " + row, file=sys.stderr)
        return

    if "--seed" not in sys.argv:
        sys.exit("usage: convert_tiles.py --seed | --preview  (see the module docstring)")

    project = {
        "projectType": PROJECT_TYPE,
        "version": PROJECT_VERSION,
        "cardWidth": 8,
        "cardHeight": 8,
        "cardCount": TOTAL_CARDS,
        "palette": ["#%02X%02X%02X" % rgb for rgb in STIC],
        "colorNames": STIC_NAMES,
        "cards": cards,
        "bindings": bindings(cards),
    }
    CARDS.parent.mkdir(parents=True, exist_ok=True)
    CARDS.write_text(json.dumps(project, indent=1) + "\n")
    print("wrote %s (%d cards)" % (CARDS, TOTAL_CARDS), file=sys.stderr)



if __name__ == "__main__":
    main()
