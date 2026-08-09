#!/usr/bin/env python3
"""Convert the FujiRealm charsetter project into Lynx sprite data + CLUT.

Reads atari8-client/art/fujirealm_charsetter.json (via the shared validator in
tools/charsetter.py), composes each logical 2x2 tile / player frame into a
16x16 4bpp totally-literal Suzy sprite, assigns per-tile-type pens from one
16-color CLUT, and writes deterministic C arrays into art/lynx_art.[ch].

Pixel values are final CLUT indices, so the client uses one identity penpal
for every sprite. Terrain tiles are opaque; entity sprites use pen 0 as
transparent (Suzy non-collideable sprite type skips pen 0).

Usage: tools/import_lynx_art.py [--preview out.png] [--check]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
import sys
from pathlib import Path

CLIENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CLIENT_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from charsetter import validate_project  # noqa: E402

PROJECT = REPO_ROOT / "atari8-client" / "art" / "fujirealm_charsetter.json"
TILESET = CLIENT_ROOT / "art" / "lynx_tileset.json"
OUT_C = CLIENT_ROOT / "art" / "lynx_art.c"
OUT_H = CLIENT_ROOT / "art" / "lynx_art.h"

# Logical tile ids 0..TILE_COUNT-1, shared with the Atari client and the
# server's terrain stream. Phase 61 (The Dam Below) grew the allocation from 40
# to 52 to make room for the named cast and the Floodworks props; see
# docs/TILE_ALLOCATION.md, which is the id contract. The index into
# every tile array here IS the server's tile id.
TILE_COUNT = 52
PLAYER_FRAME_COUNT = 12

# ---------------------------------------------------------------------------
# The global 16-color CLUT (RGB). Index 0 doubles as the transparent pen for
# entity sprites, so nothing opaque may map to it except true black.
CLUT = (
    (0, 0, 0),         # 0  black / transparent
    (44, 92, 40),      # 1  dark green (grass shadow, border, foliage dark)
    (74, 132, 58),     # 2  grass
    (104, 168, 76),    # 3  grass light
    (140, 194, 92),    # 4  leaf highlight
    (98, 62, 30),      # 5  trunk / dark brown
    (152, 108, 62),    # 6  mid brown (road, beaver body)
    (204, 176, 132),   # 7  tan / skin / road light
    (28, 52, 110),     # 8  deep water / HUD navy
    (62, 122, 198),    # 9  water
    (158, 204, 236),   # 10 water sparkle / pale blue
    (124, 116, 104),   # 11 stone light
    (78, 72, 66),      # 12 stone dark
    (206, 70, 50),     # 13 red (roofs, hearts, flowers)
    (228, 188, 64),    # 14 gold / yellow
    (236, 236, 236),   # 15 white
)

# Per-role pen maps: ANTIC4 pixel value (0,1,2,3) plus the char hi-bit
# variant of 3 -> CLUT index. Key order: (v0, v1, v2, v3, v3hi).
G = dict(zip("01234", (2, 3, 1, 3, 3)))          # grass-ish default


def role(v0, v1, v2, v3, v3hi):
    return {"0": v0, "1": v1, "2": v2, "3": v3, "4": v3hi}


ROLE_GRASS = role(2, 3, 1, 3, 3)
ROLE_TREE = role(2, 1, 5, 4, 6)
ROLE_HERB = role(2, 3, 1, 13, 13)
ROLE_WATER = role(8, 9, 8, 10, 10)
ROLE_ROAD = role(6, 7, 5, 7, 7)
ROLE_BUILD = role(2, 11, 12, 13, 13)
ROLE_BORDER = role(1, 1, 1, 1, 1)
ROLE_CAVE = role(12, 11, 5, 7, 7)
ROLE_GRAVE = role(2, 11, 12, 15, 15)
ROLE_GOLD = role(2, 14, 5, 14, 14)
ROLE_STICKS = role(2, 6, 5, 7, 7)
ROLE_CHARM = role(2, 13, 5, 15, 15)
ROLE_HUD = role(0, 15, 12, 14, 14)               # internal glyph tiles
# The Dam Below cast and bestiary. These only seed the initial pixels for a new
# slot; once the tileset holds the slot, the tileset's own rows win.
ROLE_SNAKE = role(2, 3, 1, 14, 14)
ROLE_NPC_TAN = role(2, 7, 5, 14, 14)             # Daniel, generic townsfolk
ROLE_NPC_BROWN = role(2, 7, 5, 6, 6)             # Wilhelm
ROLE_NPC_BLUE = role(2, 10, 8, 15, 15)           # Nerissa
ROLE_NPC_STONE = role(2, 11, 12, 15, 15)         # Lucian
ROLE_GOBLIN_NPC = role(2, 3, 1, 15, 15)          # Grix
ROLE_KEY = role(2, 14, 5, 15, 15)                # Warden Key
ROLE_SLIME = role(2, 3, 1, 10, 10)
ROLE_BAT = role(2, 12, 11, 13, 13)
ROLE_GORVAK = role(2, 13, 5, 14, 14)
ROLE_MACHINE = role(12, 11, 5, 14, 14)           # Deep Pump, Pump Controls

# tile index -> pen map (terrain tiles are opaque; index order is the locked
# logical tile list in the charsetter project).
TILE_ROLES = {
    0: ROLE_GRASS, 1: ROLE_GRASS, 2: ROLE_TREE, 3: ROLE_HERB,
    4: ROLE_TREE, 5: ROLE_TREE, 6: ROLE_STICKS, 7: ROLE_BORDER,
    8: ROLE_GRASS, 10: ROLE_ROAD, 11: ROLE_WATER,
    12: ROLE_BUILD, 13: ROLE_CAVE, 14: ROLE_GRAVE, 15: ROLE_CAVE,
    16: ROLE_CAVE, 17: ROLE_CAVE, 34: ROLE_GOLD, 35: ROLE_STICKS,
    36: ROLE_GRASS, 37: ROLE_NPC_TAN, 38: ROLE_GOBLIN_NPC, 39: ROLE_KEY,
    # Phase 61: slot 9 was Beaver Hurt (art deleted, the hurt state is now a
    # blink) and 37-39 were Farmer Dan / Friendly Goblin / Lost Charm.
    9: ROLE_SNAKE,
    40: ROLE_NPC_TAN,      # Daniel
    41: ROLE_NPC_BROWN,    # Wilhelm
    42: ROLE_NPC_STONE,    # Lucian
    43: ROLE_NPC_BLUE,     # Nerissa
    44: ROLE_SLIME, 45: ROLE_SLIME,
    46: ROLE_BAT, 47: ROLE_BAT,
    48: ROLE_GORVAK,
    49: ROLE_MACHINE,      # Deep Pump
    50: ROLE_MACHINE,      # Pump Controls
    51: ROLE_NPC_BROWN,    # Wilhelm Working
}
# 18..33 are internal HUD glyph tiles; keep them renderable just in case.
for internal in range(18, 34):
    TILE_ROLES[internal] = ROLE_HUD

# Entity sprites drawn over terrain: pen0 transparent (0), body colors per
# entity. Source logical tile index -> (name, pen map).
#
# Only kinds that arrive in a WORLD_STATE dynamic-entity slot need a sprite.
# The named NPCs (37, 38, 40-43) and the Floodworks props (49, 50) are stamped
# into the terrain stream as a static overlay instead, so they are terrain-only
# and deliberately absent here -- except Wilhelm, who is both a town landmark
# and an escorted entity.
ENTITY_SPRITES = (
    ("beaver", 8, role(0, 6, 5, 15, 15)),
    ("snake", 9, role(0, 3, 1, 14, 14)),
    ("goblin", 36, role(0, 3, 1, 13, 13)),
    ("slime0", 44, role(0, 3, 1, 10, 10)),
    ("slime1", 45, role(0, 3, 1, 10, 10)),
    ("bat0", 46, role(0, 12, 11, 13, 13)),
    ("bat1", 47, role(0, 12, 11, 13, 13)),
    ("gorvak", 48, role(0, 13, 5, 14, 14)),
    ("wilhelm", 41, role(0, 7, 5, 6, 6)),
    ("wilhelm_working", 51, role(0, 7, 5, 6, 6)),
    ("bullet", 6, role(0, 14, 5, 15, 15)),
    # Item drops render over terrain, so pen 0 is transparent. These are
    # added to the tileset by tools/add_item_sprites.py and hand-tuned in the
    # editor; the tile_index/pen_map here only seed the legacy A8-conversion
    # fallback used before the tileset exists.
    ("item_gold", 34, role(0, 14, 5, 14, 14)),
    ("item_sticks", 35, role(0, 6, 5, 7, 7)),
    ("item_herb", 3, role(0, 3, 1, 13, 13)),
    ("item_potion", 3, role(0, 9, 5, 10, 10)),
    ("item_key", 39, role(0, 14, 5, 15, 15)),
)
# Player frames (12): outfit green, skin tan, accents.
ROLE_PLAYER = role(0, 1, 7, 14, 13)

# ---------------------------------------------------------------------------
# 4x5 HUD font, ASCII 32..95. '#' is repurposed as a heart glyph.
FONT_4X5 = {
    "A": ".##. #..# #### #..# #..#", "B": "###. #..# ###. #..# ###.",
    "C": ".### #... #... #... .###", "D": "###. #..# #..# #..# ###.",
    "E": "#### #... ###. #... ####", "F": "#### #... ###. #... #...",
    "G": ".### #... #.## #..# .###", "H": "#..# #..# #### #..# #..#",
    "I": "###. .#.. .#.. .#.. ###.", "J": "..## ...# ...# #..# .##.",
    "K": "#..# #.#. ##.. #.#. #..#", "L": "#... #... #... #... ####",
    "M": "#..# #### #### #..# #..#", "N": "#..# ##.# #.## #..# #..#",
    "O": ".##. #..# #..# #..# .##.", "P": "###. #..# ###. #... #...",
    "Q": ".##. #..# #..# #.## .###", "R": "###. #..# ###. #.#. #..#",
    "S": ".### #... .##. ...# ###.", "T": "#### ..#. ..#. ..#. ..#.",
    "U": "#..# #..# #..# #..# .##.", "V": "#..# #..# #..# .##. .##.",
    "W": "#..# #..# #### #### #..#", "X": "#..# .##. .##. .##. #..#",
    "Y": "#..# .##. ..#. ..#. ..#.", "Z": "#### ...# .##. #... ####",
    "0": ".##. #..# #..# #..# .##.", "1": ".#.. ##.. .#.. .#.. ###.",
    "2": "###. ...# .##. #... ####", "3": "###. ...# .##. ...# ###.",
    "4": "#..# #..# #### ...# ...#", "5": "#### #... ###. ...# ###.",
    "6": ".### #... ###. #..# .##.", "7": "#### ...# ..#. .#.. .#..",
    "8": ".##. #..# .##. #..# .##.", "9": ".##. #..# .### ...# ###.",
    "!": ".#.. .#.. .#.. .... .#..", '"': "#.#. #.#. .... .... ....",
    "#": ".##. #### #### .##. ..#.",  # heart
    "$": ".### ##.. .##. ..## ###.", "%": "#..# ...# .##. #... #..#",
    "&": ".##. #... .##. #.#. .###", "'": ".#.. .#.. .... .... ....",
    "(": "..#. .#.. .#.. .#.. ..#.", ")": ".#.. ..#. ..#. ..#. .#..",
    "*": ".... #.#. .##. #.#. ....", "+": ".... .#.. ###. .#.. ....",
    ",": ".... .... .... .#.. #...", "-": ".... .... ###. .... ....",
    ".": ".... .... .... .... .#..", "/": "...# ..#. .#.. #... ....",
    ":": ".... .#.. .... .#.. ....", ";": ".... .#.. .... .#.. #...",
    "<": "..#. .#.. #... .#.. ..#.", "=": ".... ###. .... ###. ....",
    ">": "#... .#.. ..#. .#.. #...", "?": "###. ...# .##. .... .#..",
    "@": ".##. #..# #.## #... .###", "[": ".##. .#.. .#.. .#.. .##.",
    "\\": "#... .#.. ..#. ...# ....", "]": ".##. ..#. ..#. ..#. .##.",
    "^": ".#.. #.#. .... .... ....", "_": ".... .... .... .... ####",
    " ": ".... .... .... .... ....",
}


def glyph_rows(char):
    spec = FONT_4X5.get(char, FONT_4X5[" "]).split()
    rows = []
    for row in spec:
        bits = 0
        for i, cell in enumerate(row):
            if cell == "#":
                bits |= 8 >> i
        rows.append(bits)
    return rows


# ---------------------------------------------------------------------------
def char_pixels(font, code):
    """8 rows of 4 ANTIC4 pixel values '0'..'4' (4 = hi-bit variant of 3)."""
    hi = bool(code & 0x80)
    base = (code & 0x7F) * 8
    rows = []
    for r in range(8):
        byte = font[base + r]
        row = []
        for p in range(4):
            v = (byte >> (6 - 2 * p)) & 3
            row.append("4" if v == 3 and hi else str(v))
        rows.append(row)
    return rows


def compose_block(font, quads):
    """quads = (tl, tr, bl, br) char codes -> 16 rows x 8 source pixels."""
    tl, tr, bl, br = (char_pixels(font, c) for c in quads)
    return [tl[r] + tr[r] for r in range(8)] + [bl[r] + br[r] for r in range(8)]


def halve_rows(rows):
    """16 source rows -> 8, for the 8x8 Lynx tile grid.

    Merging a pair of rows by simply keeping the top one loses any feature
    that is a single row tall. Instead find the tile's most common value --
    its fill -- and whenever exactly one of the pair differs from the fill,
    keep that one, so thin horizontal detail survives the halving.
    """
    fill = Counter(v for row in rows for v in row).most_common(1)[0][0]
    out = []
    for index in range(0, len(rows), 2):
        top, bottom = rows[index], rows[index + 1]
        merged = []
        for a, b in zip(top, bottom):
            if a == b or a != fill:
                merged.append(a)
            else:
                merged.append(b)
        out.append(merged)
    return out


def pack_sprite(rows):
    """8 rows of 8 CLUT indices -> totally-literal 4bpp sprite, 8px wide.

    Two pixels pack per byte, leftmost in the high nibble, because Suzy
    reads the literal bit stream most significant bits first.
    """
    out = bytearray()
    for row in rows:
        # A byte-aligned totally-literal line still needs a zero pad byte;
        # Suzy otherwise consumes the next line's count as pixel data.
        out.append(6)  # count + 4 pixel bytes + EOL pad
        for i in range(0, len(row), 2):
            out.append((row[i] << 4) | row[i + 1])
        out.append(0)
    out.append(0)  # end of sprite
    return bytes(out)


# Tiles that are an object standing on some other ground. The renderer used to
# draw these as a base tile plus a transparent object on top; the CPU tile
# blitter instead uses a precomposed opaque raw tile (object pixels over the
# base where the object pen is 0), so terrain is always one flat copy.
#
# The base is per tile, not always grass: the Floodworks props sit on cave
# floor, and compositing them over grass would ring them with green. Keep in
# sync with object_tile_base in render.c.
GRASS_TILE_INDEX = 0
CAVE_FLOOR_TILE_INDEX = 15
OBJECT_TILE_BASE = {
    3: GRASS_TILE_INDEX,    # herb
    14: GRASS_TILE_INDEX,   # grave
    37: GRASS_TILE_INDEX,   # town NPC (generic)
    38: GRASS_TILE_INDEX,   # Grix
    40: GRASS_TILE_INDEX,   # Daniel
    41: GRASS_TILE_INDEX,   # Wilhelm
    42: GRASS_TILE_INDEX,   # Lucian
    43: GRASS_TILE_INDEX,   # Nerissa
    49: CAVE_FLOOR_TILE_INDEX,   # Deep Pump
    50: CAVE_FLOOR_TILE_INDEX,   # Pump Controls
    51: GRASS_TILE_INDEX,   # Wilhelm Working
}


def pack_raw_row(row8):
    """8 CLUT indices -> 4 bytes, two pixels per byte, leftmost in the high
    nibble -- the Lynx 4bpp framebuffer's own pixel order, so these bytes copy
    straight into the display buffer (no Suzy count/pad framing)."""
    return bytes(((row8[i] << 4) | row8[i + 1]) for i in range(0, 8, 2))


def raw_tile(rows, base_rows=None):
    """8 rows of 8 CLUT indices -> 32 raw framebuffer bytes for the CPU blitter.

    With base_rows given, pen 0 of this tile is replaced by the pixel of the
    ground beneath it, precomposing an object tile into one opaque cell.
    """
    out = bytearray()
    for y, row in enumerate(rows):
        if base_rows is not None:
            row = [base_rows[y][x] if row[x] == 0 else row[x] for x in range(8)]
        out += pack_raw_row(row)
    return bytes(out)


def raw_tiles(tile_rows):
    """Per-tile CLUT rows -> raw 32-byte blobs, object tiles precomposed over
    whichever ground tile they stand on."""
    def base_for(index):
        base = OBJECT_TILE_BASE.get(index)
        return None if base is None else tile_rows[base]

    return [raw_tile(tile_rows[i], base_for(i)) for i in range(len(tile_rows))]


def clut_rows(pixels, pen_map):
    """16x8 ANTIC source -> 8 rows of 8 CLUT indices."""
    return [[pen_map[v] for v in row] for row in halve_rows(pixels)]


def sprite_bytes(pixels, pen_map):
    """16x8 ANTIC source pixels -> 8x8 Lynx sprite (legacy conversion path).

    The art is authored 8 wide and was previously doubled to 16 screen
    pixels; at the 8x8 grid it maps 1:1, so horizontal detail is unchanged.
    """
    return pack_sprite(clut_rows(pixels, pen_map))


def emit_rows(data, per_line=12):
    lines = []
    for start in range(0, len(data), per_line):
        chunk = data[start : start + per_line]
        lines.append("    " + ",".join(f"0x{b:02X}" for b in chunk) + ",")
    return lines


def rows_from_hex(rows, label):
    """8 strings of 8 hex digits -> 8 rows of 8 CLUT indices."""
    if not isinstance(rows, list) or len(rows) != 8:
        raise SystemExit(f"{label}: expected 8 rows, got {len(rows) if isinstance(rows, list) else type(rows).__name__}")
    out = []
    for y, row in enumerate(rows):
        if not isinstance(row, str) or len(row) != 8:
            raise SystemExit(f"{label} row {y}: expected 8 hex digits, got {row!r}")
        try:
            out.append([int(ch, 16) for ch in row])
        except ValueError:
            raise SystemExit(f"{label} row {y}: {row!r} is not hex")
    return out


def build_from_tileset():
    """Build from the hand-editable tileset, the source of truth once seeded."""
    data = json.loads(TILESET.read_text(encoding="utf-8"))
    if data.get("projectType") != "fujirealm-lynx-tiles":
        raise SystemExit(f"{TILESET}: not a fujirealm-lynx-tiles project")
    if data.get("tileWidth") != 8 or data.get("tileHeight") != 8:
        raise SystemExit(f"{TILESET}: only 8x8 tiles are supported")

    palette = data.get("palette", [])
    if len(palette) != 16:
        raise SystemExit(f"{TILESET}: palette must hold 16 colours")
    clut = []
    for index, value in enumerate(palette):
        text = str(value).lstrip("#")
        if len(text) != 6:
            raise SystemExit(f"{TILESET}: palette[{index}] must be #RRGGBB")
        clut.append(tuple(int(text[i:i + 2], 16) for i in (0, 2, 4)))

    tiles = sorted(data.get("tiles", []), key=lambda t: t["index"])
    if len(tiles) != TILE_COUNT:
        raise SystemExit(f"{TILESET}: expected {TILE_COUNT} tiles, got {len(tiles)}")
    tile_rows = [rows_from_hex(t["rows"], f"tile {t['index']}") for t in tiles]
    tile_blobs = [pack_sprite(rows) for rows in tile_rows]
    tile_raw_blobs = raw_tiles(tile_rows)

    players = sorted(data.get("players", []), key=lambda p: p["index"])
    if len(players) != PLAYER_FRAME_COUNT:
        raise SystemExit(
            f"{TILESET}: expected {PLAYER_FRAME_COUNT} player frames, got {len(players)}")
    player_blobs = [pack_sprite(rows_from_hex(p["rows"], f"player {p['index']}"))
                    for p in players]

    expected = [name for name, _, _ in ENTITY_SPRITES]
    entities = {e["name"]: e for e in data.get("entities", [])}
    missing = [name for name in expected if name not in entities]
    if missing:
        raise SystemExit(f"{TILESET}: missing entity sprites: {', '.join(missing)}")
    entity_blobs = [(name, pack_sprite(rows_from_hex(entities[name]["rows"],
                                                     f"entity {name}")))
                    for name in expected]

    font_rows = []
    for code in range(32, 96):
        font_rows.extend(glyph_rows(chr(code)))
    return (tile_blobs, tile_raw_blobs, player_blobs, entity_blobs, font_rows,
            clut)


def build():
    if TILESET.exists():
        return build_from_tileset()
    # Before the tileset is seeded, fall back to converting the Atari art
    # directly. export_lynx_tileset.py writes that conversion out once, after
    # which this path is no longer used.
    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    font, tiles, sprites = validate_project(project)

    tile_rows = []
    for index in range(TILE_COUNT):
        quads = tuple(tiles[q][index] for q in range(4))
        pixels = compose_block(font, quads)
        tile_rows.append(clut_rows(pixels, TILE_ROLES[index]))
    tile_blobs = [pack_sprite(rows) for rows in tile_rows]
    tile_raw_blobs = raw_tiles(tile_rows)

    player_blobs = []
    for index in range(PLAYER_FRAME_COUNT):
        quads = tuple(sprites[q][index] for q in range(4))
        pixels = compose_block(font, quads)
        player_blobs.append(sprite_bytes(pixels, ROLE_PLAYER))

    entity_blobs = []
    for name, tile_index, pen_map in ENTITY_SPRITES:
        quads = tuple(tiles[q][tile_index] for q in range(4))
        pixels = compose_block(font, quads)
        entity_blobs.append((name, sprite_bytes(pixels, pen_map)))

    font_rows = []
    for code in range(32, 96):
        font_rows.extend(glyph_rows(chr(code)))

    return (tile_blobs, tile_raw_blobs, player_blobs, entity_blobs, font_rows,
            list(CLUT))


# Per-map palettes. The server's MAP_CHANGE carries a palette_id (0 overworld,
# 1 cave, 2 PvP realm) and the Lynx has one CLUT, so the same art is re-tinted
# rather than re-drawn: the cave goes dim and blue, the arena hot and red.
# Index 0 must stay the true black that entity sprites treat as transparent.
def tint(clut, r_mul, g_mul, b_mul):
    out = []
    for index, (r, g, b) in enumerate(clut):
        if index == 0:
            out.append((0, 0, 0))
            continue
        out.append((min(255, (r * r_mul) // 100),
                    min(255, (g * g_mul) // 100),
                    min(255, (b * b_mul) // 100)))
    return out


PALETTE_TINTS = (
    (100, 100, 100),   # 0 overworld: the authored colours
    (62, 72, 115),     # 1 starter cave: darker, cooler
    (118, 78, 82),     # 2 PvP realm: hot
)


def pack_clut(clut):
    """16 RGB triples -> the TGI palette's 16 green bytes then 16 blue/red."""
    green = [g >> 4 for (_, g, _) in clut]
    bluered = [((b >> 4) << 4) | (r >> 4) for (r, _, b) in clut]
    return green, bluered


