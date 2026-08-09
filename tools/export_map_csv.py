#!/usr/bin/env python3
"""Export the overworld, starter-cave, and PvP-realm maps to editable CSV grids.

Run from the repo root:
    python3 tools/export_map_csv.py

Writes maps/overworld.csv, maps/cave.csv, and maps/pvp_realm.csv.
Edit those with any spreadsheet program, then run tools/import_map_csv.py to write the edits
back into the server source. See maps/README.md for the full legend.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from server.entities import (
    ENEMY_BAT,
    ENEMY_BEAVER,
    ENEMY_GOBLIN,
    ENEMY_SLIME,
    ENEMY_SNAKE,
)
from server.game import (
    STATIC_ENEMY_SPAWNS,
)
from server.world_layout_data import (
    DANIEL_X,
    DANIEL_Y,
    DEEP_PUMP_CONTROLS_MARKER,
    GORVAK_MARKER,
    GRIX_X,
    GRIX_Y,
    LUCIAN_POS,
    NERISSA_POS,
    OVERWORLD_BRIDGE_TILES,
    WARDEN_KEY_MARKER,
    WILHELM_BRIDGE_DESTINATION,
    WILHELM_POS,
)

# Enemy species id -> CSV marker (inverse of the importer's ENEMY_MARKER_CODES).
ENEMY_SPAWN_CODES = {
    ENEMY_BEAVER: "V",
    ENEMY_GOBLIN: "G",
    ENEMY_SNAKE: "S",
    ENEMY_SLIME: "M",
    ENEMY_BAT: "B",
}
from server.world import (
    BORDER,
    BUILDING,
    CAVE_ENTRANCE,
    CAVE_EXIT,
    CAVE_FLOOR,
    CAVE_WALL,
    GRAVE,
    HERB,
    MAP_OVERWORLD,
    MAP_PVP_REALM,
    MAP_STARTER_CAVE,
    OVERWORLD_CAVE_ENTRANCE,
    OVERWORLD_PVP_REALM_ENTRANCE,
    OVERWORLD_RESPAWN,
    OVERWORLD_START,
    PVP_REALM_ENTRY,
    PVP_REALM_EXIT,
    ROAD,
    STARTER_CAVE_EXIT,
    TREE_DAMAGED,
    TREE_FULL,
    TREE_STUMP,
    WATER,
    World,
    build_overworld,
    build_pvp_realm,
    build_starter_cave,
)

SEED = 1  # matches the fixed seed hybrid_server.py always uses

MAPS_DIR = REPO_ROOT / "maps"

# Terrain tile value -> single-character CSV code. GRASS (overworld) and
# CAVE_WALL (cave) are each that grid's "background" and map to "" (blank
# cell) rather than an explicit code, since they're the overwhelming
# majority of cells. BORDER is always the outer ring; it's shown for
# visual orientation only and is regenerated automatically on import
# regardless of what's in the cell, so it isn't part of the editable
# legend.
OVERWORLD_CODES = {
    TREE_FULL: "T",
    TREE_DAMAGED: "T",
    TREE_STUMP: "T",
    HERB: "H",
    ROAD: "R",
    BUILDING: "U",
    GRAVE: "X",
    CAVE_ENTRANCE: "C",
    WATER: "W",
}
CAVE_CODES = {
    CAVE_FLOOR: ".",
    CAVE_EXIT: "C",
    HERB: "H",
}
PVP_REALM_CODES = OVERWORLD_CODES
BORDER_CODE = "#"
CANONICAL_STORY_MARKERS = {
    "DAN": (MAP_OVERWORLD, DANIEL_X, DANIEL_Y),
    "GRX": (MAP_OVERWORLD, GRIX_X, GRIX_Y),
}
OPTIONAL_STORY_MARKERS = {
    "NER": None if NERISSA_POS is None else (MAP_OVERWORLD, NERISSA_POS[0], NERISSA_POS[1]),
    "WIL": None if WILHELM_POS is None else (MAP_OVERWORLD, WILHELM_POS[0], WILHELM_POS[1]),
    "LUC": None if LUCIAN_POS is None else (MAP_OVERWORLD, LUCIAN_POS[0], LUCIAN_POS[1]),
    "KEY": WARDEN_KEY_MARKER,
    "GOR": GORVAK_MARKER,
    "DPC": DEEP_PUMP_CONTROLS_MARKER,
    "WBD": WILHELM_BRIDGE_DESTINATION,
}


def entity_overlay(map_id: int) -> dict[tuple[int, int], str]:
    overlay: dict[tuple[int, int], str] = {}
    for x, y, kind in STATIC_ENEMY_SPAWNS.get(map_id, ()):
        overlay[(x, y)] = ENEMY_SPAWN_CODES.get(kind, "V")
    if map_id == MAP_OVERWORLD:
        # Bridge deck cells are ROAD terrain; re-mark them "=" so the marker
        # survives the CSV round trip (enemy/NPC overlays take precedence only
        # where they coincide, which the map author must avoid).
        for coord in OVERWORLD_BRIDGE_TILES:
            overlay[coord] = "="
        for marker, record in CANONICAL_STORY_MARKERS.items():
            _, x, y = record
            overlay[(x, y)] = marker
        for marker, record in OPTIONAL_STORY_MARKERS.items():
            if record is None or record[0] != MAP_OVERWORLD:
                continue
            overlay[(record[1], record[2])] = marker
    else:
        for marker, record in OPTIONAL_STORY_MARKERS.items():
            if record is None or record[0] != map_id:
                continue
            overlay[(record[1], record[2])] = marker
    return overlay


def write_grid(path: Path, world: World, tile_codes: dict[int, str], border_value: int, overlay: dict[tuple[int, int], str]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        header = ["y\\x"] + [str(x) for x in range(world.width)]
        writer.writerow(header)
        for y in range(world.height):
            row = [str(y)]
            for x in range(world.width):
                code = overlay.get((x, y))
                if code is None:
                    tile = world.tile(x, y)
                    if tile == border_value:
                        code = BORDER_CODE
                    else:
                        code = tile_codes.get(tile, "")
                row.append(code)
            writer.writerow(row)


def main() -> int:
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    overworld = build_overworld(SEED)
    overworld_overlay = entity_overlay(MAP_OVERWORLD)
    overworld_overlay[OVERWORLD_START] = "O"
    overworld_overlay[OVERWORLD_RESPAWN] = "X"
    overworld_overlay[OVERWORLD_CAVE_ENTRANCE] = "C"
    overworld_overlay[OVERWORLD_PVP_REALM_ENTRANCE] = "P"
    write_grid(MAPS_DIR / "overworld.csv", overworld, OVERWORLD_CODES, BORDER, overworld_overlay)
    print(f"Wrote {MAPS_DIR / 'overworld.csv'} ({overworld.width}x{overworld.height})")
    print(
        f"  Start at {OVERWORLD_START}, grave/respawn at {OVERWORLD_RESPAWN}, "
        f"cave entrance at {OVERWORLD_CAVE_ENTRANCE}, "
        f"PvP realm entrance at {OVERWORLD_PVP_REALM_ENTRANCE}"
    )

    cave = build_starter_cave(SEED)
    cave_overlay = entity_overlay(MAP_STARTER_CAVE)
    cave_overlay[STARTER_CAVE_EXIT] = "C"
    write_grid(MAPS_DIR / "cave.csv", cave, CAVE_CODES, BORDER, cave_overlay)
    print(f"Wrote {MAPS_DIR / 'cave.csv'} ({cave.width}x{cave.height})")
    print(f"  Cave exit at {STARTER_CAVE_EXIT}")

    pvp_realm = build_pvp_realm(SEED)
    pvp_overlay = entity_overlay(MAP_PVP_REALM)
    pvp_overlay[PVP_REALM_ENTRY] = "E"
    pvp_overlay[PVP_REALM_EXIT] = "P"
    write_grid(MAPS_DIR / "pvp_realm.csv", pvp_realm, PVP_REALM_CODES, BORDER, pvp_overlay)
    print(f"Wrote {MAPS_DIR / 'pvp_realm.csv'} ({pvp_realm.width}x{pvp_realm.height})")
    print(f"  PvP realm entry at {PVP_REALM_ENTRY}, exit at {PVP_REALM_EXIT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
