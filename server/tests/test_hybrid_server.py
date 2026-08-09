import socket
import io
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

from server.hybrid_server import (
    CLIENT_LINK_PROFILES,
    LINK_PROFILE_DEFAULT,
    LINK_PROFILE_LYNX_COMLYNX,
    FujiRealmHybridServer,
    ClientSession,
    SessionOutput,
)
from server.login_server import SessionStore
from server.protocol import (
    REALTIME_PREAMBLE,
    WINDOW_H,
    WINDOW_W,
    _normalize_realtime,
    AuthPacket,
    Hello,
    MapReadyPacket,
    PacketType,
    PacketStreamDecoder,
    PlayerStatePacket,
    REALTIME_MAGIC,
    RealtimeType,
    ResyncRequestPacket,
    Welcome,
    CacheStepAckPacket,
    NetStatsPacket,
    WindowCommitPacket,
    decode_map_change,
    decode_inventory_update,
    decode_item_drops,
    decode_player_state,
    decode_message,
    decode_remote_players,
    decode_terrain_edge,
    decode_hud_update,
    decode_welcome,
    decode_window_commit_ack,
    decode_window_row,
    decode_world_state,
    encode_auth,
    encode_hello,
    encode_map_ready,
    encode_player_state,
    encode_welcome,
    encode_resync_request,
    encode_cache_step_ack,
    encode_net_stats,
    encode_window_commit,
    realtime_packet_size,
)
from server.world import HERB, MAP_OVERWORLD, MAP_PVP_REALM
from server.world import MAP_STARTER_CAVE
from server.world import PALETTE_CAVE, TILESET_CAVE
from server.world_layout_data import PVP_REALM_RESPAWN
from server.items import ITEM_STICKS
from server.quests import MSG_PLAYER_ENTERED, MSG_PLAYER_LEFT, QUEST_ROAD_TROUBLE, QUEST_STATE_ACTIVE


TOKEN_A = 0x41414141
TOKEN_B = 0x42424242


class FakeLobbyPublisher:
    def __init__(self):
        self.publish_calls = []
        self.delete_calls = 0

    def publish(self, curplayers, status):
        self.publish_calls.append((status, curplayers))
        return True

    def delete(self):
        self.delete_calls += 1
        return True


def player_state(seq, x, y, facing=3, buttons=0, fire=0, pickup=0, pvp=0, rx_drops=0):
    return encode_player_state(
        PlayerStatePacket(
            seq=seq,
            x=x,
            y=y,
            facing=facing,
            buttons=buttons,
            fire_counter=fire,
            pickup_counter=pickup,
            last_server_seq=0,
            rx_drops=rx_drops,
            pvp_toggle_counter=pvp,
        )
    )


