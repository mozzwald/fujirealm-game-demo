"""Shared schema for art/intv_cards.json -- the Intellivision art source of truth.

Two tools sit either side of this file: tools/convert_tiles.py seeds the JSON
from the Lynx tileset (bootstrap only), and tools/gen_gfx.py compiles it to
gfx.bas (wired into the Makefile). tools/tile-editor/intv-model.js is the
browser-side twin of the validation and the word encoder here; changes to
either must land in both.

A GRAM card is 8x8 1bpp. Colour is not in the card: the screen runs in
colour-stack mode with all four entries black (MODE 0,0,0,0,0 in
fujirealm.bas), so the background is always black and each BACKTAB word
carries one STIC foreground colour for the cell. That is why every card here
is a shape plus a single colour index, and why the same player cards can be
re-coloured for remote players without spending more GRAM.
"""

import json

PROJECT_TYPE = "fujirealm-intv-cards"
PROJECT_VERSION = 1

CARD_W = 8
CARD_H = 8
GRAM_CAPACITY = 64          # the STIC's GRAM holds 64 cards; we use 40

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
TILE_COUNT = 52             # tile_word covers ids 0-51; unused ids emit word 0

TOTAL_TILE_CARDS = len(USED_TILES)          # 35
CARD_PLY_FRONT = TOTAL_TILE_CARDS           # players[0]
CARD_PLY_RIGHT = TOTAL_TILE_CARDS + 1       # players[2]
CARD_PLY_LEFT = TOTAL_TILE_CARDS + 2        # players[4]
CARD_POTION = TOTAL_TILE_CARDS + 3          # entities[14] item_potion
CARD_HEART = TOTAL_TILE_CARDS + 4           # hand-drawn HUD glyph
TOTAL_CARDS = TOTAL_TILE_CARDS + 5          # 40

COLOR_LOCAL = 7    # WHITE  -- local player card color
COLOR_REMOTE = 10  # ORANGE -- remote players, same cards recolored

# --- runtime bindings -------------------------------------------------------
# These are the contract with render.bas and the server's ids, not art. The
# editor shows them and refuses to save a file whose bindings were altered.

# facing 0-7 (up,down,left,right,ul,ur,dl,dr) -> player card, mirroring the
# Lynx facing_frame table (no back art; up shares the front card).
FACING_CARD = [CARD_PLY_FRONT, CARD_PLY_FRONT, CARD_PLY_LEFT, CARD_PLY_RIGHT,
               CARD_PLY_LEFT, CARD_PLY_RIGHT, CARD_PLY_LEFT, CARD_PLY_RIGHT]

# WORLD_STATE entity species -> logical tile id whose card draws it
# (bat/slime animate by swapping to id+1 in the renderer).
KIND_TILE = [0, 8, 9, 46, 44, 36, 48, 41, 51]

# ITEM_DROPS item_id 0-7 -> a BACKTAB word, named either by the tile whose word
# it reuses or by a card plus an explicit recolour.
# 1 gold, 2 sticks, 3 herb, 4 potion, 5 warden key, 6 oil sample, 7 rust sample.
ITEM_WORDS = [None,
              {"tile": 34}, {"tile": 35}, {"tile": 3},
              {"card": CARD_POTION},
              {"tile": 39},
              {"card": CARD_POTION, "color": 10},   # oil sample: potion card, orange
              {"card": CARD_POTION, "color": 8}]    # rust sample: potion card, grey
HUD_WORDS = [{"card": CARD_HEART}]                  # index 0 = heart

KINDS = ("tile", "player", "item", "hud")


class CardError(Exception):
    """A malformed or contract-violating art/intv_cards.json."""


def rows_from_mask(mask):
    """[[bool]*8]*8 -> the 8 '#'/'.' strings stored in JSON and taken by BITMAP."""
    return ["".join("#" if m else "." for m in row) for row in mask]


def card_record(index, kind, name, color, mask, tile=None, rule=None):
    card = {"index": index, "kind": kind, "name": name}
    if tile is not None:
        card["tile"] = tile
    if rule is not None:
        card["seedRule"] = rule
    card["color"] = color
    card["rows"] = rows_from_mask(mask)
    return card


def comment_for(card):
    """The ' GRAM n <- ... comment in gfx.bas. Kept identical to what the
    pre-editor generator wrote, so a reseed diffs clean against the shipped file."""
    if card["kind"] == "tile":
        return "tile %d %s (%s, fg %s)" % (card["tile"], card["name"],
                                           card.get("seedRule", "hand"),
                                           STIC_NAMES[card["color"]])
    return card["name"]


