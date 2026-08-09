"""Human-like AI test clients for the FujiRealm hybrid server.

Each named bot is a full protocol client on plain TCP: it resumes (or
registers) an identity on the login server, bootstraps terrain over the
framed byte-stream protocol, then attaches to the realtime port and plays --
acknowledged cache steps, window fills with commit/NACK recovery, MAP_READY
after map changes, the same dance the Atari client performs. Navigation uses
only terrain the server has actually sent.

Behavior: wanders with a persistent heading and destination episodes
(strolls, pauses, town visits, occasional cave trips), never enters the PvP
realm, never initiates combat, retaliates only after taking damage, and only
picks up loot dropped by enemies it killed itself. Bots avoid crowding real
players and each other. Identity tokens persist in a local state file so a
named bot is the same character across restarts.

Usage (from the repository root, or as a plain script from anywhere):
    python3 -m server.ai_player --server fujinet.online --names Zorak,Mira
    python3 /path/to/server/ai_player.py --names LocalTest --no-breaks
"""

from __future__ import annotations

import argparse
import json
import math
import random
import socket
import threading
import time
from pathlib import Path

try:
    from .protocol import (
        LOGIN_OK,
        REALTIME_PREAMBLE,
        RESUME_OK,
        RENAME_OK,
        WINDOW_H,
        WINDOW_W,
        AuthPacket,
        CacheStepAckPacket,
        Hello,
        LoginRequest,
        MapReadyPacket,
        PacketError,
        PacketStreamDecoder,
        PacketType,
        PlayerStatePacket,
        RealtimeType,
        RenameRequest,
        ResumeRequest,
        ResyncRequestPacket,
        WindowCommitPacket,
        _normalize_realtime,
        decode_hud_update,
        decode_item_drops,
        decode_login_response,
        decode_map_change,
        decode_message,
        decode_remote_players,
        decode_rename_response,
        decode_respawn_event,
        decode_resume_response,
        decode_terrain_edge,
        decode_window,
        decode_window_commit_ack,
        decode_window_row,
        decode_world_state,
        encode_auth,
        encode_cache_step_ack,
        encode_hello,
        encode_login_request,
        encode_map_ready,
        encode_player_state,
        encode_realtime_bye,
        encode_rename_request,
        encode_resume_request,
        encode_resync_request,
        encode_window_commit,
    )
    from .world import (
        CAVE_ENTRANCE,
        CAVE_EXIT,
        HERB,
        MAP_OVERWORLD,
        MAP_PVP_REALM,
        MAP_STARTER_CAVE,
        PLAYER_BLOCKING,
    )
    from .world_layout_data import (
        OVERWORLD_CAVE_ENTRANCE,
        OVERWORLD_PVP_REALM_ENTRANCE,
        OVERWORLD_START,
        PVP_REALM_EXIT,
        STARTER_CAVE_EXIT,
    )
except ImportError:  # pragma: no cover - direct script execution
    # Run as a plain script (python3 path/to/server/ai_player.py): put the
    # repository root on the path so the server package imports resolve.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from server.protocol import (
        LOGIN_OK,
        REALTIME_PREAMBLE,
        RESUME_OK,
        RENAME_OK,
        WINDOW_H,
        WINDOW_W,
        AuthPacket,
        CacheStepAckPacket,
        Hello,
        LoginRequest,
        MapReadyPacket,
        PacketError,
        PacketStreamDecoder,
        PacketType,
        PlayerStatePacket,
        RealtimeType,
        RenameRequest,
        ResumeRequest,
        ResyncRequestPacket,
        WindowCommitPacket,
        _normalize_realtime,
        decode_hud_update,
        decode_item_drops,
        decode_login_response,
        decode_map_change,
        decode_message,
        decode_remote_players,
        decode_rename_response,
        decode_respawn_event,
        decode_resume_response,
        decode_terrain_edge,
        decode_window,
        decode_window_commit_ack,
        decode_window_row,
        decode_world_state,
        encode_auth,
        encode_cache_step_ack,
        encode_hello,
        encode_login_request,
        encode_map_ready,
        encode_player_state,
        encode_realtime_bye,
        encode_rename_request,
        encode_resume_request,
        encode_resync_request,
        encode_window_commit,
    )
    from server.world import (
        CAVE_ENTRANCE,
        CAVE_EXIT,
        HERB,
        MAP_OVERWORLD,
        MAP_PVP_REALM,
        MAP_STARTER_CAVE,
        PLAYER_BLOCKING,
    )
    from server.world_layout_data import (
        OVERWORLD_CAVE_ENTRANCE,
        OVERWORLD_PVP_REALM_ENTRANCE,
        OVERWORLD_START,
        PVP_REALM_EXIT,
        STARTER_CAVE_EXIT,
    )


REGISTER = b"REGISTER"
DEFAULT_PORT = 9000
DEFAULT_LOGIN_PORT = 9010
DEFAULT_STATE_FILE = "ai_players_state.json"
USERNAME_MAX = 10

# Client facing codes (game.py CLIENT_AIM_*).
FACE_UP, FACE_DOWN, FACE_LEFT, FACE_RIGHT = 0, 1, 2, 3
STEPS = {FACE_UP: (0, -1), FACE_DOWN: (0, 1), FACE_LEFT: (-1, 0), FACE_RIGHT: (1, 0)}

STATE_SEND_INTERVAL = 0.15
COMMIT_RETRY_INTERVAL = 0.75
COMMIT_RETRY_LIMIT = 8
FILL_NACK_INTERVAL = 1.0
FULL_ROWS_MASK = (1 << WINDOW_H) - 1
RETALIATE_WINDOW = 12.0
RETALIATE_MAX_CHASE = 4
LOOT_WINDOW = 10.0
FLEE_HEALTH_FRACTION = 0.3
CROWD_DISTANCE = 5
CROWD_PATIENCE = 10.0
STATUS_INTERVAL = 30.0
# Movement is greedy nearest-tile hill-climbing, not real pathfinding: in a
# maze-like area (e.g. the walled town's checkerboard buildings) it can find
# only one legal neighbor at a dead-end pocket and ping-pong between it and
# the tile before it forever. Each such step "succeeds" (a legal move was
# made), so stuck_count alone never catches it. Track the best distance to
# the current target and give up the goal if it hasn't improved recently.
NAV_STALL_TIMEOUT = 5.0


