from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.charsetter import (
    ANIMATION_SPECS,
    DEFINITION_SPECS,
    FONT_BYTES,
    PM_LOCAL_FRAMES,
    PM_MISSILE_H,
    PM_PLAYER_H,
    PM_TILE_ROWS,
    PROJECT_TYPE,
    CharsetterError,
    build_project,
    extract_source_art,
    generate_include,
    generate_pm_include,
    pm_frames_from_sprites,
    pm_missile_from_tiles,
    validate_project,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "atari8-client" / "fujirealm.asm"
PROJECT = REPO_ROOT / "atari8-client" / "art" / "fujirealm_charsetter.json"


class CharsetterV6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.font, cls.tiles, cls.sprites, cls.palette = extract_source_art(SOURCE)

    def fresh_project(self) -> dict:
        return build_project(self.font, self.tiles, self.sprites, self.palette)

    def test_generated_project_matches_effective_source_art(self) -> None:
        tracked = json.loads(PROJECT.read_text(encoding="utf-8"))
        font, tiles, sprites = validate_project(tracked)
        self.assertEqual(font, self.font)
        self.assertEqual(tiles, self.tiles)
        self.assertEqual(sprites, self.sprites)
        self.assertEqual(tracked["projectType"], PROJECT_TYPE)
        self.assertEqual(tracked["logicalTileCount"], 52)
        self.assertEqual(len(tracked["fontData"]), FONT_BYTES)
        self.assertNotIn("mapData", tracked)
        self.assertTrue(any(value & 0x80 for table in tiles for value in table))

    def test_library_contains_only_rendered_2x2_art(self) -> None:
        project = self.fresh_project()
        visible = [definition for definition in project["tileDefinitions"] if definition["visible"]]
        names = {definition["name"] for definition in visible}
        expected = {
            "Grass",
            "Herb",
            "Beaver",
            "Hostile Goblin",
            "Grix",
            "Local Player Front 0",
            "Remote Player Front 0",
            "Town NPC (Generic)",
            "Warden Key",
            "Daniel",
            "Wilhelm",
            "Wilhelm Working",
            "Lucian",
            "Nerissa",
            "Snake",
            "Slime 0",
            "Slime 1",
            "Bat 0",
            "Bat 1",
            "Gorvak",
            "Deep Pump",
            "Pump Controls",
        }
        self.assertTrue(expected <= names)
        self.assertEqual(len(project["tileDefinitions"]), len(DEFINITION_SPECS))
        self.assertEqual(len(visible), 47)
        self.assertFalse(next(item for item in project["tileDefinitions"] if item["name"] == "HUD Digit 2")["visible"])

    def test_animation_groups_are_complete_and_locked(self) -> None:
        project = self.fresh_project()
        self.assertEqual(project["animations"], list(ANIMATION_SPECS))
        self.assertEqual(len(project["animations"]), 9)
        self.assertTrue(all(len(animation["frameIds"]) == 2 for animation in project["animations"]))
        slime_0 = next(item for item in project["tileDefinitions"] if item["name"] == "Slime 0")
        slime_1 = next(item for item in project["tileDefinitions"] if item["name"] == "Slime 1")
        self.assertNotEqual(slime_0["characters"][:2], slime_1["characters"][:2])
        self.assertEqual(slime_0["characters"][2:], slime_1["characters"][2:])

    def test_all_128_glyphs_have_one_intentional_runtime_owner(self) -> None:
        project = self.fresh_project()
        definitions = {
            definition["name"]: definition
            for definition in project["tileDefinitions"]
        }
        owners: dict[str, set[int]] = {}
        for definition in project["tileDefinitions"]:
            if (
                definition["targetType"] != "logicalTile"
                or not definition["visible"]
                or definition["name"] in {
                    "Slime 0", "Slime 1", "Bat 0", "Bat 1",
                    "Wilhelm", "Wilhelm Working",
                }
            ):
                continue
            characters = (
                definition["characters"][:2]
                if definition["name"] == "Bullet"
                else definition["characters"]
            )
            owners[definition["name"]] = {character & 0x7F for character in characters}

        owners["Slime"] = {
            character & 0x7F
            for name in ("Slime 0", "Slime 1")
            for character in definitions[name]["characters"]
        }
        owners["Bat"] = {
            character & 0x7F
            for name in ("Bat 0", "Bat 1")
            for character in definitions[name]["characters"]
        }
        owners["Wilhelm"] = {
            character & 0x7F
            for name in ("Wilhelm", "Wilhelm Working")
            for character in definitions[name]["characters"]
        }
        owners["HUD separator blank"] = {33}
        owner_names = list(owners)
        for index, first in enumerate(owner_names):
            for second in owner_names[index + 1 :]:
                self.assertFalse(
                    owners[first] & owners[second],
                    f"{first} and {second} share {sorted(owners[first] & owners[second])}",
                )

        local_player = {
            character & 0x7F
            for definition in project["tileDefinitions"]
            if definition["targetType"] == "playerSprite" and definition["targetIndex"] < 6
            for character in definition["characters"]
        }
        remote_player = {
            character & 0x7F
            for definition in project["tileDefinitions"]
            if definition["targetType"] == "playerSprite" and definition["targetIndex"] >= 6
            for character in definition["characters"]
        }
        self.assertEqual(remote_player, local_player)
        self.assertFalse(local_player & set().union(*owners.values()))
        self.assertEqual(set().union(*owners.values(), local_player), set(range(128)))
        self.assertEqual(len(owners["Bat"]), 8)
        self.assertEqual(len(owners["Slime"]), 6)
        self.assertEqual(len(owners["Gorvak"]), 4)
        for name in (
            "Snake",
            "Hostile Goblin",
            "Town NPC (Generic)",
            "Grix",
            "Daniel",
            "Lucian",
            "Nerissa",
            "Deep Pump",
        ):
            self.assertEqual(len(owners[name]), 4, name)
        self.assertEqual(len(owners["Pump Controls"]), 2)
        self.assertEqual(len(owners["Wilhelm"]), 6)

    def test_phase_61_projectile_uses_only_upper_character_cells(self) -> None:
        project = self.fresh_project()
        bullet = next(item for item in project["tileDefinitions"] if item["name"] == "Bullet")
        self.assertEqual(bullet["characters"][:2], [0x4E, 0x4F])
        self.assertEqual(bullet["characters"][2:], [0, 0])

        source = SOURCE.read_text(encoding="utf-8")
        draw = source.split("\ndraw_bullet_top_at_target\n", 1)[1].split(
            "\nrestore_target_top_cell\n", 1
        )[0]
        restore = source.split("\nrestore_target_top_cell\n", 1)[1].split(
            "\ninventory_modal_lines\n", 1
        )[0]
        self.assertIn("tile2x2_tl,x", draw)
        self.assertIn("tile2x2_tr,x", draw)
        self.assertNotIn("tile2x2_bl", draw)
        self.assertNotIn("tile2x2_br", draw)
        self.assertIn("tile2x2_tl,x", restore)
        self.assertIn("tile2x2_tr,x", restore)
        self.assertNotIn("tile2x2_bl", restore)
        self.assertNotIn("tile2x2_br", restore)

    def test_phase_61_removed_beaver_hurt_and_masks_hit_bit_locally(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("BEAVER_HURT", source)
        self.assertIn("and #ENEMY_KIND_MASK", source)
        self.assertIn("sta enemy_hit_timer,x", source)
        self.assertIn("dec enemy_hit_timer,x", source)

    def test_font_binary_override_round_trips(self) -> None:
        project = self.fresh_project()
        font_override = bytearray(project["fontData"])
        font_override[123] ^= 0xFF
        font, tiles, sprites = validate_project(project, font_override=bytes(font_override))
        self.assertEqual(font[123], font_override[123])
        self.assertEqual(tiles, self.tiles)
        self.assertEqual(sprites, self.sprites)

    def test_edited_glyph_and_composition_reach_generated_include(self) -> None:
        project = self.fresh_project()
        project["fontData"][0] = 0xA5
        grass = next(item for item in project["tileDefinitions"] if item["name"] == "Grass")
        grass["characters"] = [0x81, 0x02, 0x83, 0x04]
        font, tiles, sprites = validate_project(project)
        include = generate_include(font, tiles, sprites, Path("edited.json"))
        self.assertEqual([table[0] for table in tiles], grass["characters"])
        self.assertIn("dta $A5", include)
        self.assertIn("tile2x2_tl_overworld", include)
        self.assertIn("player_sprite_br", include)

    def test_modified_runtime_bindings_are_rejected(self) -> None:
        renamed = self.fresh_project()
        renamed["tileDefinitions"][0]["name"] = "Lawn"
        with self.assertRaisesRegex(CharsetterError, "locked field 'name'"):
            validate_project(renamed)

        rebound = self.fresh_project()
        rebound["tileDefinitions"][0]["targetIndex"] = 1
        with self.assertRaisesRegex(CharsetterError, "locked field 'targetIndex'"):
            validate_project(rebound)

        animations = self.fresh_project()
        animations["animations"][0]["frameIds"].reverse()
        with self.assertRaisesRegex(CharsetterError, "animation definitions"):
            validate_project(animations)

    def test_duplicate_missing_and_malformed_definitions_are_rejected(self) -> None:
        duplicate = self.fresh_project()
        duplicate["tileDefinitions"].append(copy.deepcopy(duplicate["tileDefinitions"][0]))
        with self.assertRaisesRegex(CharsetterError, "duplicate tile definition id"):
            validate_project(duplicate)

        missing = self.fresh_project()
        missing["tileDefinitions"].pop()
        with self.assertRaisesRegex(CharsetterError, "tile definition set is invalid"):
            validate_project(missing)

        bad_font = self.fresh_project()
        bad_font["fontData"].pop()
        with self.assertRaisesRegex(CharsetterError, "exactly 1024"):
            validate_project(bad_font)

    def test_generated_include_can_be_written_as_ascii(self) -> None:
        font, tiles, sprites = validate_project(self.fresh_project())
        include = generate_include(font, tiles, sprites, Path("fujirealm.json"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "art.inc"
            output.write_text(include, encoding="ascii")
            self.assertGreater(output.stat().st_size, 7000)


class PlayerMissileArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.font, cls.tiles, cls.sprites, cls.palette = extract_source_art(SOURCE)

    def test_derived_frames_have_the_expected_shape(self) -> None:
        plane0, plane1 = pm_frames_from_sprites(self.font, self.sprites)
        self.assertEqual(len(plane0), PM_LOCAL_FRAMES * PM_PLAYER_H)
        self.assertEqual(len(plane1), PM_LOCAL_FRAMES * PM_PLAYER_H)
        self.assertTrue(all(0 <= byte <= 255 for byte in plane0 + plane1))

    def test_overhang_rows_are_blank_and_the_tile_rows_are_not(self) -> None:
        plane0, plane1 = pm_frames_from_sprites(self.font, self.sprites)
        overhang = PM_PLAYER_H - PM_TILE_ROWS
        for frame in range(PM_LOCAL_FRAMES):
            base = frame * PM_PLAYER_H
            self.assertEqual(plane0[base : base + overhang], [0] * overhang)
            self.assertEqual(plane1[base : base + overhang], [0] * overhang)
            body = plane0[base + overhang : base + PM_PLAYER_H]
            body += plane1[base + overhang : base + PM_PLAYER_H]
            self.assertTrue(any(body), f"frame {frame} converted to an empty sprite")

    def test_pixel_pairs_split_across_the_two_planes(self) -> None:
        # An ANTIC 4 pixel value of 3 has to light both planes, which is what
        # GTIA shows as COLPM0 OR COLPM1; 1 and 2 light exactly one each.
        font = [0] * FONT_BYTES
        sprites = [[glyph] * 12 for glyph in (1, 2, 3, 4)]
        font[1 * 8] = 0b01_10_11_00
        plane0, plane1 = pm_frames_from_sprites(font, sprites)
        row = PM_PLAYER_H - PM_TILE_ROWS
        # Pixels left to right are 1, 2, 3, 0 from the top-left character and
        # four transparent ones from the (blank) top-right character.
        self.assertEqual(plane0[row], 0b1010_0000)
        self.assertEqual(plane1[row], 0b0110_0000)

    def test_authored_frames_take_precedence_over_the_derived_ones(self) -> None:
        authored = [
            {"p0": [0xFF] * PM_PLAYER_H, "p1": [0x00] * PM_PLAYER_H}
            for _ in range(PM_LOCAL_FRAMES)
        ]
        include = generate_pm_include(self.font, self.tiles, self.sprites, Path("p.json"), authored)
        self.assertIn("authored in the tile editor", include)
        self.assertIn("$FF", include)
        derived = generate_pm_include(self.font, self.tiles, self.sprites, Path("p.json"))
        self.assertIn("derived from its 2x2 character frames", derived)
        self.assertNotEqual(include, derived)

    def test_malformed_authored_frames_are_rejected(self) -> None:
        short = [{"p0": [0] * PM_PLAYER_H, "p1": [0] * PM_PLAYER_H}] * (PM_LOCAL_FRAMES - 1)
        with self.assertRaisesRegex(CharsetterError, "pmSprites must contain"):
            generate_pm_include(self.font, self.tiles, self.sprites, Path("p.json"), short)

        bad_rows = [
            {"p0": [0] * PM_PLAYER_H, "p1": [0] * (PM_PLAYER_H - 1)}
            for _ in range(PM_LOCAL_FRAMES)
        ]
        with self.assertRaisesRegex(CharsetterError, r"pmSprites\[0\].p1 must contain"):
            generate_pm_include(self.font, self.tiles, self.sprites, Path("p.json"), bad_rows)

        bad_byte = [
            {"p0": [0] * PM_PLAYER_H, "p1": [0] * PM_PLAYER_H}
            for _ in range(PM_LOCAL_FRAMES)
        ]
        bad_byte[2]["p0"][5] = 256
        with self.assertRaisesRegex(CharsetterError, r"pmSprites\[2\].p0\[5\] must be a byte"):
            generate_pm_include(self.font, self.tiles, self.sprites, Path("p.json"), bad_byte)

    def test_missile_downsamples_the_bullet_glyph(self) -> None:
        rows = pm_missile_from_tiles(self.font, self.tiles)
        self.assertEqual(len(rows), PM_MISSILE_H)
        self.assertTrue(all(0 <= value <= 3 for value in rows))
        # The bullet glyph is a small diamond in the bottom rows of its top
        # cell, so the top rows must stay empty and the bottom ones must not.
        self.assertEqual(rows[:5], [0] * 5)
        self.assertTrue(all(rows[5:]))

    def test_missile_halves_map_to_the_two_pixels(self) -> None:
        font = [0] * FONT_BYTES
        tiles = [[glyph] * 52 for glyph in (1, 2, 3, 4)]
        font[1 * 8 + 0] = 0b00_00_00_11  # left character lit -> left pixel
        font[2 * 8 + 1] = 0b11_00_00_00  # right character lit -> right pixel
        rows = pm_missile_from_tiles(font, tiles)
        self.assertEqual(rows[0], 2)
        self.assertEqual(rows[1], 1)
        self.assertEqual(rows[2], 0)

    def test_authored_missile_takes_precedence_and_is_validated(self) -> None:
        authored = [1, 2, 3, 0, 1, 2, 3, 0]
        include = generate_pm_include(
            self.font, self.tiles, self.sprites, Path("p.json"), None, authored
        )
        self.assertIn("authored in the tile editor", include)
        self.assertIn("pm_bullet_data", include)
        self.assertIn("downsampled from the BULLET tile", generate_pm_include(
            self.font, self.tiles, self.sprites, Path("p.json")
        ))

        with self.assertRaisesRegex(CharsetterError, "pmMissile must contain"):
            generate_pm_include(
                self.font, self.tiles, self.sprites, Path("p.json"), None, [0, 0]
            )
        with self.assertRaisesRegex(CharsetterError, r"pmMissile\[3\] must be 0-3"):
            generate_pm_include(
                self.font, self.tiles, self.sprites, Path("p.json"), None, [0, 0, 0, 4, 0, 0, 0, 0]
            )

    def test_include_is_ascii_writable(self) -> None:
        include = generate_pm_include(self.font, self.tiles, self.sprites, Path("p.json"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pm.inc"
            output.write_text(include, encoding="ascii")
            self.assertIn("pm_player_p0_data", output.read_text(encoding="ascii"))
            self.assertIn("pm_player_p1_data", output.read_text(encoding="ascii"))


if __name__ == "__main__":
    unittest.main()