def write_output(tile_blobs, tile_raw_blobs, player_blobs, entity_blobs,
                 font_rows, clut, check=False):
    blob_len = len(tile_blobs[0])
    raw_len = len(tile_raw_blobs[0])
    h = [
        "/* Generated by tools/import_lynx_art.py -- do not edit. */",
        "#ifndef LYNX_ART_H",
        "#define LYNX_ART_H",
        "",
        f"#define ART_SPRITE_BYTES {blob_len}",
        f"#define ART_TILE_RAW_BYTES {raw_len}",
        f"#define ART_TILE_COUNT {TILE_COUNT}",
        f"#define ART_PLAYER_FRAMES {PLAYER_FRAME_COUNT}",
        "",
        "/* TGI palettes, one per server palette_id: 16 green bytes then 16",
        "   blue/red bytes each. Index 0 is the overworld / boot palette. */",
        f"#define ART_PALETTE_COUNT {len(PALETTE_TINTS)}",
        "extern const unsigned char art_clut[ART_PALETTE_COUNT][32];",
        "/* Terrain tiles as raw 4bpp framebuffer bytes (8 rows x 4 bytes) for",
        "   the CPU tile blitter, which is the only terrain path. Object tiles",
        "   are precomposed opaque over the ground they stand on. */",
        f"extern const unsigned char art_tiles_raw[{TILE_COUNT}][ART_TILE_RAW_BYTES];",
        f"extern const unsigned char art_player[{PLAYER_FRAME_COUNT}][ART_SPRITE_BYTES];",
    ]
    for name, _ in entity_blobs:
        h.append(f"extern const unsigned char art_{name}[ART_SPRITE_BYTES];")
    h += [
        "",
        "/* 4x5 font, ASCII 32..95, 5 bytes per glyph (row bits 3..0). */",
        "extern const unsigned char art_font4x5[64 * 5];",
        "",
        "#endif",
        "",
    ]

    c = [
        "/* Generated by tools/import_lynx_art.py -- do not edit. */",
        '#include "lynx_art.h"',
        "",
        "const unsigned char art_clut[ART_PALETTE_COUNT][32] = {",
    ]
    for index, tints in enumerate(PALETTE_TINTS):
        green, bluered = pack_clut(tint(clut, *tints))
        c += [
            f"  {{ /* palette {index} */",
            "    " + ",".join(f"0x{v:02X}" for v in green) + ",",
            "    " + ",".join(f"0x{v:02X}" for v in bluered) + ",",
            "  },",
        ]
    c += [
        "};",
        "",
        f"const unsigned char art_tiles_raw[{TILE_COUNT}][ART_TILE_RAW_BYTES] = {{",
    ]
    for index, blob in enumerate(tile_raw_blobs):
        c.append(f"  {{ /* tile {index} */")
        c.extend(emit_rows(blob))
        c.append("  },")
    c += ["};", "",
          f"const unsigned char art_player[{PLAYER_FRAME_COUNT}][ART_SPRITE_BYTES] = {{"]
    for index, blob in enumerate(player_blobs):
        c.append(f"  {{ /* frame {index} */")
        c.extend(emit_rows(blob))
        c.append("  },")
    c.append("};")
    for name, blob in entity_blobs:
        c += ["", f"const unsigned char art_{name}[ART_SPRITE_BYTES] = {{"]
        c.extend(emit_rows(blob))
        c.append("};")
    c += ["", "const unsigned char art_font4x5[64 * 5] = {"]
    c.extend(emit_rows(bytes(font_rows), per_line=20))
    c += ["};", ""]

    h_text = "\n".join(h)
    c_text = "\n".join(c)
    if check:
        return (OUT_H.exists() and OUT_C.exists() and
                OUT_H.read_text(encoding="ascii") == h_text and
                OUT_C.read_text(encoding="ascii") == c_text)
    OUT_C.parent.mkdir(parents=True, exist_ok=True)
    OUT_H.write_text(h_text, encoding="ascii")
    OUT_C.write_text(c_text, encoding="ascii")
    return True


