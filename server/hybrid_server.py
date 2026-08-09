"""Hybrid server: one port, concurrent TCP bootstrap and realtime clients.

A single selector loop accepts connections continuously and classifies each
by its first bytes (after the REGISTER/probe strip): framed $BF packets are
bootstrap (HELLO -> WELCOME + WINDOW chunks), 64-byte $AD packets are
realtime. Realtime connections must authenticate with NET_RT_AUTH before any
PLAYER_STATE is honored; all authenticated players share one GameState.
"""

from __future__ import annotations

import argparse
import selectors
import socket
import time
import traceback
from collections import deque
from dataclasses import dataclass

try:
    from .game import MAP_OVERWORLD, GameState
    from .lobby_client import LobbyConfig, LobbyPublisher
    from .pvp_bots import DEFAULT_PVP_BOT_TOKEN_BASE, PVP_BOT_MAX_COUNT, PvpBotConfig, PvpBotController
    from .protocol import (
        MAGIC,
        REALTIME_DEFAULT_REMOTE_PLAYERS,
        REALTIME_MAGIC,
        REALTIME_PREAMBLE,
        REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED,
        REALTIME_PACKET_BYTES,
        REALTIME_SMALL_PACKET_BYTES,
        WINDOW_H,
        WINDOW_W,
        ItemDropsPacket,
        PacketError,
        PacketStreamDecoder,
        RealtimeFrameDecoder,
        PacketType,
        PlayerStatePacket,
        RemotePlayersPacket,
        CacheStepAckPacket,
        TerrainEdgePacket,
        MapChangePacket,
        RealtimeType,
        Welcome,
        WindowCommitAckPacket,
        WindowRowPacket,
        decode_auth,
        decode_hello,
        decode_map_ready,
        decode_player_state,
        decode_resync_request,
        decode_cache_step_ack,
        decode_net_stats,
        decode_window_commit,
        encode_window_commit_ack,
        encode_hud_update,
        encode_inventory_update,
        encode_item_drops,
        encode_map_summary,
        encode_map_change,
        encode_dialogue_page,
        encode_message,
        encode_quest_update,
        encode_remote_players,
        encode_respawn_event,
        encode_terrain_edge,
        encode_welcome,
        encode_window,
        encode_window_row,
        encode_world_state,
        WorldStatePacket,
        seq_delta,
        window_chunks,
    )
    from .login_server import SessionStore
    from .quests import MSG_PLAYER_ENTERED, MSG_PLAYER_LEFT, MSG_WELCOME_BACK, MSG_WELCOME_NEW
    from .bootstrap_server import REGISTER, SMOKE_PROBE
except ImportError:  # pragma: no cover - direct script execution
    from game import MAP_OVERWORLD, GameState
    from lobby_client import LobbyConfig, LobbyPublisher
    from pvp_bots import DEFAULT_PVP_BOT_TOKEN_BASE, PVP_BOT_MAX_COUNT, PvpBotConfig, PvpBotController
    from protocol import (
        MAGIC,
        REALTIME_DEFAULT_REMOTE_PLAYERS,
        REALTIME_MAGIC,
        REALTIME_PREAMBLE,
        REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED,
        REALTIME_PACKET_BYTES,
        REALTIME_SMALL_PACKET_BYTES,
        WINDOW_H,
        WINDOW_W,
        ItemDropsPacket,
        PacketError,
        PacketStreamDecoder,
        RealtimeFrameDecoder,
        PacketType,
        PlayerStatePacket,
        RemotePlayersPacket,
        CacheStepAckPacket,
        TerrainEdgePacket,
        MapChangePacket,
        RealtimeType,
        Welcome,
        WindowCommitAckPacket,
        WindowRowPacket,
        decode_auth,
        decode_hello,
        decode_map_ready,
        decode_player_state,
        decode_resync_request,
        decode_cache_step_ack,
        decode_net_stats,
        decode_window_commit,
        encode_window_commit_ack,
        encode_hud_update,
        encode_inventory_update,
        encode_item_drops,
        encode_map_summary,
        encode_map_change,
        encode_dialogue_page,
        encode_message,
        encode_quest_update,
        encode_remote_players,
        encode_respawn_event,
        encode_terrain_edge,
        encode_welcome,
        encode_window,
        encode_window_row,
        encode_world_state,
        WorldStatePacket,
        seq_delta,
        window_chunks,
    )
    from login_server import SessionStore
    from quests import MSG_PLAYER_ENTERED, MSG_PLAYER_LEFT, MSG_WELCOME_BACK, MSG_WELCOME_NEW
    from bootstrap_server import REGISTER, SMOKE_PROBE


KIND_UNKNOWN = "unknown"
KIND_BOOTSTRAP = "bootstrap"
KIND_REALTIME = "realtime"

AUTH_TIMEOUT = 5.0
PLAYER_IDLE_TIMEOUT = 35.0
REMOTE_REFRESH_INTERVAL = 0.5
# How long a finished fill may wait for the client's WINDOW_COMMIT before
# the server abandons it and starts a fresh transaction (which discards the
# client's staged rows). The client's silence NACK (~0.75 s cadence, missing
# rows only, same fill id) is the primary recovery under loss; this timeout
# is the last resort and must leave room for several NACK rounds.
WINDOW_COMMIT_TIMEOUT = 6.0
# While a player is transition-loading (MAP_CHANGE sent, MAP_READY not yet
# received), re-send the MAP_CHANGE at this interval. Play stays paused for
# the player the whole time, so a transition packet lost on the serial link
# heals instead of stranding the client on the old map's art.
MAP_CHANGE_RESEND_INTERVAL = 2.0
# Phase 40: relative cache movement is one acknowledged step at a time. A
# step unacknowledged past this deadline is retransmitted byte-identically;
# past the retry ceiling the server escalates to a full window fill. Sized
# for remote (VPS) links: internet RTT + serial transit both ways + client
# frame processing can reach ~300 ms, and retransmitting before the ACK can
# arrive wastes line budget and burns the retry ceiling spuriously.
CACHE_STEP_RETRANSMIT = 0.5
# Steps in flight at once (go-back-N). Stop-and-wait capped throughput at
# 1 step/RTT (~3-4/s on a VPS link), below sustained walking speed; a
# 3-deep pipeline triples it while each lost step still costs only one
# retransmit round of itself plus its followers.
CACHE_STEP_PIPELINE = 3
CACHE_STEP_RETRY_LIMIT = 4
# Phase 42 output scheduler: per-session byte budget sized for the 31,250
# baud deployment standard (~3,125 B/s line rate) with headroom for the
# client's own transmissions and serial service jitter.
DEFAULT_CLIENT_BYTE_RATE = 2000.0
DEFAULT_CLIENT_BURST_BYTES = 384
MESSAGE_QUEUE_LIMIT = 8
DEFAULT_EDGE_BUDGET = 3
# WINDOW_ROW packets sent per tick during an in-band window fill. At 31250
# baud the line carries ~3125 B/s; each row is 64 bytes and WORLD_STATE
# adds 640 B/s, so 2 rows/tick (~1920 B/s total) keeps ~40% headroom while
# halving fill time vs 1. Raise via --resync-row-budget with care.
DEFAULT_RESYNC_ROW_BUDGET = 2


# Phase 54: per-client link profiles. The HELLO flags byte (always sent,
# previously ignored) declares what link the client is on, so each session
# is paced to its own line instead of every session being paced for the
# slowest one. Unknown ids fall back to the default profile, so a client
# cannot talk the server into a rate the deployment has not vetted and old
# clients (which send flags 0) are unchanged by construction.
@dataclass(frozen=True)
class ClientLinkProfile:
    name: str
    line_rate: float  # bytes/s the physical link carries, documentation
    byte_rate: float  # output budget: line_rate * LINK_BUDGET_FRACTION
    burst_bytes: int  # token-bucket burst: ~BURST_SECONDS at byte_rate
    resync_row_budget: int  # WINDOW_ROW packets per tick during a fill
    edge_budget: int


# Headroom for the client's own transmissions and serial service jitter on
# a half-duplex line. 0.64 is the historical Atari ratio (2000 / 3125); the
# byte_rate values below are that fraction of line rate, rounded, but
# profile 0 must remain numerically identical to the historical constants
# (the tests guard this against literals).
LINK_BUDGET_FRACTION = 0.64
# The default burst (384 B at 2000 B/s) is ~0.192 s of line budget; the
# other profiles keep the same time constant.
LINK_BURST_SECONDS = 0.192

LINK_PROFILE_DEFAULT = 0
LINK_PROFILE_LYNX_COMLYNX = 1
LINK_PROFILE_ATARI_19200 = 2

