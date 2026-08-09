"""EDGE-style realtime UDP server prototype for FujiRealm."""

from __future__ import annotations

import argparse
import socket
import time

try:
    from .game import GameState
    from .protocol import (
        PacketError,
        PlayerStatePacket,
        RealtimeType,
        TerrainEdgePacket,
        WorldStatePacket,
        decode_player_state,
        encode_terrain_edge,
        encode_world_state,
        seq_delta,
    )
except ImportError:  # pragma: no cover - direct script execution
    from game import GameState
    from protocol import (
        PacketError,
        PlayerStatePacket,
        RealtimeType,
        TerrainEdgePacket,
        WorldStatePacket,
        decode_player_state,
        encode_terrain_edge,
        encode_world_state,
        seq_delta,
    )


class FujiRealmRealtimeServer:
    def __init__(
        self,
        host: str,
        port: int,
        tick_hz: int = 10,
        debug: bool = False,
        edge_budget: int = 4,
    ) -> None:
        self.host = host
        self.port = port
        self.tick_hz = tick_hz
        self.debug = debug
        self.edge_budget = edge_budget

    def serve_once(self, duration: float | None = None, game: GameState | None = None) -> None:
        game = game if game is not None else GameState(seed=1)
        latest_player: PlayerStatePacket | None = None
        latest_client_seq: int | None = None
        target: tuple[str, int] | None = None
        server_seq = 0
        window_origin = game.window_origin()
        next_tick = time.monotonic()
        stop_at = None if duration is None else next_tick + duration
        tick_interval = 1.0 / max(1, self.tick_hz)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.setblocking(False)
            if self.debug:
                print(f"realtime listening {self.host}:{self.port}")
            while stop_at is None or time.monotonic() < stop_at:
                try:
                    data, addr = sock.recvfrom(2048)
                except BlockingIOError:
                    pass
                else:
                    try:
                        player = decode_player_state(data)
                    except PacketError:
                        continue
                    if latest_client_seq is None or seq_delta(player.seq, latest_client_seq) > 0:
                        latest_player = player
                        latest_client_seq = player.seq
                        target = addr
                        if self.debug:
                            print(
                                f"rx PLAYER_STATE seq={player.seq} pos={player.x},{player.y} "
                                f"facing={player.facing} buttons={player.buttons:02x} "
                                f"fire={player.fire_counter} pickup={player.pickup_counter}"
                            )

                now = time.monotonic()
                if now < next_tick:
                    time.sleep(min(0.001, next_tick - now))
                    continue

                snapshot, accepted = game.step_player_state(latest_player)
                if latest_player is not None and not accepted and self.debug:
                    print(
                        "tx correction "
                        f"seq={server_seq} client={latest_player.seq} "
                        f"server_pos={snapshot.player_x},{snapshot.player_y}"
                    )
                if target is not None:
                    edge_budget = self.edge_budget
                    while edge_budget > 0 and not game.window_origin_matches_player(*window_origin):
                        next_origin = game.next_window_origin_toward_player(*window_origin)
                        edge = game.edge_window(window_origin[0], window_origin[1], next_origin[0], next_origin[1])
                        edge_seq = server_seq
                        edge_packet = TerrainEdgePacket(
                            seq=edge_seq,
                            origin_x=edge.origin_x,
                            origin_y=edge.origin_y,
                            width=edge.width,
                            height=edge.height,
                            tiles=edge.tiles,
                        )
                        sock.sendto(encode_terrain_edge(edge_packet), target)
                        window_origin = next_origin
                        edge_budget -= 1
                        server_seq = (server_seq + 1) & 0xFFFF
                        if self.debug:
                            print(
                                f"tx TERRAIN_EDGE seq={edge_seq} "
                                f"origin={edge.origin_x},{edge.origin_y} size={edge.width}x{edge.height} "
                                f"window={window_origin[0]},{window_origin[1]}"
                            )
                    packet = WorldStatePacket(
                        seq=server_seq,
                        player_x=snapshot.player_x,
                        player_y=snapshot.player_y,
                        health=snapshot.health,
                        correction_flags=0 if accepted else 1,
                        beavers=snapshot.beavers,
                        tile_x=snapshot.tile_x,
                        tile_y=snapshot.tile_y,
                        tile_id=snapshot.tile_id,
                        echo_client_seq=latest_client_seq or 0,
                    )
                    sock.sendto(encode_world_state(packet), target)
                    if self.debug:
                        print(
                            f"tx WORLD_STATE seq={server_seq} echo={packet.echo_client_seq} "
                            f"corr={packet.correction_flags} player={packet.player_x},{packet.player_y} "
                            f"beavers={len(packet.beavers)} window={window_origin[0]},{window_origin[1]} "
                            f"tile={packet.tile_x},{packet.tile_y}:{packet.tile_id}"
                        )
                    server_seq = (server_seq + 1) & 0xFFFF
                next_tick += tick_interval
                if next_tick <= now:
                    next_tick = now + tick_interval


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--tick-hz", type=int, default=10)
    parser.add_argument("--edge-budget", type=int, default=4)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    FujiRealmRealtimeServer(args.host, args.port, args.tick_hz, args.debug, args.edge_budget).serve_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
