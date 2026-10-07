#!/usr/bin/env python3
"""Draw the FN Realm launcher icons from the game's own sprites, as 1-bit
BMPs for PilRC: the hero facing a goblin, pixel-doubled for the 32x22 icon
and at native size for the 15x9 list-view icon.

Usage: mkicon.py <icon.bmp> <icon-small.bmp>
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import palm_art  # noqa: E402


def sprite_bits(pixels):
    """8x8 grey characters -> 8x8 of 0/1, dark greys black."""
    return [[1 if ch in "x#" else 0 for ch in row] for row in pixels]


def doubled(bits):
    out = []
    for row in bits:
        wide = [b for b in row for _ in (0, 1)]
        out += [wide, list(wide)]
    return out


def place(canvas, bits, x0, y0):
    for y, row in enumerate(bits):
        for x, b in enumerate(row):
            if b and 0 <= y0 + y < len(canvas) and 0 <= x0 + x < len(canvas[0]):
                canvas[y0 + y][x0 + x] = 1


def write_bmp(path, canvas):
    height, width = len(canvas), len(canvas[0])
    stride = ((width + 31) // 32) * 4
    pixels = b""
    for row in reversed(canvas):  # BMP rows run bottom-up
        data = bytearray(stride)
        for x, b in enumerate(row):
            if not b:             # palette entry 1 is white
                data[x >> 3] |= 0x80 >> (x & 7)
        pixels += bytes(data)
    palette = struct.pack("<II", 0x000000, 0xFFFFFF)
    header = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 1, 0, len(pixels),
                         2835, 2835, 2, 2)
    offset = 14 + len(header) + len(palette)
    Path(path).write_bytes(b"BM" + struct.pack("<IHHI", offset + len(pixels), 0, 0, offset)
                           + header + palette + pixels)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    _, sprites, names, player_count = palm_art.build()
    hero = sprite_bits(sprites[2])            # facing right
    goblin = sprite_bits(sprites[player_count + names.index("goblin")])

    big = [[0] * 32 for _ in range(22)]
    place(big, doubled(hero), 0, 4)
    place(big, doubled(goblin), 16, 4)
    write_bmp(sys.argv[1], big)

    small = [[0] * 15 for _ in range(9)]
    place(small, hero, 0, 1)
    place(small, goblin, 7, 1)
    write_bmp(sys.argv[2], small)


if __name__ == "__main__":
    main()
