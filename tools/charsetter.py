#!/usr/bin/env python3
"""FujiRealm art conversion helpers for the FujiRealm tile editor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .export_tile_map import (
        ParseError,
        eval_expr,
        load_asm,
        parse_font,
        parse_game_palette,
        parse_table,
        strip_comment,
    )
except ImportError:  # Direct execution from tools/*.py.
    from export_tile_map import (
        ParseError,
        eval_expr,
        load_asm,
        parse_font,
        parse_game_palette,
        parse_table,
        strip_comment,
    )


FONT_BYTES = 1024
PROJECT_VERSION = 4
PROJECT_TYPE = "fujirealm-tiles"
TILE_COUNT = 52
SPRITE_COUNT = 12
QUADRANTS = ("tl", "tr", "bl", "br")
OVERWORLD_TABLES = tuple(f"tile2x2_{quadrant}_overworld" for quadrant in QUADRANTS)
CAVE_TABLES = tuple(f"tile2x2_{quadrant}_cave" for quadrant in QUADRANTS)
SPRITE_TABLES = tuple(f"player_sprite_{quadrant}" for quadrant in QUADRANTS)

# Player/Missile art for the local player. A normal-width GTIA player is
# 8 pixels wide, which is exactly the width of the 2x2 character sprite it
# replaces, so the PM frames are derived from that art rather than drawn
# separately. The extra rows overhang above the tile.
PM_PLAYER_H = 24
PM_TILE_ROWS = 16
PM_LOCAL_FRAMES = 6

# Bullets ride the four GTIA missiles, which are two bits wide and share one
# 256-byte area. That is the whole budget: eight rows of two pixels, in one
# color (COLPF3, via fifth-player mode). The default is downsampled from the
# BULLET tile's top cell so a project that has never edited it still looks
# like the character bullet did.
PM_MISSILE_H = 8
BULLET_TILE_INDEX = 6

TILE_NAMES = (
    "Grass",
    "Local Player Front 0 (Legacy Tile)",
    "Tree Full",
    "Herb",
    "Tree Damaged",
    "Tree Stump",
    "Bullet",
    "Border",
    "Beaver",
    "Snake",
    "Road",
    "Water",
    "Building",
    "Cave Entrance",
    "Grave",
    "Cave Floor",
    "Cave Wall",
    "Cave Exit",
    "HUD Digit 2",
    "HUD Digit 3",
    "HUD Digit 4",
    "HUD Digit 5",
    "HUD Digit 6",
    "HUD Digit 7",
    "HUD Digit 8",
    "HUD Digit 9",
    "HUD B",
    "HUD L",
    "HUD S",
    "HUD Colon",
    "Local Player Right 1 (Legacy Tile)",
    "Local Player Left 0 (Legacy Tile)",
    "Local Player Left 1 (Legacy Tile)",
    "HUD Blank",
    "Gold",
    "Sticks",
    "Hostile Goblin",
    "Town NPC (Generic)",
    "Grix",
    "Warden Key",
    "Daniel",
    "Wilhelm",
    "Lucian",
    "Nerissa",
    "Slime 0",
    "Slime 1",
    "Bat 0",
    "Bat 1",
    "Gorvak",
    "Deep Pump",
    "Pump Controls",
    "Wilhelm Working",
)

SPRITE_NAMES = (
    "Local Player Front 0",
    "Local Player Front 1",
    "Local Player Right 0",
    "Local Player Right 1",
    "Local Player Left 0",
    "Local Player Left 1",
    "Remote Player Front 0",
    "Remote Player Front 1",
    "Remote Player Right 0",
    "Remote Player Right 1",
    "Remote Player Left 0",
    "Remote Player Left 1",
)

VISIBLE_LOGICAL_TILES = frozenset(
    (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, *range(34, 52))
)
TERRAIN_TILES = frozenset((0, 2, 3, 4, 5, 7, 10, 11, 12, 13, 14, 15, 16, 17))
ENTITY_TILES = frozenset((8, 9, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 51))
ITEM_TILES = frozenset((6, 34, 35, 39))
PROP_TILES = frozenset((49, 50))


class CharsetterError(RuntimeError):
    pass


@dataclass(frozen=True)
class DefinitionSpec:
    id: str
    name: str
    category: str
    target_type: str
    target_index: int
    visible: bool


def _slug(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in value)
    return "-".join(normalized.split())


def definition_specs() -> tuple[DefinitionSpec, ...]:
    definitions: list[DefinitionSpec] = []
    for index, name in enumerate(TILE_NAMES):
        if index in TERRAIN_TILES:
            category = "Terrain"
        elif index in ENTITY_TILES:
            category = "Entities"
        elif index in ITEM_TILES:
            category = "Items"
        elif index in PROP_TILES:
            category = "Props"
        else:
            category = "Internal"
        definitions.append(
            DefinitionSpec(
                f"logical-{index:02d}-{_slug(name)}",
                name,
                category,
                "logicalTile",
                index,
                index in VISIBLE_LOGICAL_TILES,
            )
        )
    for index, name in enumerate(SPRITE_NAMES):
        category = "Local Player" if index < 6 else "Remote Player"
        definitions.append(
            DefinitionSpec(
                f"sprite-{index:02d}-{_slug(name)}",
                name,
                category,
                "playerSprite",
                index,
                True,
            )
        )
    return tuple(definitions)


DEFINITION_SPECS = definition_specs()
SPEC_BY_TARGET = {(spec.target_type, spec.target_index): spec for spec in DEFINITION_SPECS}
SPEC_BY_ID = {spec.id: spec for spec in DEFINITION_SPECS}


def animation_specs() -> tuple[dict[str, Any], ...]:
    groups = (
        ("local-front", "Local Player Front", "playerSprite", 0, 1),
        ("local-right", "Local Player Right", "playerSprite", 2, 3),
        ("local-left", "Local Player Left", "playerSprite", 4, 5),
        ("remote-front", "Remote Player Front", "playerSprite", 6, 7),
        ("remote-right", "Remote Player Right", "playerSprite", 8, 9),
        ("remote-left", "Remote Player Left", "playerSprite", 10, 11),
        ("slime", "Slime", "logicalTile", 44, 45),
        ("bat", "Bat", "logicalTile", 46, 47),
        ("wilhelm-working", "Wilhelm Working", "logicalTile", 41, 51),
    )
    animations = []
    for identifier, name, target_type, first, second in groups:
        animations.append(
            {
                "id": identifier,
                "name": name,
                "frameIds": [
                    SPEC_BY_TARGET[(target_type, first)].id,
                    SPEC_BY_TARGET[(target_type, second)].id,
                ],
                "intervalMs": 250,
            }
        )
    return tuple(animations)


ANIMATION_SPECS = animation_specs()


def _bytes(value: Any, name: str, expected: int | None = None) -> list[int]:
    if not isinstance(value, list):
        raise CharsetterError(f"{name} must be an array")
    if expected is not None and len(value) != expected:
        raise CharsetterError(f"{name} must contain exactly {expected} bytes, found {len(value)}")
    result: list[int] = []
    for index, byte in enumerate(value):
        if not isinstance(byte, int) or isinstance(byte, bool) or not 0 <= byte <= 255:
            raise CharsetterError(f"{name}[{index}] is not a byte: {byte!r}")
        result.append(byte)
    return result


def _parse_optional_table(
    lines: list[tuple[Path, int, str]], constants: dict[str, int], label: str
) -> list[int] | None:
    try:
        return parse_table(lines, constants, label)
    except ParseError as exc:
        if "label not found" in str(exc):
            return None
        raise


def _parse_constants_lenient(lines: list[tuple[Path, int, str]]) -> dict[str, int]:
    """Resolve simple constants and leave MADS location expressions alone."""
    import re

    constants: dict[str, int] = {}
    pending: list[tuple[str, str, str]] = []
    for path, lineno, raw in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", strip_comment(raw))
        if match:
            pending.append((match.group(1), match.group(2).strip(), f"{path}:{lineno}"))
    changed = True
    while pending and changed:
        changed = False
        remaining: list[tuple[str, str, str]] = []
        for name, expression, where in pending:
            try:
                constants[name] = eval_expr(expression, constants, where)
                changed = True
            except ParseError:
                remaining.append((name, expression, where))
        pending = remaining
    return constants


def extract_source_art(source: Path) -> tuple[list[int], list[list[int]], list[list[int]], list[int]]:
    """Read the effective font/tables, including the current inline font patches."""
    try:
        lines = load_asm(source)
        constants = _parse_constants_lenient(lines)
        font = parse_font(lines, constants)
        patches = (
            ("farmer_font_data", constants.get("T2_FARMER_TL")),
            ("road_font_data", 0x5E),
            ("remote_font_data", constants.get("T2_REMOTE_F_TL")),
            ("charm_font_data", constants.get("T2_ITEM_WARDEN_KEY")),
        )
        for label, character in patches:
            values = _parse_optional_table(lines, constants, label)
            if values is None:
                continue
            if character is None:
                raise CharsetterError(f"cannot resolve the character index for {label}")
            start = character * 8
            if len(values) % 8 or start + len(values) > FONT_BYTES:
                raise CharsetterError(f"{label} does not fit the 1 KB font")
            font[start : start + len(values)] = values

        tiles = [parse_table(lines, constants, name) for name in OVERWORLD_TABLES]
        caves = [
            _parse_optional_table(lines, constants, name) or list(tiles[index])
            for index, name in enumerate(CAVE_TABLES)
        ]
        sprites = [parse_table(lines, constants, name) for name in SPRITE_TABLES]
        if any(len(table) != TILE_COUNT for table in tiles + caves):
            raise CharsetterError(
                f"overworld and cave tile tables must each contain {TILE_COUNT} entries"
            )
        if any(len(table) != SPRITE_COUNT for table in sprites):
            raise CharsetterError("player sprite tables must each contain 12 entries")
        if caves != tiles:
            raise CharsetterError("one FujiRealm project cannot represent divergent overworld and cave mappings")

        color0, color1, color2, color3, color4 = parse_game_palette(lines, constants)
        return font, tiles, sprites, [color4, color0, color1, color2, color3]
    except ParseError as exc:
        raise CharsetterError(str(exc)) from exc


def build_project(
    font: list[int], tiles: list[list[int]], sprites: list[list[int]], palette: list[int]
) -> dict[str, Any]:
    definitions = []
    for spec in DEFINITION_SPECS:
        tables = tiles if spec.target_type == "logicalTile" else sprites
        definitions.append(
            {
                "id": spec.id,
                "name": spec.name,
                "category": spec.category,
                "targetType": spec.target_type,
                "targetIndex": spec.target_index,
                "characters": [table[spec.target_index] for table in tables],
                "visible": spec.visible,
            }
        )
    return {
        "version": PROJECT_VERSION,
        "projectType": PROJECT_TYPE,
        "name": "FujiRealm Overworld",
        "mode": "antic4",
        "logicalTileCount": TILE_COUNT,
        "fontData": list(font),
        "paletteHex": list(palette),
        "paletteA4": ["#0F0F0F", "#6EAF3C", "#833B28", "#EFEFEF", "#E08CE0"],
        "fontName": "fujirealm_charsetter.fnt",
        "tileDefinitions": definitions,
        "animations": [dict(animation, frameIds=list(animation["frameIds"])) for animation in ANIMATION_SPECS],
    }


def _validate_locked_definition(entry: dict[str, Any], spec: DefinitionSpec) -> list[int]:
    locked = {
        "id": spec.id,
        "name": spec.name,
        "category": spec.category,
        "targetType": spec.target_type,
        "targetIndex": spec.target_index,
        "visible": spec.visible,
    }
    for field, expected in locked.items():
        if entry.get(field) != expected:
            raise CharsetterError(f"tile definition {spec.id!r} has modified locked field {field!r}")
    return _bytes(entry.get("characters"), f"tile definition {spec.id!r} characters", 4)


def validate_project(
    project: dict[str, Any], font_override: bytes | None = None
) -> tuple[list[int], list[list[int]], list[list[int]]]:
    if not isinstance(project, dict):
        raise CharsetterError("project root must be an object")
    if project.get("version") != PROJECT_VERSION:
        raise CharsetterError(f"project version must be {PROJECT_VERSION}")
    if project.get("projectType") != PROJECT_TYPE:
        raise CharsetterError(f"project type must be {PROJECT_TYPE}")
    if project.get("mode") != "antic4":
        raise CharsetterError("project mode must be antic4")
    if project.get("logicalTileCount") != TILE_COUNT:
        raise CharsetterError(f"logicalTileCount must be {TILE_COUNT}")
    font = list(font_override) if font_override is not None else _bytes(project.get("fontData"), "fontData", FONT_BYTES)
    if len(font) != FONT_BYTES:
        raise CharsetterError(f"font override must contain exactly {FONT_BYTES} bytes")

    definitions = project.get("tileDefinitions")
    if not isinstance(definitions, list):
        raise CharsetterError("tileDefinitions must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for entry in definitions:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise CharsetterError("every tile definition must have an id")
        identifier = entry["id"]
        if identifier in by_id:
            raise CharsetterError(f"duplicate tile definition id: {identifier}")
        by_id[identifier] = entry
    if set(by_id) != set(SPEC_BY_ID):
        missing = sorted(set(SPEC_BY_ID) - set(by_id))
        extra = sorted(set(by_id) - set(SPEC_BY_ID))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise CharsetterError("tile definition set is invalid: " + "; ".join(details))

    blocks: dict[tuple[str, int], list[int]] = {}
    for spec in DEFINITION_SPECS:
        blocks[(spec.target_type, spec.target_index)] = _validate_locked_definition(by_id[spec.id], spec)
    animations = project.get("animations")
    if animations != list(ANIMATION_SPECS):
        raise CharsetterError("animation definitions do not match the locked FujiRealm runtime bindings")

    tile_blocks = [blocks[("logicalTile", index)] for index in range(TILE_COUNT)]
    sprite_blocks = [blocks[("playerSprite", index)] for index in range(SPRITE_COUNT)]
    tiles = [[block[quadrant] for block in tile_blocks] for quadrant in range(4)]
    sprites = [[block[quadrant] for block in sprite_blocks] for quadrant in range(4)]
    return font, tiles, sprites


def _emit_table(lines: list[str], label: str, values: list[int], per_line: int = 16) -> None:
    lines.append(label)
    for start in range(0, len(values), per_line):
        chunk = values[start : start + per_line]
        lines.append("        dta " + ",".join(f"${value:02X}" for value in chunk))


def pm_frames_from_sprites(
    font: list[int], sprites: list[list[int]]
) -> tuple[list[int], list[int]]:
    """Convert the 6 local-player character frames into the P0/P1 bitplanes.

    An ANTIC 4 character is 4 pixels of 2 bits each, so a 2x2 sprite is
    already 8 pixels wide by 16 rows at 2 bits per pixel -- exactly a
    normal-width player split across two overlapped bitplanes. Pixel value 1
    lights P0, 2 lights P1, and 3 lights both, which GTIA shows as
    COLPM0 OR COLPM1 under multicolor player mode. The art is placed at the
    bottom of the taller PM frame so it still fills its tile and the spare
    rows overhang above it.
    """
    top_left, top_right, bottom_left, bottom_right = sprites
    plane0: list[int] = []
    plane1: list[int] = []
    for frame in range(PM_LOCAL_FRAMES):
        rows0 = [0] * PM_PLAYER_H
        rows1 = [0] * PM_PLAYER_H
        halves = ((top_left, top_right), (bottom_left, bottom_right))
        for half, (left_table, right_table) in enumerate(halves):
            # Bit 7 of a screen code selects COLPF3 in ANTIC 4; it is not part
            # of the glyph index, and the local player frames never set it.
            left = (left_table[frame] & 0x7F) * 8
            right = (right_table[frame] & 0x7F) * 8
            for line in range(8):
                pixels = (font[left + line] << 8) | font[right + line]
                bits0 = 0
                bits1 = 0
                for pixel in range(8):
                    value = (pixels >> (14 - pixel * 2)) & 3
                    bits0 = (bits0 << 1) | (value & 1)
                    bits1 = (bits1 << 1) | ((value >> 1) & 1)
                row = PM_PLAYER_H - PM_TILE_ROWS + half * 8 + line
                rows0[row] = bits0
                rows1[row] = bits1
        plane0.extend(rows0)
        plane1.extend(rows1)
    return plane0, plane1


def pm_missile_from_tiles(font: list[int], tiles: list[list[int]]) -> list[int]:
    """Downsample the BULLET tile's top cell to the missile's two pixels.

    The character bullet was eight pixels wide; a missile is two. Each half of
    the row collapses to one lit pixel if any of its four pixels were lit,
    which keeps the glyph's vertical profile -- the part that still reads at
    this size -- rather than any of its horizontal detail.
    """
    top_left, top_right = tiles[0], tiles[1]
    left = (top_left[BULLET_TILE_INDEX] & 0x7F) * 8
    right = (top_right[BULLET_TILE_INDEX] & 0x7F) * 8
    rows = []
    for line in range(PM_MISSILE_H):
        pixels = (font[left + line] << 8) | font[right + line]
        value = 0
        if pixels & 0xFF00:
            value |= 2
        if pixels & 0x00FF:
            value |= 1
        rows.append(value)
    return rows


def parse_pm_missile(value: Any) -> list[int]:
    """Read the tile editor's explicitly authored missile art."""
    if not isinstance(value, list) or len(value) != PM_MISSILE_H:
        raise CharsetterError(f"pmMissile must contain {PM_MISSILE_H} rows")
    rows = []
    for index, entry in enumerate(value):
        if not isinstance(entry, int) or isinstance(entry, bool) or not 0 <= entry <= 3:
            raise CharsetterError(f"pmMissile[{index}] must be 0-3")
        rows.append(entry)
    return rows


