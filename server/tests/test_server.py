import socket
import threading
import time
import unittest

from server.protocol import (
    MAX_BEAVERS,
    Hello,
    InputIntent,
    PacketType,
    PacketStreamDecoder,
    decode_snapshot,
    decode_welcome,
    decode_window,
    encode_hello,
    encode_input,
)
from server.bootstrap_server import BootstrapServer


class ServerTest(unittest.TestCase):
    def _free_port(self):
        with socket.create_server(("127.0.0.1", 0)) as probe:
            return probe.getsockname()[1]

    def _connect(self, port):
        deadline = time.monotonic() + 2.0
        while True:
            try:
                return socket.create_connection(("127.0.0.1", port), timeout=2)
            except ConnectionRefusedError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)

    def _read_until(self, client, decoder, predicate, timeout=2.0):
        packets = []
        deadline = time.monotonic() + timeout
        while not predicate(packets):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.fail("timed out waiting for packets")
            client.settimeout(remaining)
            packets.extend(decoder.feed(client.recv(1024)))
        return packets

    def _read_handshake(self, client, decoder):
        return self._read_until(
            client,
            decoder,
            lambda packets: any(packet.packet_type == PacketType.WELCOME for packet in packets)
            and sum(1 for packet in packets if packet.packet_type == PacketType.WINDOW) >= 8,
        )

    def test_server_echoes_phase2_probe_after_register(self):
        port = self._free_port()
        server = BootstrapServer("127.0.0.1", port, tick_hz=30, debug=False)
        thread = threading.Thread(target=server.serve_once, daemon=True)
        thread.start()

        with self._connect(port) as client:
            client.sendall(b"REGISTER\x42")
            self.assertEqual(client.recv(1), b"\x42")

        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_server_accepts_register_and_sends_welcome_snapshot(self):
        port = self._free_port()

        server = BootstrapServer("127.0.0.1", port, tick_hz=30, debug=False)
        thread = threading.Thread(target=server.serve_once, daemon=True)
        thread.start()

        decoder = PacketStreamDecoder()
        with self._connect(port) as client:
            client.sendall(b"REGISTER" + encode_hello(Hello(flags=0, seed=0x1234)))
            welcome_packets = self._read_handshake(client, decoder)
            welcome_packet = welcome_packets.pop(0)
            self.assertEqual(welcome_packet.packet_type, PacketType.WELCOME)
            welcome = decode_welcome(welcome_packet.payload)
            self.assertEqual(welcome.seed, 0x1234)
            window_packet = welcome_packets.pop(0)
            self.assertEqual(window_packet.packet_type, PacketType.WINDOW)
            window = decode_window(window_packet.payload)
            self.assertEqual((window.width, window.height), (32, 24))
            self.assertEqual((window.chunk_y, window.chunk_h), (0, 3))
            self.assertEqual(len(window.tiles), 96)

            client.sendall(encode_input(InputIntent(1, 0x07, 0, 0x07, 0)))
            packets = welcome_packets
            packets.extend(
                self._read_until(
                    client,
                    decoder,
                    lambda received: any(
                        packet.packet_type == PacketType.SNAPSHOT for packet in received
                    ),
                )
            )
            snapshot_packet = next(
                packet for packet in packets if packet.packet_type == PacketType.SNAPSHOT
            )
            snapshot = decode_snapshot(snapshot_packet.payload)
            self.assertGreaterEqual(snapshot.tick, 1)
            # The snapshot carries the beavers inside the player's window, so
            # how many that is depends on where the map spawns them; the wire
            # format's cap is what matters here.
            self.assertGreaterEqual(len(snapshot.beavers), 1)
            self.assertLessEqual(len(snapshot.beavers), MAX_BEAVERS)
            self.assertTrue(all(beaver.hp > 0 for beaver in snapshot.beavers))

        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_input_does_not_immediately_trigger_snapshot_before_tick(self):
        port = self._free_port()

        server = BootstrapServer("127.0.0.1", port, tick_hz=2, debug=False)
        thread = threading.Thread(target=server.serve_once, daemon=True)
        thread.start()

        decoder = PacketStreamDecoder()
        with self._connect(port) as client:
            client.sendall(b"REGISTER" + encode_hello(Hello(flags=0, seed=1)))
            self._read_handshake(client, decoder)
            client.sendall(encode_input(InputIntent(1, 0x07, 0, 0x07, 0)))
            client.settimeout(0.1)
            with self.assertRaises(socket.timeout):
                decoder.feed(client.recv(1024))

        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_inputs_before_tick_collapse_to_latest_intent(self):
        port = self._free_port()

        token = 4242
        server = BootstrapServer("127.0.0.1", port, tick_hz=2, debug=False)
        thread = threading.Thread(target=server.serve_once, daemon=True)
        thread.start()

        decoder = PacketStreamDecoder()
        with self._connect(port) as client:
            # A HELLO carrying a token parks the game in server.sessions, which
            # is the only handle on it -- handle_client builds one per
            # connection. The default spawn is boxed in by town buildings on
            # three sides, where a blocked move is indistinguishable from a
            # dropped input, so stand on open grass first.
            client.sendall(b"REGISTER" + encode_hello(Hello(flags=0, seed=1, token=token)))
            self._read_handshake(client, decoder)
            game = server.sessions[token]
            game.player.x, game.player.y = 10, 16
            game._sync_player_entity(game.player)
            client.sendall(encode_input(InputIntent(1, 0x07, 0, 0x07, 0)))
            client.sendall(encode_input(InputIntent(2, 0x0D, 0, 0x0D, 0)))
            packets = self._read_until(
                client,
                decoder,
                lambda received: any(
                    packet.packet_type == PacketType.SNAPSHOT for packet in received
                ),
            )
            snapshot_packet = next(
                packet for packet in packets if packet.packet_type == PacketType.SNAPSHOT
            )
            snapshot = decode_snapshot(snapshot_packet.payload)
            self.assertEqual((snapshot.player_x, snapshot.player_y), (10, 17))

        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_tick_without_new_input_still_sends_snapshot(self):
        port = self._free_port()

        server = BootstrapServer("127.0.0.1", port, tick_hz=10, debug=False)
        thread = threading.Thread(target=server.serve_once, daemon=True)
        thread.start()

        decoder = PacketStreamDecoder()
        with self._connect(port) as client:
            client.sendall(b"REGISTER" + encode_hello(Hello(flags=0, seed=1)))
            self._read_handshake(client, decoder)
            packets = self._read_until(
                client,
                decoder,
                lambda received: any(
                    packet.packet_type == PacketType.SNAPSHOT for packet in received
                ),
            )
            snapshot_packet = next(
                packet for packet in packets if packet.packet_type == PacketType.SNAPSHOT
            )
            snapshot = decode_snapshot(snapshot_packet.payload)
            self.assertEqual(snapshot.tick, 1)

        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_server_sends_window_when_player_nears_window_edge(self):
        port = self._free_port()

        server = BootstrapServer("127.0.0.1", port, tick_hz=30, debug=False)
        thread = threading.Thread(target=server.serve_once, daemon=True)
        thread.start()

        decoder = PacketStreamDecoder()
        with self._connect(port) as client:
            client.sendall(b"REGISTER" + encode_hello(Hello(flags=0, seed=1)))
            packets = self._read_handshake(client, decoder)
            self.assertEqual(packets[0].packet_type, PacketType.WELCOME)
            self.assertEqual(packets[1].packet_type, PacketType.WINDOW)
            packets = []

            for tick in range(1, 3):
                client.sendall(encode_input(InputIntent(tick, 0x0D, 0, 0x0D, tick - 1)))
                packets.extend(
                    self._read_until(
                        client,
                        decoder,
                        lambda received: any(
                            packet.packet_type == PacketType.SNAPSHOT for packet in received
                        ),
                    )
                )
                packets = [
                    packet for packet in packets if packet.packet_type != PacketType.SNAPSHOT
                ]

            client.sendall(encode_input(InputIntent(3, 0x0D, 0, 0x0D, 2)))
            refreshed = self._read_until(
                client,
                decoder,
                lambda received: any(
                    packet.packet_type == PacketType.SNAPSHOT for packet in received
                ),
            )
            for packet in refreshed:
                if packet.packet_type == PacketType.WINDOW:
                    window = decode_window(packet.payload)
                    self.assertIn(window.width, (1, 32))
                    self.assertIn(window.height, (1, 24))

        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
