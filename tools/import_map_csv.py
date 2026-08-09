#!/usr/bin/env python3
"""Import edited maps/{overworld,cave}.csv back into the server.

Run from the repo root:
    python3 tools/import_map_csv.py

Regenerates server/world_layout_data.py in full from the editable CSV
files. That module is the single source of truth for the map layout,
farmer position, static beaver/goblin spawns, and the transition points
-- world.py and game.py import from it. Re-run this script every time
you edit the CSVs; do not hand-edit
world_layout_data.py, it gets overwritten.

See maps/README.md for the full legend.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MAPS_DIR = REPO_ROOT / "maps"
OUTPUT = REPO_ROOT / "server" / "world_layout_data.py"
STORY_LAYOUT_PATH = MAPS_DIR / "story_layout.json"

# Deliberately NOT imported from server.world: that module itself
# imports from world_layout_data.py, the file this script generates, so
# importing it here would fail on a from-scratch run. These must stay in
# sync with the constants in server/world.py and server/entities.py.
WORLD_W = 128
WORLD_H = 96
GRASS = 0
TREE_FULL = 2
HERB = 3
BORDER = 7
ROAD = 10
WATER = 11
BUILDING = 12
CAVE_ENTRANCE = 13
GRAVE = 14
CAVE_FLOOR = 15
CAVE_WALL = 16
CAVE_EXIT = 17
MAP_OVERWORLD = 0
MAP_STARTER_CAVE = 1
MAP_PVP_REALM = 2
ENEMY_BEAVER = 1
ENEMY_SNAKE = 2
ENEMY_BAT = 3
ENEMY_SLIME = 4
ENEMY_GOBLIN = 5

# Reverse of export_map_csv.py's OVERWORLD_CODES/CAVE_CODES. "" is each
# grid's background tile (GRASS for overworld, CAVE_WALL for cave) and is
# not listed here since it's the fallback default.
OVERWORLD_TERRAIN_CODES = {
    "T": TREE_FULL,
    "H": HERB,
    "R": ROAD,
    "U": BUILDING,
    "W": WATER,
}
CAVE_TERRAIN_CODES = {
    ".": CAVE_FLOOR,
    "H": HERB,
}
# Enemy spawn markers -> species id. V/G are locked; S/M/B are provisional
# species codes wired up ahead of the Phase 62 map redraw (legend in
# maps/README.md). The cell's terrain defaults to the walkable entity tile.
ENEMY_MARKER_CODES = {
    "V": ENEMY_BEAVER,
    "G": ENEMY_GOBLIN,
    "S": ENEMY_SNAKE,
    "M": ENEMY_SLIME,
    "B": ENEMY_BAT,
}
# Canonical multi-character story anchors for the Phase 62 map pass. Legacy
# one-letter F/N markers are still accepted as aliases so the current overworld
# can import cleanly while the user migrates the CSV.
STORY_MARKER_CODES = {
    "NER": "NERISSA",
    "DAN": "DANIEL",
    "WIL": "WILHELM",
    "LUC": "LUCIAN",
    "GRX": "GRIX",
    "KEY": "WARDEN_KEY",
    "GOR": "GORVAK",
    "DPC": "DEEP_PUMP_CONTROLS",
    "WBD": "WILHELM_BRIDGE_DESTINATION",
}
LEGACY_MARKER_ALIASES = {
    "F": "DAN",
    "N": "GRX",
}
# Codes that mean "an entity/marker lives here", handled separately from
# plain terrain -- the cell's underlying terrain defaults to the grid's
# background tile.
ENTITY_CODES = (
    set(ENEMY_MARKER_CODES)
    | set(STORY_MARKER_CODES)
    | set(LEGACY_MARKER_ALIASES)
    | {"X", "O", "C", "P", "E"}
)
# The completed bridge is ordinary ROAD at runtime; the "=" marker only records
# which road cells the server masks as WATER until a player repairs the bridge.
BRIDGE_CODE = "="
PVP_REALM_TERRAIN_CODES = OVERWORLD_TERRAIN_CODES


class MapCsvError(ValueError):
    pass


MAP_NAME_TO_ID = {
    "overworld": MAP_OVERWORLD,
    "cave": MAP_STARTER_CAVE,
    "pvp_realm": MAP_PVP_REALM,
}


def canonical_marker(code: str) -> str:
    return LEGACY_MARKER_ALIASES.get(code, code)


def read_grid(path: Path) -> list[list[str]]:
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise MapCsvError(f"{path}: empty file")
    body = rows[1:]
    if len(body) != WORLD_H:
        raise MapCsvError(f"{path}: expected {WORLD_H} data rows, found {len(body)}")
    grid: list[list[str]] = []
    for y, row in enumerate(body):
        cells = row[1:]
        if len(cells) != WORLD_W:
            raise MapCsvError(f"{path}: row {y} has {len(cells)} cells, expected {WORLD_W}")
        grid.append([c.strip() for c in cells])
    return grid


def parse_map(
    path: Path, terrain_codes: dict[str, int], background: int, entity_terrain: int, map_id: int
) -> tuple[list[int], list[tuple[int, int, int]], dict[str, tuple[int, int]], list[tuple[int, int]]]:
    grid = read_grid(path)
    tiles = [background] * (WORLD_W * WORLD_H)
    enemies: list[tuple[int, int, int]] = []
    markers: dict[str, tuple[int, int]] = {}
    bridge_tiles: list[tuple[int, int]] = []

    for y in range(WORLD_H):
        for x in range(WORLD_W):
            code = grid[y][x]
            is_border = x == 0 or y == 0 or x == WORLD_W - 1 or y == WORLD_H - 1
            if is_border:
                # Always regenerated, regardless of what's in the cell.
                tiles[y * WORLD_W + x] = BORDER
                continue
            if not code:
                continue
            if code == BRIDGE_CODE:
                # Completed bridge deck: ordinary ROAD terrain, but recorded so
                # the server can mask it as WATER per-player until repair. Unlike
                # unique markers, "=" may appear many times.
                tiles[y * WORLD_W + x] = ROAD
                bridge_tiles.append((x, y))
                continue
            if code in ENEMY_MARKER_CODES:
                enemies.append((x, y, ENEMY_MARKER_CODES[code]))
                # An entity marker fully occupies the cell in the CSV, so
                # the walkable terrain it stands on (not the grid's
                # background, e.g. cave wall) has to be filled in here.
                tiles[y * WORLD_W + x] = entity_terrain
                continue
            if code in ENTITY_CODES:
                marker = canonical_marker(code)
                if marker in markers:
                    raise MapCsvError(
                        f"{path}: duplicate '{code}' marker at ({x},{y}) -- "
                        f"already placed at {markers[marker]}, expected exactly one"
                    )
                markers[marker] = (x, y)
                tiles[y * WORLD_W + x] = entity_terrain
                continue
            if code in terrain_codes:
                tiles[y * WORLD_W + x] = terrain_codes[code]
                continue
            raise MapCsvError(f"{path}: unrecognized code '{code}' at ({x},{y})")

    return tiles, enemies, markers, bridge_tiles


def format_tiles(name: str, tiles: list[int]) -> str:
    lines = [f"{name} = ["]
    for y in range(WORLD_H):
        row = tiles[y * WORLD_W : (y + 1) * WORLD_W]
        lines.append("    " + ",".join(str(t) for t in row) + ",")
    lines.append("]")
    return "\n".join(lines)


def format_spawns(
    overworld_enemies: list[tuple[int, int, int]],
    cave_enemies: list[tuple[int, int, int]],
    pvp_realm_enemies: list[tuple[int, int, int]],
) -> str:
    kind_names = {
        ENEMY_BEAVER: "ENEMY_BEAVER",
        ENEMY_SNAKE: "ENEMY_SNAKE",
        ENEMY_BAT: "ENEMY_BAT",
        ENEMY_SLIME: "ENEMY_SLIME",
        ENEMY_GOBLIN: "ENEMY_GOBLIN",
    }

    def fmt(entries: list[tuple[int, int, int]]) -> str:
        lines = []
        for x, y, kind in entries:
            lines.append(f"        ({x}, {y}, {kind_names[kind]}),")
        return "\n".join(lines)

    return (
        "STATIC_ENEMY_SPAWNS = {\n"
        f"    {MAP_OVERWORLD}: (  # MAP_OVERWORLD\n"
        f"{fmt(overworld_enemies)}\n"
        "    ),\n"
        f"    {MAP_STARTER_CAVE}: (  # MAP_STARTER_CAVE\n"
        f"{fmt(cave_enemies)}\n"
        "    ),\n"
        f"    {MAP_PVP_REALM}: (  # MAP_PVP_REALM\n"
        f"{fmt(pvp_realm_enemies)}\n"
        "    ),\n"
        "}"
    )


def format_bridge_tiles(bridge: list[tuple[int, int]]) -> str:
    if not bridge:
        return "OVERWORLD_BRIDGE_TILES = ()"
    lines = ["OVERWORLD_BRIDGE_TILES = ("]
    for x, y in bridge:
        lines.append(f"    ({x}, {y}),")
    lines.append(")")
    return "\n".join(lines)


def _fmt_optional_coord(name: str, coord: tuple[int, int] | None) -> str:
    return f"{name} = {coord!r}"


def _fmt_optional_map_coord(name: str, marker: tuple[int, int, int] | None) -> str:
    return f"{name} = {marker!r}"


def format_named_npc_spawns(markers: dict[str, tuple[int, int]]) -> str:
    entries: list[tuple[str, str, tuple[int, int] | None]] = [
        ("NPC_DANIEL", "DANIEL", markers.get("DAN")),
        ("NPC_NERISSA", "NERISSA", markers.get("NER")),
        ("NPC_WILHELM", "WILHELM", markers.get("WIL")),
        ("NPC_LUCIAN", "LUCIAN", markers.get("LUC")),
        ("NPC_GRIX", "GRIX", markers.get("GRX")),
    ]
    lines = ["NAMED_NPC_SPAWNS = ("]
    for subtype, _label, coord in entries:
        if coord is None:
            continue
        lines.append(f"    ({subtype}, {MAP_OVERWORLD}, {coord[0]}, {coord[1]}),")
    lines.append(")")
    return "\n".join(lines)


def format_story_layout(story_layout: dict[str, object]) -> str:
    def fmt_region(name: str) -> str:
        region = story_layout.get(name)
        if region is None:
            return f"{name.upper()} = None"
        assert isinstance(region, dict)
        map_id = MAP_NAME_TO_ID[region["map"]]
        return (
            f"{name.upper()} = "
            f"({map_id}, {region['x1']}, {region['y1']}, {region['x2']}, {region['y2']})"
        )

    def fmt_path(name: str) -> str:
        path = story_layout[name]["points"]
        return f"{name.upper()} = ({''.join(f'({x}, {y}),' for x, y in path)})"

    def fmt_points(name: str) -> str:
        points = story_layout[name]["points"]
        return f"{name.upper()} = ({''.join(f'({x}, {y}),' for x, y in points)})"

    return "\n".join(
        (
            fmt_path("wilhelm_escort_path"),
            fmt_region("bridge_defense_region"),
            fmt_region("snake_region"),
            fmt_region("slime_region"),
            fmt_region("gorvak_room_region"),
            f"GORVAK_SUMMON_MAP_ID = {MAP_NAME_TO_ID[story_layout['gorvak_summon_points']['map']]}",
            fmt_points("gorvak_summon_points"),
        )
    )


def _validate_point_list(name: str, payload: object, *, allow_empty: bool) -> list[tuple[int, int]]:
    if not isinstance(payload, list):
        raise MapCsvError(f"story_layout.json: '{name}' must be a list of [x, y] pairs")
    points: list[tuple[int, int]] = []
    for index, point in enumerate(payload):
        if (
            not isinstance(point, list)
            or len(point) != 2
            or not all(isinstance(value, int) for value in point)
        ):
            raise MapCsvError(f"story_layout.json: '{name}[{index}]' must be [x, y]")
        x, y = point
        if not (0 <= x < WORLD_W and 0 <= y < WORLD_H):
            raise MapCsvError(f"story_layout.json: '{name}[{index}]' out of bounds: ({x},{y})")
        points.append((x, y))
    if not allow_empty and not points:
        raise MapCsvError(f"story_layout.json: '{name}' must not be empty")
    return points


def _validate_region(name: str, payload: object) -> dict[str, int | str] | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise MapCsvError(f"story_layout.json: '{name}' must be null or an object")
    required = ("map", "x1", "y1", "x2", "y2")
    for key in required:
        if key not in payload:
            raise MapCsvError(f"story_layout.json: '{name}' missing '{key}'")
    map_name = payload["map"]
    if map_name not in MAP_NAME_TO_ID:
        raise MapCsvError(f"story_layout.json: '{name}.map' must be one of {sorted(MAP_NAME_TO_ID)}")
    x1, y1, x2, y2 = payload["x1"], payload["y1"], payload["x2"], payload["y2"]
    if not all(isinstance(value, int) for value in (x1, y1, x2, y2)):
        raise MapCsvError(f"story_layout.json: '{name}' coordinates must be integers")
    if not (0 <= x1 <= x2 < WORLD_W and 0 <= y1 <= y2 < WORLD_H):
        raise MapCsvError(f"story_layout.json: '{name}' has invalid bounds")
    return {"map": map_name, "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def load_story_layout(
    overworld_tiles: list[int],
    overworld_markers: dict[str, tuple[int, int]],
) -> dict[str, object]:
    with STORY_LAYOUT_PATH.open() as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise MapCsvError("story_layout.json: top level must be an object")
    wilhelm_path_payload = payload.get("wilhelm_escort_path")
    if not isinstance(wilhelm_path_payload, dict) or wilhelm_path_payload.get("map") != "overworld":
        raise MapCsvError("story_layout.json: 'wilhelm_escort_path' must be an object with map='overworld'")
    wilhelm_points = _validate_point_list(
        "wilhelm_escort_path.points", wilhelm_path_payload.get("points"), allow_empty=True
    )
    for index, (x, y) in enumerate(wilhelm_points):
        if overworld_tiles[y * WORLD_W + x] not in (GRASS, ROAD):
            raise MapCsvError(
                f"story_layout.json: 'wilhelm_escort_path.points[{index}]' is not walkable on the overworld"
            )
    if wilhelm_points:
        start = overworld_markers.get("WIL")
        end = overworld_markers.get("WBD")
        if start is not None and wilhelm_points[0] != start:
            raise MapCsvError(
                f"story_layout.json: Wilhelm path must start at WIL {start}, found {wilhelm_points[0]}"
            )
        if end is not None and wilhelm_points[-1] != end:
            raise MapCsvError(
                f"story_layout.json: Wilhelm path must end at WBD {end}, found {wilhelm_points[-1]}"
            )
        for prev, cur in zip(wilhelm_points, wilhelm_points[1:]):
            if abs(prev[0] - cur[0]) + abs(prev[1] - cur[1]) != 1:
                raise MapCsvError("story_layout.json: Wilhelm path must move one tile at a time")
    gorvak_summons_payload = payload.get("gorvak_summon_points")
    if not isinstance(gorvak_summons_payload, dict) or gorvak_summons_payload.get("map") != "cave":
        raise MapCsvError("story_layout.json: 'gorvak_summon_points' must be an object with map='cave'")
    return {
        "wilhelm_escort_path": {"map": "overworld", "points": wilhelm_points},
        "bridge_defense_region": _validate_region("bridge_defense_region", payload.get("bridge_defense_region")),
        "snake_region": _validate_region("snake_region", payload.get("snake_region")),
        "slime_region": _validate_region("slime_region", payload.get("slime_region")),
        "gorvak_room_region": _validate_region("gorvak_room_region", payload.get("gorvak_room_region")),
        "gorvak_summon_points": {
            "map": "cave",
            "points": _validate_point_list(
                "gorvak_summon_points.points", gorvak_summons_payload.get("points"), allow_empty=True
            ),
        },
    }


def main() -> int:
    overworld_tiles, overworld_enemies, overworld_markers, overworld_bridge = parse_map(
        MAPS_DIR / "overworld.csv", OVERWORLD_TERRAIN_CODES, GRASS, GRASS, MAP_OVERWORLD
    )
    cave_tiles, cave_enemies, cave_markers, _cave_bridge = parse_map(
        MAPS_DIR / "cave.csv", CAVE_TERRAIN_CODES, CAVE_WALL, CAVE_FLOOR, MAP_STARTER_CAVE
    )
    pvp_realm_tiles, pvp_realm_enemies, pvp_realm_markers, _pvp_bridge = parse_map(
        MAPS_DIR / "pvp_realm.csv", PVP_REALM_TERRAIN_CODES, GRASS, GRASS, MAP_PVP_REALM
    )

    for required in ("DAN", "GRX", "X", "O", "C", "P"):
        if required not in overworld_markers:
            raise MapCsvError(f"overworld.csv: missing required marker '{required}'")
    if "C" not in cave_markers:
        raise MapCsvError("cave.csv: missing required marker 'C' (cave exit)")
    if "E" not in pvp_realm_markers:
        raise MapCsvError("pvp_realm.csv: missing required marker 'E' (realm entry)")
    if "P" not in pvp_realm_markers:
        raise MapCsvError("pvp_realm.csv: missing required marker 'P' (realm exit)")

    story_layout = load_story_layout(overworld_tiles, overworld_markers)

    farmer_x, farmer_y = overworld_markers["DAN"]
    goblin_npc_x, goblin_npc_y = overworld_markers["GRX"]
    start = overworld_markers["O"]
    respawn = overworld_markers["X"]
    cave_entrance = overworld_markers["C"]
    cave_return = (cave_entrance[0], cave_entrance[1] + 1)
    pvp_realm_entrance = overworld_markers["P"]
    pvp_realm_return = (pvp_realm_entrance[0], pvp_realm_entrance[1] + 1)
    pvp_realm_entry = pvp_realm_markers["E"]
    cave_exit = cave_markers["C"]
    pvp_realm_exit = pvp_realm_markers["P"]
    story_markers = {
        "WARDEN_KEY_MARKER": (
            MAP_OVERWORLD,
            overworld_markers["KEY"][0],
            overworld_markers["KEY"][1],
        )
        if "KEY" in overworld_markers
        else None,
        "GORVAK_MARKER": (
            MAP_STARTER_CAVE,
            cave_markers["GOR"][0],
            cave_markers["GOR"][1],
        )
        if "GOR" in cave_markers
        else None,
        "DEEP_PUMP_CONTROLS_MARKER": (
            MAP_STARTER_CAVE,
            cave_markers["DPC"][0],
            cave_markers["DPC"][1],
        )
        if "DPC" in cave_markers
        else None,
        "WILHELM_BRIDGE_DESTINATION": (
            MAP_OVERWORLD,
            overworld_markers["WBD"][0],
            overworld_markers["WBD"][1],
        )
        if "WBD" in overworld_markers
        else None,
    }

    overworld_tiles[respawn[1] * WORLD_W + respawn[0]] = GRAVE
    overworld_tiles[cave_entrance[1] * WORLD_W + cave_entrance[0]] = CAVE_ENTRANCE
    overworld_tiles[pvp_realm_entrance[1] * WORLD_W + pvp_realm_entrance[0]] = CAVE_ENTRANCE
    cave_tiles[cave_exit[1] * WORLD_W + cave_exit[0]] = CAVE_EXIT
    pvp_realm_tiles[pvp_realm_exit[1] * WORLD_W + pvp_realm_exit[0]] = CAVE_EXIT

    module = f'''"""Hand-authored world layout -- generated by tools/import_map_csv.py from