def parse_pm_sprites(value: Any) -> tuple[list[int], list[int]]:
    """Read the tile editor's explicitly authored PM frames."""
    if not isinstance(value, list) or len(value) != PM_LOCAL_FRAMES:
        raise CharsetterError(f"pmSprites must contain {PM_LOCAL_FRAMES} frames")
    plane0: list[int] = []
    plane1: list[int] = []
    for index, frame in enumerate(value):
        if not isinstance(frame, dict):
            raise CharsetterError(f"pmSprites[{index}] must be an object")
        for plane, destination in (("p0", plane0), ("p1", plane1)):
            rows = frame.get(plane)
            if not isinstance(rows, list) or len(rows) != PM_PLAYER_H:
                raise CharsetterError(
                    f"pmSprites[{index}].{plane} must contain {PM_PLAYER_H} rows"
                )
            for row, byte in enumerate(rows):
                if not isinstance(byte, int) or isinstance(byte, bool) or not 0 <= byte <= 255:
                    raise CharsetterError(f"pmSprites[{index}].{plane}[{row}] must be a byte")
                destination.append(byte)
    return plane0, plane1


def generate_pm_include(
    font: list[int],
    tiles: list[list[int]],
    sprites: list[list[int]],
    source: Path,
    pm_sprites: Any = None,
    pm_missile: Any = None,
) -> str:
    # pmSprites is optional. Without it the PM frames are derived from the
    # character art, which keeps projects that predate PM editing building
    # unchanged and keeps the two in sync until someone edits PM art directly.
    if pm_sprites is None:
        plane0, plane1 = pm_frames_from_sprites(font, sprites)
        origin = "derived from its 2x2 character frames"
    else:
        plane0, plane1 = parse_pm_sprites(pm_sprites)
        origin = "authored in the tile editor"
    lines = [
        "; Generated by tools/import_charsetter.py",
        f"; Source project: {source}",
        f"; Player/Missile art for the local player, {origin}:",
        f"; {PM_LOCAL_FRAMES} frames of {PM_PLAYER_H} rows, 8 pixels wide,",
        "; split into the P0 and P1 bitplanes that GTIA overlaps to produce",
        "; three sprite colors.",
        "",
    ]
    _emit_table(lines, "pm_player_p0_data", plane0, per_line=PM_PLAYER_H)
    lines.append("")
    _emit_table(lines, "pm_player_p1_data", plane1, per_line=PM_PLAYER_H)
    if pm_missile is None:
        rows = pm_missile_from_tiles(font, tiles)
        missile_origin = "downsampled from the BULLET tile"
    else:
        rows = parse_pm_missile(pm_missile)
        missile_origin = "authored in the tile editor"
    lines.extend(
        [
            "",
            f"; Bullet missile art, {missile_origin}: {PM_MISSILE_H} rows of two",
            "; pixels, held in bits 0-1 and shifted into whichever of M0-M3 the",
            "; bullet is using.",
        ]
    )
    _emit_table(lines, "pm_bullet_data", rows, per_line=PM_MISSILE_H)
    lines.append("")
    return "\n".join(lines)