def bindings(cards):
    return {
        "facingCard": list(FACING_CARD),
        "localColor": COLOR_LOCAL,
        "remoteColor": COLOR_REMOTE,
        "kindTile": list(KIND_TILE),
        "itemWords": [None if spec is None else dict(spec) for spec in ITEM_WORDS],
        "hudWords": [dict(spec) for spec in HUD_WORDS],
    }


def word(card, color):
    """BACKTAB word: bit 11 selects GRAM, bits 3-10 the card, bits 0-2 the
    colour's low three bits, and bit 12 its high bit (the pastel half)."""
    w = 0x0800 + card * 8 + (color & 7)
    if color >= 8:
        w += 0x1000
    return w


def tile_words(cards):
    """Logical tile id 0-51 -> BACKTAB word; 0 for ids the game never streams."""
    words = [0] * TILE_COUNT
    for card in cards:
        if card["kind"] == "tile":
            words[card["tile"]] = word(card["index"], card["color"])
    return words


def spec_word(spec, cards, words):
    """Resolve an itemWords/hudWords entry to a literal BACKTAB word."""
    if spec is None:
        return 0
    if "tile" in spec:
        return words[spec["tile"]]
    color = spec.get("color", cards[spec["card"]]["color"])
    return word(spec["card"], color)


# --- validation -------------------------------------------------------------

def _check_rows(rows, label):
    if not isinstance(rows, list) or len(rows) != CARD_H:
        raise CardError("%s: expected %d rows" % (label, CARD_H))
    for y, row in enumerate(rows):
        if not isinstance(row, str) or len(row) != CARD_W:
            raise CardError("%s row %d: expected %d characters" % (label, y, CARD_W))
        for ch in row:
            if ch not in "#.":
                raise CardError("%s row %d: %r is not '#' or '.'" % (label, y, ch))


def validate(project):
    """Raise CardError unless the project is loadable and its bindings are the
    ones the renderer was built against. Bindings are generator-owned: art is
    what you edit, and a file that moved a card out from under render.bas
    should fail here rather than three layers down in a stale ROM."""
    if not isinstance(project, dict):
        raise CardError("project root must be an object")
    if project.get("projectType") != PROJECT_TYPE:
        raise CardError("projectType must be %s" % PROJECT_TYPE)
    if project.get("version") != PROJECT_VERSION:
        raise CardError("version must be %d" % PROJECT_VERSION)
    if project.get("cardWidth") != CARD_W or project.get("cardHeight") != CARD_H:
        raise CardError("only %dx%d cards are supported" % (CARD_W, CARD_H))

    cards = project.get("cards")
    if not isinstance(cards, list) or len(cards) != TOTAL_CARDS:
        raise CardError("expected %d cards" % TOTAL_CARDS)
    seen_tiles = set()
    for slot, card in enumerate(cards):
        label = "card %d" % slot
        if card.get("index") != slot:
            raise CardError("%s: index must equal its position" % label)
        if card.get("kind") not in KINDS:
            raise CardError("%s: kind must be one of %s" % (label, ", ".join(KINDS)))
        color = card.get("color")
        if not isinstance(color, int) or isinstance(color, bool) or not 0 <= color < len(STIC):
            raise CardError("%s: color must be a STIC index 0-15" % label)
        if color == 0:
            raise CardError("%s: color 0 is black, which is the background -- "
                            "the card would be invisible" % label)
        _check_rows(card.get("rows"), label)
        if card["kind"] == "tile":
            tile = card.get("tile")
            if tile not in USED_TILES:
                raise CardError("%s: tile %r is not a streamed tile id" % (label, tile))
            if tile in seen_tiles:
                raise CardError("%s: duplicate tile id %d" % (label, tile))
            seen_tiles.add(tile)
    if seen_tiles != set(USED_TILES):
        missing = sorted(set(USED_TILES) - seen_tiles)
        raise CardError("no card for tile id(s) %s" % ", ".join(str(t) for t in missing))

    expected = bindings(cards)
    if project.get("bindings") != expected:
        raise CardError("bindings are generated metadata and must not be edited; "
                        "they no longer match tools/intv_cards.py")
    return project


def load(path):
    try:
        project = json.loads(path.read_text())
    except FileNotFoundError:
        raise CardError("%s does not exist; seed it with "
                        "python3 tools/convert_tiles.py --seed" % path)
    except json.JSONDecodeError as exc:
        raise CardError("%s is not valid JSON: %s" % (path, exc))
    return validate(project)
