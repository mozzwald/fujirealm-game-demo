#!/usr/bin/env python3
"""Convert the Lynx tileset into 4-gray Palm art for the FujiRealm client.

Source of truth is lynx-client/art/lynx_tileset.json (8x8 tiles, 16-colour
CLUT). Parsing, the entity list and the object-over-ground compositing table
are imported from the Lynx importer, so the clients cannot drift apart.

Palm OS draws 2 bits per pixel with 0 = white and 3 = black. Every tile and
sprite has its own hand-chosen pen -> grey map (TILE_MAPS, SPRITE_MAPS), and a
few are redrawn pixel by pixel (TILE_PIXELS, SPRITE_PIXELS); see the house
rules above those tables. --preview writes a sheet of the result.

Output (C, for m68k-palmos-gcc):
The arrays are static, behind ART_GREY / ART_MONO / ART_COLOUR: gfx.c defines the one it
draws with and includes palm_art.c (see palm_art.h for why it is not linked).

  * art_tiles[52][8]       terrain, one UInt16 per 8-pixel row, leftmost
                           pixel in the top two bits; object tiles composited
                           over their ground
  * art_sprites[N][8], art_masks[N][8]
                           players then entities; the mask has 11 for every
                           opaque pixel
  * ART_SPRITE_* indices for the entity sprites

Usage: palm_art.py <out.c> <out.h> [--preview out.png]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "lynx-client" / "tools"))

import import_lynx_art as lynx  # noqa: E402  (after sys.path setup)

# Palm greys, written as characters: "." white, "+" light grey, "x" dark
# grey, "#" black, and " " transparent (sprites only).
GREY = {".": 0, "+": 1, "x": 2, "#": 3}

# Every tile and sprite gets its own pen -> grey map, chosen by eye from the
# Lynx art: one global map cannot work, because the Lynx tells things apart
# by hue (a green slime on green grass, a white hat on white stone) and four
# greys have no hue. The house rules:
#   * ground is light: grass white with light flecks, road and cave floor
#     light grey, so anything dark standing on it reads;
#   * walls and water are dark;
#   * figures are black and dark grey, with white only where dark pixels
#     enclose it (eyes, a face, the bullet's core), so they read on every
#     ground.
# A map must name every pen its art uses; build() fails on one it misses.
# Pen numbers are lynx-client/tools/import_lynx_art.py's CLUT indices.
GRASS = {2: ".", 3: "+"}
CAVE_FLOOR = {0: "+", 12: "x"}

TILE_MAPS = {
    0: GRASS,                                       # grass
    2: {**GRASS, 1: "x", 5: "#"},                   # tree: dark crown, black trunk
    3: {**GRASS, 13: "#"},                          # herb (pixels below)
    4: {**GRASS, 1: "x", 5: "#"},                   # damaged tree
    5: {**GRASS, 5: "#", 15: "+"},                  # stump: black bark, pale cut
    6: {0: "+", 12: "#", 15: "."},                  # bullet (legacy terrain id)
    7: {1: "x", 12: "#"},                           # border hedge
    8: {0: ".", 5: "#", 15: "."},                   # beaver (legacy terrain id)
    9: {**GRASS, 3: "#", 14: "x"},                  # snake (legacy terrain id)
    10: {5: "+", 7: "x"},                           # road: light, dark pebbles
    11: {8: "x", 10: "x"},                          # water (pixels below)
    12: {2: "x", 11: "+", 12: "x"},                 # stone (pixels below)
    13: {7: "+", 12: "#"},                          # cave entrance
    14: {**GRASS, 11: ".", 12: "x"},                # grave: dark stone, white cross
    15: CAVE_FLOOR,                                 # cave floor
    16: {6: "#", 7: "x", 12: "#", 15: "+"},         # cave wall: dark rock
    17: {7: "+", 12: "#"},                          # cave exit
    34: {**GRASS, 6: "#", 14: "+"},                 # gold
    35: {**GRASS, 5: "#"},                          # sticks
    36: {**GRASS, 12: "#", 15: "."},                # goblin: black, white eyes
    37: {**GRASS, 5: "#", 7: "x", 14: "+"},         # townsfolk
    38: {**GRASS, 1: "#"},                          # Grix (eyes below)
    39: {**GRASS, 15: "#"},                         # Warden Key: black on grass
    40: {**GRASS, 5: "#", 7: "x", 14: "+"},         # Daniel
    41: {**GRASS, 5: "#", 12: "x", 14: "+"},        # Wilhelm
    42: {**GRASS, 8: "#", 12: "x", 15: "+"},        # Lucian: pale head, dark robe
    43: {**GRASS, 5: "#", 8: "x", 13: "#", 15: "."},  # Nerissa: face in black hair
    44: {**GRASS, 3: "x"},                          # slime, eyes are grass
    45: {**GRASS, 3: "x"},
    46: {**GRASS, 5: "#"},                          # bat
    47: {**GRASS, 5: "#"},
    48: {**GRASS, 8: "#", 14: "."},                 # Gorvak: white eyes
    49: {0: "+", 5: "#", 9: "x", 10: "."},          # Deep Pump, on cave floor
    50: {0: "+", 9: "x", 12: "#", 13: "#", 14: "."},  # Pump Controls
    51: {**GRASS, 5: "#", 12: "x", 14: "+"},        # Wilhelm working
}
# Legacy ids the terrain stream never sends (1, 18-33): drawn as plain grass.
UNUSED_TILES = {1} | set(range(18, 34))

# Whole-tile pixels where remapping alone cannot carry the shape. Each must
# still be the same object as the Lynx tile, just drawn for four greys.
TILE_PIXELS = {
    3: [  # herb: a ring flower on a dark-leaved stalk
        "........",
        ".+..+...",
        "...##...",
        "..#..#..",
        "...##...",
        ".x.xx.x.",
        "..xxxx..",
        "...xx...",
    ],
    11: [  # water: dark, with light ripples that tile edge to edge
        "xxxxxxxx",
        "xx++xxxx",
        "x+xx+xxx",
        "xxxxxxxx",
        "xxxxxx++",
        "+xxxx+xx",
        "xxxxxxxx",
        "xxxxxxxx",
    ],
    12: [  # stone (walls and rock massifs): big light blocks, dark joints,
           # mostly light so it never reads as water
        "++++x+++",
        "++++x+++",
        "++++x+++",
        "xxxxxxxx",
        "x+++++++",
        "x+++++++",
        "x+++++++",
        "xxxxxxxx",
    ],
    38: [  # Grix: the Lynx silhouette, with eyes so he reads as a face
        "..####..",
        ".#.##.#.",
        ".######.",
        "..####..",
        ".######.",
        ".######.",
        "..####..",
        ".##..##.",
    ],
}

SPRITE_MAPS = {
    "beaver": {0: " ", 5: "#", 15: "."},
    "snake": {0: " ", 3: "#", 13: "x"},
    "goblin": {0: " ", 12: "#", 15: "."},
    "slime0": {0: " ", 3: "x"},
    "slime1": {0: " ", 3: "x"},
    "bat0": {0: " ", 11: "#"},
    "bat1": {0: " ", 11: "#"},
    "gorvak": {0: " ", 8: "#", 13: "."},
    "wilhelm": {0: " ", 5: "#", 9: "+", 14: "x"},
    "wilhelm_working": {0: " ", 5: "#", 9: "+", 14: "x"},
    "bullet": {0: " ", 12: "#", 15: "."},
    "item_gold": {0: " ", 6: "#", 14: "+"},
    "item_sticks": {0: " ", 5: "#"},
    "item_herb": {0: " ", 3: "x", 13: "#"},
    "item_potion": {0: " ", 12: "#", 13: "+"},
    "item_key": {0: " ", 14: "#"},
}
# The player, drawn by hand rather than remapped: the Lynx hero is a white
# hat over a navy shirt, which in greys is a dark blob. Here a black outline
# carries the shape and the face is white, so the hero reads on any ground.
# The local player's shirt is light grey, everyone else's black. Frames are
# the Lynx order: 0-1 front, 2-3 facing right, 4-5 facing left (mirrored
# here; the Lynx reuses the right-facing art), then 6-11 the same for remote
# players.
PLAYER_FRONT = (
    [
        "  ####  ",
        " #....# ",
        " #....# ",
        "  ####  ",
        "#++++++#",
        "  ####  ",
        "  #  #  ",
        " ##  ## ",
    ],
    [
        "  ####  ",
        " #....# ",
        " #....# ",
        "  ####  ",
        "#++++++#",
        "  ####  ",
        " #    # ",
        "##    ##",
    ],
)
PLAYER_SIDE = (  # facing right
    [
        "  ####  ",
        " #....# ",
        " #.....#",
        "  ####  ",
        "  #++#  ",
        "  ####  ",
        "  #  #  ",
        "  #  ## ",
    ],
    [
        "  ####  ",
        " #....# ",
        " #.....#",
        "  ####  ",
        "  #++## ",
        "  ####  ",
        " #   #  ",
        "##   ## ",
    ],
)


def player_frames():
    def figure(rows, remote):
        return [row.replace("+", "#") if remote else row for row in rows]

    def mirror(rows):
        return [row[::-1] for row in rows]

    frames = []
    for remote in (False, True):
        frames += [figure(PLAYER_FRONT[0], remote), figure(PLAYER_FRONT[1], remote),
                   figure(PLAYER_SIDE[0], remote), figure(PLAYER_SIDE[1], remote),
                   figure(mirror(PLAYER_SIDE[0]), remote),
                   figure(mirror(PLAYER_SIDE[1]), remote)]
    return frames


# Sprite pixels that need more than a remap.
SPRITE_PIXELS = {
    "item_herb": [  # the same ring flower as the herb tile
        "        ",
        "        ",
        "   ##   ",
        "  #..#  ",
        "   ##   ",
        " x xx x ",
        "  xxxx  ",
        "   xx   ",
    ],
    "slime0": [  # outlined, so it reads on light grey ground too
        "        ",
        "        ",
        "  ####  ",
        " #x##x# ",
        "#xxxxxx#",
        "#xxxxxx#",
        " #x##x# ",
        "  ####  ",
    ],
    "slime1": [
        "  ####  ",
        " #x##x# ",
        " #x##x# ",
        "#xxxxxx#",
        "#xxxxxx#",
        "#xx##xx#",
        " #xxxx# ",
        "  ####  ",
    ],
}


# ---- 1-bit art ---------------------------------------------------------
# The Palm draws in black and white (see gfx.h). Each tile's grey art drops
# to 1 bit by MONO_DEFAULT -- light grey to white, dark grey to black --
# unless MONO_MAPS gives that tile or sprite its own rule, or MONO_PIXELS
# redraws it outright. Dithering the greys was tried first and is unreadable
# at 8x8: every road and floor turns into a grid of dots.
MONO_DEFAULT = {".": ".", "+": ".", "x": "#", "#": "#", " ": " "}

MONO_MAPS = {
    7: {"x": "."},          # border hedge: a checkerboard, not a black wall
    13: {},                 # cave entrance: white face, black openings
    17: {},
    "slime0": {"x": "."},   # white body inside the black outline
    "slime1": {"x": "."},
}

MONO_PIXELS = {
    0: [  # grass: almost bare, two flecks so it is not mistaken for floor
        "........",
        "........",
        "...#....",
        "........",
        "........",
        "......#.",
        "........",
        "........",
    ],
    10: [  # road: gravel, much denser than grass
        "........",
        ".#....#.",
        "....#...",
        "#.......",
        "......#.",
        "..#.....",
        ".....#..",
        "........",
    ],
    15: [  # cave floor: bare, one pebble
        "........",
        "........",
        "..#.....",
        "........",
        "........",
        "........",
        "......#.",
        "........",
    ],
    2: [  # tree: black crown with a highlight, trunk
        "........",
        "..####..",
        ".#.#####",
        ".##.####",
        "..####..",
        "...##...",
        "...##...",
        "..####..",
    ],
    4: [  # damaged tree: a ragged crown
        "........",
        "..##.#..",
        ".#.####.",
        ".#.####.",
        "..###...",
        "...##...",
        "....#...",
        "..###...",
    ],
    37: [  # townsfolk: hat, face, coat, legs
        ".####...",
        "######..",
        ".#..#...",
        ".####...",
        "#.##.#..",
        ".####...",
        ".#..#...",
        "##..##..",
    ],
    40: [  # Daniel: as the townsfolk, with his staff
        ".####.#.",
        "######.#",
        ".#..#..#",
        ".####..#",
        "#.##.###",
        ".####..#",
        ".#..#..#",
        "##..##.#",
    ],
    42: [  # Lucian: white hair over a black robe, staff on the left
        "#..##...",
        "#.#..#..",
        "#.#..#..",
        "#..##...",
        "#######.",
        "#.####..",
        "#.####..",
        "#.#..#..",
    ],
}


def mono(pixels, key):
    if key in MONO_PIXELS:
        rows = MONO_PIXELS[key]
        if len(rows) != 8 or any(len(r) != 8 or set(r) - set(".# ") for r in rows):
            sys.exit(f"palm_art: bad 1-bit art for {key}")
        return rows
    rule = {**MONO_DEFAULT, **MONO_MAPS.get(key, {})}
    return ["".join(rule[ch] for ch in row) for row in pixels]


def build_mono():
    tiles, sprites, names, player_count = build()
    keys = [f"player {i}" for i in range(player_count)] + names
    return ([mono(t, i) for i, t in enumerate(tiles)],
            [mono(sp, k) for sp, k in zip(sprites, keys)], names, player_count)


# ---- Colour art ----------------------------------------------------------
# Colour Palms (OS 3.5 and later) draw the Lynx art itself: its 16 pens,
# object tiles composited over their ground as on the Lynx, and its per-map
# palette tints. The client turns pens into the screen's palette indices at
# run time (WinRGBToIndex). Player frames 4-5 (facing left) are mirrored from
# 2-3; the Lynx flips them in hardware.


def build_colour():
    tile_rows, player_rows, names, entity_rows = load()
    tiles = composite(tile_rows)
    players = [rows for rows in player_rows]
    for base in (0, 6):
        players[base + 4] = [row[::-1] for row in player_rows[base + 2]]
        players[base + 5] = [row[::-1] for row in player_rows[base + 3]]
    palettes = [lynx.tint(list(lynx.CLUT), *t) for t in lynx.PALETTE_TINTS]
    return tiles, players + entity_rows, palettes


def pack1(pixels):
    return [sum(0x80 >> x for x, ch in enumerate(row) if ch == "#") for row in pixels]


def pack1_mask(pixels):
    return [sum(0x80 >> x for x, ch in enumerate(row) if ch != " ") for row in pixels]


def apply_map(rows, pen_map, label):
    out = []
    for row in rows:
        line = ""
        for pen in row:
            if pen not in pen_map:
                sys.exit(f"palm_art: {label} uses pen {pen}, which its map lacks")
            line += pen_map[pen]
        out.append(line)
    return out


def check_pixels(pixels, label, sprite):
    allowed = set(GREY) | ({" "} if sprite else set())
    if len(pixels) != 8 or any(len(r) != 8 or set(r) - allowed for r in pixels):
        sys.exit(f"palm_art: bad pixel art for {label}")
    return pixels


def load():
    data = json.loads(lynx.TILESET.read_text(encoding="utf-8"))
    tiles = sorted(data["tiles"], key=lambda t: t["index"])
    tile_rows = [lynx.rows_from_hex(t["rows"], f"tile {t['index']}") for t in tiles]
    players = sorted(data["players"], key=lambda p: p["index"])
    player_rows = [lynx.rows_from_hex(p["rows"], f"player {p['index']}")
                   for p in players]
    by_name = {e["name"]: e for e in data["entities"]}
    names = [name for name, _, _ in lynx.ENTITY_SPRITES]
    entity_rows = [lynx.rows_from_hex(by_name[n]["rows"], f"entity {n}") for n in names]
    return tile_rows, player_rows, names, entity_rows


def composite(tile_rows):
    """Object tiles drawn over the ground they stand on (pen 0 -> ground)."""
    out = []
    for index, rows in enumerate(tile_rows):
        base = lynx.OBJECT_TILE_BASE.get(index)
        if base is not None:
            ground = tile_rows[base]
            rows = [[ground[y][x] if rows[y][x] == 0 else rows[y][x]
                     for x in range(8)] for y in range(8)]
        out.append(rows)
    return out


def pack(pixels):
    """8 grey characters per row -> one UInt16 per row, leftmost pixel in
    the top two bits; transparent pixels are white."""
    words = []
    for row in pixels:
        value = 0
        for ch in row:
            value = (value << 2) | GREY.get(ch, 0)
        words.append(value)
    return words


def pack_mask(pixels):
    words = []
    for row in pixels:
        value = 0
        for ch in row:
            value = (value << 2) | (0 if ch == " " else 3)
        words.append(value)
    return words


def build():
    """-> (tiles, sprites, sprite names, player count), all as pixel rows."""
    tile_rows, player_rows, names, entity_rows = load()
    tiles = []
    for index, rows in enumerate(composite(tile_rows)):
        label = f"tile {index}"
        if index in TILE_PIXELS:
            tiles.append(check_pixels(TILE_PIXELS[index], label, False))
        elif index in UNUSED_TILES:
            tiles.append(["." * 8] * 8)
        else:
            tiles.append(check_pixels(apply_map(rows, TILE_MAPS[index], label),
                                      label, False))
    sprites = [check_pixels(f, f"player {i}", True)
               for i, f in enumerate(player_frames())]
    if len(sprites) != len(player_rows):
        sys.exit("palm_art: player frame count differs from the Lynx tileset")
    for name, rows in zip(names, entity_rows):
        if name in SPRITE_PIXELS:
            sprites.append(check_pixels(SPRITE_PIXELS[name], name, True))
        else:
            sprites.append(check_pixels(apply_map(rows, SPRITE_MAPS[name], name),
                                        name, True))
    return tiles, sprites, names, len(player_rows)


def c_words(words):
    return ", ".join(f"0x{w:04X}" for w in words)


def preview(path, tiles, sprites):
    """Every tile, then every sprite over grass, at 4x."""
    from PIL import Image

    shade = {".": 255, "+": 170, "x": 85, "#": 0}
    scale, cols = 4, 16
    grass = tiles[0]
    items = tiles + sprites
    img = Image.new("RGB", (cols * 9 * scale, ((len(items) + cols - 1) // cols) * 9 * scale),
                    (255, 0, 255))
    for n, art in enumerate(items):
        ox, oy = (n % cols) * 9, (n // cols) * 9
        for y in range(8):
            for x in range(8):
                ch = art[y][x] if art[y][x] != " " else grass[y][x]
                v = shade[ch]
                img.paste((v, v, v), ((ox + x) * scale, (oy + y) * scale,
                                      (ox + x + 1) * scale, (oy + y + 1) * scale))
    img.save(path)


def main():
    args = sys.argv[1:]
    preview_path = None
    if "--preview" in args:
        i = args.index("--preview")
        preview_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    out_c, out_h = Path(args[0]), Path(args[1])
    tiles, sprites, names, player_count = build()
    mono_tiles, mono_sprites, _, _ = build_mono()
    if preview_path:
        preview(preview_path, mono_tiles, mono_sprites)

    h = ["/* Generated by tools/palm_art.py from lynx-client/art/lynx_tileset.json."
         " Do not edit. */",
         "#ifndef FUJIREALM_PALM_ART_H", "#define FUJIREALM_PALM_ART_H", "",
         f"#define ART_TILE_COUNT {len(tiles)}",
         f"#define ART_PLAYER_COUNT {player_count}",
         f"#define ART_SPRITE_COUNT {len(sprites)}"]
    for i, name in enumerate(names):
        h.append(f"#define ART_SPRITE_{name.upper()} {player_count + i}")
    h += ["",
          "/* The arrays themselves are static in palm_art.c, which gfx.c includes:",
          " * m68k-palmos-gcc puts const data in the code section, where only code",
          " * in the same file can reach it (PC-relative). Another file would look",
          " * for it A5-relative in the data segment and read unrelated memory. */",
          "", "#endif", ""]

    c = ["/* Generated by tools/palm_art.py from lynx-client/art/lynx_tileset.json."
         " Do not edit. */", f'#include "{out_h.name}"', "",
         "#ifdef ART_GREY", "static const unsigned short art_tiles[ART_TILE_COUNT][8] = {"]
    for index, tile in enumerate(tiles):
        c.append(f"    {{ {c_words(pack(tile))} }}, /* {index} */")
    labels = [f"player {i}" for i in range(player_count)] + names
    c += ["};", "", "static const unsigned short art_sprites[ART_SPRITE_COUNT][8] = {"]
    for label, s in zip(labels, sprites):
        c.append(f"    {{ {c_words(pack(s))} }}, /* {label} */")
    c += ["};", "", "static const unsigned short art_masks[ART_SPRITE_COUNT][8] = {"]
    for label, m in zip(labels, sprites):
        c.append(f"    {{ {c_words(pack_mask(m))} }}, /* {label} */")
    c += ["};", "#endif /* ART_GREY */", ""]

    def bytes_(values):
        return ", ".join(f"0x{v:02X}" for v in values)

    c += ["#ifdef ART_MONO"]
    c.append("static const unsigned char art_tiles1[ART_TILE_COUNT][8] = {")
    for index, tile in enumerate(mono_tiles):
        c.append(f"    {{ {bytes_(pack1(tile))} }}, /* {index} */")
    c += ["};", "", "static const unsigned char art_sprites1[ART_SPRITE_COUNT][8] = {"]
    for label, sp in zip(labels, mono_sprites):
        c.append(f"    {{ {bytes_(pack1(sp))} }}, /* {label} */")
    c += ["};", "", "static const unsigned char art_masks1[ART_SPRITE_COUNT][8] = {"]
    for label, sp in zip(labels, mono_sprites):
        c.append(f"    {{ {bytes_(pack1_mask(sp))} }}, /* {label} */")
    c += ["};", "#endif /* ART_MONO */", ""]

    colour_tiles, colour_sprites, palettes = build_colour()

    def pens(rows):
        # Two pens per byte, left pixel in the high nibble: the colour build
        # is the largest, and the app is one 32 KB code segment.
        flat = [p for row in rows for p in row]
        return ", ".join(f"0x{(flat[i] << 4) | flat[i + 1]:02X}" for i in range(0, 64, 2))

    c += ["#ifdef ART_COLOUR",
          "/* Lynx pens 0-15, two pixels per byte (left in the high nibble), row by",
          " * row; pen 0 is transparent in sprites. */",
          "static const unsigned char art_tiles8[ART_TILE_COUNT][32] = {"]
    for index, rows in enumerate(colour_tiles):
        c.append(f"    {{ {pens(rows)} }}, /* {index} */")
    c += ["};", "", "static const unsigned char art_sprites8[ART_SPRITE_COUNT][32] = {"]
    for label, rows in zip(labels, colour_sprites):
        c.append(f"    {{ {pens(rows)} }}, /* {label} */")
    c += ["};", "",
          "/* The Lynx CLUT under each map's tint (MAP_CHANGE palette_id), as RGB. */",
          f"#define ART_PALETTE_COUNT {len(palettes)}",
          "static const unsigned char art_palettes[ART_PALETTE_COUNT][16][3] = {"]
    for pal in palettes:
        c.append("    { " + ", ".join(f"{{ {r}, {g}, {b} }}" for r, g, b in pal) + " },")
    c += ["};", "#endif /* ART_COLOUR */", ""]

    out_c.parent.mkdir(parents=True, exist_ok=True)
    out_c.write_text("\n".join(c), encoding="utf-8")
    out_h.write_text("\n".join(h), encoding="utf-8")


if __name__ == "__main__":
    main()
