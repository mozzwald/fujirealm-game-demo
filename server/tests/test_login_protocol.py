import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from server.game import GameState
from server.hybrid_server import FujiRealmHybridServer
from server.login_server import LoginServer, SessionStore
from server.protocol import (
    LOGIN_OK,
    LOGIN_USERNAME_TAKEN,
    RENAME_OK,
    RENAME_TOKEN_UNKNOWN,
    RENAME_USERNAME_TAKEN,
    RESUME_OK,
    Hello,
    LoginRequest,
    LoginResponse,
    PacketError,
    PacketType,
    RenameRequest,
    RenameResponse,
    ResumeRequest,
    ResumeResponse,
    decode_hello,
    decode_login_request,
    decode_login_response,
    decode_packet,
    decode_rename_request,
    decode_rename_response,
    decode_resume_request,
    decode_resume_response,
    encode_hello,
    encode_login_request,
    encode_login_response,
    encode_rename_request,
    encode_rename_response,
    encode_resume_request,
    encode_resume_response,
)


class LoginProtocolTest(unittest.TestCase):
    def test_login_request_round_trip(self):
        packet = decode_packet(encode_login_request(LoginRequest("PlayerOne")))
        self.assertEqual(packet.packet_type, PacketType.LOGIN_REQUEST)
        self.assertEqual(decode_login_request(packet.payload), LoginRequest("PlayerOne"))

    def test_login_response_round_trip(self):
        packet = decode_packet(encode_login_response(LoginResponse(LOGIN_OK, "1234567890")))
        self.assertEqual(packet.packet_type, PacketType.LOGIN_RESPONSE)
        self.assertEqual(decode_login_response(packet.payload), LoginResponse(LOGIN_OK, "1234567890"))

    def test_resume_round_trips(self):
        request = decode_packet(encode_resume_request(ResumeRequest("1234")))
        self.assertEqual(request.packet_type, PacketType.RESUME_REQUEST)
        self.assertEqual(decode_resume_request(request.payload), ResumeRequest("1234"))
        response = decode_packet(encode_resume_response(ResumeResponse(RESUME_OK, "PlayerOne")))
        self.assertEqual(response.packet_type, PacketType.RESUME_RESPONSE)
        self.assertEqual(decode_resume_response(response.payload), ResumeResponse(RESUME_OK, "PlayerOne"))

    def test_rename_round_trips(self):
        request = decode_packet(encode_rename_request(RenameRequest("1234", "PlayerTwo")))
        self.assertEqual(request.packet_type, PacketType.RENAME_REQUEST)
        self.assertEqual(decode_rename_request(request.payload), RenameRequest("1234", "PlayerTwo"))
        response = decode_packet(encode_rename_response(RenameResponse(RENAME_OK)))
        self.assertEqual(response.packet_type, PacketType.RENAME_RESPONSE)
        self.assertEqual(decode_rename_response(response.payload), RenameResponse(RENAME_OK))

    def test_rename_rejects_malformed_fields(self):
        with self.assertRaises(PacketError):
            decode_rename_request(b"\x00")
        with self.assertRaises(PacketError):
            decode_rename_request(b"\x01\xff\x01A")
        with self.assertRaises(PacketError):
            decode_rename_request(b"\x0b12345678901\x01A")
        with self.assertRaises(PacketError):
            encode_rename_request(RenameRequest("1234", "Bad,Name"))
        with self.assertRaises(PacketError):
            decode_rename_response(b"")
        with self.assertRaises(PacketError):
            decode_rename_response(b"\x00\x00")

    def test_hello_carries_token(self):
        packet = decode_packet(encode_hello(Hello(flags=1, seed=2, token=0x12345678)))
        self.assertEqual(decode_hello(packet.payload), Hello(flags=1, seed=2, token=0x12345678))

    def test_duplicate_username_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions.json")
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            self.assertIsNone(store.register("PlayerOne"))
            self.assertEqual(LoginResponse(LOGIN_USERNAME_TAKEN, "0").status, LOGIN_USERNAME_TAKEN)

    def test_resume_known_and_unknown_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions.json")
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            self.assertEqual(store.resume(token or ""), "PlayerOne")
            self.assertEqual(store.resume("99"), "Player99")

    def test_store_survives_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            store = SessionStore(path)
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            reloaded = SessionStore(path)
            self.assertTrue(reloaded.username_taken("PlayerOne"))
            self.assertEqual(reloaded.resume(token or ""), "PlayerOne")

    def test_store_preserves_player_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            store = SessionStore(path)
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            store.save_player_state(token or "", "PlayerOne", {"level": 7, "gold": 23})
            reloaded = SessionStore(path)
            self.assertEqual(reloaded.load_player_state(token or ""), {"level": 7, "gold": 23})

    def test_resume_keeps_existing_player_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            store = SessionStore(path)
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            store.save_player_state(token or "", "PlayerOne", {"level": 4})
            self.assertEqual(store.resume(token or ""), "PlayerOne")
            self.assertEqual(store.load_player_state(token or ""), {"level": 4})

    def test_rename_preserves_record_and_rejects_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            store = SessionStore(path)
            token = store.register("PlayerOne")
            other_token = store.register("PlayerTwo")
            self.assertIsNotNone(token)
            self.assertIsNotNone(other_token)
            store.save_player_state(token or "", "PlayerOne", {"level": 7, "gold": 23})
            store.set_online(token or "", True)
            before = store.get_record(token or "")
            self.assertIsNotNone(before)
            assert before is not None
            self.assertEqual(store.rename(token or "", "PlayerThree"), RENAME_OK)
            after = SessionStore(path).get_record(token or "")
            self.assertIsNotNone(after)
            assert after is not None
            self.assertEqual(after["username"], "PlayerThree")
            self.assertEqual(after["player_state"], before["player_state"])
            self.assertEqual(after["online"], before["online"])
            self.assertEqual(after["last_seen_at"], before["last_seen_at"])
            self.assertEqual(store.rename(token or "", "PlayerTwo"), RENAME_USERNAME_TAKEN)
            self.assertEqual(store.rename(token or "", "PlayerThree"), RENAME_OK)

    def test_rename_unknown_token_does_not_create_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions.json")
            self.assertEqual(store.rename("404", "PlayerOne"), RENAME_TOKEN_UNKNOWN)
            self.assertIsNone(store.get_record("404"))

    def test_stale_player_state_save_keeps_renamed_username(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            store = SessionStore(path)
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            stale = SessionStore(path)
            self.assertEqual(store.rename(token or "", "PlayerTwo"), RENAME_OK)
            self.assertEqual(stale.get_record(token or "")["username"], "PlayerTwo")
            stale.save_player_state(token or "", "PlayerOne", {"level": 9})
            record = SessionStore(path).get_record(token or "")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record["username"], "PlayerTwo")
            self.assertEqual(record["player_state"], {"level": 9})

    def test_store_tracks_online_status_without_losing_player_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            store = SessionStore(path)
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            store.save_player_state(token or "", "PlayerOne", {"level": 4})
            store.set_online(token or "", True)
            reloaded = SessionStore(path)
            record = reloaded.get_record(token or "")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertTrue(record["online"])
            self.assertIsInstance(record["last_seen_at"], int)
            self.assertEqual(reloaded.load_player_state(token or ""), {"level": 4})
            reloaded.set_all_offline()
            self.assertFalse(SessionStore(path).get_record(token or "")["online"])

    def test_hybrid_hello_token_reattaches_existing_game(self):
        server = FujiRealmHybridServer("127.0.0.1", 0)
        game = GameState(seed=7)
        game.player.x = 33
        server.sessions[1234] = game
        hello = decode_hello(decode_packet(encode_hello(Hello(flags=0, seed=1, token=1234))).payload)
        attached = server.sessions.get(hello.token)
        self.assertIs(attached, game)
        self.assertEqual(attached.player.x, 33)

    def test_login_server_drops_idle_client_after_timeout(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        left.settimeout(0.05)
        server = LoginServer(client_timeout=0.05)
        worker = threading.Thread(target=server.handle_client, args=(left,), daemon=True)
        start = time.monotonic()
        worker.start()
        worker.join(timeout=0.5)
        self.assertFalse(worker.is_alive())
        self.assertLess(time.monotonic() - start, 0.5)

    def test_login_server_handles_rename_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / "sessions.json")
            token = store.register("PlayerOne")
            self.assertIsNotNone(token)
            left, right = socket.socketpair()
            self.addCleanup(left.close)
            self.addCleanup(right.close)
            right.settimeout(0.5)
            server = LoginServer(store=store, client_timeout=0.5)
            worker = threading.Thread(target=server.handle_client, args=(left,), daemon=True)
            worker.start()
            right.sendall(encode_rename_request(RenameRequest(token or "", "PlayerTwo")))
            packet = decode_packet(right.recv(1024))
            self.assertEqual(packet.packet_type, PacketType.RENAME_RESPONSE)
            self.assertEqual(decode_rename_response(packet.payload), RenameResponse(RENAME_OK))
            worker.join(timeout=0.5)
            self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main()
