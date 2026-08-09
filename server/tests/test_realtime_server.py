import socket
import threading
import time
import unittest

from server.protocol import (
    PacketError,
    _normalize_realtime,
    PlayerStatePacket,
    RealtimeType,
    decode_terrain_edge,
    decode_world_state,
    encode_player_state,
)
from server.realtime_server import FujiRealmRealtimeServer


class RealtimeServerTest(unittest.TestCase):
    def _free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def _send_until_response(self, client, packet, port, timeout=1.0):
        deadline = time.monotonic() + timeout
        client.settimeout(0.05)
        while True:
            client.sendto(packet, ("127.0.0.1", port))
            try:
                return client.recvfrom(128)
            except socket.timeout:
                if time.monotonic() >= deadline:
                    raise

    def test_realtime_server_replies_with_world_state(self):
        port = self._free_port()
        server = FujiRealmRealtimeServer("127.0.0.1", port, tick_hz=30, debug=False)
        thread = threading.Thread(target=lambda: server.serve_once(duration=0.5), daemon=True)
        thread.start()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            response, _ = self._send_until_response(
                client,
                encode_player_state(
                    PlayerStatePacket(
                        seq=1,
                        x=11,
                        y=10,
                        facing=0,
                        buttons=0,
                        fire_counter=0,
                        pickup_counter=0,
                        last_server_seq=0,
                    )
                ),
                port,
            )
            state = decode_world_state(response)
            self.assertEqual((state.player_x, state.player_y), (11, 10))
            self.assertEqual(state.echo_client_seq, 1)
            self.assertEqual(state.correction_flags, 0)

        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())

    def test_realtime_server_corrects_blocked_player_state(self):
        port = self._free_port()
        server = FujiRealmRealtimeServer("127.0.0.1", port, tick_hz=30, debug=False)
        thread = threading.Thread(target=lambda: server.serve_once(duration=0.5), daemon=True)
        thread.start()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            response, _ = self._send_until_response(
                client,
                encode_player_state(
                    PlayerStatePacket(
                        seq=1,
                        x=0,
                        y=0,
                        facing=0,
                        buttons=0,
                        fire_counter=0,
                        pickup_counter=0,
                        last_server_seq=0,
                    )
                ),
                port,
            )
            state = decode_world_state(response)
            self.assertEqual((state.player_x, state.player_y), (10, 10))
            self.assertEqual(state.correction_flags, 1)

        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())

    def test_realtime_server_sends_terrain_edge_before_world_state_at_cache_margin(self):
        port = self._free_port()
        server = FujiRealmRealtimeServer("127.0.0.1", port, tick_hz=30, debug=False)
        thread = threading.Thread(target=lambda: server.serve_once(duration=0.5), daemon=True)
        thread.start()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            packet = encode_player_state(
                PlayerStatePacket(
                    seq=1,
                    x=25,
                    y=10,
                    facing=0,
                    buttons=0,
                    fire_counter=0,
                    pickup_counter=0,
                    last_server_seq=0,
                )
            )
            deadline = time.monotonic() + 1.0
            client.settimeout(0.05)
            terrain = None
            world = None
            while time.monotonic() < deadline and (terrain is None or world is None):
                client.sendto(packet, ("127.0.0.1", port))
                try:
                    response, _ = client.recvfrom(128)
                except socket.timeout:
                    continue
                try:
                    raw = _normalize_realtime(response)
                except PacketError:
                    continue
                if raw[2] == RealtimeType.TERRAIN_EDGE and terrain is None:
                    terrain = response
                elif raw[2] == RealtimeType.WORLD_STATE and world is None:
                    world = response
            self.assertIsNotNone(terrain)
            self.assertIsNotNone(world)
            edge = decode_terrain_edge(terrain)
            state = decode_world_state(world)
            self.assertEqual((edge.origin_x, edge.origin_y, edge.width, edge.height), (32, 0, 1, 24))
            self.assertEqual((state.player_x, state.player_y), (25, 10))

        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
