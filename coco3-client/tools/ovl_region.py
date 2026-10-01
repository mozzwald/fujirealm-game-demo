#!/usr/bin/env python3
"""Print the overlay region's start or end address (hex, for cmoc --org and
ovl_pack.py), read from the game's linker map; or, with check128k, fail if
the region's code before hwscroll.c outgrows what play.c saves on 128K."""

from __future__ import annotations

import re
import sys

SYMBOLS = {"start": "_ovl_region_start", "end": "_ovl_region_end"}
# play.c SAVE_OFS_128K (the HUD image's end, $14A0) up to terrain.h
# TERRAIN_FILL_OFS ($1D00).
SAVE_128K = 0x1D00 - 0x14A0


def check_128k(map_path: str) -> int:
    with open(map_path, encoding="ascii") as f:
        text = f.read()
    start = re.search(r"Symbol: _ovl_region_start \(\S+\) = ([0-9A-F]+)", text)
    hw = re.search(r"Section: code \(hwscroll\.o\) load at ([0-9A-F]+)", text)
    if not start or not hw:
        print(f"region start or hwscroll.o not in {map_path}", file=sys.stderr)
        return 1
    size = int(hw.group(1), 16) - int(start.group(1), 16)
    if size > SAVE_128K:
        print(f"128K renderer code is {size} bytes; 128K saves only {SAVE_128K}",
              file=sys.stderr)
        return 1
    return 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "check128k":
        return check_128k(sys.argv[2])
    if len(sys.argv) != 3 or sys.argv[1] not in SYMBOLS:
        print("usage: ovl_region.py start|end|check128k GAME.map", file=sys.stderr)
        return 2
    pattern = re.compile(rf"Symbol: {SYMBOLS[sys.argv[1]]} \(\S+\) = ([0-9A-F]+)")
    with open(sys.argv[2], encoding="ascii") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                print(match.group(1))
                return 0
    print(f"{SYMBOLS[sys.argv[1]]} not in {sys.argv[2]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
