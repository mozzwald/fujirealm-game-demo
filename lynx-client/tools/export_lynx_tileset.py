#!/usr/bin/env python3
"""Seed art/lynx_tileset.json from the Atari charsetter project.

The Lynx art started as an automatic conversion of the Atari 8-bit tiles:
each 16x8 ANTIC block halved vertically to 8x8 and its pen values mapped
into the shared 16-colour CLUT. That conversion is a starting point, not the
destination -- 8x8 art wants different choices than art drawn for 16x16
cells, and the halving is a heuristic.

So this writes the converted pixels out as an editable tileset which then
becomes the source of truth: charsetter edits the JSON, and
import_lynx_art.py builds the C arrays from it. Re-running OVERWRITES
hand-drawn work, which is why it is a separate command rather than part of
`make art`.

Once the tileset exists, the useful mode is a merge: the Atari side keeps
adding logical tiles (Phase 61 took the allocation from 40 to 52), and those
new slots want seeding without discarding the slots that have since been
drawn by hand. A merge fills in whatever the tileset is missing, reseeds only
the slots you name, and preserves everything else byte for byte.

    python3 tools/export_lynx_tileset.py              # first seed only
    python3 tools/export_lynx_tileset.py --merge      # add missing slots
    python3 tools/export_lynx_tileset.py --merge --reseed-tiles 9,37-39,40-51
    python3 tools/export_lynx_tileset.py --force      # re-seed everything
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import import_lynx_art as conv


def rows_to_hex(rows):
    """8 rows of 8 CLUT indices -> 8 strings of 8 hex digits."""
    return ["".join(f"{value:X}" for value in row) for row in rows]


def parse_index_list(text, limit):
    """"9,37-39,44" -> {9, 37, 38, 39, 44}, validated against limit."""
    if not text:
        return set()
    out = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                lo, hi = int(lo), int(hi)
            except ValueError:
                raise SystemExit(f"bad index range {part!r}")
            if lo > hi:
                raise SystemExit(f"bad index range {part!r}: {lo} > {hi}")
            out.update(range(lo, hi + 1))
        else:
            try:
                out.add(int(part))
            except ValueError:
                raise SystemExit(f"bad index {part!r}")
    bad = sorted(i for i in out if not 0 <= i < limit)
    if bad:
        raise SystemExit(f"index out of range 0..{limit - 1}: {bad}")
    return out


def parse_name_list(text):
    return {part.strip() for part in (text or "").split(",") if part.strip()}


def convert_from_atari():
    """The Atari-derived conversion for every slot, as a seed source."""
    project = json.loads(conv.PROJECT.read_text(encoding="utf-8"))
    font, tiles, sprites = conv.validate_project(project)

    # Names come from the Atari project so the library reads the same in both
    # editors; they are labels only and the build ignores them.
    names = {}
    for definition in project.get("tileDefinitions", []):
        if definition.get("targetType") == "logicalTile":
            names[definition["targetIndex"]] = definition.get("name", "")

    tile_entries = []
    for index in range(conv.TILE_COUNT):
        quads = tuple(tiles[q][index] for q in range(4))
        pixels = conv.compose_block(font, quads)
        name = names.get(index, f"tile {index}")
        tile_entries.append({
            "index": index,
            "name": name,
            # The Atari project keeps player-frame and HUD-glyph art in tile
            # slots the Lynx never renders (it draws the player from sprites
            # and the HUD from its own font). Flag those so the editor can
            # hide them; the tile id still maps straight to the array index.
            "used": not ("Legacy" in name or name.startswith("HUD")),
            "rows": rows_to_hex(conv.clut_rows(pixels, conv.TILE_ROLES[index])),
        })

    player_entries = []
    for index in range(conv.PLAYER_FRAME_COUNT):
        quads = tuple(sprites[q][index] for q in range(4))
        pixels = conv.compose_block(font, quads)
        player_entries.append({
            "index": index,
            "rows": rows_to_hex(conv.clut_rows(pixels, conv.ROLE_PLAYER)),
        })

    entity_entries = []
    for name, tile_index, pen_map in conv.ENTITY_SPRITES:
        quads = tuple(tiles[q][tile_index] for q in range(4))
        pixels = conv.compose_block(font, quads)
        entity_entries.append({
            "name": name,
            "rows": rows_to_hex(conv.clut_rows(pixels, pen_map)),
        })

    palette = [f"#{r:02X}{g:02X}{b:02X}" for (r, g, b) in conv.CLUT]
    return tile_entries, player_entries, entity_entries, palette


def build_tileset(existing=None, reseed_tiles=frozenset(),
                  reseed_entities=frozenset(), reseed_players=False,
                  reseed_palette=False, report=None):
    """Merge the Atari conversion into `existing` (None = full seed).

    A slot takes its pixels from the conversion when it is explicitly reseeded
    or absent from `existing`; otherwise the existing rows are preserved
    untouched. Names and `used` flags always refresh from the Atari project, so
    a repurposed slot relabels itself in the editor (slot 9 "Beaver Hurt" ->
    "Snake") without disturbing hand-drawn pixels.
    """
    tile_entries, player_entries, entity_entries, palette = convert_from_atari()
    if report is None:
        report = {}
    report.setdefault("seeded", [])
    report.setdefault("preserved", [])
    report.setdefault("dropped", [])

    if existing is None:
        report["seeded"] = ["all tiles", "all players", "all entities", "palette"]
        return {
            "version": 1,
            "projectType": "fujirealm-lynx-tiles",
            "tileWidth": 8,
            "tileHeight": 8,
            # Index 0 is the transparent pen for entity sprites, so nothing
            # opaque may be assigned to it except true black.
            "palette": palette,
            "tiles": tile_entries,
            "players": player_entries,
            "entities": entity_entries,
        }

    old_tiles = {t["index"]: t for t in existing.get("tiles", [])}
    for entry in tile_entries:
        index = entry["index"]
        old = old_tiles.get(index)
        if old is None:
            report["seeded"].append(f"tile {index} ({entry['name']}, new)")
        elif index in reseed_tiles:
            report["seeded"].append(f"tile {index} ({entry['name']})")
        else:
            entry["rows"] = old["rows"]
            report["preserved"].append(f"tile {index}")

    old_players = {p["index"]: p for p in existing.get("players", [])}
    for entry in player_entries:
        old = old_players.get(entry["index"])
        if old is not None and not reseed_players:
            entry["rows"] = old["rows"]
            report["preserved"].append(f"player {entry['index']}")
        else:
            report["seeded"].append(f"player {entry['index']}")

    old_entities = {e["name"]: e for e in existing.get("entities", [])}
    for entry in entity_entries:
        name = entry["name"]
        old = old_entities.get(name)
        if old is not None and name not in reseed_entities:
            entry["rows"] = old["rows"]
            report["preserved"].append(f"entity {name}")
        else:
            report["seeded"].append(f"entity {name}"
                                    + ("" if old is not None else " (new)"))
    # An entity the build no longer declares is dead weight in the editor.
    live = {entry["name"] for entry in entity_entries}
    report["dropped"] = [f"entity {name}" for name in sorted(old_entities)
                         if name not in live]

    if not reseed_palette:
        palette = existing.get("palette", palette)
    else:
        report["seeded"].append("palette")

    return {
        "version": 1,
        "projectType": "fujirealm-lynx-tiles",
        "tileWidth": 8,
        "tileHeight": 8,
        "palette": palette,
        "tiles": tile_entries,
        "players": player_entries,
        "entities": entity_entries,
    }


def summarize(report):
    def line(label, items):
        if not items:
            return
        shown = ", ".join(items[:12])
        more = f" (+{len(items) - 12} more)" if len(items) > 12 else ""
        print(f"{label}: {shown}{more}")

    line("seeded", report["seeded"])
    line("preserved", report["preserved"])
    line("dropped", report["dropped"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing tileset, discarding edits")
    parser.add_argument("--merge", action="store_true",
                        help="keep existing slots, add whatever is missing")
    parser.add_argument("--reseed-tiles", default="",
                        help="tile indices to re-convert, e.g. 9,37-39,44-51")
    parser.add_argument("--reseed-entities", default="",
                        help="entity sprite names to re-convert")
    parser.add_argument("--reseed-players", action="store_true")
    parser.add_argument("--reseed-palette", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    parser.add_argument("--out", type=Path, default=conv.TILESET)
    args = parser.parse_args()

    reseed_tiles = parse_index_list(args.reseed_tiles, conv.TILE_COUNT)
    reseed_entities = parse_name_list(args.reseed_entities)
    known = {name for name, _, _ in conv.ENTITY_SPRITES}
    unknown = sorted(reseed_entities - known)
    if unknown:
        raise SystemExit(f"unknown entity sprite(s): {', '.join(unknown)}")

    merging = args.merge or reseed_tiles or reseed_entities or \
        args.reseed_players or args.reseed_palette
    existing = None
    if args.out.exists():
        if args.force:
            pass
        elif merging:
            existing = json.loads(args.out.read_text(encoding="utf-8"))
        else:
            print(f"{args.out} already exists; re-seeding would discard "
                  f"hand-drawn art. Pass --merge to add only what is missing, "
                  f"or --force to overwrite everything.", file=sys.stderr)
            return 1

    report = {}
    data = build_tileset(existing, reseed_tiles, reseed_entities,
                         args.reseed_players, args.reseed_palette, report)
    summarize(report)
    if args.dry_run:
        print("dry run: nothing written")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
