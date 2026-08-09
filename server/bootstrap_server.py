"""Authoritative FujiRealm TCP server."""

from __future__ import annotations

import argparse
import select
import socket
import time

try:
    from .game import GameState
    from .protocol import (
        Hello,
        InputIntent,
        PacketStreamDecoder,
        PacketType,
        Welcome,
        decode_hello,
        decode_input,
        encode_snapshot,
        encode_welcome,
        encode_window,
        window_chunks,
    )
except ImportError:  # pragma: no cover - direct script execution
    from game import GameState
    from protocol import (
        Hello,
        InputIntent,
        PacketStreamDecoder,
        PacketType,
        Welcome,
        decode_hello,
        decode_input,
        encode_snapshot,
        encode_welcome,
        encode_window,
        window_chunks,
    )


REGISTER = b"REGISTER"
SMOKE_PROBE = 0x42
NEUTRAL_STICK = 0x0F


def strip_register(data: bytes, debug: bool = False) -> bytes:
    if not data.startswith(REGISTER):
        return data
    if debug:
        print("rx REGISTER")
    return data[len(REGISTER) :]


class BootstrapServer:
    def __init__(self, host: str, port: int, tick_hz: int = 10, debug: bool = False) -> None:
        self.host = host
        self.port = port
        self.tick_hz = tick_hz
        self.debug = debug
        self.sessions: dict[int, GameState] = {}

    def serve_once(self) -> None:
        with socket.create_server((self.host, self.port), reuse_port=False) as server:
            server.listen(1)
            if self.debug:
                print(f"listening {self.host}:{self.port}")
            conn, addr = server.accept()
            with conn:
                if self.debug:
                    print(f"client {addr[0]}:{addr[1]}")
                self.handle_client(conn)

    def handle_client(self, conn: socket.socket) -> None:
        conn.setblocking(False)
        decoder = PacketStreamDecoder()
        game = GameState(seed=1)
        pending = bytearray()
        hello_seen = False
        latest_input = InputIntent(0, NEUTRAL_STICK, 0, 0, 0)
        input_pending = False
        pending_fire = 0
        window_origin = (0, 0)
        queued_windows: list[bytes] = []
        tick_interval = 1.0 / max(1, self.tick_hz)
        next_tick = time.monotonic() + tick_interval

        while True:
            timeout = max(0.0, next_tick - time.monotonic()) if hello_seen else None
            readable, _, _ = select.select([conn], [], [], timeout)
            if readable:
                chunk = conn.recv(1024)
                if not chunk:
                    return
                if self.debug:
                    print(f"rx raw {chunk.hex()}")
                if not hello_seen:
                    chunk = strip_register(chunk, self.debug)
                    if chunk.startswith(bytes((SMOKE_PROBE,))):
                        conn.sendall(bytes((SMOKE_PROBE,)))
                        if self.debug:
                            print("rx/tx smoke probe 42")
                        chunk = chunk[1:]
                pending.extend(chunk)
                packets = decoder.feed(bytes(pending))
                pending.clear()
                for packet in packets:
                    if packet.packet_type == PacketType.HELLO:
                        hello = decode_hello(packet.payload)
                        if hello.token:
                            game = self.sessions.get(hello.token)
                            if game is None:
                                game = GameState(seed=hello.seed or 1)
                                self.sessions[hello.token] = game
                        else:
                            game = GameState(seed=hello.seed or 1)
                        conn.sendall(encode_welcome(Welcome(player_id=1, seed=game.seed)))
                        window = game.window()
                        window_origin = (window.origin_x, window.origin_y)
                        for chunk in window_chunks(window):
                            conn.sendall(encode_window(chunk))
                        hello_seen = True
                        next_tick = time.monotonic() + tick_interval
                        if self.debug:
                            print(f"rx HELLO flags={hello.flags:02x} seed={hello.seed} token={hello.token}")
                    elif packet.packet_type == PacketType.INPUT:
                        player_input = decode_input(packet.payload)
                        latest_input = player_input
                        input_pending = True
                        pending_fire = player_input.buttons
                        if self.debug:
                            print(
                                "rx INPUT "
                                f"tick={player_input.tick} raw={player_input.direction:02x} "
                                f"buttons={player_input.buttons:02x} aim={player_input.aim}"
                            )
            if hello_seen and time.monotonic() >= next_tick:
                if input_pending:
                    tick_input = InputIntent(
                        game.tick + 1,
                        latest_input.direction,
                        pending_fire,
                        latest_input.aim,
                        latest_input.ack_tick,
                    )
                else:
                    tick_input = InputIntent(
                        game.tick + 1,
                        NEUTRAL_STICK,
                        0,
                        latest_input.aim,
                        latest_input.ack_tick,
                    )
                input_pending = False
                pending_fire = 0
                game.step(tick_input)
                sent_window_chunk = False
                if game.needs_window(*window_origin) and not queued_windows:
                    next_origin = game.next_window_origin(*window_origin)
                    window = game.edge_window(*window_origin, *next_origin)
                    queued_windows.extend(encode_window(chunk) for chunk in window_chunks(window))
                if queued_windows:
                    conn.sendall(queued_windows.pop(0))
                    sent_window_chunk = True
                    window_origin = next_origin
                snapshot = game.snapshot_for_window(*window_origin)
                conn.sendall(encode_snapshot(snapshot))
                if self.debug:
                    print(
                        f"tx TICK {game.tick} "
                        f"input_raw={tick_input.direction:02x} buttons={tick_input.buttons:02x} "
                        f"aim={tick_input.aim} player={snapshot.player_x},{snapshot.player_y} "
                        f"beavers={len(snapshot.beavers)} window={window_origin[0]},{window_origin[1]} "
                        f"window_chunk={int(sent_window_chunk)}"
                    )
                next_tick += tick_interval
                now = time.monotonic()
                if next_tick <= now:
                    next_tick = now + tick_interval


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--tick-hz", type=int, default=10)
    parser.add_argument("--edge-budget", type=int, default=4)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    server = BootstrapServer(args.host, args.port, args.tick_hz, args.debug)
    if args.once:
        server.serve_once()
        return 0
    while True:
        server.serve_once()


if __name__ == "__main__":
    raise SystemExit(main())
