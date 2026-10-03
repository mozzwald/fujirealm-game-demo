#!/usr/bin/env python3
"""Write FujiRealm.info, the Workbench tool icon, from the game's own art.

The player faces a goblin across a strip of grass, drawn from the Lynx
tileset (lynx-client/art/lynx_tileset.json) and mapped to the four
Workbench 1.3 colours: blue (background), white, black, orange. Hires
Workbench pixels are twice as tall as wide, so 8x8 art is scaled 3x
horizontally and 2x vertically to look square.

Format: the classic DiskObject (magic, Gadget with one Image, planar image
data, Tool Types), big-endian, as in fujinet-weather's amiga/support/mkicon.py. No Tool Types.

Usage: mkicon.py <out.info>
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import amiga_art  # noqa: E402

SX, SY = 3, 2
STACK = 16384
WB = [(0x00, 0x55, 0xAA), (0xFF, 0xFF, 0xFF), (0x00, 0x00, 0x22), (0xFF, 0x88, 0x00)]


def nearest_wb(rgb):
    """Nearest of white/black/orange: an opaque pixel must never turn into
    the background blue, or the figures dissolve into it."""
    return min((1, 2, 3), key=lambda i: sum((a - b) ** 2 for a, b in zip(rgb, WB[i])))


def scaled(rows, clut):
    """8x8 pens -> SX*8 x SY*8 WB pens; pen 0 stays background blue."""
    out = []
    for row in rows:
        line = []
        for pen in row:
            line += [0 if pen == 0 else nearest_wb(clut[pen])] * SX
        out += [list(line) for _ in range(SY)]
    return out


def draw():
    clut, _tiles, players, names, entities = amiga_art.load()
    hero = scaled(players[2], clut)                      # facing right
    goblin = scaled(entities[names.index("goblin")], clut)
    gap = 8
    width = len(hero[0]) + gap + len(goblin[0])
    img = [row_h + [0] * gap + row_g for row_h, row_g in zip(hero, goblin)]
    img.append([0] * width)
    img.append([3 if x % 3 else 0 for x in range(width)])  # a strip of ground
    return img


def planes(img):
    w, words = len(img[0]), (len(img[0]) + 15) // 16
    out = bytearray()
    for plane in range(2):
        for row in img:
            bits = [(p >> plane) & 1 for p in row] + [0] * (words * 16 - w)
            for i in range(words):
                v = 0
                for b in bits[i * 16:(i + 1) * 16]:
                    v = (v << 1) | b
                out += struct.pack(">H", v)
    return bytes(out)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    img = draw()
    w, h = len(img[0]), len(img)
    gadget = struct.pack(">IhhhhHHHIIIiIHI", 0, 0, 0, w, h, 0x0004, 0x0003, 0x0001,
                         1, 0, 0, 0, 0, 0, 0)
    header = struct.pack(">HH", 0xE310, 1) + gadget + struct.pack(
        ">BBIIiiIIi", 3, 0, 0, 0, -0x80000000, -0x80000000, 0, 0, STACK)
    image = struct.pack(">hhhhhIBBI", 0, 0, w, h, 2, 1, 3, 0, 0) + planes(img)
    Path(sys.argv[1]).write_bytes(header + image)
    for row in img:
        print("".join(" #@o"[p] for p in row).rstrip())


if __name__ == "__main__":
    main()
