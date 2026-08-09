"""Phase 56: persistent main-story state, normalization, and the test-player tool."""

import subprocess
import sys
import unittest
from pathlib import Path

from server.game import (
    GameState,
    PlayerState,
    deserialize_player_state,
    serialize_player_state,
)
from server.login_server import SessionStore
from server.quests import (
    QUEST_LIVING_MUD,
    QUEST_NONE,
    QUEST_STATE_COMPLETE,
    QUEST_STATE_NOT_STARTED,
    STORY_STAGE_BRIDGE,
    STORY_STAGE_COMPLETE,
    STORY_STAGE_GORVAK,
    STORY_STAGE_NONE,
    STORY_STAGE_RETURN_NERISSA,
    STORY_STAGE_WARDEN_KEY,
)

V6_DIR = Path(__file__).resolve().parents[2]
TOOL = V6_DIR / "tools" / "manage_test_player.py"

STORY_FIELDS = (
    "story_stage",
    "story_step",
    "bridge_materials_staged",
    "bridge_repaired",
    "grix_callout_seen",
    "warden_key_collected",
    "gorvak_defeated",
    "deep_pump_shutdown",
    "pvp_unlocked",
)


class StoryStatePersistenceTest(unittest.TestCase):
    def test_all_story_fields_survive_round_trip(self):
        p = PlayerState(token=1, username="Hero")
        p.story_stage = STORY_STAGE_GORVAK
        p.story_step = 2
        p.bridge_materials_staged = True
        p.bridge_repaired = True
        p.grix_callout_seen = True
        p.warden_key_collected = True
        p.gorvak_defeated = True
        payload = serialize_player_state(p)
        for field in STORY_FIELDS:
            self.assertIn(field, payload)
        restored = deserialize_player_state(1, "Hero", payload)
        for field in STORY_FIELDS:
            self.assertEqual(getattr(restored, field), getattr(p, field), field)

    def test_old_save_defaults_every_story_field(self):
        # An old save has none of the new keys; they must default, not raise.
        legacy = {"level": 4, "class_id": 1, "active_quest_id": 0, "map_id": 0}
        restored = deserialize_player_state(2, "Legacy", legacy)
        self.assertEqual(restored.story_stage, STORY_STAGE_NONE)
        self.assertEqual(restored.story_step, 0)
        self.assertFalse(restored.bridge_repaired)
        self.assertFalse(restored.warden_key_collected)
        self.assertFalse(restored.gorvak_defeated)
        self.assertFalse(restored.deep_pump_shutdown)
        self.assertFalse(restored.pvp_unlocked)

    def test_invalid_stage_falls_back_to_none(self):
        restored = deserialize_player_state(3, "Bad", {"story_stage": 999})
        self.assertEqual(restored.story_stage, STORY_STAGE_NONE)

    def test_stale_living_mud_done_is_cleared_on_load_past_that_point(self):
        # A save from well past Living Mud (e.g. the whole chain finished)
        # that still carries the old QUEST_LIVING_MUD/COMPLETE pair must not
        # resurface "Living Mud done" as the HUD quest line forever -- there
        # is no later quest id to ever overwrite it.
        payload = {
            "story_stage": STORY_STAGE_COMPLETE,
            "active_quest_id": QUEST_LIVING_MUD,
            "quest_state": QUEST_STATE_COMPLETE,
            "quest_progress": 4,
            "quest_target": 4,
        }
        restored = deserialize_player_state(5, "Done", payload)
        self.assertEqual(restored.active_quest_id, QUEST_NONE)
        self.assertEqual(restored.quest_state, QUEST_STATE_NOT_STARTED)
        self.assertEqual(restored.quest_progress, 0)
        self.assertEqual(restored.quest_target, 0)

    def test_living_mud_in_progress_survives_load_untouched(self):
        # The clear only applies once the story has actually moved past
        # Living Mud -- an in-progress or just-completed-this-stage save
        # must round-trip normally.
        payload = {
            "story_stage": STORY_STAGE_BRIDGE,
            "active_quest_id": QUEST_LIVING_MUD,
            "quest_state": QUEST_STATE_COMPLETE,
            "quest_progress": 4,
            "quest_target": 4,
        }
        restored = deserialize_player_state(6, "StillMuddy", payload)
        self.assertEqual(restored.active_quest_id, QUEST_LIVING_MUD)
        self.assertEqual(restored.quest_state, QUEST_STATE_COMPLETE)

    def test_transient_encounter_state_is_not_persisted(self):
        # Only stable fields belong in the save; nothing volatile leaks through.
        p = PlayerState(token=4, username="Temp")
        p.activity_messages.append("Keep them off me!")
        p.pending_messages.append((1, "hi"))
        payload = serialize_player_state(p)
        for volatile in (
            "activity_messages",
            "pending_messages",
            "pending_map_change",
            "latest_respawn_event",
            "transition_loading",
            "shot_counter",
            "respawn_counter",
        ):
            self.assertNotIn(volatile, payload)


