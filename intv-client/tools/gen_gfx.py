#!/usr/bin/env python3
"""Compile art/intv_cards.json into gfx.bas -- GRAM cards + BACKTAB colour tables.

The emitted file is exactly what the pre-editor generator produced, comments
included, so seeding the JSON from the shipped art and regenerating is a no-op
diff. Schema, bindings and the word encoder live in tools/intv_cards.py.

Usage (from intv-client/):
    python3 tools/gen_gfx.py > gfx.bas
    python3 tools/gen_gfx.py --check      # fail if gfx.bas is stale
"""

import sys
from pathlib import Path

from intv_cards import (
    GRAM_CAPACITY, KIND_TILE, TILE_COUNT, TOTAL_CARDS,
    CardError, comment_for, load, spec_word, tile_words, word,
)

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "art/intv_cards.json"
GFX = ROOT / "gfx.bas"

# The STIC latches a DEFINE at the next video frame, so each batch is followed
# by WAIT; the hardware takes at most 16 cards per DEFINE.
CARDS_PER_DEFINE = 16


def generate(project):
    cards = project["cards"]
    out = []
    out.append("' gfx.bas -- GRAM cards + color tables (GENERATED FILE, edit the art in")
    out.append("' tools/tile-editor/intv.html; regenerate: make art, or python3 tools/gen_gfx.py > gfx.bas)")
    out.append("' Source art: art/intv_cards.json. %d of %d GRAM cards used."
               % (TOTAL_CARDS, GRAM_CAPACITY))
    out.append("")
    out.append("' gfx_init: one-time GRAM load. Each DEFINE takes effect on the next video")
    out.append("' frame, so every DEFINE is followed by WAIT (max %d cards per DEFINE)."
               % CARDS_PER_DEFINE)
    out.append("gfx_init: PROCEDURE")
    for base in range(0, TOTAL_CARDS, CARDS_PER_DEFINE):
        n = min(CARDS_PER_DEFINE, TOTAL_CARDS - base)
        out.append("    DEFINE %d, %d, gfx_b%d : WAIT" % (base, n, base))
    out.append("END")
    out.append("")
    for card in cards:
        if card["index"] % CARDS_PER_DEFINE == 0:
            out.append("gfx_b%d:" % card["index"])
        out.append("' GRAM %d <- %s" % (card["index"], comment_for(card)))
        for row in card["rows"]:
            out.append("    BITMAP \"%s\"" % row)
    out.append("")

    words = tile_words(cards)
    out.append("' tile_word: BACKTAB word (GRAM card + fg color, color-stack mode) per")
    out.append("' logical tile id 0-%d. Unused/legacy ids render as blank (word 0)." % (TILE_COUNT - 1))
    out.append("tile_word:")
    for row in range(0, TILE_COUNT, 8):
        chunk = words[row:row + 8]
        out.append("    DATA %s\t' ids %d-%d" %
                   (",".join("$%04X" % w for w in chunk), row, min(row + 7, TILE_COUNT - 1)))
    out.append("")

    binds = project["bindings"]
    out.append("' ply_word/rem_word: facing 0-7 -> player BACKTAB word (local white,")
    out.append("' remote orange; same GRAM cards, recolored via the word).")
    out.append("ply_word:")
    out.append("    DATA %s" % ",".join("$%04X" % word(c, binds["localColor"])
                                        for c in binds["facingCard"]))
    out.append("rem_word:")
    out.append("    DATA %s" % ",".join("$%04X" % word(c, binds["remoteColor"])
                                        for c in binds["facingCard"]))
    out.append("")

    out.append("' kind_tile: WORLD_STATE entity species 1-%d -> tile id for its card"
               % (len(KIND_TILE) - 1))
    out.append("' (index 0 unused; bat/slime renderers add the FRAME anim bit).")
    out.append("kind_tile:")
    out.append("    DATA %s" % ",".join(str(t) for t in binds["kindTile"]))
    out.append("")

    out.append("' item_word: ITEM_DROPS item_id 0-7 -> BACKTAB word.")
    out.append("' 1 gold, 2 sticks, 3 herb, 4 potion, 5 warden key, 6 oil sample, 7 rust sample.")
    out.append("item_word:")
    out.append("    DATA %s" % ",".join("$%04X" % spec_word(spec, cards, words)
                                        for spec in binds["itemWords"]))
    out.append("")
    out.append("' hud_word: HUD glyph words (index 0 = heart). A DATA table rather than a")
    out.append("' CONST so files compiled before this one can reference it.")
    out.append("hud_word:")
    out.append("    DATA %s" % ",".join("$%04X" % spec_word(spec, cards, words)
                                        for spec in binds["hudWords"]))
    out.append("")
    return "\n".join(out) + "\n"


def main():
    try:
        project = load(CARDS)
    except CardError as exc:
        sys.exit("%s: %s" % (CARDS.name, exc))
    text = generate(project)

    if "--check" in sys.argv:
        if not GFX.exists():
            sys.exit("gfx.bas is missing; run: make -C intv-client art")
        if GFX.read_text() != text:
            sys.exit("gfx.bas is stale -- art/intv_cards.json has moved on. "
                     "Run: make -C intv-client art")
        print("gfx.bas is current with art/intv_cards.json")
        return
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