class HybridServerTest(unittest.TestCase):
    def setUp(self):
        self.server = None
        self.thread = None
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            try:
                client.close()
            except OSError:
                pass
        if self.server is not None:
            self.server.stop()
        if self.thread is not None:
            self.thread.join(timeout=3)
            self.assertFalse(self.thread.is_alive())

    def _start_server(
        self,
        tick_hz=30,
        auth_timeout=5.0,
        player_idle_timeout=35.0,
        duration=15.0,
        session_store=None,
        lobby_publisher=None,
        visible_remotes=3,
        test_pvp_bots=0,
        resync_row_budget=1,
        client_byte_rate=None,
        use_link_profiles=False,
    ):
        if session_store is None:
            tempdir = tempfile.TemporaryDirectory()
            self.addCleanup(tempdir.cleanup)
            session_store = SessionStore(f"{tempdir.name}/sessions.json")
        port = self._free_port()
        if use_link_profiles:
            # Phase 54: no overrides -- pacing comes from each session's
            # declared link profile.
            resync_row_budget = None
            client_byte_rate = None
        elif client_byte_rate is None:
            client_byte_rate = 1e6
        self.server = FujiRealmHybridServer(
            "127.0.0.1",
            port,
            tick_hz=tick_hz,
            debug=False,
            auth_timeout=auth_timeout,
            player_idle_timeout=player_idle_timeout,
            visible_remotes=visible_remotes,
            test_pvp_bots=test_pvp_bots,
            resync_row_budget=resync_row_budget,
            session_store=session_store,
            client_byte_rate=client_byte_rate,
            lobby_publisher=lobby_publisher,
        )
        self.thread = threading.Thread(target=lambda: self.server.serve(duration=duration), daemon=True)
        self.thread.start()
        return port

    def _store_with_names(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        store = SessionStore(f"{tempdir.name}/sessions.json")
        store.sessions = {
            str(TOKEN_A): {"username": "Alice"},
            str(TOKEN_B): {"username": "Bob"},
        }
        return store

    def _free_port(self):
        with socket.create_server(("127.0.0.1", 0)) as probe:
            return probe.getsockname()[1]

    def _connect(self, port):
        deadline = time.monotonic() + 2.0
        while True:
            try:
                client = socket.create_connection(("127.0.0.1", port), timeout=2)
                self.clients.append(client)
                return client
            except ConnectionRefusedError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)

    def test_map_ready_realtime_packet_clears_transition_loading(self):
        self.server = FujiRealmHybridServer("127.0.0.1", 0)
        player = self.server.game.ensure_player(TOKEN_A)
        player.transition_loading = True
        client, server_sock = socket.socketpair()
        self.clients.extend((client, server_sock))
        session = ClientSession(server_sock, ("local", 0), time.monotonic())
        session.token = TOKEN_A
        session.rx.extend(encode_map_ready(MapReadyPacket(1, player.map_id, 0, 0)))

        self.server._process_realtime(session)

        self.assertFalse(player.transition_loading)
        self.assertGreater(player.transition_grace_ticks, 0)

    def _recv_exact(self, client, count):
        data = bytearray()
        while len(data) < count:
            chunk = client.recv(count - len(data))
            if not chunk:
                raise EOFError("socket closed")
            data.extend(chunk)
        return bytes(data)

    def _recv_realtime_packet(self, client):
        # v3 wire frames are COBS-encoded and zero-delimited; return the
        # validated raw frame (type at [2], decoders accept it directly).
        buf = bytearray()
        while True:
            chunk = client.recv(1)
            if not chunk:
                raise AssertionError("connection closed mid-frame")
            if chunk[0] != 0:
                buf += chunk
                continue
            if not buf:
                continue
            return _normalize_realtime(bytes(buf))

    def _recv_packet_of_type(self, client, wanted, limit=200):
        for _ in range(limit):
            packet = self._recv_realtime_packet(client)
            if packet[2] in wanted:
                return packet
        raise AssertionError(f"no packet of type {wanted} within {limit} packets")

    def _recv_message_id(self, client, message_id, limit=200):
        for _ in range(limit):
            message = decode_message(self._recv_packet_of_type(client, {RealtimeType.MESSAGE}, limit=limit))
            if message.message_id == message_id:
                return message
        raise AssertionError(f"no MESSAGE id {message_id} within {limit} messages")

    def _bootstrap(self, port, token, flags=0):
        client = self._connect(port)
        client.settimeout(2.0)
        client.sendall(b"REGISTER" + encode_hello(Hello(flags=flags, seed=0, token=token)))
        decoder = PacketStreamDecoder()
        packets = []
        while not any(packet.packet_type == PacketType.WELCOME for packet in packets) or sum(
            1 for packet in packets if packet.packet_type == PacketType.WINDOW
        ) < 8:
            packets.extend(decoder.feed(client.recv(1024)))
        client.close()
        return packets

    def _place_player(self, token, x, y):
        """Put the server-side player at (x, y) before its realtime attach.

        A session's window origin is derived from the player's position at
        AUTH. Tests pick coordinates for the window geometry they want, which
        is nowhere near the map's spawn point, so attaching with a first
        PLAYER_STATE far from where the player actually is reads to the server
        as a teleport: it starts a full 24-row window fill that swamps
        whatever the test is really asserting. Placing the player first models
        a client reporting the position it already holds.

        Tests of the window-fill machinery itself want that fill, and so
        attach without placing; tests of steady-state gameplay pass
        ``place=True`` to ``_open_realtime``.
        """
        player = self.server.game.ensure_player(token)
        player.x, player.y = x, y
        return player

    def _open_realtime(self, port, token, first_state=None, place=False, start=None):
        # start=(x, y): the player is already here, and the first PLAYER_STATE
        # reports somewhere else -- for tests that need a specific gap between
        # the session's window origin and its target.
        if start is not None:
            self._place_player(token, *start)
        elif first_state is not None and place:
            state = decode_player_state(first_state)
            self._place_player(token, state.x, state.y)
        client = self._connect(port)
        client.settimeout(2.0)
        client.sendall(b"REGISTER" + REALTIME_PREAMBLE + encode_auth(AuthPacket(seq=0, token=token)))
        if first_state is not None:
            client.sendall(first_state)
        return client

    def test_bootstrap_sends_welcome_and_window_for_token(self):
        port = self._start_server(client_byte_rate=2000.0)
        packets = self._bootstrap(port, TOKEN_A)
        welcome = next(packet for packet in packets if packet.packet_type == PacketType.WELCOME)
        self.assertEqual(decode_welcome(welcome.payload).seed, self.server.game.seed)
        self.assertIn(TOKEN_A, self.server.game.players)

    def test_bootstrap_socket_can_transition_to_realtime(self):
        port = self._start_server(client_byte_rate=2000.0)
        client = self._connect(port)
        client.settimeout(2.0)
        client.sendall(b"REGISTER" + encode_hello(Hello(flags=0, seed=0, token=TOKEN_A)))

        decoder = PacketStreamDecoder()
        packets = []
        while not any(packet.packet_type == PacketType.WELCOME for packet in packets) or sum(
            1 for packet in packets if packet.packet_type == PacketType.WINDOW
        ) < 8:
            packets.extend(decoder.feed(client.recv(1024)))

        origin = self.server.game.window_origin(TOKEN_A)
        client.sendall(
            REALTIME_PREAMBLE
            + encode_auth(AuthPacket(seq=0, token=TOKEN_A))
            + player_state(1, origin[0] + WINDOW_W // 2, origin[1] + WINDOW_H // 2)
        )
        packet = self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})

        self.assertEqual(packet[2], RealtimeType.WORLD_STATE)
        self.assertIn(TOKEN_A, self.server.realtime_by_token)
        self.assertEqual(self.server.realtime_by_token[TOKEN_A].kind, "realtime")

    # ------------------------------------------------------------------
    # Phase 54: per-client link profiles

    def _profile_session(self, server):
        client, server_sock = socket.socketpair()
        self.clients.extend((client, server_sock))
        return ClientSession(server_sock, ("local", 0), time.monotonic())

    def test_link_profile_default_matches_historical_constants(self):
        # The Atari regression guard: compare against literals, not the
        # constants, so a table or constant edit cannot silently move the
        # Atari numbers.
        profile = CLIENT_LINK_PROFILES[LINK_PROFILE_DEFAULT]
        self.assertEqual(profile.byte_rate, 2000.0)
        self.assertEqual(profile.burst_bytes, 384)
        self.assertEqual(profile.resync_row_budget, 2)
        self.assertEqual(profile.edge_budget, 3)

    def test_apply_link_profile_unknown_id_falls_back_to_default(self):
        self.server = FujiRealmHybridServer("127.0.0.1", 0)
        session = self._profile_session(self.server)
        self.server._apply_link_profile(session, 0xC7)
        self.assertEqual(session.link_profile_id, LINK_PROFILE_DEFAULT)
        self.assertEqual(session.out.rate, 2000.0)
        self.assertEqual(session.out.burst, 384)
        self.assertEqual(session.resync_row_budget, 2)

    def test_apply_link_profile_lynx_paces_without_minting_burst(self):
        self.server = FujiRealmHybridServer("127.0.0.1", 0)
        session = self._profile_session(self.server)
        tokens_before = session.out.tokens
        self.server._apply_link_profile(session, LINK_PROFILE_LYNX_COMLYNX)
        self.assertEqual(session.link_profile_id, LINK_PROFILE_LYNX_COMLYNX)
        self.assertEqual(session.out.rate, 2800.0)
        self.assertEqual(session.out.burst, 384)
        self.assertEqual(session.resync_row_budget, 2)
        # Applying the profile must not mint tokens mid-stream.
        self.assertEqual(session.out.tokens, tokens_before)

    def test_explicit_overrides_beat_link_profile(self):
        self.server = FujiRealmHybridServer(
            "127.0.0.1", 0, client_byte_rate=1234.0, resync_row_budget=5
        )
        session = self._profile_session(self.server)
        self.server._apply_link_profile(session, LINK_PROFILE_LYNX_COMLYNX)
        self.assertEqual(session.out.rate, 1234.0)
        self.assertEqual(session.resync_row_budget, 5)
        # No burst override was given, so that one still follows the profile.
        self.assertEqual(session.out.burst, 384)

    def test_bootstrap_with_lynx_flags_paces_session_and_realtime(self):
        # Same-socket transition (the Lynx path): HELLO flags=1 must pace the
        # bootstrap itself and survive into the realtime attach.
        port = self._start_server(use_link_profiles=True)
        client = self._connect(port)
        client.settimeout(5.0)
        client.sendall(
            b"REGISTER" + encode_hello(Hello(flags=LINK_PROFILE_LYNX_COMLYNX, seed=0, token=TOKEN_A))
        )
        decoder = PacketStreamDecoder()
        packets = []
        while not any(packet.packet_type == PacketType.WELCOME for packet in packets) or sum(
            1 for packet in packets if packet.packet_type == PacketType.WINDOW
        ) < 8:
            packets.extend(decoder.feed(client.recv(1024)))
        origin = self.server.game.window_origin(TOKEN_A)
        client.sendall(
            REALTIME_PREAMBLE
            + encode_auth(AuthPacket(seq=0, token=TOKEN_A))
            + player_state(1, origin[0] + WINDOW_W // 2, origin[1] + WINDOW_H // 2)
        )
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})

        session = self.server.realtime_by_token[TOKEN_A]
        self.assertEqual(session.link_profile_id, LINK_PROFILE_LYNX_COMLYNX)
        self.assertEqual(session.out.rate, 2800.0)
        self.assertEqual(session.resync_row_budget, 2)

    def test_concurrent_sessions_are_paced_by_their_own_profiles(self):
        # An Atari (flags 0, second-connection realtime) and a Lynx (flags 1)
        # at once: each session must carry its own declared profile, the
        # Atari adopting profile 0 by token on its fresh realtime socket.
        port = self._start_server(use_link_profiles=True)
        self._bootstrap(port, TOKEN_A, flags=0)
        self._bootstrap(port, TOKEN_B, flags=LINK_PROFILE_LYNX_COMLYNX)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10))
        self._recv_packet_of_type(client_a, {RealtimeType.WORLD_STATE})
        self._recv_packet_of_type(client_b, {RealtimeType.WORLD_STATE})

        session_a = self.server.realtime_by_token[TOKEN_A]
        session_b = self.server.realtime_by_token[TOKEN_B]
        self.assertEqual(session_a.link_profile_id, LINK_PROFILE_DEFAULT)
        self.assertEqual(session_a.out.rate, 2000.0)
        self.assertEqual(session_a.resync_row_budget, 2)
        self.assertEqual(session_b.link_profile_id, LINK_PROFILE_LYNX_COMLYNX)
        self.assertEqual(session_b.out.rate, 2800.0)
        self.assertEqual(session_b.resync_row_budget, 2)

    def test_anonymous_hello_is_rejected(self):
        port = self._start_server()
        client = self._connect(port)
        client.settimeout(2.0)
        client.sendall(b"REGISTER" + encode_hello(Hello(flags=0, seed=0, token=0)))
        self.assertEqual(client.recv(1024), b"")

    def test_two_clients_play_concurrently_and_see_each_other(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10), place=True)

        world_a = decode_world_state(
            self._recv_packet_of_type(client_a, {RealtimeType.WORLD_STATE})
        )
        world_b = decode_world_state(
            self._recv_packet_of_type(client_b, {RealtimeType.WORLD_STATE})
        )
        self.assertEqual((world_a.player_x, world_a.player_y), (11, 10))
        self.assertEqual((world_b.player_x, world_b.player_y), (13, 10))

        remote_a = decode_remote_players(
            self._recv_packet_of_type(client_a, {RealtimeType.REMOTE_PLAYERS})
        )
        self.assertEqual(len(remote_a.players), 1)
        self.assertEqual((remote_a.players[0].x, remote_a.players[0].y), (13, 10))

        # B moves; A sees the update.
        client_b.sendall(player_state(seq=2, x=14, y=10))
        deadline = time.monotonic() + 2.0
        while True:
            remote_a = decode_remote_players(
                self._recv_packet_of_type(client_a, {RealtimeType.REMOTE_PLAYERS})
            )
            if remote_a.players and (remote_a.players[0].x, remote_a.players[0].y) == (14, 10):
                break
            self.assertLess(time.monotonic(), deadline, "A never saw B move")

    def test_item_drop_is_visible_to_any_client_and_clears_after_pickup(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        # Row 10 has a tree at x=12 in the current hand-authored map, so
        # the walk-onto-it step below needs a clear spot; use row 16.
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=16), place=True)
        self._recv_packet_of_type(client_a, {RealtimeType.WORLD_STATE})
        self.server.game.spawn_item(12, 16, ITEM_STICKS, map_id=self.server.game.players[TOKEN_A].map_id)

        client_a.sendall(player_state(seq=2, x=11, y=16))
        drops = decode_item_drops(self._recv_packet_of_type(client_a, {RealtimeType.ITEM_DROPS}))
        self.assertEqual(len(drops.items), 1)
        self.assertEqual((drops.items[0].x, drops.items[0].y), (12, 16))

        # Walk onto it and pick it up (pickup_counter edge): the drop
        # disappears from the next ITEM_DROPS snapshot (count 0).
        client_a.sendall(player_state(seq=3, x=12, y=16, pickup=1))
        deadline = time.monotonic() + 2.0
        while True:
            drops = decode_item_drops(self._recv_packet_of_type(client_a, {RealtimeType.ITEM_DROPS}))
            if not drops.items:
                break
            self.assertLess(time.monotonic(), deadline, "drop never cleared after pickup")

    def test_remote_players_empty_after_disconnect(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10), place=True)
        remote_a = decode_remote_players(
            self._recv_packet_of_type(client_a, {RealtimeType.REMOTE_PLAYERS})
        )
        self.assertEqual(len(remote_a.players), 1)
        client_b.close()
        deadline = time.monotonic() + 2.0
        while True:
            remote_a = decode_remote_players(
                self._recv_packet_of_type(client_a, {RealtimeType.REMOTE_PLAYERS})
            )
            if not remote_a.players:
                break
            self.assertLess(time.monotonic(), deadline, "A never saw B leave")

    def test_player_enter_message_uses_username(self):
        port = self._start_server(session_store=self._store_with_names())
        self._bootstrap(port, TOKEN_A)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        self._recv_packet_of_type(client_a, {RealtimeType.WORLD_STATE})
        self._bootstrap(port, TOKEN_B)
        self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10))
        message = self._recv_message_id(client_a, MSG_PLAYER_ENTERED)
        self.assertEqual(message.text, "BOB HAS ENTERED THE REALM!")

    def test_bootstrap_reloads_session_store_for_new_login(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = f"{tempdir.name}/sessions.json"
        stale_store = SessionStore(path)
        port = self._start_server(session_store=stale_store)
        writer = SessionStore(path)
        token = writer.register("MOZZXL")
        self.assertIsNotNone(token)
        token_int = int(token or "0")
        self._bootstrap(port, token_int)
        self.assertEqual(self.server.game.players[token_int].username, "MOZZXL")

    def test_player_leave_message_uses_username(self):
        port = self._start_server(session_store=self._store_with_names())
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10))
        self._recv_message_id(client_a, MSG_PLAYER_ENTERED)
        client_b.close()
        message = self._recv_message_id(client_a, MSG_PLAYER_LEFT)
        self.assertEqual(message.text, "BOB HAS LEFT THE REALM!")

    def test_realtime_attach_and_drop_updates_session_online_status(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = f"{tempdir.name}/sessions.json"
        store = SessionStore(path)
        store.save_player_state(TOKEN_A, "ALICE", {"level": 4})
        port = self._start_server(session_store=store)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            record = SessionStore(path).get_record(TOKEN_A)
            if record is not None and record.get("online") is True:
                break
            time.sleep(0.01)
        self.assertTrue(SessionStore(path).get_record(TOKEN_A)["online"])
        client.close()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            record = SessionStore(path).get_record(TOKEN_A)
            if record is not None and record.get("online") is False:
                break
            time.sleep(0.01)
        self.assertFalse(SessionStore(path).get_record(TOKEN_A)["online"])

    def test_full_health_player_receives_herb_tile_without_consuming_it(self):
        port = self._start_server()
        world = self.server.game.world_for(MAP_OVERWORLD)
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        self._bootstrap(port, TOKEN_A)
        self.server.game.players[TOKEN_A].health = self.server.game.players[TOKEN_A].max_health
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        world_state = decode_world_state(self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE}))
        self.assertEqual((world_state.player_x, world_state.player_y), (11, 10))
        self.assertEqual((world_state.tile_x, world_state.tile_y, world_state.tile_id), (11, 10, HERB))
        self.assertEqual(world.tile(11, 10), HERB)
        self.assertEqual(world.herb_respawn_ticks, {})

    def test_reauth_replacement_does_not_broadcast_leave_or_enter(self):
        port = self._start_server(session_store=self._store_with_names())
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10))
        self._recv_message_id(client_a, MSG_PLAYER_ENTERED)
        self.server.game.players[TOKEN_A].pending_messages.clear()
        old_session = self.server.realtime_by_token[TOKEN_B]

        new_client = self._connect(port)
        new_client.settimeout(2.0)
        new_client.sendall(b"REGISTER" + REALTIME_PREAMBLE + encode_auth(AuthPacket(seq=1, token=TOKEN_B)))
        deadline = time.monotonic() + 1.0
        while self.server.realtime_by_token.get(TOKEN_B) is old_session and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertIsNot(self.server.realtime_by_token[TOKEN_B], old_session)
        self.assertEqual(self.server.game.players[TOKEN_A].pending_messages, [])

    def test_restart_restores_persistent_player_progress(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = f"{tempdir.name}/sessions.json"
        initial_store = SessionStore(path)
        initial_store.sessions = {str(TOKEN_A): {"username": "Alice"}}
        initial_store.save()

        port = self._start_server(session_store=SessionStore(path), duration=5.0)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        player = self.server.game.players[TOKEN_A]
        player.level = 7
        player.xp = 140
        player.xp_next = 160
        player.max_health = 18
        player.health = 17
        player.gold = 23
        player.inventory.add_item(ITEM_STICKS, 2)
        player.active_quest_id = QUEST_ROAD_TROUBLE
        player.quest_state = QUEST_STATE_ACTIVE
        player.quest_progress = 2
        player.quest_target = 3
        player.x = 14
        player.y = 10
        client.close()
        deadline = time.monotonic() + 1.0
        while TOKEN_A not in self.server.game.offline_players and time.monotonic() < deadline:
            time.sleep(0.01)
        self.server.stop()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())
        self.server = None
        self.thread = None

        port = self._start_server(session_store=SessionStore(path), duration=5.0)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=14, y=10))
        world = decode_world_state(self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE}))
        hud = decode_hud_update(self._recv_packet_of_type(client, {RealtimeType.HUD_UPDATE}))
        inventory = decode_inventory_update(self._recv_packet_of_type(client, {RealtimeType.INVENTORY_UPDATE}))
        self.assertEqual((world.player_x, world.player_y), (14, 10))
        self.assertEqual((hud.level, hud.hp, hud.max_hp, hud.gold), (7, 17, 24, 23))
        self.assertEqual(inventory.slots, ((ITEM_STICKS, 2),))
        restored = self.server.game.players[TOKEN_A]
        self.assertEqual((restored.active_quest_id, restored.quest_state, restored.quest_progress), (QUEST_ROAD_TROUBLE, QUEST_STATE_ACTIVE, 2))

    def test_restart_rejects_stale_client_position_until_restored_position_is_echoed(self):
        # Overworld, deliberately: a non-Overworld start now goes through an
        # explicit MAP_CHANGE handshake first (Phase 68 fresh-boot art fix)
        # whose spawn_x/spawn_y already carries the restored position, which
        # is a different (also-tested, see test_fresh_boot_into_cave_sends_
        # map_change_with_cave_art) mechanism than the stale-position
        # rejection this test is about.
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = f"{tempdir.name}/sessions.json"
        store = SessionStore(path)
        store.sessions = {
            str(TOKEN_A): {
                "username": "Alice",
                "player_state": {
                    "class_id": 1,
                    "level": 5,
                    "xp": 80,
                    "health": 12,
                    "gold": 0,
                    "inventory": [],
                    "active_quest_id": 0,
                    "quest_state": 0,
                    "quest_progress": 0,
                    "quest_target": 0,
                    "pending_quest_offer_id": 0,
                    "map_id": MAP_OVERWORLD,
                    "x": 14,
                    "y": 10,
                    "respawn_map_id": MAP_OVERWORLD,
                    "respawn_x": 8,
                    "respawn_y": 10,
                    "pvp_enabled": False,
                    "visited_zones": [],
                },
            }
        }
        store.save()
        port = self._start_server(session_store=SessionStore(path))
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=8, y=10))
        world = decode_world_state(self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE}))
        self.assertEqual(world.correction_flags, 1)
        self.assertEqual((world.player_x, world.player_y), (14, 10))
        client.sendall(player_state(seq=2, x=14, y=10))
        world = decode_world_state(self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE}))
        self.assertEqual(world.correction_flags, 0)
        self.assertEqual((world.player_x, world.player_y), (14, 10))

    def test_remote_players_empty_after_idle_timeout(self):
        port = self._start_server(player_idle_timeout=0.5)
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10), place=True)
        remote_a = decode_remote_players(
            self._recv_packet_of_type(client_a, {RealtimeType.REMOTE_PLAYERS})
        )
        self.assertEqual(len(remote_a.players), 1)
        deadline = time.monotonic() + 2.0
        seq = 2
        while True:
            client_a.sendall(player_state(seq=seq, x=11, y=10))
            seq += 1
            remote_a = decode_remote_players(
                self._recv_packet_of_type(client_a, {RealtimeType.REMOTE_PLAYERS})
            )
            if not remote_a.players:
                break
            self.assertLess(time.monotonic(), deadline, "A never saw idle B time out")

    def test_inventory_update_sent_after_pickup(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        player = self.server.game.ensure_player(TOKEN_A)
        self.server.game.spawn_item(player.x, player.y, ITEM_STICKS, quantity=2, map_id=player.map_id)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=player.x, y=player.y, pickup=1))
        inventory = decode_inventory_update(
            self._recv_packet_of_type(client, {RealtimeType.INVENTORY_UPDATE})
        )
        self.assertEqual(inventory.slots, ((ITEM_STICKS, 2),))

    def test_player_state_is_ignored_until_auth(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._connect(port)
        client.settimeout(0.3)
        client.sendall(b"REGISTER" + REALTIME_PREAMBLE + player_state(seq=1, x=11, y=10))
        with self.assertRaises(TimeoutError):
            client.recv(64)
        # After AUTH, states are honored.
        client.settimeout(2.0)
        client.sendall(encode_auth(AuthPacket(seq=0, token=TOKEN_A)))
        client.sendall(player_state(seq=2, x=11, y=10))
        world = decode_world_state(self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE}))
        self.assertEqual((world.player_x, world.player_y), (11, 10))

    def test_unauthenticated_realtime_connection_times_out(self):
        port = self._start_server(auth_timeout=0.3)
        self._bootstrap(port, TOKEN_A)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        stale = self._connect(port)
        stale.settimeout(2.0)
        stale.sendall(b"REGISTER" + player_state(seq=1, x=12, y=10))
        self.assertEqual(stale.recv(64), b"")  # dropped by the server
        # The authenticated client is unaffected.
        world = decode_world_state(self._recv_packet_of_type(client_a, {RealtimeType.WORLD_STATE}))
        self.assertEqual((world.player_x, world.player_y), (11, 10))

    def test_players_block_each_other_with_correction(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=11, y=16), place=True)
        self._recv_packet_of_type(client_b, {RealtimeType.WORLD_STATE})
        # A stands beside B and tries to step onto it.
        client_a = self._open_realtime(
            port, TOKEN_A, player_state(seq=1, x=11, y=16), start=(10, 16)
        )
        world_a = decode_world_state(
            self._recv_packet_of_type(client_a, {RealtimeType.WORLD_STATE})
        )
        self.assertEqual(world_a.correction_flags, 1)
        self.assertEqual((world_a.player_x, world_a.player_y), (10, 16))

    def test_map_transition_isolates_players_across_maps(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        # The cave entrance sits at OVERWORLD_CAVE_ENTRANCE == (118,10) (see
        # world_layout_data.py); stage both players beside it on open grass.
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=117, y=10))
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=117, y=11))
        # The far teleports start full-window fills; commit them like a real
        # client so the sessions' committed origins reach the staging area.
        rows_a = self._collect_window_rows(client_a)
        self._commit_window_rows(client_a, rows_a, MAP_OVERWORLD, seq=2)
        rows_b = self._collect_window_rows(client_b)
        self._commit_window_rows(client_b, rows_b, MAP_OVERWORLD, seq=2)
        remote_b = decode_remote_players(
            self._recv_packet_of_type(client_b, {RealtimeType.REMOTE_PLAYERS})
        )
        self.assertEqual(len(remote_b.players), 1)

        # A steps onto the cave entrance; server answers MAP_CHANGE and keeps
        # the session, streaming the cave window as rows on the same
        # connection (the client never leaves streaming mode).
        client_a.sendall(player_state(seq=2, x=118, y=10))
        map_change = decode_map_change(
            self._recv_packet_of_type(client_a, {RealtimeType.MAP_CHANGE})
        )
        self.assertEqual(map_change.map_id, MAP_STARTER_CAVE)
        rows = self._collect_window_rows(client_a)
        self.assertEqual([row.row_index for row in rows], list(range(WINDOW_H)))
        cave = self.server.game.world_for(MAP_STARTER_CAVE)
        for row in rows:
            self.assertEqual(
                row.tiles, cave.window_tiles(row.origin_x, row.origin_y, WINDOW_W, 1)
            )
        self._commit_window_rows(client_a, rows, MAP_STARTER_CAVE, seq=3)
        client_a.sendall(encode_map_ready(MapReadyPacket(4, MAP_STARTER_CAVE, 0, 0)))

        # B sees A leave the overworld.
        deadline = time.monotonic() + 2.0
        while True:
            remote_b = decode_remote_players(
                self._recv_packet_of_type(client_b, {RealtimeType.REMOTE_PLAYERS})
            )
            if not remote_b.players:
                break
            self.assertLess(time.monotonic(), deadline, "B never saw A leave")

        # A keeps playing on the same connection: echo the spawn (the server
        # holds the player there until the client catches up), then observe
        # cave state. The starter cave has more enemies than one snapshot can show.
        client_a.sendall(player_state(seq=3, x=map_change.spawn_x, y=map_change.spawn_y))
        deadline = time.monotonic() + 2.0
        while True:
            world_a = decode_world_state(
                self._recv_packet_of_type(client_a, {RealtimeType.WORLD_STATE})
            )
            live = [(b.x, b.y) for b in world_a.beavers if b.hp > 0]
            if len(live) >= 1:
                break
            self.assertLess(time.monotonic(), deadline, "A never saw cave beavers")
        self.assertEqual(
            (world_a.player_x, world_a.player_y), (map_change.spawn_x, map_change.spawn_y)
        )
        # B keeps playing on the overworld.
        world_b = decode_world_state(
            self._recv_packet_of_type(client_b, {RealtimeType.WORLD_STATE})
        )
        self.assertEqual((world_b.player_x, world_b.player_y), (117, 11))

    def _recv_eof(self, client):
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            chunk = client.recv(1024)
            if chunk == b"":
                return b""
        raise AssertionError("expected EOF")

    def test_reconnect_resumes_session_without_duplicate_entity(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        # x=12,y=10 is a tree in the current hand-authored map; use a
        # clear spot for this initial connection.
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        world = decode_world_state(self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE}))
        self.assertEqual((world.player_x, world.player_y), (11, 10))
        client.close()
        # The client's reconnect flow always re-bootstraps before re-AUTH.
        self._bootstrap(port, TOKEN_A)
        client2 = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=13, y=10))
        world = decode_world_state(self._recv_packet_of_type(client2, {RealtimeType.WORLD_STATE}))
        self.assertEqual(world.correction_flags, 1)
        self.assertEqual((world.player_x, world.player_y), (11, 10))
        client2.sendall(player_state(seq=2, x=11, y=10))
        self._recv_packet_of_type(client2, {RealtimeType.WORLD_STATE})
        client2.sendall(player_state(seq=3, x=13, y=10))
        world = decode_world_state(self._recv_packet_of_type(client2, {RealtimeType.WORLD_STATE}))
        self.assertEqual((world.player_x, world.player_y), (13, 10))
        game = self.server.game
        player_entities = [
            entity
            for entity in game.entities.values()
            if entity.is_player and entity.owner_id == TOKEN_A
        ]
        self.assertEqual(len(player_entities), 1)
        self.assertEqual(len([t for t in game.players if t == TOKEN_A]), 1)

    def test_reauth_keepalive_preserves_session_trackers(self):
        left, right = socket.socketpair()
        self.clients.extend([left, right])
        self.server = FujiRealmHybridServer("127.0.0.1", 0, tick_hz=30, debug=False)
        session = ClientSession(left, ("127.0.0.1", 0), time.monotonic())
        session.kind = "realtime"
        session.token = TOKEN_A
        self.server.game.ensure_player(TOKEN_A)
        self.server.realtime_by_token[TOKEN_A] = session
        session.window_origin = (7, 3)
        session.hud_sent = (1, 2, 3)
        session.quest_sent = (4, 5, 6)
        session.message_counter_sent = 9
        session.respawn_counter_sent = 10
        before_heard = session.last_heard_at
        session.rx.extend(encode_auth(AuthPacket(seq=99, token=TOKEN_A)))
        self.server._process_realtime(session)
        self.assertIs(self.server.realtime_by_token[TOKEN_A], session)
        self.assertEqual(session.window_origin, (7, 3))
        self.assertEqual(session.hud_sent, (1, 2, 3))
        self.assertEqual(session.quest_sent, (4, 5, 6))
        self.assertEqual(session.message_counter_sent, 9)
        self.assertEqual(session.respawn_counter_sent, 10)
        self.assertGreater(session.last_heard_at, before_heard)

    def test_debug_errors_only_suppresses_debug_stream(self):
        server = FujiRealmHybridServer("127.0.0.1", 0, debug=False, debug_errors_only=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            server._log_debug("debug line")
            server._log_error("error line")
        self.assertEqual(buf.getvalue().strip(), "error line")

    def test_debug_errors_only_logs_net_rx_drop_delta(self):
        session = ClientSession(socket.socket(), ("127.0.0.1", 1234), time.monotonic())
        self.addCleanup(session.conn.close)
        session.token = TOKEN_A
        server = FujiRealmHybridServer("127.0.0.1", 0, debug=False, debug_errors_only=True)
        first = PlayerStatePacket(
            seq=1,
            x=11,
            y=10,
            facing=3,
            buttons=0,
            fire_counter=0,
            pickup_counter=0,
            last_server_seq=0,
            rx_drops=250,
        )
        second = PlayerStatePacket(
            seq=2,
            x=11,
            y=10,
            facing=3,
            buttons=0,
            fire_counter=0,
            pickup_counter=0,
            last_server_seq=0,
            rx_drops=3,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            server._log_rx_drops(session, first)
            server._log_rx_drops(session, second)
        self.assertEqual(
            buf.getvalue(),
            f"net_rx_drops token={TOKEN_A} seq=2 delta=9 total=3\n",
        )

    def test_visible_remote_and_bot_limits_are_validated(self):
        with self.assertRaises(ValueError):
            FujiRealmHybridServer("127.0.0.1", 0, visible_remotes=13)
        with self.assertRaises(ValueError):
            FujiRealmHybridServer("127.0.0.1", 0, test_pvp_bots=25)
        with self.assertRaises(ValueError):
            FujiRealmHybridServer("127.0.0.1", 0, test_pvp_bots=1, test_pvp_bot_orbit_every=0)
        server = FujiRealmHybridServer("127.0.0.1", 0, test_pvp_bots=1, test_pvp_bots_no_fire=True)
        self.assertFalse(server.pvp_bots.config.can_fire)
        server = FujiRealmHybridServer("127.0.0.1", 0, test_pvp_bots=1, test_pvp_bot_mode="orbit")
        self.assertEqual(server.pvp_bots.config.mode, "orbit")
        server = FujiRealmHybridServer("127.0.0.1", 0, test_pvp_bots=1, test_pvp_bot_mode="path")
        self.assertEqual(server.pvp_bots.config.mode, "path")

    def test_bootstrap_seed_avoids_welcome_resync_magic(self):
        unsafe = 0x00BF
        self.assertIn(0xBF, encode_welcome(Welcome(player_id=1, seed=unsafe))[1:])
        seed = FujiRealmHybridServer._bootstrap_safe_seed(unsafe)
        self.assertNotEqual(seed, unsafe)
        self.assertNotIn(0xBF, encode_welcome(Welcome(player_id=1, seed=seed))[1:])

    def test_lobby_publish_tracks_start_join_leave_and_shutdown(self):
        lobby = FakeLobbyPublisher()
        port = self._start_server(lobby_publisher=lobby, duration=5.0)
        deadline = time.monotonic() + 1.0
        while not lobby.publish_calls and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(lobby.publish_calls[0], ("online", 0))

        self._bootstrap(port, TOKEN_A)
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        deadline = time.monotonic() + 1.0
        while ("online", 1) not in lobby.publish_calls and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn(("online", 1), lobby.publish_calls)

        self._bootstrap(port, TOKEN_B)
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=13, y=10))
        deadline = time.monotonic() + 1.0
        while ("online", 2) not in lobby.publish_calls and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn(("online", 2), lobby.publish_calls)

        client_b.close()
        deadline = time.monotonic() + 1.0
        while lobby.publish_calls.count(("online", 1)) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreaterEqual(lobby.publish_calls.count(("online", 1)), 2)

        self.server.stop()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(lobby.delete_calls, 1)
        self.server = None
        self.thread = None
        client_a.close()

    def test_lobby_publish_does_not_count_pvp_bots(self):
        lobby = FakeLobbyPublisher()
        self._start_server(lobby_publisher=lobby, test_pvp_bots=12, duration=1.0)
        deadline = time.monotonic() + 1.0
        while not lobby.publish_calls and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(lobby.publish_calls[0], ("online", 0))

    def test_pvp_bots_are_not_persisted(self):
        store = self._store_with_names()
        self.server = FujiRealmHybridServer(
            "127.0.0.1",
            0,
            session_store=store,
            test_pvp_bots=12,
        )
        for token in self.server.pvp_bots.bot_tokens:
            self.server._save_player_state(token, "BOT", {"level": 9})
            self.assertIsNone(store.get_record(token))

    def test_pvp_bots_are_visible_as_remote_players_in_arena(self):
        port = self._start_server(visible_remotes=12, test_pvp_bots=12)
        self._bootstrap(port, TOKEN_A)
        player = self.server.game.ensure_player(TOKEN_A)
        player.map_id = MAP_PVP_REALM
        player.x = PVP_REALM_RESPAWN[0] + 6
        player.y = PVP_REALM_RESPAWN[1]
        player.respawn_map_id = MAP_PVP_REALM
        player.respawn_x, player.respawn_y = PVP_REALM_RESPAWN
        player.pvp_enabled = True
        self.server.game.world_for(MAP_PVP_REALM)
        self.server.game._sync_player_entity(player)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=player.x, y=player.y))
        packet = self._recv_packet_of_type(client, {RealtimeType.REMOTE_PLAYERS}, limit=200)
        remotes = decode_remote_players(packet)
        self.assertEqual(len(remotes.players), 12)
        self.assertTrue(all(record.state & 0x02 for record in remotes.players))

    def test_fresh_boot_into_cave_sends_map_change_with_cave_art(self):
        # A player who last logged out in the cave (or PvP realm) and then
        # boots fresh must get an explicit MAP_CHANGE with the cave's
        # tileset/palette on this very first realtime attach -- the plain
        # bootstrap window carries no art fields, and the client otherwise
        # keeps rendering with the Overworld palette it defaults to at boot.
        # Route through the real client sequence (legacy HELLO/WELCOME/
        # WINDOW bootstrap, THEN the realtime AUTH attach) via _bootstrap()
        # + _open_realtime() -- a prior version of this test skipped the
        # legacy bootstrap and went straight to _open_realtime(), which
        # left session.needs_full_resync True and masked a real bug: the
        # legacy bootstrap that every real connection performs first always
        # marks the token bootstrapped before the realtime attach runs, so
        # a fix gated on needs_full_resync there never actually fired.
        port = self._start_server()
        player = self.server.game.ensure_player(TOKEN_A)
        player.map_id = MAP_STARTER_CAVE
        player.x, player.y = 20, 20
        self.server.game.world_for(MAP_STARTER_CAVE)
        self.server.game._sync_player_entity(player)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=player.x, y=player.y))
        map_change = decode_map_change(
            self._recv_packet_of_type(client, {RealtimeType.MAP_CHANGE})
        )
        self.assertEqual(map_change.map_id, MAP_STARTER_CAVE)
        self.assertEqual(map_change.tileset_id, TILESET_CAVE)
        self.assertEqual(map_change.palette_id, PALETTE_CAVE)

    def test_fresh_boot_into_overworld_sends_no_map_change(self):
        # The common case (Overworld start) already matches the client's
        # boot-time default art, so no extra MAP_CHANGE/pause handshake is
        # needed -- only remote/window streaming, matching prior behavior.
        port = self._start_server()
        self.server.game.ensure_player(TOKEN_A)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=12, y=10))
        packet = self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        self.assertEqual(packet[2], RealtimeType.WORLD_STATE)

    def test_reauth_new_socket_supersedes_old_session(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        old_client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=12, y=10))
        self._recv_packet_of_type(old_client, {RealtimeType.WORLD_STATE})
        old_session = self.server.realtime_by_token[TOKEN_A]
        new_client = self._connect(port)
        new_client.settimeout(2.0)
        new_client.sendall(b"REGISTER" + REALTIME_PREAMBLE + encode_auth(AuthPacket(seq=1, token=TOKEN_A)))
        deadline = time.monotonic() + 1.0
        while self.server.realtime_by_token.get(TOKEN_A) is old_session and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNot(self.server.realtime_by_token[TOKEN_A], old_session)
        self.assertNotIn(old_session.conn, self.server.sessions)
        self.assertIn(TOKEN_A, self.server.game.players)
        # The replaced socket carried no fresh bootstrap, so the server cannot
        # trust the client's terrain cache: it streams a fresh full window
        # in-band and the session stays connected.
        new_client.sendall(player_state(seq=2, x=13, y=10))
        rows = self._collect_window_rows(new_client)
        self.assertEqual(len(rows), WINDOW_H)
        # Play continues on the same connection.
        new_client.sendall(player_state(seq=3, x=13, y=10))
        world = decode_world_state(self._recv_packet_of_type(new_client, {RealtimeType.WORLD_STATE}))
        self.assertEqual((world.player_x, world.player_y), (13, 10))

    def _collect_window_rows(self, client, expected=WINDOW_H):
        rows = []
        while len(rows) < expected:
            packet = self._recv_packet_of_type(client, {RealtimeType.WINDOW_ROW})
            rows.append(decode_window_row(packet))
        return rows

    def _commit_window_rows(self, client, rows, map_id, seq=1):
        # Acknowledge a completed fill the way the Atari client does: the
        # server holds edge streaming until a matching WINDOW_COMMIT arrives.
        first = rows[0]
        client.sendall(
            encode_window_commit(
                WindowCommitPacket(
                    seq=seq,
                    fill_id=first.fill_id,
                    origin_x=first.origin_x,
                    origin_y=first.origin_y - first.row_index,
                    map_id=map_id,
                )
            )
        )

    def test_far_teleport_streams_window_rows_in_band(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        spot = self._enterable_far_tile()
        # A jump far beyond edge-streaming range resyncs with 24 absolute
        # rows on the same connection instead of a MAP_CHANGE disconnect.
        client.sendall(player_state(seq=2, x=spot[0], y=spot[1]))
        rows = self._collect_window_rows(client)
        self.assertEqual([row.row_index for row in rows], list(range(WINDOW_H)))
        # Every row is self-describing and agrees on one window origin.
        origins = {(row.origin_x, row.origin_y - row.row_index) for row in rows}
        self.assertEqual(len(origins), 1)
        origin = origins.pop()
        self.assertEqual(origin, self.server.game.window_origin(TOKEN_A))
        # Row tiles match the authoritative world (including any static NPC
        # overlay, e.g. Farmer Dan/the goblin, the same way the server
        # itself builds row data -- not the raw terrain, which omits them).
        for row in rows:
            self.assertEqual(
                row.tiles, self.server.game.window_row_tiles(row.origin_x, row.origin_y, TOKEN_A)
            )
        # The session survives and keeps playing.
        world_state = decode_world_state(
            self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        )
        self.assertEqual((world_state.player_x, world_state.player_y), spot)

    def _ack_edges_until(self, client, origin, target, seq=100, deadline_s=4.0):
        # Model a live client: apply each acknowledged cache step (deriving
        # the new origin from the strip geometry), ACK it, and repeat until
        # the window origin reaches the target. Retransmits are re-ACKed.
        origin = list(origin)
        last_revision = None
        deadline = time.monotonic() + deadline_s
        while tuple(origin) != tuple(target):
            self.assertLess(time.monotonic(), deadline, f"origin stuck at {origin}")
            packet = self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE})
            edge = decode_terrain_edge(packet)
            if edge.revision != last_revision:
                if edge.width == 1 and edge.origin_x == origin[0] + WINDOW_W:
                    origin[0] += 1
                elif edge.width == 1 and edge.origin_x == origin[0] - 1:
                    origin[0] -= 1
                elif edge.height == 1 and edge.origin_y == origin[1] + WINDOW_H:
                    origin[1] += 1
                elif edge.height == 1 and edge.origin_y == origin[1] - 1:
                    origin[1] -= 1
                else:
                    self.fail(f"non-adjacent step {edge.origin_x},{edge.origin_y} at {origin}")
                last_revision = edge.revision
            seq += 1
            client.sendall(
                encode_cache_step_ack(
                    CacheStepAckPacket(seq=seq, revision=edge.revision, origin_x=origin[0], origin_y=origin[1])
                )
            )
        return tuple(origin)

    def test_resync_request_small_gap_replays_edges(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        # Player at x=20 puts the window target at origin (4,0); acknowledge
        # the initial steps like a real client.
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=20, y=10), start=(11, 10))
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        self._ack_edges_until(client, (0, 0), (4, 0))
        deadline = time.monotonic() + 1.0
        while self.server.realtime_by_token[TOKEN_A].window_origin != (4, 0):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        # Claim the client window is 2 columns behind: the server rewinds
        # and replays relative steps (columns 34 and 35), no row fill.
        client.sendall(encode_resync_request(ResyncRequestPacket(seq=7, origin_x=2, origin_y=0)))
        edge_origins = []
        origin = [2, 0]
        last_revision = None
        while len(edge_origins) < 2:
            packet = self._recv_realtime_packet(client)
            self.assertNotEqual(packet[2], int(RealtimeType.WINDOW_ROW))
            if packet[2] != int(RealtimeType.TERRAIN_EDGE):
                continue
            edge = decode_terrain_edge(packet)
            if edge.revision != last_revision:
                edge_origins.append(edge.origin_x)
                origin[0] += 1
                last_revision = edge.revision
            client.sendall(
                encode_cache_step_ack(
                    CacheStepAckPacket(seq=8, revision=edge.revision, origin_x=origin[0], origin_y=origin[1])
                )
            )
        self.assertEqual(edge_origins, [2 + WINDOW_W, 3 + WINDOW_W])

    def test_cache_steps_pipeline_and_advance_only_on_ack(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=20, y=10), start=(11, 10))
        # The pipeline sends up to three consecutive steps without waiting:
        # distinct chained revisions covering columns 32, 33, 34.
        steps = [
            decode_terrain_edge(self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE}))
            for _ in range(3)
        ]
        first = steps[0]
        self.assertEqual(
            [step.revision for step in steps],
            [(first.revision + i) & 0xFFFF for i in range(3)],
        )
        self.assertEqual([step.origin_x for step in steps], [32, 33, 34])
        # Unacknowledged: the committed origin must not advance, and the
        # pipeline retransmits the same revisions byte-identically.
        session = self.server.realtime_by_token[TOKEN_A]
        self.assertEqual(session.window_origin, (0, 0))
        retransmit = decode_terrain_edge(
            self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE})
        )
        self.assertEqual(retransmit, first)
        # A cumulative ACK for the second step confirms the first two.
        client.sendall(
            encode_cache_step_ack(
                CacheStepAckPacket(seq=2, revision=steps[1].revision, origin_x=2, origin_y=0)
            )
        )
        deadline = time.monotonic() + 1.0
        while session.window_origin != (2, 0):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        # The pipeline tops up with fresh revisions past the third step.
        deadline = time.monotonic() + 2.0
        while True:
            self.assertLess(time.monotonic(), deadline)
            nxt = decode_terrain_edge(
                self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE})
            )
            if nxt.revision == (first.revision + 3) & 0xFFFF:
                break

    def test_duplicate_ack_triggers_fast_retransmit(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=20, y=10), start=(11, 10))
        steps = [
            decode_terrain_edge(self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE}))
            for _ in range(3)
        ]
        first = steps[0]
        # Apply step 1; steps 2/3 are "lost" client-side.
        client.sendall(
            encode_cache_step_ack(
                CacheStepAckPacket(seq=2, revision=first.revision, origin_x=1, origin_y=0)
            )
        )
        # Absorb the pipeline top-up, then wait past the fast-retransmit
        # rate limit but well short of the 0.5 s timer.
        time.sleep(0.2)
        self._drain(client)
        sent_at = time.monotonic()
        client.sendall(
            encode_cache_step_ack(
                CacheStepAckPacket(seq=3, revision=first.revision, origin_x=1, origin_y=0)
            )
        )
        nxt = decode_terrain_edge(
            self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE})
        )
        elapsed = time.monotonic() - sent_at
        self.assertEqual(nxt.revision, (first.revision + 1) & 0xFFFF)
        self.assertLess(elapsed, 0.35, "retransmit did not arrive fast")

    def test_cache_step_retry_ceiling_escalates_to_full_fill(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=20, y=10))
        # Never acknowledge: after the retry ceiling the server abandons the
        # step and streams a full window fill instead of stalling forever.
        rows = self._collect_window_rows(client)
        self.assertEqual(len(rows), WINDOW_H)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)

    def test_resync_request_at_session_origin_is_noop(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        client.sendall(encode_resync_request(ResyncRequestPacket(seq=7, origin_x=0, origin_y=0)))
        # No rows, no edges: only the normal per-tick stream continues.
        time.sleep(0.3)
        types = self._drain_frame_types(client)
        self.assertNotIn(int(RealtimeType.WINDOW_ROW), types)
        self.assertNotIn(int(RealtimeType.TERRAIN_EDGE), types)

    def test_resync_request_with_invalid_origin_streams_window_rows(self):
        # Unconstrained byte budget: this test asserts per-tick interleave,
        # not the scheduler's rate limiting.
        port = self._start_server(client_byte_rate=1e6)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        time.sleep(0.2)
        self._drain(client)
        client.sendall(encode_resync_request(ResyncRequestPacket(seq=7, origin_x=200, origin_y=0)))
        # Rows stream one per tick, interleaved with the per-tick WORLD_STATE
        # (a tick boundary may deliver a world state first).
        rows = []
        world_between = 0
        while len(rows) < 3:
            packet = self._recv_realtime_packet(client)
            if packet[2] == int(RealtimeType.WINDOW_ROW):
                rows.append(decode_window_row(packet))
            elif packet[2] == int(RealtimeType.WORLD_STATE):
                world_between += 1
        self.assertEqual([row.row_index for row in rows], [0, 1, 2])
        # WORLD_STATE keeps flowing during the fill (the scheduler coalesces
        # stale unsent snapshots, so the exact count depends on read pacing).
        self.assertGreaterEqual(world_between, 1)
        client.sendall(encode_resync_request(ResyncRequestPacket(seq=8, origin_x=200, origin_y=0)))
        row = decode_window_row(self._recv_packet_of_type(client, {RealtimeType.WINDOW_ROW}))
        self.assertEqual(row.row_index, 3)
        rows = self._collect_window_rows(client, expected=WINDOW_H - 4)
        self.assertEqual([row.row_index for row in rows], list(range(4, WINDOW_H)))
        world_state = decode_world_state(
            self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        )
        self.assertEqual((world_state.player_x, world_state.player_y), (11, 10))

    def test_resync_request_row_bitmap_resends_only_missing_rows(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        # Player at x=11,y=10 puts the window target at origin (0,0).
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        time.sleep(0.2)
        self._drain(client)
        # Invalid committed origin forces the fill path; the NACK bitmap
        # claims every row of the target-origin fill except 5 and 17.
        rows_have = 0xFFFFFF & ~((1 << 5) | (1 << 17))
        client.sendall(
            encode_resync_request(
                ResyncRequestPacket(
                    seq=7,
                    origin_x=200,
                    origin_y=0,
                    fill_origin_x=0,
                    fill_origin_y=0,
                    rows_have=rows_have,
                )
            )
        )
        rows = self._collect_window_rows(client, expected=2)
        self.assertEqual([row.row_index for row in rows], [5, 17])
        # The fill is complete: no further rows follow.
        time.sleep(0.3)
        types = self._drain_frame_types(client)
        self.assertNotIn(int(RealtimeType.WINDOW_ROW), types)

    def test_window_commit_advances_origin_and_resumes_edges(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        spot = self._far_quiet_spot()
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=spot[0], y=spot[1]))
        rows = self._collect_window_rows(client)
        session = next(s for s in self.server.sessions.values() if s.token is not None)
        self.assertTrue(session.fill_waiting_for_commit)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)
        # Walk far enough to move the window target; with the fill committed
        # the server resumes relative edge streaming from the new origin.
        # Move south: the quiet spot sits in the eastern clamp zone where
        # westward movement does not change the window origin.
        world = self.server.game.world_for(MAP_OVERWORLD)
        target = None
        for dy in range(4, 10):
            for dx in (0, -1, 1, -2, 2):
                if world.player_can_enter(spot[0] + dx, spot[1] + dy):
                    target = (spot[0] + dx, spot[1] + dy)
                    break
            if target:
                break
        self.assertIsNotNone(target, "no enterable tile south of the quiet spot")
        client.sendall(player_state(seq=2, x=target[0], y=target[1]))
        edge = decode_terrain_edge(
            self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE})
        )
        self.assertGreater(edge.width * edge.height, 0)

    def test_lost_window_commit_times_out_and_restarts_fill(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        spot = self._far_quiet_spot()
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=spot[0], y=spot[1]))
        rows = self._collect_window_rows(client)
        self.assertEqual(rows[0].fill_id, 1)
        # Never send the commit (lost in transit). The server must abandon
        # the stale transaction after WINDOW_COMMIT_TIMEOUT and start a
        # fresh fill instead of blocking edge streaming forever.
        retry_rows = self._collect_window_rows(client)
        self.assertEqual(retry_rows[0].fill_id, 2)
        self._commit_window_rows(client, retry_rows, MAP_OVERWORLD, seq=2)

    def test_duplicate_window_commit_is_harmless(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        spot = self._far_quiet_spot()
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=spot[0], y=spot[1]))
        rows = self._collect_window_rows(client)
        first = rows[0]
        origin = (first.origin_x, first.origin_y - first.row_index)
        session = next(s for s in self.server.sessions.values() if s.token is not None)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)
        time.sleep(0.3)
        self.assertEqual(session.window_origin, origin)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=3)
        time.sleep(0.3)
        self.assertEqual(session.window_origin, origin)
        self.assertIsNone(session.fill_origin)
        self.assertFalse(session.fill_waiting_for_commit)
        self.assertEqual(session.fill_id, first.fill_id)

    def test_map_change_resends_until_client_reports_ready(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=117, y=10))
        rows = self._collect_window_rows(client)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)
        # Step onto the cave entrance; the server answers MAP_CHANGE.
        client.sendall(player_state(seq=2, x=118, y=10))
        first = decode_map_change(
            self._recv_packet_of_type(client, {RealtimeType.MAP_CHANGE})
        )
        self.assertEqual(first.map_id, MAP_STARTER_CAVE)
        # Never send MAP_READY (simulating the packet lost on the serial
        # link): the server must re-send MAP_CHANGE with a fresh fill
        # instead of unpausing an unready client.
        second = decode_map_change(
            self._recv_packet_of_type(client, {RealtimeType.MAP_CHANGE}, limit=500)
        )
        self.assertEqual(second.map_id, MAP_STARTER_CAVE)
        self.assertEqual((second.spawn_x, second.spawn_y), (first.spawn_x, first.spawn_y))
        # Meanwhile the player stays paused and held at the spawn.
        player = self.server.game.players[TOKEN_A]
        self.assertTrue(player.transition_loading)
        self.assertEqual((player.x, player.y), (first.spawn_x, first.spawn_y))
        # MAP_READY ends the pause.
        client.sendall(encode_map_ready(MapReadyPacket(3, MAP_STARTER_CAVE, 0, 0)))
        deadline = time.monotonic() + 2.0
        while player.transition_loading and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(player.transition_loading)

    def test_window_commit_is_acked_and_duplicates_reacked(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        spot = self._far_quiet_spot()
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=spot[0], y=spot[1]))
        rows = self._collect_window_rows(client)
        first = rows[0]
        origin = (first.origin_x, first.origin_y - first.row_index)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)
        ack = decode_window_commit_ack(
            self._recv_packet_of_type(client, {RealtimeType.WINDOW_COMMIT_ACK})
        )
        self.assertEqual(ack.fill_id, first.fill_id)
        self.assertEqual((ack.origin_x, ack.origin_y), origin)
        # A retried commit (the ack was lost) is re-acked, not re-applied.
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=3)
        ack2 = decode_window_commit_ack(
            self._recv_packet_of_type(client, {RealtimeType.WINDOW_COMMIT_ACK})
        )
        self.assertEqual(ack2.fill_id, first.fill_id)
        session = self.server.realtime_by_token[TOKEN_A]
        self.assertEqual(session.window_origin, origin)
        self.assertIsNone(session.fill_origin)

    def test_stale_rows_after_commit_do_not_restart_fill(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        spot = self._far_quiet_spot()
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=spot[0], y=spot[1]))
        rows = self._collect_window_rows(client)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)
        self._recv_packet_of_type(client, {RealtimeType.WINDOW_COMMIT_ACK})
        # A NACK that references the committed (stale) fill id must not be
        # treated as progress for a live transaction; the server either
        # ignores it or starts a clean transaction -- never edges into a
        # half-fill. Here the gap is zero, so it must be a no-op.
        client.sendall(
            encode_resync_request(
                ResyncRequestPacket(
                    seq=3,
                    origin_x=rows[0].origin_x,
                    origin_y=rows[0].origin_y,
                    fill_origin_x=rows[0].origin_x,
                    fill_origin_y=rows[0].origin_y,
                    rows_have=0xFFFFFF,
                    fill_id=rows[0].fill_id,
                )
            )
        )
        time.sleep(0.3)
        session = self.server.realtime_by_token[TOKEN_A]
        self.assertFalse(session.fill_waiting_for_commit)

    def test_map_change_resend_preserves_inflight_fill(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=117, y=10))
        rows = self._collect_window_rows(client)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)
        self._recv_packet_of_type(client, {RealtimeType.WINDOW_COMMIT_ACK})
        client.sendall(player_state(seq=2, x=118, y=10))
        first = decode_map_change(
            self._recv_packet_of_type(client, {RealtimeType.MAP_CHANGE})
        )
        session = self.server.realtime_by_token[TOKEN_A]
        fill_id = session.fill_id
        # Withhold MAP_READY and the commit past the resend interval: the
        # MAP_CHANGE packet is re-sent, but the transition's fill keeps its
        # identity (a restart would discard the client's staged rows).
        second = decode_map_change(
            self._recv_packet_of_type(client, {RealtimeType.MAP_CHANGE}, limit=500)
        )
        self.assertEqual(second.map_id, first.map_id)
        self.assertEqual(session.fill_id, fill_id)

    def test_resync_request_new_fill_flag_starts_clean_fill(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        time.sleep(0.2)
        self._drain(client)
        # The client abandoned a dead staged fill: flags bit 1 demands a
        # clean transaction even though the committed origin matches (a
        # plain request with gap 0 would be a noop).
        client.sendall(
            encode_resync_request(
                ResyncRequestPacket(seq=7, origin_x=0, origin_y=0, flags=2)
            )
        )
        rows = self._collect_window_rows(client)
        self.assertEqual([row.row_index for row in rows], list(range(WINDOW_H)))
        self.assertGreaterEqual(rows[0].fill_id, 1)
        self._commit_window_rows(client, rows, MAP_OVERWORLD, seq=2)

    def test_resync_request_row_bitmap_wrong_fill_origin_streams_full_fill(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10), place=True)
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        time.sleep(0.2)
        self._drain(client)
        # Bitmap for a stale fill origin must be ignored: full 24-row fill.
        client.sendall(
            encode_resync_request(
                ResyncRequestPacket(
                    seq=7,
                    origin_x=200,
                    origin_y=0,
                    fill_origin_x=9,
                    fill_origin_y=9,
                    rows_have=0xFFFFFE,
                )
            )
        )
        rows = self._collect_window_rows(client, expected=WINDOW_H)
        self.assertEqual([row.row_index for row in rows], list(range(WINDOW_H)))

    def _enterable_far_tile(self):
        world = self.server.game.world_for(0)
        for y in range(40, world.height - 2):
            for x in range(70, world.width - 2):
                if world.player_can_enter(x, y):
                    return (x, y)
        raise AssertionError("no enterable far tile found")

    def test_idle_client_traffic_matches_single_player_baseline(self):
        port = self._start_server(tick_hz=20)
        self._bootstrap(port, TOKEN_A)
        self._bootstrap(port, TOKEN_B)
        # Park B on a tile far from A (outside B's window) and far from any
        # beaver, so its steady-state stream has no remote players and no
        # combat events: the single-player baseline is WORLD_STATE only.
        spot = self._far_quiet_spot()
        client_a = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=10, y=10))
        # The far teleport triggers an in-band window-row resync on the same
        # connection; wait for the 24 rows to finish streaming.
        client_b = self._open_realtime(port, TOKEN_B, player_state(seq=1, x=spot[0], y=spot[1]))
        rows_b = self._collect_window_rows(client_b)
        self._commit_window_rows(client_b, rows_b, MAP_OVERWORLD, seq=2)
        # Let the initial HUD/QUEST flush, then observe steady-state.
        time.sleep(0.5)
        self._drain(client_b)
        observed = []
        deadline = time.monotonic() + 1.0
        client_b.settimeout(1.5)
        while time.monotonic() < deadline:
            packet = self._recv_realtime_packet(client_b)
            observed.append(packet[2])
        self.assertTrue(observed)
        self.assertEqual(set(observed), {int(RealtimeType.WORLD_STATE)})

    def _far_quiet_spot(self):
        game = self.server.game
        world = game.world_for(0)
        beavers = [(b.x, b.y) for b in game.beavers if b.map_id == 0]
        for y in range(30, world.height - 2):
            for x in range(70, world.width - 2):
                if world.player_can_enter(x, y) and all(
                    abs(x - bx) + abs(y - by) >= 15 for bx, by in beavers
                ):
                    return (x, y)
        raise AssertionError("no quiet spot found")

    def _drain_frame_types(self, client):
        client.setblocking(False)
        blob = bytearray()
        try:
            while True:
                chunk = client.recv(1024)
                if not chunk:
                    break
                blob += chunk
        except BlockingIOError:
            pass
        finally:
            client.setblocking(True)
        types = set()
        for piece in bytes(blob).split(b"\x00"):
            if not piece:
                continue
            try:
                types.add(_normalize_realtime(piece)[2])
            except PacketError:
                pass
        return types

    def _drain(self, client):
        client.setblocking(False)
        try:
            while True:
                if not client.recv(4096):
                    break
        except BlockingIOError:
            pass
        finally:
            client.setblocking(True)


    def test_client_net_stats_are_received_and_recorded(self):
        port = self._start_server()
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=11, y=10))
        self._recv_packet_of_type(client, {RealtimeType.WORLD_STATE})
        client.sendall(
            encode_net_stats(
                NetStatsPacket(
                    seq=5,
                    rx_drops=3,
                    handler_overflows=1,
                    handler_serial_errors=2,
                    handler_last_status=0x50,
                    fill_id=7,
                    commit_pending=0,
                    origin_x=0,
                    origin_y=0,
                    cache_revision=0x0102,
                )
            )
        )
        deadline = time.monotonic() + 1.0
        session = self.server.realtime_by_token[TOKEN_A]
        while session.last_net_stats is None and time.monotonic() < deadline:
            time.sleep(0.01)
        stats = session.last_net_stats
        self.assertIsNotNone(stats)
        self.assertEqual(stats.rx_drops, 3)
        self.assertEqual(stats.handler_overflows, 1)
        self.assertEqual(stats.handler_last_status, 0x50)
        self.assertEqual(stats.cache_revision, 0x0102)

    def test_cache_steps_converge_with_seeded_step_loss(self):
        # A client that "loses" the first transmission of every 3rd step
        # (ignoring it until the retransmit) still converges: revisions apply
        # exactly once and the origin reaches the target.
        port = self._start_server(client_byte_rate=1e6)
        self._bootstrap(port, TOKEN_A)
        client = self._open_realtime(port, TOKEN_A, player_state(seq=1, x=20, y=10), start=(11, 10))
        origin = [0, 0]
        seen: dict[int, int] = {}
        applied: list[int] = []
        deadline = time.monotonic() + 8.0
        while tuple(origin) != (4, 0):
            self.assertLess(time.monotonic(), deadline, f"origin stuck at {origin}")
            edge = decode_terrain_edge(
                self._recv_packet_of_type(client, {RealtimeType.TERRAIN_EDGE})
            )
            seen[edge.revision] = seen.get(edge.revision, 0) + 1
            if edge.revision not in applied:
                if len(applied) % 3 == 2 and seen[edge.revision] == 1:
                    continue  # drop the first transmission of every 3rd step
                origin[0] += 1
                applied.append(edge.revision)
            client.sendall(
                encode_cache_step_ack(
                    CacheStepAckPacket(
                        seq=10 + len(applied), revision=edge.revision, origin_x=origin[0], origin_y=origin[1]
                    )
                )
            )
        self.assertEqual(applied, sorted(applied))
        self.assertEqual(len(applied), len(set(applied)))
        deadline = time.monotonic() + 1.0
        while self.server.realtime_by_token[TOKEN_A].window_origin != (4, 0):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)


