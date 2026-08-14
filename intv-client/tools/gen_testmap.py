#!/usr/bin/env python3
"""Generate testmap.bas: a real 32x24 slice of the overworld for offline mode.

The offline demo (no FujiNet mailbox present) loads this slice into the
terrain window so rendering, camera, and prediction can be exercised without
a server. The slice is the window the server would send for a player at
OVERWORLD_RESPAWN (14,70): origin = clamp(player - (16,12)) = (0,58).

Reads server/world_layout_data.py (generated from maps/overworld.csv) so the
offline terrain is byte-identical to what the live server streams.

Usage (from intv-client/): python3 tools/gen_testmap.py > testmap.bas
"""

import ast
from pathlib import Path

LAYOUT = Path(__file__).resolve().parents[2] / "server/world_layout_data.py"
WORLD_W, WORLD_H = 128, 96
WIN_W, WIN_H = 32, 24
ORIGIN_X, ORIGIN_Y = 0, 58   # clamp((14,70) - (16,12))
SPAWN_X, SPAWN_Y = 14, 70


def main():
    tree = ast.parse(LAYOUT.read_text())
    tiles = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "OVERWORLD_TILES" for t in node.targets):
            tiles = ast.literal_eval(node.value)
    assert tiles is not None and len(tiles) == WORLD_W * WORLD_H, "layout parse failed"

    print("' testmap.bas -- offline-mode terrain window (GENERATED FILE)")
    print("' A real %dx%d overworld slice at origin (%d,%d), player spawn (%d,%d)." %
          (WIN_W, WIN_H, ORIGIN_X, ORIGIN_Y, SPAWN_X, SPAWN_Y))
    print("' Regenerate with: python3 tools/gen_testmap.py > testmap.bas")
    print("' meta: origin_x, origin_y, spawn_x, spawn_y (DATA, not CONST, so the")
    print("' main file compiled before this include can reference it)")
    print("testmap_meta:")
    print("    DATA %d,%d,%d,%d" % (ORIGIN_X, ORIGIN_Y, SPAWN_X, SPAWN_Y))
    print("testmap:")
    for row in range(WIN_H):
        base = (ORIGIN_Y + row) * WORLD_W + ORIGIN_X
        vals = tiles[base:base + WIN_W]
        print("    DATA %s" % ",".join(str(v) for v in vals))


if __name__ == "__main__":
    main()