def write_preview(path, tile_blobs, player_blobs, entity_blobs):
    from PIL import Image

    # Sprites are 8x8 totally-literal: per scanline a count byte, 4 data bytes
    # (two 4bpp pixels each), and the pad byte Suzy needs after byte-aligned
    # literal data; then a 0 terminator.
    row_bytes = 4
    row_stride = row_bytes + 2

    def blit(img, ox, oy, blob, transparent):
        pos = 0
        for row in range(8):
            assert blob[pos] == row_stride, blob[pos]
            pos += 1
            for byte in range(row_bytes):
                packed = blob[pos]
                pos += 1
                for half in range(2):
                    pen = (packed >> 4) if half == 0 else (packed & 0x0F)
                    if transparent and pen == 0:
                        continue
                    img.putpixel((ox + byte * 2 + half, oy + row), CLUT[pen])
            assert blob[pos] == 0
            pos += 1
        assert pos == len(blob) - 1

    cols = 10
    cell = 10
    blobs = list(tile_blobs) + list(player_blobs) + [b for _, b in entity_blobs]
    # Only the entity sprites treat pen 0 as transparent.
    first_entity = len(tile_blobs) + len(player_blobs)
    rows = (len(blobs) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell + 2, rows * cell + 2), (32, 32, 32))
    for i, blob in enumerate(blobs):
        blit(img, 2 + (i % cols) * cell, 2 + (i // cols) * cell, blob,
             i >= first_entity)
    img = img.resize((img.width * 6, img.height * 6), Image.NEAREST)
    img.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate only")
    parser.add_argument("--preview", type=Path, help="write a PNG contact sheet")
    args = parser.parse_args()

    (tile_blobs, tile_raw_blobs, player_blobs, entity_blobs, font_rows,
     clut) = build()
    if args.preview:
        write_preview(args.preview, tile_blobs, player_blobs, entity_blobs)
    if args.check:
        if not write_output(tile_blobs, tile_raw_blobs, player_blobs,
                            entity_blobs, font_rows, clut, check=True):
            print("generated Lynx art is stale; run make art", file=sys.stderr)
            return 1
        total = sum(len(b) for b in tile_blobs + player_blobs)
        print(f"ok: {len(tile_blobs)} tiles, {len(player_blobs)} player frames, "
              f"{len(entity_blobs)} entities, {total} tile+player bytes")
        return 0
    write_output(tile_blobs, tile_raw_blobs, player_blobs, entity_blobs,
                 font_rows, clut)
    print(f"wrote {OUT_C} and {OUT_H}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
