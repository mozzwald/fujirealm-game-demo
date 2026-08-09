#!/usr/bin/env python3
"""Add item-drop sprites to an existing lynx_tileset.json in place.

Item drops (gold, sticks, herb, potion, the lost charm) render as sprites
over the terrain, so they need transparent backgrounds -- unlike the terrain
tiles, whose pen 0 is an ordinary colour. This seeds each item sprite from
the matching terrain tile already in the tileset, replacing that tile's
background (its most common pen) with the transparent pen 0, and appends it
to the tileset's entities[] for hand-tuning in the editor.

It preserves everything already in the file and is idempotent: an item
sprite that already exists is left untouched, so re-running never clobbers
hand-drawn work.

    python3 tools/add_item_sprites.py
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import import_lynx_art as conv

TRANSPARENT = 0

# item sprite name -> terrain tile index it is seeded from. Potion has no
# terrain tile, so it starts as a copy of the herb and is redrawn later.
SEED_FROM_TILE = {
    "item_gold": 34,
    "item_sticks": 35,
    "item_herb": 3,
    "item_potion": 3,
    "item_charm": 39,
}


def background_pen(rows):
    counts = collections.Counter(ch for row in rows for ch in row)
    return counts.most_common(1)[0][0]


def to_transparent(rows):
    bg = background_pen(rows)
    hidden = "0" if bg != "0" else None
    # If the background already is pen 0 there is nothing to hide; otherwise
    # every background pixel becomes transparent.
    if hidden is None:
        return [row for row in rows]
    return ["".join("0" if ch == bg else ch for ch in row) for row in rows]


def main():
    path = conv.TILESET
    if not path.exists():
        print(f"{path} does not exist; seed it with export_lynx_tileset.py first",
              file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))

    tiles = {t["index"]: t for t in data.get("tiles", [])}
    entities = data.setdefault("entities", [])
    existing = {e["name"] for e in entities}

    added = []
    for name, tile_index in SEED_FROM_TILE.items():
        if name in existing:
            continue
        source = tiles.get(tile_index)
        if source is None:
            print(f"tile {tile_index} missing; cannot seed {name}", file=sys.stderr)
            return 1
        entities.append({"name": name, "rows": to_transparent(source["rows"])})
        added.append(name)

    if not added:
        print("all item sprites already present; nothing to do")
        return 0

    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"added {len(added)} item sprites: {', '.join(added)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