class SessionOutputTest(unittest.TestCase):
    def _drain_frames(self, out):
        frames = []
        while True:
            nxt = out.next_frame()
            if nxt is None:
                return frames
            frames.append(nxt[0])

    def test_priorities_and_coalescing(self):
        out = SessionOutput(rate=1e9, burst=1 << 20)
        out.queue_latest("world", b"w1")
        out.queue_latest("world", b"w2")  # replaces w1
        out.queue_reliable(b"r1")
        out.queue_reliable(b"r2")
        out.queue_message(b"m1")
        out.queue_latest("hud", b"h1")
        self.assertEqual(self._drain_frames(out), [b"r1", b"r2", b"w2", b"h1", b"m1"])
        self.assertEqual(out.frames_coalesced, 1)

    def test_dialogue_is_a_registered_latest_slot(self):
        # Regression: _send_tick_packets queues the paged-dialogue page via
        # queue_latest("dialogue"), which KeyErrors unless the slot exists.
        out = SessionOutput(rate=1e9, burst=1 << 20)
        self.assertIn("dialogue", out.LATEST_ORDER)
        out.queue_latest("dialogue", b"d1")
        out.queue_latest("dialogue", b"d2")  # coalesces, no KeyError
        self.assertIn(b"d2", self._drain_frames(out))

    def test_message_queue_is_bounded(self):
        out = SessionOutput(rate=1e9, burst=1 << 20)
        for index in range(20):
            out.queue_message(bytes([index]))
        frames = self._drain_frames(out)
        self.assertLessEqual(len(frames), 8)
        self.assertEqual(frames[-1], bytes([19]))

    def test_flush_completes_partial_frames_without_interleaving(self):
        server = FujiRealmHybridServer("127.0.0.1", 0)
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        a.setblocking(False)
        b.setblocking(False)
        session = ClientSession(a, ("local", 0), time.monotonic())
        session.out.rate = 1e9
        session.out.burst = 1 << 20
        session.out.tokens = float(1 << 20)
        payloads = [bytes([i]) * 60 + b"\x00" for i in range(200)]
        for payload in payloads:
            session.out.queue_reliable(payload)
        received = bytearray()
        deadline = time.monotonic() + 5.0
        while (session.out.pending() or session.out.partial is not None) and time.monotonic() < deadline:
            self.assertTrue(server._flush_session_output(session, time.monotonic()))
            try:
                while True:
                    chunk = b.recv(4096)
                    if not chunk:
                        break
                    received += chunk
            except BlockingIOError:
                pass
        self.assertEqual(bytes(received), b"".join(payloads))
        self.assertGreaterEqual(session.out.write_blocked + session.out.partial_writes, 0)

    def test_token_bucket_defers_frames(self):
        server = FujiRealmHybridServer("127.0.0.1", 0)
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        a.setblocking(False)
        session = ClientSession(a, ("local", 0), time.monotonic())
        session.out.rate = 0.0  # no refill during the test
        session.out.burst = 50
        session.out.tokens = 50.0
        for index in range(10):
            session.out.queue_reliable(bytes([index]) * 20)
        self.assertTrue(server._flush_session_output(session, time.monotonic()))
        received = b.recv(4096)
        # 50-token burst admits frames 0..2 (tokens go 50->30->10->-10).
        self.assertEqual(len(received), 60)
        self.assertTrue(session.out.pending())
        self.assertEqual(session.out.budget_deferred, 1)

if __name__ == "__main__":
    unittest.main()