def manhattan(ax: int, ay: int, bx: int, by: int) -> int:
    return abs(ax - bx) + abs(ay - by)


class SessionEnded(Exception):
    """Realtime connection closed or failed; reconnect after backoff."""


class TokenStore:
    """name -> {token, map}, persisted so bots keep their identity and
    remember which map they logged off on (the server restores a player to
    its saved map with no MAP_CHANGE at attach, so the client must know)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock = threading.Lock()
        self.records: dict[str, dict] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="ascii"))
                for name, record in raw.items():
                    if isinstance(record, dict):
                        self.records[str(name)] = {
                            "token": str(record.get("token", "")),
                            "map": int(record.get("map", 0)),
                        }
                    else:  # older plain-token format
                        self.records[str(name)] = {"token": str(record), "map": 0}
            except (OSError, ValueError):
                self.records = {}

    def get(self, name: str) -> dict | None:
        with self.lock:
            record = self.records.get(name)
            return dict(record) if record is not None else None

    def _save_locked(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.records, indent=2, sort_keys=True) + "\n", encoding="ascii")
        tmp.replace(self.path)

    def put(self, name: str, token: str, map_id: int = 0) -> None:
        with self.lock:
            self.records[name] = {"token": token, "map": map_id}
            self._save_locked()

    def update_map(self, name: str, map_id: int) -> None:
        with self.lock:
            record = self.records.get(name)
            if record is None or record.get("map") == map_id:
                return
            record["map"] = map_id
            self._save_locked()


class Persona:
    """Stable per-name behavior parameters so each bot reads as a distinct
    player: gait, patience, curiosity, and how it handles obstacles."""

    def __init__(self, name: str) -> None:
        rng = random.Random(f"persona:{name}")
        self.step_interval = rng.uniform(0.22, 0.42)
        self.fire_interval = rng.uniform(0.45, 0.7)
        self.idle_chance = rng.uniform(0.1, 0.25)
        self.idle_range = (rng.uniform(3.0, 6.0), rng.uniform(10.0, 25.0))
        self.stroll_range = (8, rng.randint(14, 26))
        self.turn_small = rng.uniform(0.6, 0.85)
        self.cave_chance = rng.uniform(0.03, 0.1)
        self.town_chance = rng.uniform(0.05, 0.12)
        self.cave_stay = (90.0, rng.uniform(180.0, 300.0))
        self.handedness = rng.choice((-1, 1))


class MapMemory:
    """Terrain the server has actually sent, per map, in absolute
    coordinates. This is the bot's only source of walkability."""

    def __init__(self) -> None:
        self.maps: dict[int, dict[tuple[int, int], int]] = {}

    def tiles_for(self, map_id: int) -> dict[tuple[int, int], int]:
        return self.maps.setdefault(map_id, {})

    def apply_rect(self, map_id: int, origin_x: int, origin_y: int, width: int, tiles: bytes) -> None:
        known = self.tiles_for(map_id)
        for index, tile in enumerate(tiles):
            known[(origin_x + index % width, origin_y + index // width)] = tile

    def set_tile(self, map_id: int, x: int, y: int, tile: int) -> None:
        self.tiles_for(map_id)[(x, y)] = tile

    def tile(self, map_id: int, x: int, y: int) -> int | None:
        return self.tiles_for(map_id).get((x, y))

    def herbs_near(self, map_id: int, x: int, y: int, radius: int) -> list[tuple[int, int]]:
        known = self.tiles_for(map_id)
        return [
            pos
            for pos, tile in known.items()
            if tile == HERB and manhattan(pos[0], pos[1], x, y) <= radius
        ]


class Bot(threading.Thread):
    def __init__(self, name: str, args: argparse.Namespace, store: TokenStore, stop_event: threading.Event) -> None:
        super().__init__(name=f"bot-{name}", daemon=True)
        self.bot_name = name
        self.args = args
        self.store = store
        self.stop_event = stop_event
        self.persona = Persona(name)
        self.rng = random.Random()
        self.token: int | None = None
        self.start_map = MAP_OVERWORLD
        self._session_break_pending = False
        # Session-lifetime protocol state (reset each realtime attach).
        self.sock: socket.socket | None = None
        self.seq = 0
        self.memory = MapMemory()
        # Lifetime counters for the status line.
        self.stat_steps = 0
        self.stat_corrections = 0
        self.stat_kills = 0
        self.stat_pickups = 0
        self.stat_fills = 0
        self.stat_bad_frames = 0

    # ------------------------------------------------------------------
    # Logging

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        print(f"[{stamp}] [{self.bot_name}] {message}", flush=True)

    def debug(self, message: str) -> None:
        if self.args.debug:
            self.log(message)

    # ------------------------------------------------------------------
    # Lifecycle

    def run(self) -> None:
        backoff = 2.0
        while not self.stop_event.is_set():
            try:
                self._one_session()
                backoff = 2.0
            except SessionEnded as exc:
                self.log(f"session ended: {exc}")
            except OSError as exc:
                self.log(f"connection error: {exc}")
            except Exception as exc:  # keep the bot alive; log for diagnosis
                self.log(f"internal error: {exc!r}")
            finally:
                self._close_socket()
            if self.stop_event.is_set():
                break
            wait = backoff + self.rng.uniform(0.0, 2.0)
            if self._session_break_pending:
                wait = self.rng.uniform(self.args.break_min * 60.0, self.args.break_max * 60.0)
                self.log(f"taking a break for {wait / 60.0:.1f} min")
                self._session_break_pending = False
            self.stop_event.wait(wait)
            backoff = min(60.0, backoff * 2)
        self.log("stopped")

    def _close_socket(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _one_session(self) -> None:
        self.token = self._ensure_identity()
        self._bootstrap_terrain()
        self._play_realtime()

    # ------------------------------------------------------------------
    # Identity (login server, port 9010)

    def _login_request(self, payload: bytes) -> object:
        with socket.create_connection((self.args.server, self.args.login_port), timeout=5.0) as conn:
            conn.settimeout(5.0)
            conn.sendall(payload)
            decoder = PacketStreamDecoder()
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                packets = decoder.feed(chunk)
                if packets:
                    return packets[0]
        raise SessionEnded("no response from login server")

    def _ensure_identity(self) -> int:
        record = self.store.get(self.bot_name)
        if record is None:
            packet = self._login_request(encode_login_request(LoginRequest(self.bot_name)))
            if packet.packet_type != PacketType.LOGIN_RESPONSE:
                raise SessionEnded(f"unexpected login reply type {packet.packet_type}")
            response = decode_login_response(packet.payload)
            if response.status != LOGIN_OK:
                raise SessionEnded(
                    f"username '{self.bot_name}' is taken and no stored token exists; "
                    f"pick another name or restore the state file"
                )
            self.store.put(self.bot_name, response.token, MAP_OVERWORLD)
            self.start_map = MAP_OVERWORLD
            self.log(f"registered new identity token={response.token}")
            return int(response.token)
        stored = record["token"]
        self.start_map = record.get("map", MAP_OVERWORLD)
        packet = self._login_request(encode_resume_request(ResumeRequest(stored)))
        if packet.packet_type != PacketType.RESUME_RESPONSE:
            raise SessionEnded(f"unexpected resume reply type {packet.packet_type}")
        response = decode_resume_response(packet.payload)
        if response.status != RESUME_OK:
            raise SessionEnded(f"resume rejected status={response.status}")
        if response.username != self.bot_name:
            # Server lost or never had our name for this token (e.g. wiped
            # sessions.json auto-created PlayerXXXX): claim the name back.
            packet = self._login_request(
                encode_rename_request(RenameRequest(stored, self.bot_name))
            )
            if (
                packet.packet_type == PacketType.RENAME_RESPONSE
                and decode_rename_response(packet.payload).status == RENAME_OK
            ):
                self.log(f"renamed server identity {response.username} -> {self.bot_name}")
            else:
                self.log(f"playing as server-side name {response.username} (rename failed)")
        self.debug(f"resumed token={stored}")
        return int(stored)

    # ------------------------------------------------------------------
    # Bootstrap (framed byte-stream protocol, then close)

    def _bootstrap_terrain(self) -> None:
        assert self.token is not None
        with socket.create_connection((self.args.server, self.args.port), timeout=5.0) as conn:
            conn.settimeout(5.0)
            conn.sendall(REGISTER + encode_hello(Hello(flags=0, seed=0, token=self.token)))
            decoder = PacketStreamDecoder()
            covered = 0
            origin = None
            deadline = time.monotonic() + 8.0
            while covered < WINDOW_H:
                if time.monotonic() >= deadline:
                    raise SessionEnded("bootstrap window incomplete")
                chunk = conn.recv(4096)
                if not chunk:
                    raise SessionEnded("bootstrap connection closed early")
                for packet in decoder.feed(chunk):
                    if packet.packet_type != PacketType.WINDOW:
                        continue
                    window = decode_window(packet.payload)
                    origin = (window.origin_x, window.origin_y)
                    self.memory.apply_rect(
                        # Map id is unknown at bootstrap; the server sends the
                        # player's current map. Stored under the map id learned
                        # at attach time via _adopt_bootstrap below.
                        -1,
                        window.origin_x,
                        window.origin_y + window.chunk_y,
                        window.width,
                        window.tiles,
                    )
                    covered += window.chunk_h
        if origin is None:
            raise SessionEnded("bootstrap sent no window")
        self.bootstrap_origin = origin
        self.debug(f"bootstrap complete origin={origin[0]},{origin[1]}")

    def _adopt_bootstrap(self, map_id: int) -> None:
        staged = self.memory.maps.pop(-1, None)
        if staged:
            self.memory.tiles_for(map_id).update(staged)

    # ------------------------------------------------------------------
    # Realtime session

    def _reset_session_state(self) -> None:
        self.seq = 0
        self.map_id = self.start_map
        self.window_origin = self.bootstrap_origin
        self.x = self.window_origin[0] + WINDOW_W // 2
        self.y = self.window_origin[1] + WINDOW_H // 2
        self.facing = FACE_DOWN
        self.fire_counter = 0
        self.pickup_counter = 0
        self.last_server_seq = 0
        self.settled = False
        self.hp = 0
        self.max_hp = 0
        self.level = 1
        self.enemies: tuple = ()
        self.remotes: tuple = ()
        self.drops: tuple = ()
        self.crowded_since: float | None = None
        # Cache-step state.
        self.last_step_revision: int | None = None
        # Fill state.
        self.fill_id: int | None = None
        self.fill_origin: tuple[int, int] | None = None
        self.fill_rows_have = 0
        self.fill_last_progress = 0.0
        self.commit_pending: WindowCommitPacket | None = None
        self.commit_sent_at = 0.0
        self.commit_retries = 0
        # Map transition state.
        self.transition_hold = False
        self.pending_map_ready: int | None = None
        # Behavior state.
        self.mode = "idle"
        self.mode_until = time.monotonic() + self.rng.uniform(1.0, 3.0)
        self.waypoint: tuple[int, int] | None = None
        self.travel_goal: tuple[int, int] | None = None
        self.goal_kind: str | None = None
        self.goal_deadline = 0.0
        self.cave_leave_at = 0.0
        self.retaliate_until = 0.0
        self.retaliate_anchor: tuple[int, int] | None = None
        self.kill_spot: tuple[int, int] | None = None
        self.loot_deadline = 0.0
        self.next_step_at = 0.0
        self.next_fire_at = 0.0
        self.last_fired_at = 0.0
        self.next_pickup_at = 0.0
        self.recent_tiles: list[tuple[int, int]] = []
        self.stuck_count = 0
        self.nav_target: tuple[int, int] | None = None
        self.nav_best_distance = 0
        self.nav_progress_at = 0.0
        if self.map_id == MAP_STARTER_CAVE:
            self.cave_leave_at = time.monotonic() + self.rng.uniform(*self.persona.cave_stay)

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFFFF
        return self.seq

    def _send(self, data: bytes) -> None:
        assert self.sock is not None
        try:
            self.sock.sendall(data)
        except OSError as exc:
            raise SessionEnded(f"send failed: {exc}")

    def _send_player_state(self) -> None:
        self._send(
            encode_player_state(
                PlayerStatePacket(
                    seq=self._next_seq(),
                    x=self.x,
                    y=self.y,
                    facing=self.facing,
                    buttons=0,
                    fire_counter=self.fire_counter,
                    pickup_counter=self.pickup_counter,
                    last_server_seq=self.last_server_seq,
                    rx_drops=0,
                    pvp_toggle_counter=0,
                )
            )
        )

    def _play_realtime(self) -> None:
        assert self.token is not None
        self._reset_session_state()
        self.sock = socket.create_connection((self.args.server, self.args.port), timeout=5.0)
        self.sock.settimeout(0.05)
        self._adopt_bootstrap(self.map_id)
        self._send(REGISTER + REALTIME_PREAMBLE + encode_auth(AuthPacket(seq=0, token=self.token)))
        self._send_player_state()
        self.log(f"online at ~{self.x},{self.y} (session starting)")

        session_end = None
        if self.args.session_max > 0:
            session_end = time.monotonic() + self.rng.uniform(
                self.args.session_min * 60.0, self.args.session_max * 60.0
            )
        next_state = time.monotonic() + STATE_SEND_INTERVAL
        next_status = time.monotonic() + STATUS_INTERVAL
        buffer = bytearray()

        while not self.stop_event.is_set():
            now = time.monotonic()
            if session_end is not None and now >= session_end:
                self._send(encode_realtime_bye(self._next_seq()))
                self._session_break_pending = True
                self.log(
                    f"logging off (steps={self.stat_steps} kills={self.stat_kills} "
                    f"pickups={self.stat_pickups} corrections={self.stat_corrections})"
                )
                return
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                chunk = None
            except OSError as exc:
                raise SessionEnded(f"recv failed: {exc}")
            if chunk == b"":
                raise SessionEnded("server closed connection")
            if chunk:
                buffer.extend(chunk)
                self._drain_frames(buffer)

            now = time.monotonic()
            self._service_fill(now)
            self._drive(now)
            if now >= next_state:
                self._send_player_state()
                next_state = now + STATE_SEND_INTERVAL
            if now >= next_status:
                self.log(
                    f"status map={self.map_id} pos={self.x},{self.y} hp={self.hp}/{self.max_hp} "
                    f"mode={self.mode} steps={self.stat_steps} kills={self.stat_kills} "
                    f"pickups={self.stat_pickups} corrections={self.stat_corrections} "
                    f"fills={self.stat_fills} bad_frames={self.stat_bad_frames}"
                )
                next_status = now + STATUS_INTERVAL

    # ------------------------------------------------------------------
    # Receive path

    def _drain_frames(self, buffer: bytearray) -> None:
        while True:
            try:
                cut = buffer.index(0)
            except ValueError:
                return
            encoded = bytes(buffer[:cut])
            del buffer[: cut + 1]
            if not encoded:
                continue
            try:
                frame = _normalize_realtime(encoded)
            except PacketError:
                self.stat_bad_frames += 1
                continue
            self._handle_frame(frame)

    def _handle_frame(self, frame: bytes) -> None:
        packet_type = frame[2]
        if packet_type == RealtimeType.WORLD_STATE:
            self._on_world_state(decode_world_state(frame))
        elif packet_type == RealtimeType.TERRAIN_EDGE:
            self._on_terrain_edge(decode_terrain_edge(frame))
        elif packet_type == RealtimeType.WINDOW_ROW:
            self._on_window_row(decode_window_row(frame))
        elif packet_type == RealtimeType.WINDOW_COMMIT_ACK:
            self._on_commit_ack(decode_window_commit_ack(frame))
        elif packet_type == RealtimeType.MAP_CHANGE:
            self._on_map_change(decode_map_change(frame))
        elif packet_type == RealtimeType.REMOTE_PLAYERS:
            self.remotes = decode_remote_players(frame).players
        elif packet_type == RealtimeType.ITEM_DROPS:
            self.drops = decode_item_drops(frame).items
        elif packet_type == RealtimeType.HUD_UPDATE:
            hud = decode_hud_update(frame)
            self.hp = hud.hp
            self.max_hp = hud.max_hp
            self.level = hud.level
        elif packet_type == RealtimeType.RESPAWN_EVENT:
            self._on_respawn(decode_respawn_event(frame))
        elif packet_type == RealtimeType.MESSAGE:
            message = decode_message(frame)
            if message.text:
                self.log(f"server message: {message.text}")
        # QUEST/INVENTORY/MAP_SUMMARY and anything unknown: ignored.

    def _on_world_state(self, world) -> None:
        self.last_server_seq = world.seq
        previous_hp = self.hp if self.settled else None
        self.hp = world.health
        previous_enemies = self.enemies
        self.enemies = world.beavers
        if (world.tile_x, world.tile_y) != (0, 0):
            self.memory.set_tile(self.map_id, world.tile_x, world.tile_y, world.tile_id)
        if not self.settled:
            self.x, self.y = world.player_x, world.player_y
            self.settled = True
            self.debug(f"settled at {self.x},{self.y}")
        elif world.correction_flags & 1:
            self.stat_corrections += 1
            self.x, self.y = world.player_x, world.player_y
            self.waypoint = None
        if (
            previous_hp is not None
            and self.hp < previous_hp
            and not self.transition_hold
            and self._nearest_enemy(max_distance=6) is not None
        ):
            self._enter_retaliation()
        if self.mode == "retaliate":
            self._check_kill(previous_enemies)

    def _on_terrain_edge(self, edge) -> None:
        if self.transition_hold or self.fill_id is not None:
            # Mid-transition or mid-fill: the fill machinery owns the window.
            return
        origin = list(self.window_origin)
        if edge.revision == self.last_step_revision:
            self._ack_step(edge.revision, tuple(origin))
            return
        if edge.width == 1 and edge.origin_x == origin[0] + WINDOW_W:
            origin[0] += 1
        elif edge.width == 1 and edge.origin_x == origin[0] - 1:
            origin[0] -= 1
        elif edge.height == 1 and edge.origin_y == origin[1] + WINDOW_H:
            origin[1] += 1
        elif edge.height == 1 and edge.origin_y == origin[1] - 1:
            origin[1] -= 1
        else:
            # A follower of a lost step: duplicate-ACK our applied state to
            # trigger the server's fast retransmit.
            if self.last_step_revision is not None:
                self._ack_step(self.last_step_revision, self.window_origin)
            return
        self.memory.apply_rect(self.map_id, edge.origin_x, edge.origin_y, edge.width, edge.tiles)
        self.window_origin = tuple(origin)
        self.last_step_revision = edge.revision
        self._ack_step(edge.revision, self.window_origin)

    def _ack_step(self, revision: int, origin: tuple[int, int]) -> None:
        self._send(
            encode_cache_step_ack(
                CacheStepAckPacket(
                    seq=self._next_seq(), revision=revision, origin_x=origin[0], origin_y=origin[1]
                )
            )
        )

    def _on_window_row(self, row) -> None:
        origin = (row.origin_x, row.origin_y - row.row_index)
        if self.fill_id != row.fill_id or self.fill_origin != origin:
            self.fill_id = row.fill_id
            self.fill_origin = origin
            self.fill_rows_have = 0
            self.commit_pending = None
            self.stat_fills += 1
            self.debug(f"fill start id={row.fill_id} origin={origin[0]},{origin[1]}")
        self.memory.apply_rect(self.map_id, row.origin_x, row.origin_y, WINDOW_W, row.tiles)
        self.fill_rows_have |= 1 << row.row_index
        self.fill_last_progress = time.monotonic()
        if self.fill_rows_have == FULL_ROWS_MASK and self.commit_pending is None:
            self.commit_pending = WindowCommitPacket(
                seq=0,
                fill_id=row.fill_id,
                origin_x=origin[0],
                origin_y=origin[1],
                map_id=self.map_id,
            )
            self.commit_sent_at = 0.0
            self.commit_retries = 0

    def _service_fill(self, now: float) -> None:
        if self.commit_pending is not None:
            if now - self.commit_sent_at >= COMMIT_RETRY_INTERVAL:
                if self.commit_retries >= COMMIT_RETRY_LIMIT:
                    self.debug("commit unanswered; requesting clean fill")
                    self._send(
                        encode_resync_request(
                            ResyncRequestPacket(seq=self._next_seq(), flags=2)
                        )
                    )
                    self.fill_id = None
                    self.commit_pending = None
                    return
                packet = self.commit_pending
                self._send(
                    encode_window_commit(
                        WindowCommitPacket(
                            seq=self._next_seq(),
                            fill_id=packet.fill_id,
                            origin_x=packet.origin_x,
                            origin_y=packet.origin_y,
                            map_id=packet.map_id,
                        )
                    )
                )
                self.commit_sent_at = now
                self.commit_retries += 1
            return
        if self.fill_id is not None and now - self.fill_last_progress >= FILL_NACK_INTERVAL:
            # Silence NACK: report which rows arrived so the server resends
            # only the missing ones.
            assert self.fill_origin is not None
            self._send(
                encode_resync_request(
                    ResyncRequestPacket(
                        seq=self._next_seq(),
                        origin_x=self.window_origin[0],
                        origin_y=self.window_origin[1],
                        fill_origin_x=self.fill_origin[0],
                        fill_origin_y=self.fill_origin[1],
                        rows_have=self.fill_rows_have,
                        fill_id=self.fill_id,
                    )
                )
            )
            self.fill_last_progress = now

    def _on_commit_ack(self, ack) -> None:
        if self.commit_pending is None or ack.fill_id != self.commit_pending.fill_id:
            return
        self.window_origin = (ack.origin_x, ack.origin_y)
        self.fill_id = None
        self.fill_origin = None
        self.commit_pending = None
        self.last_step_revision = None
        self.debug(f"fill committed origin={ack.origin_x},{ack.origin_y}")
        if self.pending_map_ready is not None:
            self._send(
                encode_map_ready(
                    MapReadyPacket(
                        seq=self._next_seq(),
                        map_id=self.pending_map_ready,
                        origin_x=ack.origin_x,
                        origin_y=ack.origin_y,
                    )
                )
            )
            self.pending_map_ready = None
            self.transition_hold = False
            self.mode = "idle"
            self.mode_until = time.monotonic() + self.rng.uniform(1.0, 4.0)
            self.log(f"map {self.map_id} ready at {self.x},{self.y}")

    def _on_map_change(self, change) -> None:
        if change.map_id == self.map_id and self.transition_hold:
            # Server re-sends MAP_CHANGE until MAP_READY; the in-flight fill
            # is preserved server-side, so keep our staged rows too.
            return
        self.log(f"map change -> {change.map_id} spawn={change.spawn_x},{change.spawn_y}")
        self.store.update_map(self.bot_name, change.map_id)
        self.map_id = change.map_id
        self.x, self.y = change.spawn_x, change.spawn_y
        self.transition_hold = True
        self.pending_map_ready = change.map_id
        self.fill_id = None
        self.fill_origin = None
        self.commit_pending = None
        self.last_step_revision = None
        self.waypoint = None
        self.travel_goal = None
        self.goal_kind = None
        self.enemies = ()
        self.drops = ()
        if change.map_id == MAP_STARTER_CAVE:
            self.cave_leave_at = time.monotonic() + self.rng.uniform(*self.persona.cave_stay)
        if change.map_id == MAP_PVP_REALM:
            # Hard rule backstop: should be unreachable (the entrance tile is
            # never stepped on), but if it happens, leave immediately.
            self.log("entered PvP realm unexpectedly; heading straight to exit")

    def _on_respawn(self, event) -> None:
        self.log(f"respawned at {event.x},{event.y} hp={event.hp}")
        if event.map_id == self.map_id:
            self.x, self.y = event.x, event.y
        self.hp = event.hp
        self.mode = "idle"
        self.mode_until = time.monotonic() + self.rng.uniform(3.0, 8.0)
        self.waypoint = None
        self.travel_goal = None
        self.goal_kind = None
        self.retaliate_until = 0.0
        self.kill_spot = None

    # ------------------------------------------------------------------
    # Combat: retaliation only

    def _nearest_enemy(self, max_distance: int) -> object | None:
        best = None
        best_distance = max_distance + 1
        for enemy in self.enemies:
            if enemy.hp <= 0:
                continue
            distance = manhattan(enemy.x, enemy.y, self.x, self.y)
            if distance < best_distance:
                best = enemy
                best_distance = distance
        return best

    def _enter_retaliation(self) -> None:
        if self.mode != "retaliate":
            self.log(f"attacked at {self.x},{self.y} hp={self.hp}; retaliating")
        self.mode = "retaliate"
        self.retaliate_until = time.monotonic() + RETALIATE_WINDOW
        self.retaliate_anchor = (self.x, self.y)

    def _check_kill(self, previous_enemies) -> None:
        # An enemy we were engaging vanished from the live list: remember
        # where, so the loot pass only takes our own drops. Requires a recent
        # shot from us, and ignores enemies that merely moved a tile.
        now = time.monotonic()
        if now - self.last_fired_at > 2.0:
            return
        current = {(enemy.x, enemy.y) for enemy in self.enemies if enemy.hp > 0}
        for enemy in previous_enemies:
            if enemy.hp <= 0:
                continue
            if manhattan(enemy.x, enemy.y, self.x, self.y) > 3:
                continue
            if (enemy.x, enemy.y) in current:
                continue
            moved = any(
                abs(pos[0] - enemy.x) <= 1 and abs(pos[1] - enemy.y) <= 1 for pos in current
            )
            if moved:
                continue
            self.stat_kills += 1
            self.kill_spot = (enemy.x, enemy.y)
            self.loot_deadline = now + LOOT_WINDOW
            self.log(f"defeated attacker at {enemy.x},{enemy.y}")

    def _face_toward(self, tx: int, ty: int) -> None:
        dx = tx - self.x
        dy = ty - self.y
        if abs(dx) >= abs(dy):
            self.facing = FACE_RIGHT if dx > 0 else FACE_LEFT
        else:
            self.facing = FACE_DOWN if dy > 0 else FACE_UP

    def _drive_retaliate(self, now: float) -> None:
        if self.max_hp and self.hp <= self.max_hp * FLEE_HEALTH_FRACTION:
            self.mode = "flee"
            self.mode_until = now + 6.0
            self.log(f"low health {self.hp}/{self.max_hp}; disengaging")
            return
        target = self._nearest_enemy(max_distance=RETALIATE_MAX_CHASE)
        if target is None or now >= self.retaliate_until:
            self.mode = "loot" if self.kill_spot is not None else "idle"
            self.mode_until = now + self.rng.uniform(1.0, 3.0)
            return
        distance = manhattan(target.x, target.y, self.x, self.y)
        if distance == 1:
            self._face_toward(target.x, target.y)
            if now >= self.next_fire_at:
                self.fire_counter = (self.fire_counter + 1) & 0xFF
                self.next_fire_at = now + self.persona.fire_interval
                self.last_fired_at = now
                self._send_player_state()
        elif (target.x == self.x or target.y == self.y) and distance <= 3:
            self._face_toward(target.x, target.y)
            if now >= self.next_fire_at:
                self.fire_counter = (self.fire_counter + 1) & 0xFF
                self.next_fire_at = now + self.persona.fire_interval
                self.last_fired_at = now
                self._send_player_state()
        elif now >= self.next_step_at and self.retaliate_anchor is not None:
            if manhattan(self.x, self.y, *self.retaliate_anchor) < RETALIATE_MAX_CHASE:
                self._step_toward(target.x, target.y, allow_enemy_adjacent=True)
            self.next_step_at = now + self.persona.step_interval

    def _drive_flee(self, now: float) -> None:
        if now >= self.mode_until:
            self.mode = "idle"
            self.mode_until = now + self.rng.uniform(4.0, 10.0)
            # Injured: seek a known herb (stepping on one heals).
            herbs = self.memory.herbs_near(self.map_id, self.x, self.y, 10)
            if herbs and self.hp < self.max_hp:
                self.waypoint = min(herbs, key=lambda p: manhattan(p[0], p[1], self.x, self.y))
                self.mode = "wander"
            return
        threat = self._nearest_enemy(max_distance=8)
        if threat is None:
            self.mode_until = min(self.mode_until, now + 1.0)
            return
        if now >= self.next_step_at:
            self._step_away_from(threat.x, threat.y)
            self.next_step_at = now + self.persona.step_interval * 0.8

    def _drive_loot(self, now: float) -> None:
        if self.kill_spot is None or now >= self.loot_deadline:
            self.kill_spot = None
            self.mode = "idle"
            self.mode_until = now + self.rng.uniform(1.0, 4.0)
            return
        mine = [
            drop
            for drop in self.drops
            if manhattan(drop.x, drop.y, self.kill_spot[0], self.kill_spot[1]) <= 2
        ]
        if not mine:
            return  # drops packet may not have arrived yet; deadline bounds the wait
        target = min(mine, key=lambda d: manhattan(d.x, d.y, self.x, self.y))
        if (self.x, self.y) == (target.x, target.y):
            if now >= self.next_pickup_at:
                self.pickup_counter = (self.pickup_counter + 1) & 0xFF
                self.stat_pickups += 1
                self.next_pickup_at = now + 0.6
                self._send_player_state()
                self.log(f"picked up loot at {self.x},{self.y}")
        elif now >= self.next_step_at:
            self._step_toward(target.x, target.y, allow_enemy_adjacent=False)
            self.next_step_at = now + self.persona.step_interval

    # ------------------------------------------------------------------
    # Movement

    def _tile_forbidden(self, x: int, y: int) -> bool:
        # Transition tiles are only stepped on deliberately; the PvP realm
        # entrance is never stepped on at all.
        if self.map_id == MAP_OVERWORLD:
            if (x, y) == OVERWORLD_PVP_REALM_ENTRANCE:
                return True
            if (x, y) == OVERWORLD_CAVE_ENTRANCE and self.goal_kind != "cave":
                return True
        if self.map_id == MAP_STARTER_CAVE and (x, y) == STARTER_CAVE_EXIT and self.goal_kind != "cave_exit":
            return True
        return False

    def _step_allowed(self, x: int, y: int, allow_enemy_adjacent: bool = False) -> bool:
        tile = self.memory.tile(self.map_id, x, y)
        if tile is None or tile in PLAYER_BLOCKING:
            return False
        if self._tile_forbidden(x, y):
            return False
        for remote in self.remotes:
            if (remote.x, remote.y) == (x, y):
                return False
        if not allow_enemy_adjacent:
            for enemy in self.enemies:
                if enemy.hp > 0 and abs(enemy.x - x) <= 1 and abs(enemy.y - y) <= 1:
                    return False
        return True

    def _do_step(self, facing: int) -> None:
        dx, dy = STEPS[facing]
        self.x += dx
        self.y += dy
        self.facing = facing
        self.stat_steps += 1
        self.recent_tiles.append((self.x, self.y))
        if len(self.recent_tiles) > 12:
            self.recent_tiles.pop(0)
        self._send_player_state()

    def _step_toward(self, tx: int, ty: int, allow_enemy_adjacent: bool) -> bool:
        options = []
        for facing, (dx, dy) in STEPS.items():
            nx, ny = self.x + dx, self.y + dy
            if not self._step_allowed(nx, ny, allow_enemy_adjacent):
                continue
            score = manhattan(nx, ny, tx, ty) + self.rng.uniform(0.0, 0.4)
            repeats = self.recent_tiles.count((nx, ny))
            if repeats:
                score += 1.5 * repeats  # escalating anti-backtrack
            options.append((score, facing))
        if not options:
            self.stuck_count += 1
            return False
        options.sort()
        self.stuck_count = 0
        self._do_step(options[0][1])
        return True

    def _step_away_from(self, tx: int, ty: int) -> bool:
        options = []
        for facing, (dx, dy) in STEPS.items():
            nx, ny = self.x + dx, self.y + dy
            if not self._step_allowed(nx, ny, allow_enemy_adjacent=True):
                continue
            options.append((-manhattan(nx, ny, tx, ty) + self.rng.uniform(0.0, 0.4), facing))
        if not options:
            return False
        options.sort()
        self._do_step(options[0][1])
        return True

    def _nav_stalled(self, target: tuple[int, int], now: float) -> bool:
        """True if `target` has seen no real progress for NAV_STALL_TIMEOUT
        seconds. Catches greedy hill-climbing traps (maze pockets) that
        `stuck_count` misses because every ping-pong step is a "successful"
        legal move."""
        distance = manhattan(self.x, self.y, target[0], target[1])
        if target != self.nav_target:
            self.nav_target = target
            self.nav_best_distance = distance
            self.nav_progress_at = now
            return False
        if distance < self.nav_best_distance:
            self.nav_best_distance = distance
            self.nav_progress_at = now
            return False
        return now - self.nav_progress_at >= NAV_STALL_TIMEOUT

    # ------------------------------------------------------------------
    # Behavior selection

    def _crowded(self, now: float) -> bool:
        near = any(
            manhattan(remote.x, remote.y, self.x, self.y) <= CROWD_DISTANCE for remote in self.remotes
        )
        if not near:
            self.crowded_since = None
            return False
        if self.crowded_since is None:
            self.crowded_since = now
        return now - self.crowded_since >= CROWD_PATIENCE

    def _pick_episode(self, now: float) -> None:
        # Give someone else the spot if we've shared it too long.
        if self._crowded(now):
            nearest = min(
                self.remotes, key=lambda r: manhattan(r.x, r.y, self.x, self.y), default=None
            )
            if nearest is not None:
                away_x = self.x + (self.x - nearest.x) * 6
                away_y = self.y + (self.y - nearest.y) * 6
                self.waypoint = (away_x, away_y)
                self.mode = "wander"
                self.crowded_since = None
                self.debug("area is crowded; moving on")
                return
        roll = self.rng.random()
        if self.map_id == MAP_PVP_REALM:
            # Hard rule: bots do not play here. Head straight for the exit.
            self.goal_kind = "pvp_exit"
            self.travel_goal = PVP_REALM_EXIT
            self.goal_deadline = now + 300.0
            self.mode = "travel"
            return
        if self.map_id == MAP_STARTER_CAVE:
            if now >= self.cave_leave_at:
                self.goal_kind = "cave_exit"
                self.travel_goal = STARTER_CAVE_EXIT
                self.goal_deadline = now + 180.0
                self.mode = "travel"
                self.log("heading for the cave exit")
                return
        elif self.map_id == MAP_OVERWORLD:
            if roll < self.persona.cave_chance:
                self.goal_kind = "cave"
                self.travel_goal = OVERWORLD_CAVE_ENTRANCE
                self.goal_deadline = now + 240.0
                self.mode = "travel"
                self.log("wandering toward the cave")
                return
            if roll < self.persona.cave_chance + self.persona.town_chance:
                jitter_x = self.rng.randint(-6, 6)
                jitter_y = self.rng.randint(-4, 4)
                self.goal_kind = "visit"
                self.travel_goal = (OVERWORLD_START[0] + jitter_x, OVERWORLD_START[1] + jitter_y)
                self.goal_deadline = now + 240.0
                self.mode = "travel"
                self.debug("strolling toward town")
                return
        if roll > 1.0 - self.persona.idle_chance:
            self.mode = "idle"
            self.mode_until = now + self.rng.uniform(*self.persona.idle_range)
            return
        # Default stroll: persistent heading with a small (usually) turn.
        heading = getattr(self, "heading", self.rng.uniform(0.0, 360.0))
        if self.rng.random() < self.persona.turn_small:
            heading += self.rng.uniform(-50.0, 50.0)
        else:
            heading += self.rng.uniform(120.0, 240.0)
        self.heading = heading % 360.0
        distance = self.rng.randint(*self.persona.stroll_range)
        self.waypoint = (
            self.x + int(distance * math.cos(math.radians(self.heading))),
            self.y + int(distance * math.sin(math.radians(self.heading))),
        )
        self.mode = "wander"

    def _drive(self, now: float) -> None:
        if not self.settled or self.transition_hold:
            return
        if self.mode == "retaliate":
            self._drive_retaliate(now)
            return
        if self.mode == "flee":
            self._drive_flee(now)
            return
        if self.mode == "loot":
            self._drive_loot(now)
            return
        if self.mode == "idle":
            if now >= self.mode_until:
                self._pick_episode(now)
            return
        if self.mode == "travel":
            if self.travel_goal is None or now >= self.goal_deadline:
                self.goal_kind = None
                self.travel_goal = None
                self.mode = "idle"
                self.mode_until = now + 1.0
                return
            if (self.x, self.y) == self.travel_goal or (
                self.goal_kind == "visit"
                and manhattan(self.x, self.y, *self.travel_goal) <= 2
            ):
                self.goal_kind = None
                self.travel_goal = None
                self.nav_target = None
                self.mode = "idle"
                self.mode_until = now + self.rng.uniform(*self.persona.idle_range)
                return
            if self._nav_stalled(self.travel_goal, now):
                self.debug(f"stuck trying to reach {self.goal_kind or 'goal'}; abandoning")
                self.goal_kind = None
                self.travel_goal = None
                self.nav_target = None
                self.mode = "idle"
                self.mode_until = now + self.rng.uniform(1.0, 3.0)
                return
            if now >= self.next_step_at:
                if not self._step_toward(*self.travel_goal, allow_enemy_adjacent=False):
                    if self.stuck_count > 6:
                        self.goal_kind = None
                        self.travel_goal = None
                        self.nav_target = None
                        self.mode = "idle"
                        self.mode_until = now + 2.0
                self.next_step_at = now + self.persona.step_interval
            return
        # wander
        if self.waypoint is None:
            self._pick_episode(now)
            return
        if (
            (self.x, self.y) == self.waypoint
            or self.stuck_count > 4
            or self._nav_stalled(self.waypoint, now)
        ):
            self.waypoint = None
            self.nav_target = None
            self.stuck_count = 0
            self.mode = "idle"
            self.mode_until = now + self.rng.uniform(0.5, 3.0)
            return
        if now >= self.next_step_at:
            self._step_toward(*self.waypoint, allow_enemy_adjacent=False)
            self.next_step_at = now + self.persona.step_interval


def parse_names(raw: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    for name in names:
        if len(name) > USERNAME_MAX:
            raise argparse.ArgumentTypeError(f"name '{name}' exceeds {USERNAME_MAX} characters")
        if "," in name or not all(32 < ord(ch) < 127 for ch in name):
            raise argparse.ArgumentTypeError(f"name '{name}' has invalid characters")
    if not names:
        raise argparse.ArgumentTypeError("at least one name is required")
    if len(names) != len(set(names)):
        raise argparse.ArgumentTypeError("duplicate names")
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description="Human-like AI test clients for FujiRealm")
    parser.add_argument("--server", default="127.0.0.1", help="game server hostname")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--login-port", type=int, default=DEFAULT_LOGIN_PORT)
    parser.add_argument(
        "--names",
        type=parse_names,
        required=True,
        help="comma-separated bot names (one bot per name, shown in all logs)",
    )
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help="where bot identity tokens persist (default ./ai_players_state.json)",
    )
    parser.add_argument("--session-min", type=float, default=20.0, help="min session minutes")
    parser.add_argument("--session-max", type=float, default=60.0, help="max session minutes (0 = play forever)")
    parser.add_argument("--break-min", type=float, default=3.0, help="min minutes offline between sessions")
    parser.add_argument("--break-max", type=float, default=10.0, help="max minutes offline between sessions")
    parser.add_argument("--no-breaks", action="store_true", help="stay online continuously")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    if args.no_breaks:
        args.session_max = 0.0

    store = TokenStore(args.state_file)
    stop_event = threading.Event()
    bots = [Bot(name, args, store, stop_event) for name in args.names]
    for index, bot in enumerate(bots):
        bot.start()
        # Staggered arrivals: a burst of simultaneous logins reads as a bot
        # swarm and hammers the login server for no benefit.
        if index + 1 < len(bots):
            time.sleep(random.uniform(1.0, 4.0))
    try:
        while any(bot.is_alive() for bot in bots):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("shutting down bots...")
        stop_event.set()
    for bot in bots:
        bot.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
