"""Tests for the old-version session reset (tools/reset_old_sessions.py).

The reset wipes a save written by an older generation of the game back to a
clean level-1 new game, keeping the token, username, gold and pvp_kills, and
leaves records already stamped with the current schema version alone.
"""

import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path

from server.game import (
    MAP_OVERWORLD,
    OVERWORLD_START,
    GameState,
    PlayerState,
    deserialize_player_state,
    player_state_is_current,
    serialize_player_state,
)
from server.hybrid_server import FujiRealmHybridServer, ClientSession
from server.items import ITEM_POTION
from server.login_server import SessionStore
from server.protocol import Hello, encode_hello
from server.quests import (
    MSG_WELCOME_BACK,
    MSG_WELCOME_NEW,
    QUEST_NONE,
    QUEST_STATE_NOT_STARTED,
    STORY_STAGE_RETURN_NERISSA,
    STORY_STAGE_NONE,
)
from server.schema import PLAYER_SCHEMA_VERSION

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from reset_old_sessions import main as reset_main  # noqa: E402

TOKEN_OLD = "1111111111"
TOKEN_NEW = "2222222222"
TOKEN_BARE = "3333333333"


def legacy_state() -> dict:
    """A well-advanced save, stripped of its version stamp like a real old one."""
    player = PlayerState(int(TOKEN_OLD), "OLDPLAYER")
    player.level = 7
    player.xp = 400
    player.gold = 250
    player.pvp_kills = 9
    player.story_stage = STORY_STAGE_RETURN_NERISSA
    player.story_step = 3
    player.bridge_materials_staged = True
    player.bridge_repaired = True
    player.grix_callout_seen = True
    player.warden_key_collected = True
    player.gorvak_defeated = True
    player.pvp_unlocked = True
    player.inventory.add_item(ITEM_POTION, 4)
    payload = serialize_player_state(player)
    del payload["schema_version"]
    return payload


class SessionResetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sessions.json"
        store = SessionStore(self.path)
        store.sessions[TOKEN_OLD] = {"username": "OLDPLAYER", "player_state": legacy_state()}
        store.sessions[TOKEN_NEW] = {
            "username": "NEWPLAYER",
            "player_state": serialize_player_state(PlayerState(int(TOKEN_NEW), "NEWPLAYER")),
        }
        store.sessions[TOKEN_BARE] = {"username": "NEVERPLAYED"}
        store.save()

    def _run(self, *extra):
        return reset_main(["--store", str(self.path), "--no-backup", *extra])

    def _state(self, token):
        return SessionStore(self.path).load_player_state(token)

    def test_serialized_state_is_stamped_current(self):
        payload = serialize_player_state(PlayerState(1, "X"))
        self.assertEqual(payload["schema_version"], PLAYER_SCHEMA_VERSION)
        self.assertTrue(player_state_is_current(payload))
        self.assertFalse(player_state_is_current(legacy_state()))
        # An unstamped payload must still load without complaint.
        self.assertEqual(deserialize_player_state(1, "X", legacy_state()).level, 7)

    def test_dry_run_writes_nothing(self):
        before = self.path.read_text(encoding="ascii")
        self.assertEqual(self._run(), 0)
        self.assertEqual(self.path.read_text(encoding="ascii"), before)

    def test_stale_record_resets_but_keeps_identity_gold_and_kills(self):
        self.assertEqual(self._run("--apply"), 0)
        record = SessionStore(self.path).get_record(TOKEN_OLD)
        self.assertEqual(record["username"], "OLDPLAYER")

        state = record["player_state"]
        self.assertEqual(state["gold"], 250)
        self.assertEqual(state["pvp_kills"], 9)
        self.assertTrue(player_state_is_current(state))
        self.assertTrue(state["fresh_start"])

        self.assertEqual(state["level"], 1)
        self.assertEqual(state["xp"], 0)
        self.assertEqual(state["inventory"], [])
        self.assertEqual(state["active_quest_id"], QUEST_NONE)
        self.assertEqual(state["quest_state"], QUEST_STATE_NOT_STARTED)
        self.assertEqual(state["story_stage"], STORY_STAGE_NONE)
        self.assertEqual(state["story_step"], 0)
        for flag in (
            "bridge_materials_staged",
            "bridge_repaired",
            "grix_callout_seen",
            "warden_key_collected",
            "gorvak_defeated",
            "deep_pump_shutdown",
            "pvp_unlocked",
        ):
            self.assertFalse(state[flag], flag)
        self.assertEqual((state["map_id"], state["x"], state["y"]), (MAP_OVERWORLD, *OVERWORLD_START))

    def test_current_record_is_untouched(self):
        before = self._state(TOKEN_NEW)
        self.assertEqual(self._run("--apply"), 0)
        self.assertEqual(self._state(TOKEN_NEW), before)

    def test_record_without_player_state_is_untouched(self):
        self.assertEqual(self._run("--apply"), 0)
        record = SessionStore(self.path).get_record(TOKEN_BARE)
        self.assertEqual(record, {"username": "NEVERPLAYED"})

    def test_rerun_is_a_no_op(self):
        self.assertEqual(self._run("--apply"), 0)
        after_first = self.path.read_text(encoding="ascii")
        self.assertEqual(self._run("--apply"), 0)
        self.assertEqual(self.path.read_text(encoding="ascii"), after_first)

    def test_missing_store_exits_nonzero(self):
        self.assertEqual(reset_main(["--store", str(self.path.with_name("nope.json"))]), 2)

    def test_backup_is_written_before_applying(self):
        self.assertEqual(reset_main(["--store", str(self.path), "--apply"]), 0)
        backups = list(self.path.parent.glob("sessions.json.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("OLDPLAYER", backups[0].read_text(encoding="ascii"))

    def test_carried_fields_survive_garbage_values(self):
        store = SessionStore(self.path)
        state = store.load_player_state(TOKEN_OLD)
        state["gold"] = "lots"
        state["pvp_kills"] = None
        store.sessions[TOKEN_OLD]["player_state"] = state
        store.save()
        self.assertEqual(self._run("--apply"), 0)
        reset = self._state(TOKEN_OLD)
        self.assertEqual(reset["gold"], 0)
        self.assertEqual(reset["pvp_kills"], 0)


class ResetGreetingTest(unittest.TestCase):
    """A reset player is greeted as new; a genuine returning player is not."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sessions.json"
        self.socks = []

    def _bootstrap_message_id(self, state):
        token = int(TOKEN_OLD)
        store = SessionStore(self.path)
        store.save_player_state(str(token), "OLDPLAYER", state)
        server = FujiRealmHybridServer("127.0.0.1", 0, session_store=store)
        client, server_sock = socket.socketpair()
        self.socks.extend((client, server_sock))
        self.addCleanup(client.close)
        self.addCleanup(server_sock.close)
        session = ClientSession(server_sock, ("local", 0), time.monotonic())
        session.rx.extend(encode_hello(Hello(flags=0, seed=0, token=token)))
        server._process_bootstrap(session)
        return server.game.players[token].latest_message_id

    def test_fresh_start_state_greets_as_new_player(self):
        game = GameState()
        fresh = PlayerState(int(TOKEN_OLD), "OLDPLAYER")
        game._normalize_restored_player(fresh)
        state = serialize_player_state(fresh)
        state["fresh_start"] = True
        self.assertEqual(self._bootstrap_message_id(state), MSG_WELCOME_NEW)

    def test_ordinary_saved_state_greets_as_returning(self):
        game = GameState()
        player = PlayerState(int(TOKEN_OLD), "OLDPLAYER")
        game._normalize_restored_player(player)
        self.assertEqual(self._bootstrap_message_id(serialize_player_state(player)), MSG_WELCOME_BACK)


if __name__ == "__main__":
    unittest.main()
