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
    PROJECT_TYPE,
    CharsetterError,
    build_project,
    extract_source_art,
    generate_include,
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


if __name__ == "__main__":
    unittest.main()
