"""Phase 62: CSV bridge, story-marker, and enemy-species round-trip tests."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tools import export_map_csv
from tools.import_map_csv import (
    ENEMY_BAT,
    ENEMY_SLIME,
    ENEMY_SNAKE,
    ROAD,
    WORLD_H,
    WORLD_W,
    format_bridge_tiles,
    parse_map,
    OVERWORLD_TERRAIN_CODES,
    GRASS,
    MAP_OVERWORLD,
)


def _write_overworld_csv(path: Path, cells: dict[tuple[int, int], str]) -> None:
    """Write a WORLD_W x WORLD_H overworld CSV with the given interior cells."""
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["y\\x"] + [str(x) for x in range(WORLD_W)])
        for y in range(WORLD_H):
            row = [str(y)]
            for x in range(WORLD_W):
                row.append(cells.get((x, y), ""))
            writer.writerow(row)


# Required unique markers placed at safe interior coordinates.
_REQUIRED = {(10, 10): "DAN", (12, 10): "GRX", (14, 10): "X", (16, 10): "C", (18, 10): "P"}


class BridgeMarkerTest(unittest.TestCase):
    def test_legacy_f_and_n_alias_to_daniel_and_grix(self):
        cells = {(10, 10): "F", (12, 10): "N", (14, 10): "X", (16, 10): "C", (18, 10): "P"}
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "overworld.csv"
            _write_overworld_csv(csv_path, cells)
            _, _, markers, _ = parse_map(
                csv_path, OVERWORLD_TERRAIN_CODES, GRASS, GRASS, MAP_OVERWORLD
            )
        self.assertEqual(markers["DAN"], (10, 10))
        self.assertEqual(markers["GRX"], (12, 10))

    def test_story_markers_round_trip_as_entity_markers(self):
        cells = dict(_REQUIRED)
        cells[(20, 10)] = "NER"
        cells[(22, 10)] = "WIL"
        cells[(24, 10)] = "LUC"
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "overworld.csv"
            _write_overworld_csv(csv_path, cells)
            tiles, _, markers, _ = parse_map(
                csv_path, OVERWORLD_TERRAIN_CODES, GRASS, GRASS, MAP_OVERWORLD
            )
        self.assertEqual(markers["NER"], (20, 10))
        self.assertEqual(markers["WIL"], (22, 10))
        self.assertEqual(markers["LUC"], (24, 10))
        self.assertEqual(tiles[10 * WORLD_W + 20], GRASS)

    def test_bridge_marker_imports_as_road_plus_coords(self):
        cells = dict(_REQUIRED)
        bridge = [(40, 30), (41, 30), (42, 30)]
        for coord in bridge:
            cells[coord] = "="
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "overworld.csv"
            _write_overworld_csv(csv_path, cells)
            tiles, enemies, markers, bridge_tiles = parse_map(
                csv_path, OVERWORLD_TERRAIN_CODES, GRASS, GRASS, MAP_OVERWORLD
            )
        self.assertEqual(bridge_tiles, bridge)
        for x, y in bridge:
            self.assertEqual(tiles[y * WORLD_W + x], ROAD)  # base terrain is road

    def test_bridge_marker_may_repeat_and_is_not_a_unique_marker(self):
        cells = dict(_REQUIRED)
        cells[(40, 30)] = "="
        cells[(40, 31)] = "="  # a second "=" must NOT raise a duplicate error
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "overworld.csv"
            _write_overworld_csv(csv_path, cells)
            _, _, markers, bridge_tiles = parse_map(
                csv_path, OVERWORLD_TERRAIN_CODES, GRASS, GRASS, MAP_OVERWORLD
            )
        self.assertNotIn("=", markers)
        self.assertEqual(len(bridge_tiles), 2)

    def test_enemy_species_markers_map_to_ids(self):
        cells = dict(_REQUIRED)
        cells[(40, 30)] = "S"  # snake
        cells[(41, 30)] = "M"  # slime
        cells[(42, 30)] = "B"  # bat
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "overworld.csv"
            _write_overworld_csv(csv_path, cells)
            _, enemies, _, _ = parse_map(
                csv_path, OVERWORLD_TERRAIN_CODES, GRASS, GRASS, MAP_OVERWORLD
            )
        kinds = {(x, y): kind for x, y, kind in enemies}
        self.assertEqual(kinds[(40, 30)], ENEMY_SNAKE)
        self.assertEqual(kinds[(41, 30)], ENEMY_SLIME)
        self.assertEqual(kinds[(42, 30)], ENEMY_BAT)

    def test_format_bridge_tiles_output(self):
        self.assertEqual(format_bridge_tiles([]), "OVERWORLD_BRIDGE_TILES = ()")
        text = format_bridge_tiles([(1, 2), (3, 4)])
        self.assertIn("(1, 2),", text)
        self.assertIn("(3, 4),", text)

    def test_exporter_marks_bridge_coords(self):
        # The exporter overlay must re-emit "=" for every bridge coordinate so
        # the marker survives an export/import round trip.
        original = export_map_csv.OVERWORLD_BRIDGE_TILES
        export_map_csv.OVERWORLD_BRIDGE_TILES = ((40, 30), (41, 30))
        try:
            overlay = export_map_csv.entity_overlay(MAP_OVERWORLD)
        finally:
            export_map_csv.OVERWORLD_BRIDGE_TILES = original
        self.assertEqual(overlay[(40, 30)], "=")
        self.assertEqual(overlay[(41, 30)], "=")


if __name__ == "__main__":
    unittest.main()