def generate_include(font: list[int], tiles: list[list[int]], sprites: list[list[int]], source: Path) -> str:
    lines = [
        "; Generated by tools/import_charsetter.py",
        f"; Source project: {source}",
        "; Edit the FujiRealm tile-editor project, then regenerate this file.",
        "",
    ]
    for quadrant, table in zip(QUADRANTS, tiles):
        _emit_table(lines, f"tile2x2_{quadrant}", table)
    lines.extend(["", "        org FONT"])
    _emit_table(lines, "font_data", font)
    # The cave shares the overworld FONT page (see apply_tileset_cave), so no
    # separate cave-font glyph copy is reserved. Freeing $7C00-$8000 gives the
    # paged dialogue modal a contiguous home (plan 14.11); a distinct cave font
    # is re-homed during the later art/tile-budget phase if needed.
    lines.extend(["", "        org $8000"])
    for quadrant, table in zip(QUADRANTS, sprites):
        _emit_table(lines, f"player_sprite_{quadrant}", table)
    lines.append("")
    for quadrant, table in zip(QUADRANTS, tiles):
        _emit_table(lines, f"tile2x2_{quadrant}_overworld", table)
    lines.extend(
        [
            "",
            "; Overworld and cave intentionally share one logical mapping.",
            *[
                f"tile2x2_{quadrant}_cave = tile2x2_{quadrant}_overworld"
                for quadrant in QUADRANTS
            ],
        ]
    )
    lines.append("")
    return "\n".join(lines)