maps/overworld.csv, maps/cave.csv, and maps/pvp_realm.csv. Do NOT edit this file by hand;
edit the CSVs and re-run that script instead. See maps/README.md.
"""

from __future__ import annotations

from .entities import (
    ENEMY_BAT,
    ENEMY_BEAVER,
    ENEMY_GOBLIN,
    ENEMY_SLIME,
    ENEMY_SNAKE,
    NPC_DANIEL,
    NPC_GRIX,
    NPC_LUCIAN,
    NPC_NERISSA,
    NPC_WILHELM,
)

DANIEL_X = {farmer_x}
DANIEL_Y = {farmer_y}
FARMER_X = DANIEL_X
FARMER_Y = DANIEL_Y
GRIX_X = {goblin_npc_x}
GRIX_Y = {goblin_npc_y}
GOBLIN_NPC_X = GRIX_X
GOBLIN_NPC_Y = GRIX_Y
NERISSA_POS = {overworld_markers.get("NER")!r}
WILHELM_POS = {overworld_markers.get("WIL")!r}
LUCIAN_POS = {overworld_markers.get("LUC")!r}

OVERWORLD_START = {start!r}
OVERWORLD_RESPAWN = {respawn!r}
OVERWORLD_CAVE_ENTRANCE = {cave_entrance!r}
OVERWORLD_CAVE_RETURN = {cave_return!r}
OVERWORLD_PVP_REALM_ENTRANCE = {pvp_realm_entrance!r}
OVERWORLD_PVP_REALM_RETURN = {pvp_realm_return!r}
STARTER_CAVE_EXIT = {cave_exit!r}
PVP_REALM_ENTRY = {pvp_realm_entry!r}
PVP_REALM_RESPAWN = {pvp_realm_entry!r}
PVP_REALM_EXIT = {pvp_realm_exit!r}

{format_bridge_tiles(overworld_bridge)}

{format_named_npc_spawns(overworld_markers)}

{_fmt_optional_map_coord("WARDEN_KEY_MARKER", story_markers["WARDEN_KEY_MARKER"])}
{_fmt_optional_map_coord("GORVAK_MARKER", story_markers["GORVAK_MARKER"])}
{_fmt_optional_map_coord("DEEP_PUMP_CONTROLS_MARKER", story_markers["DEEP_PUMP_CONTROLS_MARKER"])}
{_fmt_optional_map_coord("WILHELM_BRIDGE_DESTINATION", story_markers["WILHELM_BRIDGE_DESTINATION"])}

{format_story_layout(story_layout)}

{format_spawns(overworld_enemies, cave_enemies, pvp_realm_enemies)}

{format_tiles("OVERWORLD_TILES", overworld_tiles)}

{format_tiles("CAVE_TILES", cave_tiles)}

{format_tiles("PVP_REALM_TILES", pvp_realm_tiles)}
'''

    OUTPUT.write_text(module)
    print(f"Wrote {OUTPUT}")
    print(f"  Daniel at ({farmer_x},{farmer_y}), Grix at ({goblin_npc_x},{goblin_npc_y})")
    print(f"  Start at {start}, respawn/grave at {respawn}, cave entrance at {cave_entrance}")
    print(f"  Cave exit at {cave_exit}")
    print(f"  PvP realm entrance at {pvp_realm_entrance}, exit at {pvp_realm_exit}")
    if overworld_markers.get("NER") is not None:
        print(f"  Nerissa at {overworld_markers['NER']}")
    if overworld_markers.get("WIL") is not None:
        print(f"  Wilhelm at {overworld_markers['WIL']}")
    if overworld_markers.get("LUC") is not None:
        print(f"  Lucian at {overworld_markers['LUC']}")
    print(
        f"  {len(overworld_enemies)} overworld enemy spawns, "
        f"{len(cave_enemies)} cave enemy spawns, "
        f"{len(pvp_realm_enemies)} PvP realm enemy spawns"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MapCsvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