CLIENT_LINK_PROFILES: dict[int, ClientLinkProfile] = {
    # Atari at 31,250 baud (10 bits/byte): exactly today's constants.
    LINK_PROFILE_DEFAULT: ClientLinkProfile(
        name="atari_31250",
        line_rate=3125.0,
        byte_rate=DEFAULT_CLIENT_BYTE_RATE,
        burst_bytes=DEFAULT_CLIENT_BURST_BYTES,
        resync_row_budget=DEFAULT_RESYNC_ROW_BUDGET,
        edge_budget=DEFAULT_EDGE_BUDGET,
    ),
    # Lynx ComLynx at 62,500 baud, odd parity (11 bits/byte): ~5,681 B/s line.
    # 2,800 is the hardware-validated working rate (2026-07-23). The 0.64 ratio
    # suggested 3,636, but that runs a *half-duplex* line at ~70% utilisation,
    # and since the client must also transmit PLAYER_STATE the two directions
    # collide: the server never sees the move, corrects the player back, and
    # walking freezes in place (parity/framing errors show on the link page).
    # 2,800 (~56% one-way) leaves room for the client's transmits in the quiet
    # gap after each server tick; on hardware it walked, entered/exited PvP and
    # crossed the world without freezing, while staying above the old 2,000
    # default so enemy motion is smoother than the Atari baseline.
    #
    # Even 2,800 is only safe because the CPU tile blitter drains the driver's
    # 256-byte RX ring every row during a repaint (render_set_rx_pump); a 94 ms
    # repaint would otherwise take in ~263 B and overflow it. Burst and rows
    # stay at the defaults (they overflow within one tick regardless). Pushing
    # back toward 3,636 would need the client to schedule its transmits into the
    # inter-tick quiet window -- deferred, marginal gain over 2,800.
    LINK_PROFILE_LYNX_COMLYNX: ClientLinkProfile(
        name="lynx_comlynx_62500",
        line_rate=5681.0,
        byte_rate=2800.0,
        burst_bytes=DEFAULT_CLIENT_BURST_BYTES,
        resync_row_budget=DEFAULT_RESYNC_ROW_BUDGET,
        edge_budget=DEFAULT_EDGE_BUDGET,
    ),
    # Slower Atari selection (19,200 baud, ~1,920 B/s), currently
    # over-served by the default budget.
    LINK_PROFILE_ATARI_19200: ClientLinkProfile(
        name="atari_19200",
        line_rate=1920.0,
        byte_rate=1229.0,
        burst_bytes=236,
        resync_row_budget=1,
        edge_budget=DEFAULT_EDGE_BUDGET,
    ),
}
DEFAULT_LOBBY_BASE_URL = "https://lobby.fujinet.online"
DEFAULT_LOBBY_CREATOR_ID = 0x3022
DEFAULT_LOBBY_APP_ID = 0x02
DEFAULT_LOBBY_GAME_NAME = "FujiRealm Demo"
DEFAULT_LOBBY_SERVER_NAME = "The Realm"
DEFAULT_LOBBY_REGION = "us"
DEFAULT_LOBBY_SERVER_URL = "tcp://fujinet.online:9010"
DEFAULT_LOBBY_MAX_PLAYERS = 32
DEFAULT_LOBBY_CLIENT_PLATFORM = "atari"
DEFAULT_LOBBY_CLIENT_URL = "TNFS://tnfs.fujinet.online/ATARI/netgames/fujirealm.atr"
DEFAULT_GAME_SEED = 1
AUTH_TIMEOUT_CHURN_THRESHOLD = 2
# Bound on the per-host auth-timeout diagnostic counters: internet bots
# arrive from ever-new addresses, and the counts are only churn telemetry.
AUTH_TIMEOUT_HOSTS_MAX = 256
# A bootstrap not followed by a realtime attach within this window is
# abandoned; expiring the marker merely forces a full window resync if the
# client ever does attach.
BOOTSTRAP_TOKEN_TTL = 300.0
# When the session window origin is further than this from its target, a
# 1-tile-at-a-time edge stream would saturate the ~3 KB/s Netstream link for
# seconds (respawn/teleport). Stream a fresh full window in-band instead.
# 12 (not 8) so a player running at full speed during the ~0.8 s fill cannot
# ping-pong straight into another fill.
WINDOW_RESYNC_DISTANCE = 12


class SessionOutput:
    """Prioritized, coalescing, token-bucket-limited output queue.

    Reliable frames (window rows, cache steps, map changes, acks) keep FIFO
    order and identity. Replaceable state (world/remote/items/UI) keeps only
    the newest unsent frame per category. Messages use a bounded FIFO. A
    partially written frame always completes before the next is selected,
    so COBS frames are never interleaved.
    """

    # "dialogue" sits high so a page the player is blocked on is not starved
    # under heavy terrain/world load (the busy-load path exercised on hardware).
    LATEST_ORDER = ("world", "remote", "dialogue", "items", "hud", "quest", "inventory", "map_summary")

    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self.partial: bytes | None = None
        self.partial_offset = 0
        self.reliable: deque[bytes] = deque()
        self.latest: dict[str, bytes | None] = {slot: None for slot in self.LATEST_ORDER}
        self.messages: deque[bytes] = deque()
        self.bytes_queued = 0
        self.bytes_sent = 0
        self.frames_coalesced = 0
        self.write_blocked = 0
        self.partial_writes = 0
        self.budget_deferred = 0

    def queue_reliable(self, data: bytes) -> None:
        self.reliable.append(data)
        self.bytes_queued += len(data)

    def queue_latest(self, slot: str, data: bytes) -> None:
        if self.latest[slot] is not None:
            self.frames_coalesced += 1
        self.latest[slot] = data
        self.bytes_queued += len(data)

    def queue_message(self, data: bytes) -> None:
        if len(self.messages) >= MESSAGE_QUEUE_LIMIT:
            self.messages.popleft()
        self.messages.append(data)
        self.bytes_queued += len(data)

    def clear_latest(self) -> None:
        for slot in self.latest:
            self.latest[slot] = None

    def pending(self) -> bool:
        if self.partial is not None:
            return True
        if self.reliable or self.messages:
            return True
        return any(frame is not None for frame in self.latest.values())

    def refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.last_refill)
        self.last_refill = now
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)

    def next_frame(self) -> tuple[bytes, bool] | None:
        if self.reliable:
            return self.reliable.popleft(), True
        for slot in self.LATEST_ORDER:
            frame = self.latest[slot]
            if frame is not None:
                self.latest[slot] = None
                return frame, False
        if self.messages:
            return self.messages.popleft(), False
        return None


class ClientSession:
    def __init__(self, conn: socket.socket, addr: tuple[str, int], now: float) -> None:
        self.conn = conn
        self.addr = addr
        self.connected_at = now
        self.last_heard_at = now
        self.kind = KIND_UNKNOWN
        self.rx = bytearray()
        self.decoder = PacketStreamDecoder()
        self.frame_decoder = RealtimeFrameDecoder()
        self.token: int | None = None
        self.latest: PlayerStatePacket | None = None
        self.latest_seq: int | None = None
        self.accepted = True
        self.server_seq = 0
        self.window_origin: tuple[int, int] = (0, 0)
        self.hud_sent: tuple[int, ...] | None = None
        self.quest_sent: tuple[int, ...] | None = None
        self.inventory_sent: tuple[int, ...] | None = None
        self.message_counter_sent = 0
        self.respawn_counter_sent = 0
        self.remote_sent: tuple = ()
        self.remote_sent_at = 0.0
        self.items_sent: tuple = ()
        self.items_sent_at = 0.0
        self.map_summary_sent: tuple | None = None
        self.last_rx_drops: int | None = None
        self.bootstrap_done = False
        self.needs_full_resync = False
        # Remaining WINDOW_ROW indices of an in-band window resync, sent in
        # order from the front; None = idle. A client NACK (rows_have bitmap)
        # starts a fill holding only the missing rows.
        self.resync_rows: list[int] | None = None
        self.fill_id = 0
        self.fill_origin: tuple[int, int] | None = None
        self.fill_waiting_for_commit = False
        self.fill_waiting_since = 0.0
        self.last_map_change = None
        self.map_change_sent_at = 0.0
        self.last_net_stats = None
        # Phase 40 acknowledged cache steps, pipelined (go-back-N): an
        # ordered queue of unacked (revision, origin, packet) steps.
        # window_origin advances only on the client's ACKs; an ACK for a
        # later step confirms every earlier one (the client applies in
        # order). The retransmit timer tracks the oldest unacked step.
        self.next_cache_revision = 0
        self.inflight_steps: deque = deque()
        self.step_sent_at = 0.0
        self.step_retries = 0
        self.last_acked_revision = 0
        # Phase 54: link-profile-derived pacing, per session. Applied from
        # the default profile at accept and from the HELLO flags byte at
        # bootstrap (or adopted by token at realtime attach); explicit CLI
        # overrides win. edge_budget currently has no consumer (the Phase 40
        # step pipeline superseded it) but follows the profile so a future
        # consumer is per-session from the start.
        self.link_profile_id = LINK_PROFILE_DEFAULT
        self.resync_row_budget = DEFAULT_RESYNC_ROW_BUDGET
        self.edge_budget = DEFAULT_EDGE_BUDGET
        self.out = SessionOutput(DEFAULT_CLIENT_BYTE_RATE, DEFAULT_CLIENT_BURST_BYTES)

    def next_seq(self) -> int:
        seq = self.server_seq
        self.server_seq = (self.server_seq + 1) & 0xFFFF
        return seq