class StoryNormalizationTest(unittest.TestCase):
    def setUp(self):
        self.game = GameState()

    def test_pvp_unlocked_backfills_full_chain(self):
        p = PlayerState(token=1, username="Champ")
        p.pvp_unlocked = True
        p.story_stage = STORY_STAGE_NONE  # contradictory
        self.game._normalize_story_state(p)
        self.assertTrue(p.deep_pump_shutdown)
        self.assertTrue(p.gorvak_defeated)
        self.assertTrue(p.warden_key_collected)
        self.assertEqual(p.story_stage, STORY_STAGE_COMPLETE)

    def test_pump_shutdown_implies_prereqs_and_stage_floor(self):
        p = PlayerState(token=2, username="Plumber")
        p.deep_pump_shutdown = True
        p.story_stage = STORY_STAGE_NONE
        self.game._normalize_story_state(p)
        self.assertTrue(p.gorvak_defeated)
        self.assertTrue(p.warden_key_collected)
        self.assertGreaterEqual(p.story_stage, STORY_STAGE_RETURN_NERISSA)

    def test_warden_key_raises_stage_floor(self):
        p = PlayerState(token=3, username="Finder")
        p.warden_key_collected = True
        p.story_stage = STORY_STAGE_NONE
        self.game._normalize_story_state(p)
        self.assertGreaterEqual(p.story_stage, STORY_STAGE_WARDEN_KEY)

    def test_normalizer_never_lowers_stage(self):
        p = PlayerState(token=4, username="Ahead")
        p.story_stage = STORY_STAGE_COMPLETE
        p.warden_key_collected = True  # floor is only WARDEN_KEY
        self.game._normalize_story_state(p)
        self.assertEqual(p.story_stage, STORY_STAGE_COMPLETE)

    def test_interrupted_bridge_encounter_rewinds_step(self):
        p = PlayerState(token=5, username="Escort")
        p.story_stage = STORY_STAGE_BRIDGE
        p.bridge_repaired = False
        p.story_step = 7  # mid-defense; transient, must reset
        self.game._normalize_story_state(p)
        self.assertEqual(p.story_step, 0)

    def test_interrupted_gorvak_encounter_rewinds_step(self):
        p = PlayerState(token=6, username="Boss")
        p.story_stage = STORY_STAGE_GORVAK
        p.gorvak_defeated = False
        p.story_step = 3
        self.game._normalize_story_state(p)
        self.assertEqual(p.story_step, 0)


class TestPlayerToolTest(unittest.TestCase):
    """The manage_test_player CLI writes saves that load through normal code."""

    def _run(self, store, *args):
        result = subprocess.run(
            [sys.executable, str(TOOL), "--store", str(store), *args],
            cwd=str(V6_DIR),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_create_edit_and_login_restore(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "sessions.json"
            self._run(
                store, "create", "--username", "GORVAKTEST", "--token", "424242",
                "--level", "5", "--stage", "gorvak", "--warden-key",
                "--gorvak-defeated", "--anchor", "cave", "--set-item", "sticks:3",
            )
            # Force an impossible combo, confirm the tool normalizes on write.
            self._run(store, "set", "--token", "424242", "--pvp-unlocked", "--stage", "none")

            # Load the tool-written store exactly as the live server would.
            session = SessionStore(str(store))
            game = GameState(player_state_loader=lambda t: session.get_record(str(t)))
            player = game.ensure_player(424242)
            self.assertEqual(player.level, 5)
            self.assertEqual(player.story_stage, STORY_STAGE_COMPLETE)
            self.assertTrue(player.pvp_unlocked)
            self.assertTrue(player.gorvak_defeated)
            self.assertTrue(player.warden_key_collected)
            self.assertTrue(player.deep_pump_shutdown)

    def test_reset_returns_clean_new_game_state(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "sessions.json"
            self._run(store, "create", "--username", "DIRTY", "--token", "555001", "--stage", "gorvak", "--warden-key")
            self._run(store, "reset", "--token", "555001")
            session = SessionStore(str(store))
            game = GameState(player_state_loader=lambda t: session.get_record(str(t)))
            player = game.ensure_player(555001)
            self.assertEqual(player.story_stage, STORY_STAGE_NONE)
            self.assertFalse(player.warden_key_collected)
            self.assertEqual(player.inventory.as_tuple(), ())


if __name__ == "__main__":
    unittest.main()