class FujiRealmHybridServer:
    def __init__(
        self,
        host: str,
        port: int,
        tick_hz: int = 10,
        debug: bool = False,
        debug_errors_only: bool = False,
        edge_budget: int | None = None,
        resync_row_budget: int | None = None,
        client_byte_rate: float | None = None,
        client_burst_bytes: int | None = None,
        visible_remotes: int = REALTIME_DEFAULT_REMOTE_PLAYERS,
        auth_timeout: float = AUTH_TIMEOUT,
        player_idle_timeout: float = PLAYER_IDLE_TIMEOUT,
        test_pvp_bots: int = 0,
        test_pvp_bot_move_every: int = 4,
        test_pvp_bot_mode: str = "arena",
        test_pvp_bot_orbit_every: int = 8,
        test_pvp_bot_fire_cooldown: float = 2.0,
        test_pvp_bots_no_fire: bool = False,
        test_pvp_bot_token_base: int = DEFAULT_PVP_BOT_TOKEN_BASE,
        session_store: SessionStore | None = None,
        lobby_enabled: bool = False,
        lobby_base_url: str = DEFAULT_LOBBY_BASE_URL,
        lobby_creator_id: int = DEFAULT_LOBBY_CREATOR_ID,
        lobby_app_id: int = DEFAULT_LOBBY_APP_ID,
        lobby_game_name: str = DEFAULT_LOBBY_GAME_NAME,
        lobby_server_name: str = DEFAULT_LOBBY_SERVER_NAME,
        lobby_region: str = DEFAULT_LOBBY_REGION,
        lobby_server_url: str = DEFAULT_LOBBY_SERVER_URL,
        lobby_max_players: int = DEFAULT_LOBBY_MAX_PLAYERS,
        lobby_client_platform: str = DEFAULT_LOBBY_CLIENT_PLATFORM,
        lobby_client_url: str = DEFAULT_LOBBY_CLIENT_URL,
        lobby_timeout: float = 2.0,
        lobby_publisher: LobbyPublisher | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.tick_hz = tick_hz
        self.debug = debug
        self.debug_errors_only = debug_errors_only
        # Phase 54: these are *overrides*. None means "use the session's
        # link profile"; an explicit value (CLI flag or test constructor)
        # wins over the profile table for every session, preserving the
        # pre-profile operator workflow.
        self.edge_budget = edge_budget
        self.resync_row_budget = None if resync_row_budget is None else max(1, resync_row_budget)
        self.client_byte_rate = client_byte_rate
        self.client_burst_bytes = client_burst_bytes
        if not 1 <= visible_remotes <= REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED:
            raise ValueError(f"visible_remotes must be 1..{REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED}")
        self.visible_remotes = visible_remotes
        self.auth_timeout = auth_timeout
        self.player_idle_timeout = player_idle_timeout
        self.session_store = session_store or SessionStore()
        self.pvp_bot_tokens: set[int] = set(
            range(test_pvp_bot_token_base, test_pvp_bot_token_base + max(0, test_pvp_bots))
        )
        self.game = GameState(
            # Bootstrap parser recovery treats mid-packet 0xBF as a resync
            # marker, so WELCOME bytes after the initial magic must not contain
            # 0xBF. Keep randomized future seeds behind _bootstrap_safe_seed().
            seed=self._bootstrap_safe_seed(DEFAULT_GAME_SEED),
            create_default_player=False,
            player_state_loader=self._load_player_record,
            player_state_saver=self._save_player_state,
        )
        bot_fire_cooldown_ticks = max(1, round(test_pvp_bot_fire_cooldown * max(1, tick_hz)))
        self.pvp_bots = PvpBotController(
            self.game,
            PvpBotConfig(
                enabled=test_pvp_bots > 0,
                count=test_pvp_bots,
                token_base=test_pvp_bot_token_base,
                move_every_ticks=test_pvp_bot_move_every,
                mode=test_pvp_bot_mode,
                orbit_every_ticks=test_pvp_bot_orbit_every,
                fire_cooldown_ticks=bot_fire_cooldown_ticks,
                can_fire=not test_pvp_bots_no_fire,
            ),
        )
        self.sessions: dict[socket.socket, ClientSession] = {}
        self.realtime_by_token: dict[int, ClientSession] = {}
        self.auth_timeout_counts: dict[str, int] = {}
        # Tokens that completed a bootstrap since their last realtime attach,
        # mapped to when. An AUTH without one means the socket was replaced
        # underneath the client (FujiNet firmware reconnects TCP
        # transparently), so its terrain cache is unsynced and needs a forced
        # re-bootstrap. Entries expire after BOOTSTRAP_TOKEN_TTL.
        self.bootstrapped_tokens: dict[int, float] = {}
        # Phase 54: link profile declared in the bootstrap HELLO, by token,
        # so a client that opens a *second* connection for realtime (the
        # Atari path) is paced by the profile it declared. Entries expire
        # with bootstrapped_tokens; a miss falls back to the session's
        # current (default) profile.
        self.bootstrapped_profiles: dict[int, int] = {}
        self.selector: selectors.BaseSelector | None = None
        self._stop_requested = False
        self._shutdown_in_progress = False
        if lobby_publisher is not None:
            self.lobby = lobby_publisher
        elif lobby_enabled:
            self.lobby = LobbyPublisher(
                LobbyConfig(
                    base_url=lobby_base_url,
                    game=lobby_game_name,
                    creator_id=lobby_creator_id,
                    app_id=lobby_app_id,
                    server=lobby_server_name,
                    region=lobby_region,
                    server_url=lobby_server_url,
                    max_players=lobby_max_players,
                    client_platform=lobby_client_platform,
                    client_url=lobby_client_url,
                    timeout=lobby_timeout,
                ),
                self._log_error,
            )
        else:
            self.lobby = None

    def _apply_link_profile(self, session: ClientSession, profile_id: int) -> None:
        """Pace a session per its declared link profile (Phase 54).

        Unknown ids fall back to the default profile. Explicit server-level
        overrides (--client-byte-rate and friends) beat the profile table.
        The token bucket's accumulated tokens are clamped, never raised, so
        applying a profile mid-stream cannot mint a burst.
        """
        profile = CLIENT_LINK_PROFILES.get(profile_id)
        if profile is None:
            profile_id = LINK_PROFILE_DEFAULT
            profile = CLIENT_LINK_PROFILES[LINK_PROFILE_DEFAULT]
        session.link_profile_id = profile_id
        session.out.rate = self.client_byte_rate if self.client_byte_rate is not None else profile.byte_rate
        session.out.burst = (
            self.client_burst_bytes if self.client_burst_bytes is not None else profile.burst_bytes
        )
        session.out.tokens = min(session.out.tokens, float(session.out.burst))
        session.resync_row_budget = (
            self.resync_row_budget if self.resync_row_budget is not None else profile.resync_row_budget
        )
        session.edge_budget = self.edge_budget if self.edge_budget is not None else profile.edge_budget

    def username_for_token(self, token: int) -> str:
        record = self.session_store.get_record(token)
        if record is None:
            return f"Player{token & 0xFFFF:04X}"
        return record["username"]

    @staticmethod
    def _bootstrap_safe_seed(seed: int) -> int:
        seed &= 0xFFFF
        for _ in range(0x10000):
            welcome = encode_welcome(Welcome(player_id=1, seed=seed))
            if 0xBF not in welcome[1:]:
                return seed
            seed = (seed + 1) & 0xFFFF
        raise ValueError("could not find bootstrap-safe WELCOME seed")

    def _load_player_record(self, token: int) -> dict[str, object] | None:
        pvp_bots = getattr(self, "pvp_bots", None)
        if pvp_bots is not None and token in pvp_bots.bot_tokens:
            return None
        if token in self.pvp_bot_tokens:
            return None
        return self.session_store.get_record(token)

    def _save_player_state(self, token: int, username: str, player_state: dict[str, object]) -> None:
        pvp_bots = getattr(self, "pvp_bots", None)
        if pvp_bots is not None and token in pvp_bots.bot_tokens:
            return
        if token in self.pvp_bot_tokens:
            return
        self.session_store.save_player_state(token, username, player_state)

    def stop(self) -> None:
        self._stop_requested = True

    def _log_debug(self, message: str) -> None:
        if self.debug:
            print(message)

    def _log_error(self, message: str) -> None:
        if self.debug or self.debug_errors_only:
            print(message)

    def _publish_lobby(self, status: str) -> None:
        if self.lobby is not None:
            self.lobby.publish(len(self.realtime_by_token), status)

    def _delete_lobby(self) -> None:
        if self.lobby is not None:
            print("lobby delete on shutdown")
            if self.lobby.delete():
                print("lobby delete succeeded")
            else:
                print("lobby delete failed")

    # ------------------------------------------------------------------
    # Main loop

    def serve(self, duration: float | None = None) -> None:
        tick_interval = 1.0 / max(1, self.tick_hz)
        next_tick = time.monotonic()
        stop_at = None if duration is None else time.monotonic() + duration
        self.selector = selectors.DefaultSelector()
        with socket.create_server((self.host, self.port), reuse_port=False) as server:
            server.setblocking(False)
            server.listen()
            self.selector.register(server, selectors.EVENT_READ, "server")
            self._log_debug(f"hybrid server listening {self.host}:{self.port}")
            self.session_store.set_all_offline()
            if self.pvp_bots.config.enabled:
                self._log_debug(
                    f"pvp bots enabled count={self.pvp_bots.config.count} "
                    f"visible_remotes={self.visible_remotes} "
                    f"mode={self.pvp_bots.config.mode} "
                    f"move_every={self.pvp_bots.config.move_every_ticks} "
                    f"orbit_every={self.pvp_bots.config.orbit_every_ticks} "
                    f"fire_cd_ticks={self.pvp_bots.config.fire_cooldown_ticks} "
                    f"can_fire={int(self.pvp_bots.config.can_fire)}"
                )
            self._publish_lobby("online")
            try:
                while not self._stop_requested and (stop_at is None or time.monotonic() < stop_at):
                    timeout = max(0.0, min(0.02, next_tick - time.monotonic()))
                    for key, mask in self.selector.select(timeout):
                        if key.data == "server":
                            try:
                                conn, addr = server.accept()
                                conn.setblocking(False)
                            except OSError as exc:
                                # ECONNABORTED, EMFILE, ...: a hostile peer
                                # or fd pressure must not kill the listener.
                                self._log_error(f"accept failed: {exc}")
                                continue
                            session = ClientSession(conn, addr, time.monotonic())
                            self._apply_link_profile(session, LINK_PROFILE_DEFAULT)
                            session.out.tokens = float(session.out.burst)
                            self.sessions[conn] = session
                            self.selector.register(conn, selectors.EVENT_READ, "client")
                            self._log_debug(f"client connected {addr[0]}:{addr[1]}")
                            continue
                        conn = key.fileobj
                        assert isinstance(conn, socket.socket)
                        session = self.sessions.get(conn)
                        if session is None:
                            continue
                        if mask & selectors.EVENT_WRITE:
                            if not self._flush_session_output(session, time.monotonic()):
                                self._drop_session(session, "send failed")
                                continue
                        if not (mask & selectors.EVENT_READ):
                            continue
                        try:
                            chunk = conn.recv(1024)
                        except BlockingIOError:
                            continue
                        except OSError:
                            chunk = b""
                        if not chunk:
                            self._drop_session(session, "closed")
                            continue
                        self._log_debug(f"rx raw {chunk.hex()}")
                        session.rx.extend(chunk)
                        try:
                            self._process_session(session)
                        except Exception:
                            # One malformed client must not crash the server.
                            self._log_error(
                                f"session error {session.addr[0]}:{session.addr[1]} "
                                f"token={session.token}:\n{traceback.format_exc()}"
                            )
                            self._drop_session(session, "internal error")

                    try:
                        self._drop_stale_sessions()
                    except Exception:
                        self._log_error(f"stale-session sweep failed:\n{traceback.format_exc()}")
                    now = time.monotonic()
                    if now >= next_tick:
                        try:
                            self._tick(now)
                        except Exception:
                            self._log_error(f"tick failed:\n{traceback.format_exc()}")
                        next_tick += tick_interval
                        if next_tick <= now:
                            next_tick = now + tick_interval
            finally:
                self._shutdown_in_progress = True
                for session in list(self.sessions.values()):
                    self._drop_session(session, "server stopping")
                self._delete_lobby()
                self.selector.close()
                self.selector = None

    # ------------------------------------------------------------------
    # Session lifecycle

    def _drop_session(self, session: ClientSession, reason: str) -> None:
        self._log_error(
            f"drop {session.kind} client {session.addr[0]}:{session.addr[1]} token={session.token} ({reason})"
        )
        if self.selector is not None:
            try:
                self.selector.unregister(session.conn)
            except (KeyError, ValueError):
                pass
        self.sessions.pop(session.conn, None)
        try:
            session.conn.close()
        except OSError:
            pass
        if session.token is not None and self.realtime_by_token.get(session.token) is session:
            token = session.token
            name = self.game.player_display_name(token)
            self.realtime_by_token.pop(token, None)
            self.game.detach_player(token)
            self.session_store.set_online(token, False)
            self.game.queue_server_message(f"{name} has left the realm!", MSG_PLAYER_LEFT)
            if not self._shutdown_in_progress:
                self._publish_lobby("online")

    def _record_auth_timeout(self, session: ClientSession) -> None:
        host = session.addr[0]
        if host not in self.auth_timeout_counts:
            while len(self.auth_timeout_counts) >= AUTH_TIMEOUT_HOSTS_MAX:
                self.auth_timeout_counts.pop(next(iter(self.auth_timeout_counts)))
        count = self.auth_timeout_counts.get(host, 0) + 1
        self.auth_timeout_counts[host] = count
        if count >= AUTH_TIMEOUT_CHURN_THRESHOLD:
            self._log_error(
                f"auth-timeout churn peer={host} count={count} "
                f"kind={session.kind} token={session.token}"
            )

    def _drop_stale_sessions(self) -> None:
        now = time.monotonic()
        for token, bootstrapped_at in list(self.bootstrapped_tokens.items()):
            if now - bootstrapped_at > BOOTSTRAP_TOKEN_TTL:
                del self.bootstrapped_tokens[token]
                self.bootstrapped_profiles.pop(token, None)
        for session in list(self.sessions.values()):
            if session.kind == KIND_REALTIME and session.token is not None:
                if now - session.last_heard_at > self.player_idle_timeout:
                    self._drop_session(session, "player idle timeout")
                continue
            if session.bootstrap_done and session.kind in (KIND_BOOTSTRAP, KIND_UNKNOWN):
                # A finished bootstrap client may close or may still be
                # receiving its paced WINDOW before sending RT3. Keep the
                # longer idle deadline until a realtime preamble classifies it.
                if now - session.last_heard_at > self.player_idle_timeout:
                    self._drop_session(session, "bootstrap idle timeout")
                continue
            if now - session.connected_at > self.auth_timeout:
                self._record_auth_timeout(session)
                self._drop_session(session, "auth timeout")

    # ------------------------------------------------------------------
    # Receive path

    def _process_session(self, session: ClientSession) -> None:
        self._consume_preamble(session)
        if session.kind == KIND_UNKNOWN:
            self._classify_session(session)
        if session.kind == KIND_BOOTSTRAP:
            self._process_bootstrap(session)
        elif session.kind == KIND_REALTIME:
            self._process_realtime(session)

    def _consume_preamble(self, session: ClientSession) -> None:
        if session.kind != KIND_UNKNOWN:
            return
        rx = session.rx
        changed = True
        while changed and rx:
            changed = False
            if rx.startswith(REGISTER):
                del rx[: len(REGISTER)]
                changed = True
                self._log_debug("rx REGISTER")
            elif REGISTER.startswith(bytes(rx)):
                # partial REGISTER prefix; wait for more bytes
                return
            if rx and rx[0] == SMOKE_PROBE:
                try:
                    session.conn.sendall(bytes((SMOKE_PROBE,)))
                except OSError:
                    self._drop_session(session, "probe send failed")
                    return
                del rx[0]
                changed = True
                self._log_debug("rx/tx smoke probe 42")

    def _classify_session(self, session: ClientSession) -> None:
        rx = session.rx
        while rx:
            if rx[0] == MAGIC:
                session.kind = KIND_BOOTSTRAP
                return
            if rx[0] == REALTIME_PREAMBLE[0]:
                prefix = bytes(rx[: len(REALTIME_PREAMBLE)])
                if prefix == REALTIME_PREAMBLE:
                    session.kind = KIND_REALTIME
                    del rx[: len(REALTIME_PREAMBLE)]
                    return
                if REALTIME_PREAMBLE.startswith(prefix):
                    # Partial preamble; wait for more bytes.
                    return
            del rx[0]

    def _process_bootstrap(self, session: ClientSession) -> None:
        session.last_heard_at = time.monotonic()
        packets = session.decoder.feed(bytes(session.rx))
        session.rx.clear()
        for packet in packets:
            if packet.packet_type != PacketType.HELLO:
                continue
            try:
                hello = decode_hello(packet.payload)
            except PacketError:
                continue
            if not hello.token:
                self._drop_session(session, "anonymous HELLO rejected")
                return
            # A state carrying "fresh_start" was written by the old-version
            # reset (tools/reset_old_sessions.py), not by play: the player kept
            # their token and name but their progress is gone, so greet them as
            # new. The flag needs no explicit clearing -- deserialize ignores it
            # and serialize never emits it, so the first save drops it.
            stored_state = self.session_store.load_player_state(hello.token)
            is_returning = (
                hello.token in self.game.players
                or hello.token in self.game.offline_players
                or (stored_state is not None and not stored_state.get("fresh_start"))
            )
            # Phase 54: the flags byte declares the client's link profile.
            # Applied before WELCOME/WINDOW are queued so the initial window
            # transfer -- the largest burst in the session -- is already
            # paced at the declared rate.
            self._apply_link_profile(session, hello.flags)
            if session.link_profile_id != LINK_PROFILE_DEFAULT:
                # A non-default link profile is rare and operationally
                # interesting (it is how a Lynx confirms it was paced for
                # ComLynx), so surface it even under --debug-errors-only,
                # where the full bootstrap-complete line below is silent.
                profile = CLIENT_LINK_PROFILES[session.link_profile_id]
                self._log_error(
                    f"link profile token={hello.token} "
                    f"id={session.link_profile_id} {profile.name} "
                    f"rate={session.out.rate:.0f} burst={session.out.burst} "
                    f"rows={session.resync_row_budget}"
                )
            player = self.game.ensure_player(hello.token)
            player = self.game.set_player_username(hello.token, self.username_for_token(hello.token))
            if is_returning:
                self.game.queue_activity_message(player, "Welcome back.", MSG_WELCOME_BACK)
            else:
                self.game.queue_activity_message(player, "Welcome to FujiRealm!", MSG_WELCOME_NEW)
            session.out.queue_reliable(encode_welcome(Welcome(player_id=1, seed=self.game.seed)))
            for window_chunk in window_chunks(self.game.window(hello.token)):
                session.out.queue_reliable(encode_window(window_chunk))
            # Bootstrap used to bypass the output scheduler and send roughly
            # 900 bytes in one burst. ComLynx has no flow control, so pace one
            # complete BF frame at a time through the normal per-client budget.
            session.out.tokens = min(session.out.tokens, 1.0)
            session.out.last_refill = time.monotonic()
            self._update_write_interest(session)
            session.bootstrap_done = True
            self.bootstrapped_tokens[hello.token] = time.monotonic()
            self.bootstrapped_profiles[hello.token] = session.link_profile_id
            # A client may keep this TCP stream and identify it again with the
            # realtime preamble after consuming WELCOME and WINDOW. Clients
            # that use the traditional second connection may still close it.
            session.kind = KIND_UNKNOWN
            session.connected_at = time.monotonic()
            session.last_heard_at = session.connected_at
            self._log_debug(
                f"bootstrap complete token={hello.token} map={player.map_id} "
                f"pos={player.x},{player.y} "
                f"profile={CLIENT_LINK_PROFILES[session.link_profile_id].name} "
                f"rate={session.out.rate:.0f} awaiting realtime preamble"
            )
            return

    def _process_realtime(self, session: ClientSession) -> None:
        rx = session.rx
        frames = session.frame_decoder.feed(bytes(rx))
        rx.clear()
        for data in frames:
            try:
                auth = decode_auth(data)
            except PacketError:
                auth = None
            if auth is not None:
                if auth.token == 0:
                    self._drop_session(session, "auth token 0 rejected")
                    return
                if session.token == auth.token:
                    session.last_heard_at = time.monotonic()
                    continue
                if session.token is None:
                    self._attach_realtime(session, auth.token)
                    continue
                continue
            if session.token is None:
                continue
            try:
                ready = decode_map_ready(data)
            except PacketError:
                pass
            else:
                session.last_heard_at = time.monotonic()
                player = self.game.players.get(session.token)
                if player is not None and player.map_id == ready.map_id:
                    self.game.mark_player_map_ready(session.token)
                    self._log_debug(
                        f"rx MAP_READY token={session.token} seq={ready.seq} "
                        f"map={ready.map_id} origin={ready.origin_x},{ready.origin_y}"
                    )
                else:
                    self._log_error(
                        f"ignored MAP_READY token={session.token} seq={ready.seq} "
                        f"map={ready.map_id}"
                    )
                continue
            try:
                resync = decode_resync_request(data)
            except PacketError:
                pass
            else:
                session.last_heard_at = time.monotonic()
                self._handle_resync_request(session, resync)
                continue
            try:
                stats = decode_net_stats(data)
            except PacketError:
                pass
            else:
                session.last_heard_at = time.monotonic()
                session.last_net_stats = stats
                self._log_debug(
                    f"net_stats token={session.token} rx_drops={stats.rx_drops} "
                    f"overflows={stats.handler_overflows} serial={stats.handler_serial_errors} "
                    f"status=${stats.handler_last_status:02X} fill={stats.fill_id} "
                    f"commit_pending={stats.commit_pending} "
                    f"origin={stats.origin_x},{stats.origin_y} rev={stats.cache_revision}"
                )
                continue
            try:
                ack = decode_cache_step_ack(data)
            except PacketError:
                pass
            else:
                session.last_heard_at = time.monotonic()
                self._handle_cache_step_ack(session, ack)
                continue
            try:
                commit = decode_window_commit(data)
            except PacketError:
                pass
            else:
                session.last_heard_at = time.monotonic()
                self._handle_window_commit(session, commit)
                continue
            try:
                player = decode_player_state(data)
            except PacketError:
                continue
            session.last_heard_at = time.monotonic()
            if session.latest_seq is None or seq_delta(player.seq, session.latest_seq) > 0:
                self._log_rx_drops(session, player)
                session.latest = player
                session.latest_seq = player.seq
                self._log_debug(
                    f"rx PLAYER_STATE token={session.token} seq={player.seq} "
                    f"pos={player.x},{player.y} facing={player.facing} "
                    f"buttons={player.buttons:02x} fire={player.fire_counter} "
                    f"pickup={player.pickup_counter}"
                )

    def _log_rx_drops(self, session: ClientSession, player: PlayerStatePacket) -> None:
        previous = session.last_rx_drops
        current = player.rx_drops & 0xFF
        session.last_rx_drops = current
        if previous is None:
            return
        delta = (current - previous) & 0xFF
        if delta == 0:
            return
        self._log_error(
            f"net_rx_drops token={session.token} seq={player.seq} "
            f"delta={delta} total={current}"
        )

    def _attach_realtime(self, session: ClientSession, token: int) -> None:
        stale = self.realtime_by_token.get(token)
        was_realtime_online = stale is not None
        if stale is not None and stale is not session:
            # Reconnect: the new socket supersedes the old session. Clear the
            # stale session's token first so dropping it does not detach the
            # player we are about to resume.
            stale.token = None
            self._drop_session(stale, "superseded by reconnect")
        player = self.game.ensure_player(token)
        player = self.game.set_player_username(token, self.username_for_token(token))
        session.token = token
        session.last_heard_at = time.monotonic()
        session.window_origin = self.game.window_origin(token)
        session.message_counter_sent = player.message_counter
        session.respawn_counter_sent = player.respawn_counter
        # No bootstrap since the last attach: the client's terrain cache may
        # not match the window origin we just derived. Force a re-bootstrap.
        session.needs_full_resync = token not in self.bootstrapped_tokens
        self.bootstrapped_tokens.pop(token, None)
        # Phase 54: adopt the profile declared at bootstrap. A same-socket
        # client already carries it on the session (the fallback); a
        # second-connection client's fresh session picks it up by token. A
        # miss leaves the accept-time default, which is profile 0.
        self._apply_link_profile(
            session, self.bootstrapped_profiles.pop(token, session.link_profile_id)
        )
        if player.transition_loading:
            if session.needs_full_resync:
                # Client state unknown mid-transition: synthesize the
                # MAP_CHANGE for the player's current map so the re-send
                # loop drives the client onto it, keeping play paused
                # until it reports ready.
                tileset_id, palette_id = self.game.map_art_ids(player.map_id)
                session.last_map_change = MapChangePacket(
                    seq=0,
                    map_id=player.map_id,
                    spawn_x=player.x,
                    spawn_y=player.y,
                    tileset_id=tileset_id,
                    palette_id=palette_id,
                    flags=1,
                )
                session.map_change_sent_at = 0.0
            else:
                # A fresh bootstrap delivered the current map's window and
                # art; the client is effectively ready.
                self.game.mark_player_map_ready(token)
        elif player.map_id != MAP_OVERWORLD:
            # A realtime attach, not mid-transition, whose player is not on
            # the client's boot-time default map (Overworld). Deliberately
            # NOT gated on session.needs_full_resync: the legacy HELLO/
            # WELCOME/WINDOW bootstrap that every connection (fresh or
            # reconnect) performs immediately before this AUTH already
            # marks the token bootstrapped, so needs_full_resync is false
            # here on essentially every normal connection -- gating on it
            # meant this branch never actually fired. Neither that legacy
            # WINDOW nor a plain realtime bootstrap window carries
            # tileset/palette fields of its own, so without an explicit
            # MAP_CHANGE here the client keeps rendering with whatever art
            # it defaulted to at boot, regardless of the player's real
            # starting map (e.g. a player who logged out in the cave or
            # PvP realm sees Overworld colors on their next login).
            # Overworld starts need no correction since that already
            # matches the client default.
            tileset_id, palette_id = self.game.map_art_ids(player.map_id)
            session.last_map_change = MapChangePacket(
                seq=0,
                map_id=player.map_id,
                spawn_x=player.x,
                spawn_y=player.y,
                tileset_id=tileset_id,
                palette_id=palette_id,
                flags=1,
            )
            session.map_change_sent_at = 0.0
            player.transition_loading = True
        self.realtime_by_token[token] = session
        self.session_store.set_online(token, True)
        if not was_realtime_online:
            self.game.queue_server_message(
                f"{self.game.player_display_name(token)} has entered the realm!",
                MSG_PLAYER_ENTERED,
                exclude_token=token,
            )
            self._publish_lobby("online")
        self._log_debug(
            f"realtime AUTH token={token} map={player.map_id} pos={player.x},{player.y}"
            f"{' (needs resync)' if session.needs_full_resync else ''}"
        )

    def _handle_resync_request(self, session: ClientSession, resync) -> None:
        token = session.token
        if token is None:
            return
        if resync.flags & 2:
            # Client abandoned a dead staged fill and wants a clean
            # transaction: cancel whatever is in flight and start over.
            self._start_window_resync(session, "client requested clean fill")
            return
        if session.fill_origin is not None and resync.fill_id == session.fill_id:
            missing = [row for row in range(WINDOW_H) if not (resync.rows_have >> row) & 1]
            session.resync_rows = missing
            session.fill_waiting_for_commit = False
            self._log_debug(
                f"fill NACK token={token} fill={resync.fill_id} missing={len(missing)}"
            )
            return
        if session.fill_waiting_for_commit:
            # The client's request does not reference the fill we finished
            # sending (its transaction state was lost or superseded). Abandon
            # the stale fill so the ordinary gap logic below can replay edges
            # or start a fresh transaction instead of blocking edges forever.
            session.fill_origin = None
            session.fill_waiting_for_commit = False
        if session.resync_rows is not None:
            # A throttled row fill can legitimately outlive the Atari client's
            # retry timer. Do not restart from row 0 mid-fill or real hardware
            # can livelock at a map entrance. If rows are still missing after
            # this fill completes, the next request will start a new fill.
            self._log_debug(
                f"window resync token={token} duplicate request ignored "
                f"remaining={len(session.resync_rows)}"
            )
            return
        player = self.game.players.get(token)
        if player is None:
            return
        world = self.game.world_for(player.map_id)
        client_origin = (resync.origin_x, resync.origin_y)
        origin_valid = (
            0 <= client_origin[0] <= world.width - WINDOW_W
            and 0 <= client_origin[1] <= world.height - WINDOW_H
        )
        gap = abs(client_origin[0] - session.window_origin[0]) + abs(
            client_origin[1] - session.window_origin[1]
        )
        if origin_valid and gap == 0:
            # Client is not actually behind (stale-edge false alarm); the
            # normal edge stream already continues from here.
            self._log_debug(f"window resync token={token} noop (client at session origin)")
            return
        if origin_valid and gap <= WINDOW_RESYNC_DISTANCE:
            # Rewind the edge stream to where the client actually is; the
            # normal relative edge streaming replays the missing strips.
            self._cancel_inflight_step(session)
            session.window_origin = client_origin
            self._log_debug(
                f"window resync token={token} edge replay from "
                f"{client_origin[0]},{client_origin[1]} gap={gap} (client request)"
            )
            return
        # NACK path: the client reports which rows of its in-progress fill
        # already arrived. If that fill matches our target origin, resend
        # only the missing rows instead of restarting all 24.
        rows = None
        if resync.rows_have:
            target_origin = self.game.window_origin(token)
            if (resync.fill_origin_x, resync.fill_origin_y) == target_origin:
                missing = [row for row in range(WINDOW_H) if not (resync.rows_have >> row) & 1]
                if missing:
                    rows = missing
        self._start_window_resync(session, f"client request gap={gap}", rows)

    def _update_write_interest(self, session: ClientSession) -> None:
        if self.selector is None:
            return
        try:
            key = self.selector.get_key(session.conn)
        except (KeyError, ValueError):
            return
        want = selectors.EVENT_READ
        if session.out.pending():
            want |= selectors.EVENT_WRITE
        if key.events != want:
            self.selector.modify(session.conn, want, key.data)

    def _queue_reliable(self, session: ClientSession, data: bytes) -> None:
        session.out.queue_reliable(data)

    def _flush_session_output(self, session: ClientSession, now: float) -> bool:
        # Returns False on a fatal socket error. BlockingIOError retains the
        # partially written frame; a frame in progress always completes
        # before the next is selected.
        out = session.out
        out.refill(now)
        while True:
            if out.partial is None:
                if out.tokens <= 0:
                    if out.pending():
                        out.budget_deferred += 1
                    break
                nxt = out.next_frame()
                if nxt is None:
                    break
                out.partial, _ = nxt
                out.partial_offset = 0
            try:
                sent = session.conn.send(out.partial[out.partial_offset :])
            except BlockingIOError:
                out.write_blocked += 1
                break
            except OSError:
                return False
            if sent <= 0:
                return False
            out.partial_offset += sent
            out.bytes_sent += sent
            out.tokens -= sent
            if out.partial_offset < len(out.partial):
                out.partial_writes += 1
                break
            out.partial = None
        self._update_write_interest(session)
        return True

    def _cancel_inflight_step(self, session: ClientSession) -> None:
        session.inflight_steps.clear()
        session.step_retries = 0

    def _service_cache_step(self, session: ClientSession, now: float) -> None:
        # Pipelined acknowledged steps: window_origin is the origin the
        # client has committed and it advances only in
        # _handle_cache_step_ack. Queued steps chain off the last queued
        # origin, so up to CACHE_STEP_PIPELINE consecutive one-tile moves
        # are in flight at once.
        token = session.token
        if token is None:
            return
        game = self.game
        if session.inflight_steps and now - session.step_sent_at >= CACHE_STEP_RETRANSMIT:
            if session.step_retries >= CACHE_STEP_RETRY_LIMIT:
                self._cancel_inflight_step(session)
                self._start_window_resync(session, "cache step retry ceiling")
                return
            # Go-back-N: resend every unacked step, oldest first,
            # byte-identically.
            for _, _, packet in session.inflight_steps:
                session.out.queue_reliable(packet)
            session.step_sent_at = now
            session.step_retries += 1
            self._log_debug(
                f"re-tx CACHE_STEP token={token} depth={len(session.inflight_steps)} "
                f"oldest_rev={session.inflight_steps[0][0]} retry={session.step_retries}"
            )
            self._update_write_interest(session)
            return
        queued = False
        while len(session.inflight_steps) < CACHE_STEP_PIPELINE:
            base = session.inflight_steps[-1][1] if session.inflight_steps else session.window_origin
            if game.window_origin_matches_player(base[0], base[1], token):
                break
            next_origin = game.next_window_origin_toward_player(base[0], base[1], token)
            if next_origin == base:
                break
            edge = game.edge_window(base[0], base[1], next_origin[0], next_origin[1], token)
            session.next_cache_revision = (session.next_cache_revision + 1) & 0xFFFF or 1
            packet = encode_terrain_edge(
                TerrainEdgePacket(
                    seq=session.next_seq(),
                    origin_x=edge.origin_x,
                    origin_y=edge.origin_y,
                    width=edge.width,
                    height=edge.height,
                    tiles=edge.tiles,
                    revision=session.next_cache_revision,
                )
            )
            if not session.inflight_steps:
                session.step_sent_at = now
                session.step_retries = 0
            session.inflight_steps.append((session.next_cache_revision, next_origin, packet))
            session.out.queue_reliable(packet)
            queued = True
            self._log_debug(
                f"tx CACHE_STEP token={token} rev={session.next_cache_revision} "
                f"origin={edge.origin_x},{edge.origin_y} size={edge.width}x{edge.height} "
                f"target={next_origin[0]},{next_origin[1]} depth={len(session.inflight_steps)}"
            )
        if queued:
            self._update_write_interest(session)

    def _handle_cache_step_ack(self, session: ClientSession, ack) -> None:
        # Cumulative: an ACK for any queued step confirms it and every
        # earlier one (the client applies steps strictly in order).
        for index, (revision, origin, _) in enumerate(session.inflight_steps):
            if revision != ack.revision:
                continue
            if (ack.origin_x, ack.origin_y) != origin:
                return
            session.window_origin = origin
            session.last_acked_revision = revision
            for _ in range(index + 1):
                session.inflight_steps.popleft()
            now = time.monotonic()
            session.step_sent_at = now
            session.step_retries = 0
            # ACK-triggered continuation keeps throughput RTT-bound rather
            # than tick-bound.
            self._service_cache_step(session, now)
            return
        # Duplicate ACK: the client re-ACKed its applied state because a
        # non-adjacent follower arrived -- the oldest inflight step was
        # lost. Fast-retransmit the pipeline immediately instead of waiting
        # out the timer (loss recovery in one RTT). Rate-limited so a burst
        # of duplicate ACKs triggers only one resend round, and it does not
        # burn the retry ceiling (loss is not a dead link).
        if not session.inflight_steps:
            return
        if ack.revision != session.last_acked_revision:
            return
        if (ack.origin_x, ack.origin_y) != session.window_origin:
            return
        now = time.monotonic()
        if now - session.step_sent_at < 0.1:
            return
        for _, _, packet in session.inflight_steps:
            session.out.queue_reliable(packet)
        session.step_sent_at = now
        self._update_write_interest(session)
        self._log_debug(
            f"fast re-tx CACHE_STEP token={session.token} "
            f"depth={len(session.inflight_steps)} dup_ack={ack.revision}"
        )

    def _send_window_commit_ack(self, session: ClientSession, fill_id: int, origin) -> None:
        session.out.queue_reliable(
            encode_window_commit_ack(
                WindowCommitAckPacket(
                    seq=session.next_seq(), fill_id=fill_id, origin_x=origin[0], origin_y=origin[1]
                )
            )
        )
        self._update_write_interest(session)

    def _handle_window_commit(self, session: ClientSession, commit) -> None:
        if session.token is None:
            return
        if session.fill_origin is None:
            # Duplicate of an already-accepted commit (our ack was lost):
            # re-acknowledge so the client stops retrying.
            if commit.fill_id == session.fill_id and (commit.origin_x, commit.origin_y) == session.window_origin:
                self._send_window_commit_ack(session, commit.fill_id, session.window_origin)
            return
        player = self.game.players.get(session.token)
        if player is None or commit.fill_id != session.fill_id:
            return
        if commit.map_id != player.map_id or (commit.origin_x, commit.origin_y) != session.fill_origin:
            return
        session.window_origin = session.fill_origin
        session.fill_origin = None
        session.fill_waiting_for_commit = False
        session.resync_rows = None
        self._log_debug(
            f"window commit token={session.token} fill={commit.fill_id} "
            f"origin={session.window_origin[0]},{session.window_origin[1]}"
        )
        self._send_window_commit_ack(session, commit.fill_id, session.window_origin)

    def _start_window_resync(
        self, session: ClientSession, reason: str, rows: list[int] | None = None
    ) -> None:
        token = session.token
        if token is None:
            return
        self._cancel_inflight_step(session)
        session.fill_id = (session.fill_id + 1) & 0xFF or 1
        session.fill_origin = self.game.window_origin(token)
        session.fill_waiting_for_commit = False
        session.resync_rows = list(rows) if rows is not None else list(range(WINDOW_H))
        self._log_debug(
            f"window resync token={token} origin={session.fill_origin[0]},{session.fill_origin[1]} "
            f"rows={len(session.resync_rows)} ({reason})"
        )

    # ------------------------------------------------------------------
    # Tick / transmit path

    def _tick(self, now: float) -> None:
        game = self.game
        game.begin_tick()
        active = [
            session
            for session in list(self.sessions.values())
            if session.kind == KIND_REALTIME and session.token is not None
        ]
        for session in active:
            if session.latest is not None:
                session.accepted = game.apply_player_state(session.latest, session.token)
        self.pvp_bots.step(game.tick, self.realtime_by_token.keys())
        game.finish_tick()
        if self.debug and game.zone_events:
            for action, zone_id in game.zone_events:
                self._log_debug(
                    f"zone {action} map={zone_id.map_id} zx={zone_id.zx} zy={zone_id.zy} "
                    f"active={len(game.active_zones)}"
                )
            game.zone_events.clear()
        for session in active:
            if session.conn not in self.sessions:
                continue
            if session.latest is None:
                continue
            try:
                self._send_tick_packets(session, now)
            except Exception:
                # Contained per session: the tick continues for everyone else.
                self._log_error(
                    f"tick send failed token={session.token}:\n{traceback.format_exc()}"
                )
                self._drop_session(session, "internal error")

    def _send_tick_packets(self, session: ClientSession, now: float) -> None:
        game = self.game
        token = session.token
        assert token is not None
        player = game.players.get(token)
        if player is None:
            return
        try:
            transition = game.consume_pending_map_change(token)
            if transition is not None:
                packet = MapChangePacket(
                    seq=session.next_seq(),
                    map_id=transition.to_map,
                    spawn_x=transition.to_x,
                    spawn_y=transition.to_y,
                    tileset_id=transition.tileset_id,
                    palette_id=transition.palette_id,
                    flags=1,
                )
                session.out.clear_latest()
                session.out.queue_reliable(encode_map_change(packet))
                self._log_debug(
                    f"tx MAP_CHANGE token={token} map={packet.map_id} "
                    f"spawn={packet.spawn_x},{packet.spawn_y} "
                    f"tileset={packet.tileset_id} palette={packet.palette_id}"
                )
                # The transition stays in-band: keep the session and stream
                # the new map's window as rows on the same connection. The
                # client applies tileset/palette locally and never leaves
                # streaming mode.
                session.remote_sent = ()
                session.items_sent = ()
                session.last_map_change = packet
                session.map_change_sent_at = now
                self._start_window_resync(session, f"map change to {transition.to_map}")
            elif (
                player.transition_loading
                and session.last_map_change is not None
                and now - session.map_change_sent_at >= MAP_CHANGE_RESEND_INTERVAL
            ):
                # The client has not reported MAP_READY: assume the
                # MAP_CHANGE (or its fill) was lost and re-send it with a
                # fresh fill. The player stays paused and protected until
                # the client is ready.
                packet = MapChangePacket(
                    seq=session.next_seq(),
                    map_id=session.last_map_change.map_id,
                    spawn_x=session.last_map_change.spawn_x,
                    spawn_y=session.last_map_change.spawn_y,
                    tileset_id=session.last_map_change.tileset_id,
                    palette_id=session.last_map_change.palette_id,
                    flags=1,
                )
                session.out.clear_latest()
                session.out.queue_reliable(encode_map_change(packet))
                session.map_change_sent_at = now
                self._log_debug(
                    f"re-tx MAP_CHANGE token={token} map={packet.map_id} (client not ready)"
                )
                if session.resync_rows is None and session.fill_origin is None:
                    # The transition's fill is gone (or never started):
                    # restart it. An in-flight or waiting fill keeps its
                    # progress -- restarting here every resend interval
                    # discarded the client's staged rows and could livelock
                    # a slow or lossy link (the PvP-arena stall). The
                    # client's NACK and commit-retry machinery finishes the
                    # existing fill; a lost MAP_CHANGE alone is healed by
                    # this packet re-send.
                    self._start_window_resync(session, "map change re-send")

            # Full-window resync: this session attached without a fresh
            # bootstrap (transparently replaced socket, client cache
            # unknown) or the window target jumped too far for edge
            # streaming (respawn/teleport). Stream 24 self-describing
            # absolute rows in-band; the connection stays up and gameplay
            # traffic continues below.
            if session.fill_waiting_for_commit and now - session.fill_waiting_since >= WINDOW_COMMIT_TIMEOUT:
                # The client's WINDOW_COMMIT was lost, or it never finished
                # the fill and its retry state was lost too. Start a fresh
                # transaction rather than waiting forever with edges blocked.
                self._start_window_resync(session, "window commit timeout")
            if session.resync_rows is None and not session.fill_waiting_for_commit:
                target_origin = game.window_origin(token)
                origin_gap = abs(target_origin[0] - session.window_origin[0]) + abs(
                    target_origin[1] - session.window_origin[1]
                )
                # Per-player story terrain change (e.g. bridge repair) forces a
                # resync so the client stops seeing the pre-change terrain.
                terrain_dirty = game.consume_pending_terrain_resync(token)
                if session.needs_full_resync or terrain_dirty or origin_gap > WINDOW_RESYNC_DISTANCE:
                    if session.needs_full_resync:
                        reason = "no bootstrap"
                    elif terrain_dirty:
                        reason = "story terrain changed"
                    else:
                        reason = f"origin gap {origin_gap}"
                    session.needs_full_resync = False
                    self._start_window_resync(session, reason)

            resync_active_this_tick = session.resync_rows is not None
            if session.resync_rows is not None:
                # Window rows replace optional realtime traffic until done.
                # The per-tick row budget (--resync-row-budget) trades fill
                # latency against line-rate headroom; WORLD_STATE keeps
                # flowing for client echo/correction.
                origin_x, origin_y = session.fill_origin or session.window_origin
                budget = session.resync_row_budget
                while budget > 0 and session.resync_rows:
                    row = session.resync_rows.pop(0)
                    session.out.queue_reliable(
                        encode_window_row(
                            WindowRowPacket(
                                seq=session.next_seq(),
                                origin_x=origin_x,
                                origin_y=origin_y + row,
                                row_index=row,
                                tiles=game.window_row_tiles(origin_x, origin_y + row, session.token),
                                fill_id=session.fill_id,
                            )
                        )
                    )
                    budget -= 1
                    self._log_debug(
                        f"tx WINDOW_ROW token={token} row={row} "
                        f"origin={origin_x},{origin_y} remaining={len(session.resync_rows)}"
                    )
                if not session.resync_rows:
                    session.resync_rows = None
                    session.fill_waiting_for_commit = True
                    session.fill_waiting_since = now
            elif not session.fill_waiting_for_commit:
                self._service_cache_step(session, now)

            snapshot = game.snapshot_for_window(*session.window_origin, token)
            world_packet = WorldStatePacket(
                seq=session.next_seq(),
                player_x=snapshot.player_x,
                player_y=snapshot.player_y,
                health=snapshot.health,
                correction_flags=0 if session.accepted else 1,
                beavers=snapshot.beavers,
                tile_x=snapshot.tile_x,
                tile_y=snapshot.tile_y,
                tile_id=snapshot.tile_id,
                echo_client_seq=session.latest_seq or 0,
            )
            session.out.queue_latest("world", encode_world_state(world_packet))
            self._log_debug(
                f"tx WORLD_STATE token={token} seq={world_packet.seq} "
                f"echo={world_packet.echo_client_seq} corr={world_packet.correction_flags} "
                f"player={world_packet.player_x},{world_packet.player_y} "
                f"beavers={len(world_packet.beavers)} "
                f"window={session.window_origin[0]},{session.window_origin[1]}"
            )
            if resync_active_this_tick:
                # Optional traffic is suppressed during a fill, but the
                # frames queued this tick (rows + world state) still go out.
                if not self._flush_session_output(session, now):
                    self._drop_session(session, "send failed")
                return

            # Remote players: change-driven, with a periodic refresh while
            # any are visible (bandwidth rule: never unconditional per tick).
            records = game.remote_players_near(token, *session.window_origin, limit=self.visible_remotes)
            if records != session.remote_sent or (
                records and now - session.remote_sent_at >= REMOTE_REFRESH_INTERVAL
            ):
                session.out.queue_latest(
                    "remote", encode_remote_players(RemotePlayersPacket(seq=session.next_seq(), players=records))
                )
                session.remote_sent = records
                session.remote_sent_at = now
                self._log_debug(
                    f"tx REMOTE_PLAYERS token={token} count={len(records)} "
                    f"cap={self.visible_remotes} packet={REALTIME_PACKET_BYTES}"
                )

            # Item drops: same change-driven rule as remote players.
            item_records = game.item_drops_near(token, *session.window_origin)
            if item_records != session.items_sent or (
                item_records and now - session.items_sent_at >= REMOTE_REFRESH_INTERVAL
            ):
                session.out.queue_latest(
                    "items", encode_item_drops(ItemDropsPacket(seq=session.next_seq(), items=item_records))
                )
                session.items_sent = item_records
                session.items_sent_at = now
                self._log_debug(f"tx ITEM_DROPS token={token} count={len(item_records)}")

            hud_state = game.hud_state_tuple(token)
            if hud_state != session.hud_sent:
                session.out.queue_latest("hud", encode_hud_update(game.hud_update_packet(session.next_seq(), token)))
                session.hud_sent = hud_state
            quest_state = game.quest_state_tuple(token)
            if quest_state != session.quest_sent:
                session.out.queue_latest("quest", encode_quest_update(game.quest_update_packet(session.next_seq(), token)))
                session.quest_sent = quest_state
            inventory_state = game.inventory_state_tuple(token)
            if inventory_state != session.inventory_sent:
                session.out.queue_latest("inventory", encode_inventory_update(game.inventory_update_packet(session.next_seq(), token)))
                session.inventory_sent = inventory_state
            map_summary_state = game.map_summary_state_tuple(token)
            if map_summary_state != session.map_summary_sent:
                session.out.queue_latest("map_summary", encode_map_summary(game.map_summary_packet(session.next_seq(), token)))
                session.map_summary_sent = map_summary_state
            if player.pending_messages:
                message = game.next_message_packet(session.next_seq(), token)
                assert message is not None
                session.out.queue_message(encode_message(message))
                session.message_counter_sent = player.message_counter
            # Paged story dialogue: the game layer decides when to (re)send the
            # current page, so this just forwards whatever it hands back.
            dialogue_packet = game.dialogue_page_to_send(session.next_seq(), token)
            if dialogue_packet is not None:
                session.out.queue_latest("dialogue", encode_dialogue_page(dialogue_packet))
            if player.latest_respawn_event is not None and player.respawn_counter != session.respawn_counter_sent:
                session.out.queue_reliable(
                    encode_respawn_event(game.respawn_event_packet(session.next_seq(), token))
                )
                session.respawn_counter_sent = player.respawn_counter
            if not self._flush_session_output(session, now):
                self._drop_session(session, "send failed")
        except OSError:
            self._drop_session(session, "send failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--tick-hz", type=int, default=10)
    # Phase 54: pacing comes from each session's declared link profile
    # (HELLO flags byte). These flags are operator overrides: when passed
    # they beat the profile table for every session.
    parser.add_argument("--edge-budget", type=int, default=None)
    parser.add_argument("--resync-row-budget", type=int, default=None)
    parser.add_argument("--client-byte-rate", type=float, default=None)
    parser.add_argument("--client-burst-bytes", type=int, default=None)
    parser.add_argument("--visible-remotes", type=int, default=REALTIME_DEFAULT_REMOTE_PLAYERS)
    parser.add_argument("--player-idle-timeout", type=float, default=PLAYER_IDLE_TIMEOUT)
    parser.add_argument("--test-pvp-bots", type=int, default=0)
    parser.add_argument("--test-pvp-bot-mode", choices=("arena", "orbit", "path"), default="arena")
    parser.add_argument("--test-pvp-bot-move-every", type=int, default=4)
    parser.add_argument("--test-pvp-bot-orbit-every", type=int, default=8)
    parser.add_argument("--test-pvp-bot-fire-cooldown", type=float, default=2.0)
    parser.add_argument("--test-pvp-bots-no-fire", action="store_true")
    parser.add_argument("--test-pvp-bot-token-base", type=lambda value: int(value, 0), default=DEFAULT_PVP_BOT_TOKEN_BASE)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--debug-errors-only", action="store_true")
    parser.add_argument("--lobby-enabled", action="store_true")
    parser.add_argument("--lobby-base-url", default=DEFAULT_LOBBY_BASE_URL)
    parser.add_argument("--lobby-creator-id", type=lambda value: int(value, 0), default=DEFAULT_LOBBY_CREATOR_ID)
    parser.add_argument("--lobby-app-id", type=lambda value: int(value, 0), default=DEFAULT_LOBBY_APP_ID)
    parser.add_argument("--lobby-game-name", default=DEFAULT_LOBBY_GAME_NAME)
    parser.add_argument("--lobby-server-name", default=DEFAULT_LOBBY_SERVER_NAME)
    parser.add_argument("--lobby-region", default=DEFAULT_LOBBY_REGION)
    parser.add_argument("--lobby-server-url", default=DEFAULT_LOBBY_SERVER_URL)
    parser.add_argument("--lobby-max-players", type=int, default=DEFAULT_LOBBY_MAX_PLAYERS)
    parser.add_argument("--lobby-client-platform", default=DEFAULT_LOBBY_CLIENT_PLATFORM)
    parser.add_argument("--lobby-client-url", default=DEFAULT_LOBBY_CLIENT_URL)
    parser.add_argument("--lobby-timeout", type=float, default=2.0)
    parser.add_argument("--lobby-delete-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.visible_remotes <= REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED:
        parser.error(f"--visible-remotes must be 1..{REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED}")
    if not 0 <= args.test_pvp_bots <= PVP_BOT_MAX_COUNT:
        parser.error(f"--test-pvp-bots must be 0..{PVP_BOT_MAX_COUNT}")
    server = FujiRealmHybridServer(
        args.host,
        args.port,
        args.tick_hz,
        args.debug,
        args.debug_errors_only,
        args.edge_budget,
        resync_row_budget=args.resync_row_budget,
        client_byte_rate=args.client_byte_rate,
        client_burst_bytes=args.client_burst_bytes,
        visible_remotes=args.visible_remotes,
        player_idle_timeout=args.player_idle_timeout,
        test_pvp_bots=args.test_pvp_bots,
        test_pvp_bot_move_every=args.test_pvp_bot_move_every,
        test_pvp_bot_mode=args.test_pvp_bot_mode,
        test_pvp_bot_orbit_every=args.test_pvp_bot_orbit_every,
        test_pvp_bot_fire_cooldown=args.test_pvp_bot_fire_cooldown,
        test_pvp_bots_no_fire=args.test_pvp_bots_no_fire,
        test_pvp_bot_token_base=args.test_pvp_bot_token_base,
        lobby_enabled=args.lobby_enabled,
        lobby_base_url=args.lobby_base_url,
        lobby_creator_id=args.lobby_creator_id,
        lobby_app_id=args.lobby_app_id,
        lobby_game_name=args.lobby_game_name,
        lobby_server_name=args.lobby_server_name,
        lobby_region=args.lobby_region,
        lobby_server_url=args.lobby_server_url,
        lobby_max_players=args.lobby_max_players,
        lobby_client_platform=args.lobby_client_platform,
        lobby_client_url=args.lobby_client_url,
        lobby_timeout=args.lobby_timeout,
    )
    if args.lobby_delete_only:
        if server.lobby is None:
            parser.error("--lobby-delete-only requires --lobby-enabled")
        if not server.lobby.delete():
            return 1
        return 0
    server.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
