"""Fixed-size-friendly FujiRealm packet protocol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct


MAGIC = 0xBF
VERSION = 1
MAX_BEAVERS = 6
WINDOW_W = 32
WINDOW_H = 24
WINDOW_CHUNK_MAX_ROWS = 3
REALTIME_MAGIC = 0xAD
REALTIME_VERSION = 2
REALTIME_SMALL_PACKET_BYTES = 32
REALTIME_PACKET_BYTES = 64
REALTIME_CHECKSUM_OFFSET = REALTIME_PACKET_BYTES - 2
REALTIME_PATTERN = 0x5A
REALTIME_VERSION_V3 = 3
REALTIME_V3_HEAD_BYTES = 6
REALTIME_V3_MAX_PAYLOAD = 54
REALTIME_V3_MAX_RAW = REALTIME_V3_HEAD_BYTES + REALTIME_V3_MAX_PAYLOAD + 2
REALTIME_V3_WORKSPACE = 64
REALTIME_PREAMBLE = b"RT3\n"
REALTIME_MAX_BEAVERS = MAX_BEAVERS
MAP_OVERWORLD = 0
MAP_STARTER_CAVE = 1
MAP_PVP_REALM = 2
TILESET_OVERWORLD = 0
TILESET_CAVE = 1
TILESET_PVP_REALM = 0
PALETTE_OVERWORLD = 0
PALETTE_CAVE = 1
PALETTE_PVP_REALM = 2
ENTITY_PLAYER = 1
ENTITY_ENEMY = 2


class PacketError(ValueError):
    pass


class PacketType(IntEnum):
    HELLO = 1
    INPUT = 2
    ACK = 3
    WINDOW = 0x80
    WELCOME = 0x81
    SNAPSHOT = 0x82
    EVENT = 0x83
    PING = 0x90
    PONG = 0x91
    LOGIN_REQUEST = 0xA0
    LOGIN_RESPONSE = 0xA1
    RESUME_REQUEST = 0xA2
    RESUME_RESPONSE = 0xA3
    RENAME_REQUEST = 0xA4
    RENAME_RESPONSE = 0xA5


LOGIN_OK = 0
LOGIN_USERNAME_TAKEN = 1
RESUME_OK = 0
RENAME_OK = 0
RENAME_USERNAME_TAKEN = 1
RENAME_TOKEN_UNKNOWN = 2
USERNAME_MAX_LEN = 10
TOKEN_MAX_LEN = 10


class RealtimeType(IntEnum):
    PLAYER_STATE = 1
    WORLD_STATE = 2
    TERRAIN_EDGE = 3
    BYE = 4
    MAP_CHANGE = 5
    ENTITY_DELTA = 6
    HUD_UPDATE = 7
    MESSAGE = 8
    QUEST_UPDATE = 9
    INVENTORY_UPDATE = 10
    RESPAWN_EVENT = 11
    PLAYER_COMMAND = 12
    AUTH = 13
    REMOTE_PLAYERS = 14
    RESYNC_REQUEST = 15
    WINDOW_ROW = 16
    ITEM_DROPS = 17
    MAP_SUMMARY = 18
    MAP_READY = 19
    WINDOW_COMMIT = 20
    CACHE_STEP_ACK = 21
    WINDOW_COMMIT_ACK = 22
    NET_STATS = 23
    DIALOGUE_PAGE = 24


class PlayerCommandType(IntEnum):
    MOVE = 1
    ATTACK = 2
    INTERACT = 3
    PICKUP = 4
    WAIT = 5
    OPEN_MODAL = 6
    CLOSE_MODAL = 7
    # Paged story dialogue (Phase 57). Pages advance only on an explicit ack;
    # the choice command carries an accept/decline for quest-offer scenes.
    DIALOGUE_ADVANCE = 8
    DIALOGUE_CHOICE = 9


# Dialogue modal flags (bitmask carried in the DIALOGUE_PAGE payload).
DIALOGUE_FLAG_QUEST_OFFER = 0x01  # show Accept / Decline on the final page
DIALOGUE_FLAG_ACK_ONLY = 0x02     # show a single dismiss/OK prompt
DIALOGUE_FLAG_LAST_PAGE = 0x04    # this is the final page of the scene
DIALOGUE_FLAG_CHUNK_END = 0x08    # last chunk of this display page (render now)

# Accept/decline choice values for PlayerCommandType.DIALOGUE_CHOICE.
DIALOGUE_CHOICE_DECLINE = 0
DIALOGUE_CHOICE_ACCEPT = 1


REALTIME_SMALL_TYPES = frozenset(
    {
        RealtimeType.PLAYER_STATE,
        RealtimeType.BYE,
        RealtimeType.MAP_CHANGE,
        RealtimeType.HUD_UPDATE,
        RealtimeType.INVENTORY_UPDATE,
        RealtimeType.RESPAWN_EVENT,
        RealtimeType.PLAYER_COMMAND,
        RealtimeType.AUTH,
        RealtimeType.RESYNC_REQUEST,
        RealtimeType.ITEM_DROPS,
        RealtimeType.MAP_READY,
        RealtimeType.WINDOW_COMMIT,
        RealtimeType.CACHE_STEP_ACK,
    }
)


@dataclass(frozen=True)
class Packet:
    packet_type: PacketType
    payload: bytes = b""


@dataclass(frozen=True)
class Hello:
    flags: int
    seed: int
    token: int = 0


@dataclass(frozen=True)
class InputIntent:
    tick: int
    direction: int
    buttons: int
    aim: int
    ack_tick: int


@dataclass(frozen=True)
class Welcome:
    player_id: int
    seed: int
    max_beavers: int = MAX_BEAVERS
    protocol_version: int = VERSION


@dataclass(frozen=True)
class Window:
    tick: int
    origin_x: int
    origin_y: int
    width: int
    height: int
    tiles: bytes


@dataclass(frozen=True)
class WindowChunk:
    tick: int
    origin_x: int
    origin_y: int
    width: int
    height: int
    chunk_y: int
    chunk_h: int
    tiles: bytes


@dataclass(frozen=True)
class BeaverSnapshot:
    x: int
    y: int
    hp: int
    kind: int


@dataclass(frozen=True)
class Snapshot:
    tick: int
    player_x: int
    player_y: int
    health: int
    score: int
    beavers: tuple[BeaverSnapshot, ...]
    tile_x: int = 0
    tile_y: int = 0
    tile_id: int = 0


@dataclass(frozen=True)
class PlayerStatePacket:
    seq: int
    x: int
    y: int
    facing: int
    buttons: int
    fire_counter: int
    pickup_counter: int
    last_server_seq: int
    rx_drops: int = 0
    pvp_toggle_counter: int = 0


@dataclass(frozen=True)
class WorldStatePacket:
    seq: int
    player_x: int
    player_y: int
    health: int
    correction_flags: int
    beavers: tuple[BeaverSnapshot, ...]
    tile_x: int = 0
    tile_y: int = 0
    tile_id: int = 0
    echo_client_seq: int = 0


@dataclass(frozen=True)
class TerrainEdgePacket:
    seq: int
    origin_x: int
    origin_y: int
    width: int
    height: int
    tiles: bytes
    revision: int = 0


@dataclass(frozen=True)
class MapChangePacket:
    seq: int
    map_id: int
    spawn_x: int
    spawn_y: int
    tileset_id: int
    palette_id: int
    flags: int = 0


@dataclass(frozen=True)
class EntityDeltaRecord:
    entity_id: int
    entity_type: int
    x: int
    y: int
    tile_id: int
    hp: int
    flags: int
    state: int


@dataclass(frozen=True)
class EntityDeltaPacket:
    seq: int
    records: tuple[EntityDeltaRecord, ...]


@dataclass(frozen=True)
class HudUpdatePacket:
    seq: int
    hp: int
    max_hp: int
    level: int
    xp: int
    xp_next: int
    gold: int
    flags: int = 0
    pvp_kills: int = 0


@dataclass(frozen=True)
class MessagePacket:
    seq: int
    message_id: int
    text: str = ""


@dataclass(frozen=True)
class QuestUpdatePacket:
    seq: int
    quest_id: int
    state: int
    text: str = ""


@dataclass(frozen=True)
class DialoguePagePacket:
    seq: int
    dialogue_id: int
    speaker_id: int
    page_index: int
    page_count: int
    flags: int = 0
    text: str = ""
    chunk_index: int = 0


@dataclass(frozen=True)
class InventoryUpdatePacket:
    seq: int
    slots: tuple[tuple[int, int], ...]
    gold: int = 0
    flags: int = 0


@dataclass(frozen=True)
class RespawnEventPacket:
    seq: int
    x: int
    y: int
    hp: int
    flags: int = 0
    map_id: int = 0
    max_hp: int = 0
    message_id: int = 0


@dataclass(frozen=True)
class PlayerCommandPacket:
    seq: int
    command: int
    direction: int
    arg0: int = 0
    arg1: int = 0
    last_server_seq: int = 0


@dataclass(frozen=True)
class AuthPacket:
    seq: int
    token: int


@dataclass(frozen=True)
class RemotePlayerRecord:
    x: int
    y: int
    facing: int
    state: int


@dataclass(frozen=True)
class RemotePlayersPacket:
    seq: int
    players: tuple[RemotePlayerRecord, ...]


@dataclass(frozen=True)
class ItemDropRecord:
    x: int
    y: int
    item_id: int
    quantity: int


@dataclass(frozen=True)
class ItemDropsPacket:
    seq: int
    items: tuple[ItemDropRecord, ...]


@dataclass(frozen=True)
class MapSummaryPacket:
    seq: int
    map_id: int
    origin_zx: int
    origin_zy: int
    width: int
    height: int
    cells: bytes


@dataclass(frozen=True)
class ResyncRequestPacket:
    """Client asks for terrain resync, reporting its current window origin.

    A small origin gap is repaired by rewinding the server's edge stream;
    only large/unknown gaps need a full window fill. `rows_have` is a 24-bit
    bitmap (bit N set = WINDOW_ROW N already received) for the client's
    in-progress fill at `fill_origin_x/y`; when it is non-zero and the fill
    origin matches the server's target, the server resends only the missing
    rows instead of restarting a full 24-row fill. Old clients leave these
    bytes zero, which requests the full fill.
    """

    seq: int
    origin_x: int = 0
    origin_y: int = 0
    fill_origin_x: int = 0
    fill_origin_y: int = 0
    rows_have: int = 0
    fill_id: int = 0
    flags: int = 0


@dataclass(frozen=True)
class MapReadyPacket:
    seq: int
    map_id: int
    origin_x: int = 0
    origin_y: int = 0


@dataclass(frozen=True)
class WindowRowPacket:
    """One absolute terrain row of an in-band window resync.

    Self-describing: the window origin is (origin_x, origin_y - row_index),
    so any single row can be applied (or lost) independently.
    """

    seq: int
    origin_x: int
    origin_y: int
    row_index: int
    tiles: bytes
    fill_id: int = 0


@dataclass(frozen=True)
class WindowCommitPacket:
    seq: int
    fill_id: int
    origin_x: int
    origin_y: int
    map_id: int
    flags: int = 1


@dataclass(frozen=True)
class LoginRequest:
    username: str


@dataclass(frozen=True)
class LoginResponse:
    status: int
    token: str


@dataclass(frozen=True)
class ResumeRequest:
    token: str


@dataclass(frozen=True)
class ResumeResponse:
    status: int
    username: str


@dataclass(frozen=True)
class RenameRequest:
    token: str
    username: str


@dataclass(frozen=True)
class RenameResponse:
    status: int


HELLO_STRUCT = struct.Struct("<BHI")
INPUT_STRUCT = struct.Struct("<HBBBH")
WELCOME_STRUCT = struct.Struct("<BHBB")
WINDOW_HEAD_STRUCT = struct.Struct("<HHHBBBBH")
SNAPSHOT_HEAD_STRUCT = struct.Struct("<HBBBH")
BEAVER_STRUCT = struct.Struct("<BBBB")
REALTIME_HEAD_STRUCT = struct.Struct("<BBBBH")
REALTIME_PLAYER_STRUCT = struct.Struct("<BBBBBBHBB")
REALTIME_WORLD_HEAD_STRUCT = struct.Struct("<BBBBHB")
REALTIME_MAP_CHANGE_STRUCT = struct.Struct("<BBBBBB")
REALTIME_ENTITY_DELTA_RECORD_STRUCT = struct.Struct("<BBBBBBBB")
REALTIME_HUD_UPDATE_STRUCT = struct.Struct("<BBBHHHBH")
REALTIME_TEXT_MAX_LEN = 39
REALTIME_INVENTORY_HEAD_STRUCT = struct.Struct("<BH")
REALTIME_INVENTORY_SLOT_STRUCT = struct.Struct("<BB")
REALTIME_MAX_INVENTORY_SLOTS = 8
REALTIME_RESPAWN_EVENT_STRUCT = struct.Struct("<BBBBBBB")
REALTIME_PLAYER_COMMAND_STRUCT = struct.Struct("<BBBBH")
REALTIME_AUTH_STRUCT = struct.Struct("<I")
REALTIME_REMOTE_PLAYER_STRUCT = struct.Struct("<BBBB")
REALTIME_REMOTE_PLAYER_RECORD_BYTES = REALTIME_REMOTE_PLAYER_STRUCT.size
REALTIME_REMOTE_PLAYERS_LARGE_CAPACITY = (
    REALTIME_CHECKSUM_OFFSET - REALTIME_HEAD_STRUCT.size
) // REALTIME_REMOTE_PLAYER_RECORD_BYTES
REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED = min(12, REALTIME_REMOTE_PLAYERS_LARGE_CAPACITY)
REALTIME_DEFAULT_REMOTE_PLAYERS = 3
REALTIME_MAX_REMOTE_PLAYERS = REALTIME_DEFAULT_REMOTE_PLAYERS
REALTIME_ITEM_DROP_STRUCT = struct.Struct("<BBBB")
REALTIME_MAX_ITEM_DROPS = 4
REALTIME_WINDOW_ROW_HEAD_STRUCT = struct.Struct("<BBBB")
REALTIME_WINDOW_ROW_TILE_OFFSET = REALTIME_HEAD_STRUCT.size + REALTIME_WINDOW_ROW_HEAD_STRUCT.size
REALTIME_MAP_SUMMARY_HEAD_STRUCT = struct.Struct("<BBBBBB")
REALTIME_MAP_SUMMARY_CELL_OFFSET = REALTIME_HEAD_STRUCT.size + REALTIME_MAP_SUMMARY_HEAD_STRUCT.size
REALTIME_MAP_SUMMARY_MAX_CELLS = REALTIME_CHECKSUM_OFFSET - REALTIME_MAP_SUMMARY_CELL_OFFSET
REALTIME_MAX_ENTITY_DELTAS = REALTIME_V3_MAX_PAYLOAD // REALTIME_ENTITY_DELTA_RECORD_STRUCT.size
# Paged story dialogue (Phase 57): dlg_id, speaker_id, page_index, page_count,
# flags, chunk_index, text_len -- then this chunk's text fills the rest of the
# v3 frame. A display page can span several chunk packets that the client
# reassembles, so pages are not limited to a single 48-char packet.
REALTIME_DIALOGUE_HEAD_STRUCT = struct.Struct("<BBBBBBB")
REALTIME_DIALOGUE_TEXT_OFFSET = REALTIME_HEAD_STRUCT.size + REALTIME_DIALOGUE_HEAD_STRUCT.size
REALTIME_DIALOGUE_MAX_TEXT = REALTIME_V3_MAX_PAYLOAD - REALTIME_DIALOGUE_HEAD_STRUCT.size


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


# ---------------------------------------------------------------------------
# Realtime protocol v3: COBS-framed, CRC-16 protected wire format.
#
# Raw frame layout (offsets preserved from v2 so per-type field offsets and
# the Atari client's apply handlers are unchanged; the magic byte became the
# payload length):
#
#   0     payload_length N (0..54)
#   1     version = 3
#   2     message_type
#   3     status (per-type status byte)
#   4-5   sequence, little endian
#   6..   payload (N bytes)
#   6+N   CRC-16/CCITT-FALSE over bytes 0..5+N, little endian
#
# Wire frame = COBS(raw) + 0x00. COBS guarantees no zero inside the encoded
# frame, so the next delimiter always restores parser alignment. Trailing
# zero bytes of the payload are stripped on encode and re-padded on decode
# (lossless), so frames are sent compact without per-encoder changes.



def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode_cobs(data: bytes) -> bytes:
    out = bytearray()
    block = bytearray()
    for byte in data:
        if byte == 0:
            out.append(len(block) + 1)
            out += block
            block.clear()
        else:
            block.append(byte)
            if len(block) == 254:
                out.append(255)
                out += block
                block.clear()
    out.append(len(block) + 1)
    out += block
    return bytes(out)


def decode_cobs(data: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        if code == 0:
            raise PacketError("zero inside cobs frame")
        index += 1
        end = index + code - 1
        if end > len(data):
            raise PacketError("cobs block overruns frame")
        out += data[index:end]
        index = end
        if code != 255 and index < len(data):
            out.append(0)
    return bytes(out)


def encode_realtime_frame(raw: bytes) -> bytes:
    return encode_cobs(raw) + b"\x00"


def _try_raw_realtime(data: bytes) -> bytes | None:
    if len(data) < REALTIME_V3_HEAD_BYTES + 2:
        return None
    n = data[0]
    if n > REALTIME_V3_MAX_PAYLOAD or data[1] != REALTIME_VERSION_V3:
        return None
    end = REALTIME_V3_HEAD_BYTES + n
    if len(data) < end + 2:
        return None
    if crc16_ccitt(bytes(data[:end])) != (data[end] | (data[end + 1] << 8)):
        return None
    return bytes(data[: end + 2])


def _normalize_realtime(data: bytes) -> bytes:
    # Accept either a raw frame (CRC verified) or a wire frame (COBS +
    # delimiter); return the exact raw frame including its CRC.
    raw = _try_raw_realtime(data)
    if raw is not None:
        return raw
    stripped = bytes(data).rstrip(b"\x00")
    try:
        decoded = decode_cobs(stripped)
    except PacketError as exc:
        raise PacketError("bad realtime frame") from exc
    raw = _try_raw_realtime(decoded)
    if raw is None:
        raise PacketError("bad realtime frame")
    return raw


class RealtimeFrameDecoder:
    """Delimiter-scanning stream decoder for realtime v3 wire frames.

    feed() returns complete, CRC-verified raw frames. A frame damaged in any
    way costs exactly the bytes up to the next zero delimiter; the parser
    realigns there unconditionally.
    """

    MAX_ENCODED = REALTIME_V3_MAX_RAW + 2

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.discarding = False
        self.frames = 0
        self.bad_frames = 0
        self.overflows = 0

    def feed(self, data: bytes) -> list[bytes]:
        frames: list[bytes] = []
        for byte in data:
            if byte == 0:
                if self.discarding:
                    self.discarding = False
                    self.buffer.clear()
                    continue
                if not self.buffer:
                    continue
                encoded = bytes(self.buffer)
                self.buffer.clear()
                try:
                    frames.append(_normalize_realtime(encoded))
                    self.frames += 1
                except PacketError:
                    self.bad_frames += 1
                continue
            if self.discarding:
                continue
            if len(self.buffer) >= self.MAX_ENCODED:
                self.overflows += 1
                self.discarding = True
                self.buffer.clear()
                continue
            self.buffer.append(byte)
        return frames


def seq_delta(newer: int, older: int) -> int:
    return ((newer - older + 0x8000) & 0xFFFF) - 0x8000


def realtime_packet_size(packet_type: RealtimeType | int) -> int:
    packet_type = RealtimeType(packet_type)
    return REALTIME_SMALL_PACKET_BYTES if packet_type in REALTIME_SMALL_TYPES else REALTIME_PACKET_BYTES


def _realtime_base(packet_type: RealtimeType, seq: int, status: int = 0) -> bytearray:
    # 64-byte workspace with the v3 header; encoders keep writing payload
    # fields at their v2 offsets (payload starts at byte 6).
    payload = bytearray(REALTIME_V3_WORKSPACE)
    payload[1] = REALTIME_VERSION_V3
    payload[2] = int(packet_type)
    payload[3] = status & 0xFF
    payload[4] = seq & 0xFF
    payload[5] = (seq >> 8) & 0xFF
    return payload


def _finalize_realtime(data: bytearray) -> bytes:
    # Strip trailing payload zeros (decoders re-pad, so this is lossless),
    # stamp the length, append CRC-16, COBS-encode, delimit.
    payload = bytes(data[REALTIME_V3_HEAD_BYTES:]).rstrip(b"\x00")
    if len(payload) > REALTIME_V3_MAX_PAYLOAD:
        raise PacketError("payload too large for realtime v3 frame")
    raw = bytearray(data[:REALTIME_V3_HEAD_BYTES])
    raw[0] = len(payload)
    raw += payload
    crc = crc16_ccitt(bytes(raw))
    raw.append(crc & 0xFF)
    raw.append((crc >> 8) & 0xFF)
    return encode_realtime_frame(bytes(raw))


def _encode_realtime_text(text: str, max_len: int = REALTIME_TEXT_MAX_LEN) -> bytes:
    # The Atari client's internal screen codes only cover ATASCII 32-95
    # (space, digits, punctuation, uppercase); anything outside that range
    # is replaced so the client never has to special-case a stray byte.
    sanitized = bytes(
        ord(ch) if 32 <= ord(ch) <= 95 else ord("?") for ch in text.upper()[:max_len]
    )
    return sanitized


def _decode_realtime_text(data: bytes, offset: int) -> str:
    length = data[offset]
    return bytes(data[offset + 1 : offset + 1 + length]).decode("ascii", "replace")


def _validate_realtime(data: bytes, expected_type: RealtimeType | None = None) -> tuple[bytes, int, int]:
    # Accepts a raw v3 frame or a complete wire frame. Returns the payload
    # workspace re-padded to 64 bytes (trailing zeros stripped on encode are
    # restored) so fixed-offset decoders read zeros beyond the sent length.
    raw = _normalize_realtime(data)
    status = raw[3]
    seq = raw[4] | (raw[5] << 8)
    try:
        packet_type = RealtimeType(raw[2])
    except ValueError as exc:
        raise PacketError("unknown realtime type") from exc
    if expected_type is not None and packet_type != expected_type:
        raise PacketError("wrong realtime type")
    padded = bytes(raw[:-2]).ljust(REALTIME_V3_WORKSPACE, b"\x00")
    return padded, status, seq


def encode_player_state(msg: PlayerStatePacket) -> bytes:
    data = _realtime_base(RealtimeType.PLAYER_STATE, msg.seq)
    REALTIME_PLAYER_STRUCT.pack_into(
        data,
        REALTIME_HEAD_STRUCT.size,
        msg.x & 0xFF,
        msg.y & 0xFF,
        msg.facing & 0xFF,
        msg.buttons & 0xFF,
        msg.fire_counter & 0xFF,
        msg.pickup_counter & 0xFF,
        msg.last_server_seq & 0xFFFF,
        msg.rx_drops & 0xFF,
        msg.pvp_toggle_counter & 0xFF,
    )
    return _finalize_realtime(data)


def decode_player_state(data: bytes) -> PlayerStatePacket:
    data, _, seq = _validate_realtime(data, RealtimeType.PLAYER_STATE)
    x, y, facing, buttons, fire_counter, pickup_counter, last_server_seq, rx_drops, pvp_toggle_counter = (
        REALTIME_PLAYER_STRUCT.unpack_from(data, REALTIME_HEAD_STRUCT.size)
    )
    return PlayerStatePacket(
        seq, x, y, facing, buttons, fire_counter, pickup_counter, last_server_seq, rx_drops, pvp_toggle_counter
    )


def encode_world_state(msg: WorldStatePacket) -> bytes:
    beavers = list(msg.beavers[:REALTIME_MAX_BEAVERS])
    while len(beavers) < REALTIME_MAX_BEAVERS:
        beavers.append(BeaverSnapshot(0, 0, 0, 0))
    data = _realtime_base(RealtimeType.WORLD_STATE, msg.seq, min(len(msg.beavers), REALTIME_MAX_BEAVERS))
    offset = REALTIME_HEAD_STRUCT.size
    REALTIME_WORLD_HEAD_STRUCT.pack_into(
        data,
        offset,
        msg.player_x & 0xFF,
        msg.player_y & 0xFF,
        msg.health & 0xFF,
        msg.correction_flags & 0xFF,
        msg.echo_client_seq & 0xFFFF,
        msg.tile_id & 0xFF,
    )
    offset += REALTIME_WORLD_HEAD_STRUCT.size
    data[offset] = msg.tile_x & 0xFF
    data[offset + 1] = msg.tile_y & 0xFF
    offset += 2
    for beaver in beavers:
        BEAVER_STRUCT.pack_into(data, offset, beaver.x & 0xFF, beaver.y & 0xFF, beaver.hp & 0xFF, beaver.kind & 0xFF)
        offset += BEAVER_STRUCT.size
    return _finalize_realtime(data)


def decode_world_state(data: bytes) -> WorldStatePacket:
    data, status, seq = _validate_realtime(data, RealtimeType.WORLD_STATE)
    offset = REALTIME_HEAD_STRUCT.size
    player_x, player_y, health, correction_flags, echo_client_seq, tile_id = REALTIME_WORLD_HEAD_STRUCT.unpack_from(
        data, offset
    )
    offset += REALTIME_WORLD_HEAD_STRUCT.size
    tile_x = data[offset]
    tile_y = data[offset + 1]
    offset += 2
    count = min(status, REALTIME_MAX_BEAVERS)
    beavers: list[BeaverSnapshot] = []
    for index in range(REALTIME_MAX_BEAVERS):
        beaver = BeaverSnapshot(*BEAVER_STRUCT.unpack_from(data, offset))
        if index < count:
            beavers.append(beaver)
        offset += BEAVER_STRUCT.size
    return WorldStatePacket(
        seq,
        player_x,
        player_y,
        health,
        correction_flags,
        tuple(beavers),
        tile_x,
        tile_y,
        tile_id,
        echo_client_seq,
    )


def encode_terrain_edge(msg: TerrainEdgePacket) -> bytes:
    if msg.width * msg.height != len(msg.tiles):
        raise PacketError("bad terrain edge tile count")
    max_tiles = REALTIME_PACKET_BYTES - REALTIME_HEAD_STRUCT.size - 6 - 2
    if len(msg.tiles) > max_tiles:
        raise PacketError("terrain edge too large")
    data = _realtime_base(RealtimeType.TERRAIN_EDGE, msg.seq, len(msg.tiles))
    offset = REALTIME_HEAD_STRUCT.size
    data[offset : offset + 6] = bytes(
        (
            msg.origin_x & 0xFF,
            msg.origin_y & 0xFF,
            msg.width & 0xFF,
            msg.height & 0xFF,
            msg.revision & 0xFF,
            (msg.revision >> 8) & 0xFF,
        )
    )
    data[offset + 6 : offset + 6 + len(msg.tiles)] = msg.tiles
    return _finalize_realtime(data)


def decode_terrain_edge(data: bytes) -> TerrainEdgePacket:
    data, status, seq = _validate_realtime(data, RealtimeType.TERRAIN_EDGE)
    offset = REALTIME_HEAD_STRUCT.size
    origin_x, origin_y, width, height = data[offset], data[offset + 1], data[offset + 2], data[offset + 3]
    tile_count = width * height
    if tile_count != status:
        raise PacketError("bad terrain edge tile count")
    tiles = bytes(data[offset + 6 : offset + 6 + tile_count])
    revision = data[offset + 4] | (data[offset + 5] << 8)
    return TerrainEdgePacket(seq, origin_x, origin_y, width, height, tiles, revision)


def encode_map_change(msg: MapChangePacket) -> bytes:
    data = _realtime_base(RealtimeType.MAP_CHANGE, msg.seq)
    REALTIME_MAP_CHANGE_STRUCT.pack_into(
        data,
        REALTIME_HEAD_STRUCT.size,
        msg.map_id & 0xFF,
        msg.spawn_x & 0xFF,
        msg.spawn_y & 0xFF,
        msg.tileset_id & 0xFF,
        msg.palette_id & 0xFF,
        msg.flags & 0xFF,
    )
    return _finalize_realtime(data)


def decode_map_change(data: bytes) -> MapChangePacket:
    data, _, seq = _validate_realtime(data, RealtimeType.MAP_CHANGE)
    return MapChangePacket(seq, *REALTIME_MAP_CHANGE_STRUCT.unpack_from(data, REALTIME_HEAD_STRUCT.size))


def encode_entity_delta(msg: EntityDeltaPacket) -> bytes:
    if len(msg.records) > REALTIME_MAX_ENTITY_DELTAS:
        raise PacketError("too many entity delta records")
    data = _realtime_base(RealtimeType.ENTITY_DELTA, msg.seq, len(msg.records))
    offset = REALTIME_HEAD_STRUCT.size
    for record in msg.records:
        REALTIME_ENTITY_DELTA_RECORD_STRUCT.pack_into(
            data,
            offset,
            record.entity_id & 0xFF,
            record.entity_type & 0xFF,
            record.x & 0xFF,
            record.y & 0xFF,
            record.tile_id & 0xFF,
            record.hp & 0xFF,
            record.flags & 0xFF,
            record.state & 0xFF,
        )
        offset += REALTIME_ENTITY_DELTA_RECORD_STRUCT.size
    return _finalize_realtime(data)


def decode_entity_delta(data: bytes) -> EntityDeltaPacket:
    data, status, seq = _validate_realtime(data, RealtimeType.ENTITY_DELTA)
    if status > REALTIME_MAX_ENTITY_DELTAS:
        raise PacketError("too many entity delta records")
    offset = REALTIME_HEAD_STRUCT.size
    records: list[EntityDeltaRecord] = []
    for _ in range(status):
        records.append(EntityDeltaRecord(*REALTIME_ENTITY_DELTA_RECORD_STRUCT.unpack_from(data, offset)))
        offset += REALTIME_ENTITY_DELTA_RECORD_STRUCT.size
    return EntityDeltaPacket(seq, tuple(records))


def encode_hud_update(msg: HudUpdatePacket) -> bytes:
    data = _realtime_base(RealtimeType.HUD_UPDATE, msg.seq)
    REALTIME_HUD_UPDATE_STRUCT.pack_into(
        data,
        REALTIME_HEAD_STRUCT.size,
        msg.hp & 0xFF,
        msg.max_hp & 0xFF,
        msg.level & 0xFF,
        msg.xp & 0xFFFF,
        msg.xp_next & 0xFFFF,
        msg.gold & 0xFFFF,
        msg.flags & 0xFF,
        msg.pvp_kills & 0xFFFF,
    )
    return _finalize_realtime(data)


def decode_hud_update(data: bytes) -> HudUpdatePacket:
    data, _, seq = _validate_realtime(data, RealtimeType.HUD_UPDATE)
    return HudUpdatePacket(seq, *REALTIME_HUD_UPDATE_STRUCT.unpack_from(data, REALTIME_HEAD_STRUCT.size))


def encode_message(msg: MessagePacket) -> bytes:
    data = _realtime_base(RealtimeType.MESSAGE, msg.seq)
    offset = REALTIME_HEAD_STRUCT.size
    text_bytes = _encode_realtime_text(msg.text)
    data[offset] = msg.message_id & 0xFF
    data[offset + 1] = len(text_bytes)
    data[offset + 2 : offset + 2 + len(text_bytes)] = text_bytes
    return _finalize_realtime(data)


def decode_message(data: bytes) -> MessagePacket:
    data, _, seq = _validate_realtime(data, RealtimeType.MESSAGE)
    offset = REALTIME_HEAD_STRUCT.size
    message_id = data[offset]
    text = _decode_realtime_text(data, offset + 1)
    return MessagePacket(seq, message_id, text)


def encode_quest_update(msg: QuestUpdatePacket) -> bytes:
    data = _realtime_base(RealtimeType.QUEST_UPDATE, msg.seq)
    offset = REALTIME_HEAD_STRUCT.size
    text_bytes = _encode_realtime_text(msg.text)
    data[offset] = msg.quest_id & 0xFF
    data[offset + 1] = msg.state & 0xFF
    data[offset + 2] = len(text_bytes)
    data[offset + 3 : offset + 3 + len(text_bytes)] = text_bytes
    return _finalize_realtime(data)


def decode_quest_update(data: bytes) -> QuestUpdatePacket:
    data, _, seq = _validate_realtime(data, RealtimeType.QUEST_UPDATE)
    offset = REALTIME_HEAD_STRUCT.size
    quest_id = data[offset]
    state = data[offset + 1]
    text = _decode_realtime_text(data, offset + 2)
    return QuestUpdatePacket(seq, quest_id, state, text)


def encode_dialogue_page(msg: DialoguePagePacket) -> bytes:
    data = _realtime_base(RealtimeType.DIALOGUE_PAGE, msg.seq)
    offset = REALTIME_HEAD_STRUCT.size
    text_bytes = _encode_realtime_text(msg.text, REALTIME_DIALOGUE_MAX_TEXT)
    REALTIME_DIALOGUE_HEAD_STRUCT.pack_into(
        data,
        offset,
        msg.dialogue_id & 0xFF,
        msg.speaker_id & 0xFF,
        msg.page_index & 0xFF,
        msg.page_count & 0xFF,
        msg.flags & 0xFF,
        msg.chunk_index & 0xFF,
        len(text_bytes),
    )
    data[REALTIME_DIALOGUE_TEXT_OFFSET : REALTIME_DIALOGUE_TEXT_OFFSET + len(text_bytes)] = text_bytes
    return _finalize_realtime(data)


def decode_dialogue_page(data: bytes) -> DialoguePagePacket:
    data, _, seq = _validate_realtime(data, RealtimeType.DIALOGUE_PAGE)
    offset = REALTIME_HEAD_STRUCT.size
    dialogue_id, speaker_id, page_index, page_count, flags, chunk_index, _text_len = (
        REALTIME_DIALOGUE_HEAD_STRUCT.unpack_from(data, offset)
    )
    text = _decode_realtime_text(data, offset + REALTIME_DIALOGUE_HEAD_STRUCT.size - 1)
    return DialoguePagePacket(
        seq, dialogue_id, speaker_id, page_index, page_count, flags, text, chunk_index
    )


def encode_inventory_update(msg: InventoryUpdatePacket) -> bytes:
    if len(msg.slots) > REALTIME_MAX_INVENTORY_SLOTS:
        raise PacketError("too many inventory slots")
    data = _realtime_base(RealtimeType.INVENTORY_UPDATE, msg.seq)
    offset = REALTIME_HEAD_STRUCT.size
    REALTIME_INVENTORY_HEAD_STRUCT.pack_into(data, offset, len(msg.slots), msg.gold & 0xFFFF)
    offset += REALTIME_INVENTORY_HEAD_STRUCT.size
    for item_id, quantity in msg.slots:
        REALTIME_INVENTORY_SLOT_STRUCT.pack_into(data, offset, item_id & 0xFF, quantity & 0xFF)
        offset += REALTIME_INVENTORY_SLOT_STRUCT.size
    return _finalize_realtime(data)


def decode_inventory_update(data: bytes) -> InventoryUpdatePacket:
    data, _, seq = _validate_realtime(data, RealtimeType.INVENTORY_UPDATE)
    offset = REALTIME_HEAD_STRUCT.size
    slot_count, gold = REALTIME_INVENTORY_HEAD_STRUCT.unpack_from(data, offset)
    if slot_count > REALTIME_MAX_INVENTORY_SLOTS:
        raise PacketError("too many inventory slots")
    offset += REALTIME_INVENTORY_HEAD_STRUCT.size
    slots: list[tuple[int, int]] = []
    for _ in range(slot_count):
        slots.append(REALTIME_INVENTORY_SLOT_STRUCT.unpack_from(data, offset))
        offset += REALTIME_INVENTORY_SLOT_STRUCT.size
    return InventoryUpdatePacket(seq, tuple(slots), gold)


def encode_respawn_event(msg: RespawnEventPacket) -> bytes:
    data = _realtime_base(RealtimeType.RESPAWN_EVENT, msg.seq)
    REALTIME_RESPAWN_EVENT_STRUCT.pack_into(
        data,
        REALTIME_HEAD_STRUCT.size,
        msg.map_id & 0xFF,
        msg.x & 0xFF,
        msg.y & 0xFF,
        msg.hp & 0xFF,
        msg.max_hp & 0xFF,
        msg.message_id & 0xFF,
        msg.flags & 0xFF,
    )
    return _finalize_realtime(data)


def decode_respawn_event(data: bytes) -> RespawnEventPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.RESPAWN_EVENT)
    map_id, x, y, hp, max_hp, message_id, flags = REALTIME_RESPAWN_EVENT_STRUCT.unpack_from(
        data, REALTIME_HEAD_STRUCT.size
    )
    return RespawnEventPacket(seq, x, y, hp, flags, map_id, max_hp, message_id)


def encode_player_command(msg: PlayerCommandPacket) -> bytes:
    data = _realtime_base(RealtimeType.PLAYER_COMMAND, msg.seq)
    REALTIME_PLAYER_COMMAND_STRUCT.pack_into(
        data,
        REALTIME_HEAD_STRUCT.size,
        msg.command & 0xFF,
        msg.direction & 0xFF,
        msg.arg0 & 0xFF,
        msg.arg1 & 0xFF,
        msg.last_server_seq & 0xFFFF,
    )
    return _finalize_realtime(data)


def decode_player_command(data: bytes) -> PlayerCommandPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.PLAYER_COMMAND)
    return PlayerCommandPacket(seq, *REALTIME_PLAYER_COMMAND_STRUCT.unpack_from(data, REALTIME_HEAD_STRUCT.size))


def encode_auth(msg: AuthPacket) -> bytes:
    data = _realtime_base(RealtimeType.AUTH, msg.seq)
    REALTIME_AUTH_STRUCT.pack_into(data, REALTIME_HEAD_STRUCT.size, msg.token & 0xFFFFFFFF)
    return _finalize_realtime(data)


def decode_auth(data: bytes) -> AuthPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.AUTH)
    (token,) = REALTIME_AUTH_STRUCT.unpack_from(data, REALTIME_HEAD_STRUCT.size)
    return AuthPacket(seq, token)


def encode_remote_players(msg: RemotePlayersPacket) -> bytes:
    if len(msg.players) > REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED:
        raise PacketError("too many remote player records")
    data = _realtime_base(RealtimeType.REMOTE_PLAYERS, msg.seq, len(msg.players))
    offset = REALTIME_HEAD_STRUCT.size
    for record in msg.players:
        REALTIME_REMOTE_PLAYER_STRUCT.pack_into(
            data,
            offset,
            record.x & 0xFF,
            record.y & 0xFF,
            record.facing & 0xFF,
            record.state & 0xFF,
        )
        offset += REALTIME_REMOTE_PLAYER_STRUCT.size
    return _finalize_realtime(data)


def decode_remote_players(data: bytes) -> RemotePlayersPacket:
    data, status, seq = _validate_realtime(data, RealtimeType.REMOTE_PLAYERS)
    if status > REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED:
        raise PacketError("too many remote player records")
    offset = REALTIME_HEAD_STRUCT.size
    records: list[RemotePlayerRecord] = []
    for _ in range(status):
        records.append(RemotePlayerRecord(*REALTIME_REMOTE_PLAYER_STRUCT.unpack_from(data, offset)))
        offset += REALTIME_REMOTE_PLAYER_STRUCT.size
    return RemotePlayersPacket(seq, tuple(records))


def encode_item_drops(msg: ItemDropsPacket) -> bytes:
    if len(msg.items) > REALTIME_MAX_ITEM_DROPS:
        raise PacketError("too many item drop records")
    data = _realtime_base(RealtimeType.ITEM_DROPS, msg.seq, len(msg.items))
    offset = REALTIME_HEAD_STRUCT.size
    for record in msg.items:
        REALTIME_ITEM_DROP_STRUCT.pack_into(
            data,
            offset,
            record.x & 0xFF,
            record.y & 0xFF,
            record.item_id & 0xFF,
            record.quantity & 0xFF,
        )
        offset += REALTIME_ITEM_DROP_STRUCT.size
    return _finalize_realtime(data)


def decode_item_drops(data: bytes) -> ItemDropsPacket:
    data, status, seq = _validate_realtime(data, RealtimeType.ITEM_DROPS)
    if status > REALTIME_MAX_ITEM_DROPS:
        raise PacketError("too many item drop records")
    offset = REALTIME_HEAD_STRUCT.size
    records: list[ItemDropRecord] = []
    for _ in range(status):
        records.append(ItemDropRecord(*REALTIME_ITEM_DROP_STRUCT.unpack_from(data, offset)))
        offset += REALTIME_ITEM_DROP_STRUCT.size
    return ItemDropsPacket(seq, tuple(records))


def encode_map_summary(msg: MapSummaryPacket) -> bytes:
    expected = msg.width * msg.height
    if expected != len(msg.cells):
        raise PacketError("map summary cell count mismatch")
    if expected > REALTIME_MAP_SUMMARY_MAX_CELLS:
        raise PacketError("map summary too large")
    data = _realtime_base(RealtimeType.MAP_SUMMARY, msg.seq, expected)
    REALTIME_MAP_SUMMARY_HEAD_STRUCT.pack_into(
        data,
        REALTIME_HEAD_STRUCT.size,
        msg.map_id & 0xFF,
        msg.origin_zx & 0xFF,
        msg.origin_zy & 0xFF,
        msg.width & 0xFF,
        msg.height & 0xFF,
        0,
    )
    offset = REALTIME_MAP_SUMMARY_CELL_OFFSET
    data[offset : offset + expected] = msg.cells
    return _finalize_realtime(data)


def decode_map_summary(data: bytes) -> MapSummaryPacket:
    data, status, seq = _validate_realtime(data, RealtimeType.MAP_SUMMARY)
    map_id, origin_zx, origin_zy, width, height, _ = REALTIME_MAP_SUMMARY_HEAD_STRUCT.unpack_from(
        data, REALTIME_HEAD_STRUCT.size
    )
    expected = width * height
    if expected != status or expected > REALTIME_MAP_SUMMARY_MAX_CELLS:
        raise PacketError("invalid map summary size")
    offset = REALTIME_MAP_SUMMARY_CELL_OFFSET
    return MapSummaryPacket(seq, map_id, origin_zx, origin_zy, width, height, bytes(data[offset : offset + expected]))


def encode_resync_request(msg: ResyncRequestPacket) -> bytes:
    data = _realtime_base(RealtimeType.RESYNC_REQUEST, msg.seq)
    data[REALTIME_HEAD_STRUCT.size] = msg.origin_x & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 1] = msg.origin_y & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 2] = msg.fill_origin_x & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 3] = msg.fill_origin_y & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 4] = msg.rows_have & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 5] = (msg.rows_have >> 8) & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 6] = (msg.rows_have >> 16) & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 7] = msg.fill_id & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 8] = msg.flags & 0xFF
    return _finalize_realtime(data)


def decode_resync_request(data: bytes) -> ResyncRequestPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.RESYNC_REQUEST)
    base = REALTIME_HEAD_STRUCT.size
    rows_have = data[base + 4] | (data[base + 5] << 8) | (data[base + 6] << 16)
    return ResyncRequestPacket(
        seq, data[base], data[base + 1], data[base + 2], data[base + 3], rows_have,
        data[base + 7], data[base + 8]
    )


def encode_map_ready(msg: MapReadyPacket) -> bytes:
    data = _realtime_base(RealtimeType.MAP_READY, msg.seq)
    data[REALTIME_HEAD_STRUCT.size] = msg.map_id & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 1] = msg.origin_x & 0xFF
    data[REALTIME_HEAD_STRUCT.size + 2] = msg.origin_y & 0xFF
    return _finalize_realtime(data)


def decode_map_ready(data: bytes) -> MapReadyPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.MAP_READY)
    offset = REALTIME_HEAD_STRUCT.size
    return MapReadyPacket(seq, data[offset], data[offset + 1], data[offset + 2])


def encode_window_row(msg: WindowRowPacket) -> bytes:
    if len(msg.tiles) != WINDOW_W:
        raise PacketError("bad window row tile count")
    data = _realtime_base(RealtimeType.WINDOW_ROW, msg.seq, len(msg.tiles))
    REALTIME_WINDOW_ROW_HEAD_STRUCT.pack_into(
        data,
        REALTIME_HEAD_STRUCT.size,
        msg.origin_x & 0xFF,
        msg.origin_y & 0xFF,
        msg.row_index & 0xFF,
        msg.fill_id & 0xFF,
    )
    data[REALTIME_WINDOW_ROW_TILE_OFFSET : REALTIME_WINDOW_ROW_TILE_OFFSET + WINDOW_W] = msg.tiles
    return _finalize_realtime(data)


def decode_window_row(data: bytes) -> WindowRowPacket:
    data, status, seq = _validate_realtime(data, RealtimeType.WINDOW_ROW)
    if status != WINDOW_W:
        raise PacketError("bad window row tile count")
    origin_x, origin_y, row_index, fill_id = REALTIME_WINDOW_ROW_HEAD_STRUCT.unpack_from(
        data, REALTIME_HEAD_STRUCT.size
    )
    tiles = bytes(data[REALTIME_WINDOW_ROW_TILE_OFFSET : REALTIME_WINDOW_ROW_TILE_OFFSET + WINDOW_W])
    return WindowRowPacket(seq, origin_x, origin_y, row_index, tiles, fill_id)


def encode_window_commit(msg: WindowCommitPacket) -> bytes:
    data = _realtime_base(RealtimeType.WINDOW_COMMIT, msg.seq)
    base = REALTIME_HEAD_STRUCT.size
    data[base : base + 5] = bytes((
        msg.fill_id & 0xFF,
        msg.origin_x & 0xFF,
        msg.origin_y & 0xFF,
        msg.map_id & 0xFF,
        msg.flags & 0xFF,
    ))
    return _finalize_realtime(data)


def decode_window_commit(data: bytes) -> WindowCommitPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.WINDOW_COMMIT)
    base = REALTIME_HEAD_STRUCT.size
    fill_id, origin_x, origin_y, map_id, flags = data[base : base + 5]
    if fill_id == 0:
        raise PacketError("window commit requires a fill id")
    return WindowCommitPacket(seq, fill_id, origin_x, origin_y, map_id, flags)


@dataclass(frozen=True)
class CacheStepAckPacket:
    seq: int
    revision: int
    origin_x: int
    origin_y: int


def encode_cache_step_ack(msg: CacheStepAckPacket) -> bytes:
    data = _realtime_base(RealtimeType.CACHE_STEP_ACK, msg.seq)
    base = REALTIME_V3_HEAD_BYTES
    data[base] = msg.revision & 0xFF
    data[base + 1] = (msg.revision >> 8) & 0xFF
    data[base + 2] = msg.origin_x & 0xFF
    data[base + 3] = msg.origin_y & 0xFF
    return _finalize_realtime(data)


def decode_cache_step_ack(data: bytes) -> CacheStepAckPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.CACHE_STEP_ACK)
    base = REALTIME_V3_HEAD_BYTES
    revision = data[base] | (data[base + 1] << 8)
    return CacheStepAckPacket(seq, revision, data[base + 2], data[base + 3])


@dataclass(frozen=True)
class WindowCommitAckPacket:
    seq: int
    fill_id: int
    origin_x: int
    origin_y: int


def encode_window_commit_ack(msg: WindowCommitAckPacket) -> bytes:
    data = _realtime_base(RealtimeType.WINDOW_COMMIT_ACK, msg.seq)
    base = REALTIME_V3_HEAD_BYTES
    data[base] = msg.fill_id & 0xFF
    data[base + 1] = msg.origin_x & 0xFF
    data[base + 2] = msg.origin_y & 0xFF
    return _finalize_realtime(data)


def decode_window_commit_ack(data: bytes) -> WindowCommitAckPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.WINDOW_COMMIT_ACK)
    base = REALTIME_V3_HEAD_BYTES
    return WindowCommitAckPacket(seq, data[base], data[base + 1], data[base + 2])


@dataclass(frozen=True)
class NetStatsPacket:
    """Phase 43 client telemetry: link-health counters reported ~every 4 s.

    All counters are 8-bit and wrap; the server logs deltas. rx_drops counts
    frames rejected by the client's COBS/CRC validation, the handler_* fields
    mirror the Netstream handler's sticky serial status.
    """

    seq: int
    rx_drops: int
    handler_overflows: int
    handler_serial_errors: int
    handler_last_status: int
    fill_id: int
    commit_pending: int
    origin_x: int
    origin_y: int
    cache_revision: int


def encode_net_stats(msg: NetStatsPacket) -> bytes:
    data = _realtime_base(RealtimeType.NET_STATS, msg.seq)
    base = REALTIME_V3_HEAD_BYTES
    data[base : base + 10] = bytes(
        (
            msg.rx_drops & 0xFF,
            msg.handler_overflows & 0xFF,
            msg.handler_serial_errors & 0xFF,
            msg.handler_last_status & 0xFF,
            msg.fill_id & 0xFF,
            msg.commit_pending & 0xFF,
            msg.origin_x & 0xFF,
            msg.origin_y & 0xFF,
            msg.cache_revision & 0xFF,
            (msg.cache_revision >> 8) & 0xFF,
        )
    )
    return _finalize_realtime(data)


def decode_net_stats(data: bytes) -> NetStatsPacket:
    data, _, seq = _validate_realtime(data, RealtimeType.NET_STATS)
    base = REALTIME_V3_HEAD_BYTES
    return NetStatsPacket(
        seq,
        data[base],
        data[base + 1],
        data[base + 2],
        data[base + 3],
        data[base + 4],
        data[base + 5],
        data[base + 6],
        data[base + 7],
        data[base + 8] | (data[base + 9] << 8),
    )


def encode_realtime_bye(seq: int) -> bytes:
    return _finalize_realtime(_realtime_base(RealtimeType.BYE, seq))


def encode_packet(packet_type: PacketType, payload: bytes = b"") -> bytes:
    if len(payload) > 255:
        raise PacketError("payload too large")
    head = bytes((MAGIC, VERSION, int(packet_type), len(payload))) + payload
    return head + bytes((checksum(head),))


def decode_packet(data: bytes) -> Packet:
    if len(data) < 5:
        raise PacketError("packet too short")
    if data[0] != MAGIC:
        raise PacketError("bad magic")
    if data[1] != VERSION:
        raise PacketError("bad protocol version")
    payload_len = data[3]
    expected = payload_len + 5
    if len(data) != expected:
        raise PacketError("bad packet length")
    if checksum(data[:-1]) != data[-1]:
        raise PacketError("bad checksum")
    try:
        packet_type = PacketType(data[2])
    except ValueError as exc:
        raise PacketError("unknown packet type") from exc
    return Packet(packet_type, data[4:-1])


class PacketStreamDecoder:
    """Incremental decoder suitable for Atari byte-stream traffic."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Packet]:
        packets: list[Packet] = []
        for byte in data:
            if not self._buf and byte != MAGIC:
                continue
            self._buf.append(byte)
            if len(self._buf) >= 4:
                expected = self._buf[3] + 5
                if len(self._buf) == expected:
                    try:
                        packets.append(decode_packet(bytes(self._buf)))
                    except PacketError:
                        pass
                    self._buf.clear()
        return packets


def encode_hello(msg: Hello) -> bytes:
    return encode_packet(PacketType.HELLO, HELLO_STRUCT.pack(msg.flags, msg.seed, msg.token))


def decode_hello(payload: bytes) -> Hello:
    if len(payload) != HELLO_STRUCT.size:
        raise PacketError("bad HELLO payload length")
    flags, seed, token = HELLO_STRUCT.unpack(payload)
    return Hello(flags, seed, token)


def _ascii_bytes(value: str, max_len: int, field_name: str) -> bytes:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise PacketError(f"non-ascii {field_name}") from exc
    if not encoded or len(encoded) > max_len:
        raise PacketError(f"bad {field_name} length")
    return encoded


def _username_bytes(value: str) -> bytes:
    encoded = _ascii_bytes(value, USERNAME_MAX_LEN, "username")
    if b"," in encoded or any(byte < 32 or byte > 126 for byte in encoded):
        raise PacketError("bad username characters")
    return encoded


def _decode_ascii(
    payload: bytes, offset: int, max_len: int, field_name: str, *, require_end: bool = True
) -> tuple[str, int]:
    if offset >= len(payload):
        raise PacketError(f"missing {field_name} length")
    length = payload[offset]
    offset += 1
    if length == 0 or length > max_len or offset + length > len(payload):
        raise PacketError(f"bad {field_name} length")
    if require_end and offset + length != len(payload):
        raise PacketError(f"bad {field_name} length")
    try:
        return payload[offset : offset + length].decode("ascii"), offset + length
    except UnicodeDecodeError as exc:
        raise PacketError(f"non-ascii {field_name}") from exc


def encode_login_request(msg: LoginRequest) -> bytes:
    username = _username_bytes(msg.username)
    return encode_packet(PacketType.LOGIN_REQUEST, bytes((len(username),)) + username)


def decode_login_request(payload: bytes) -> LoginRequest:
    username, _ = _decode_ascii(payload, 0, USERNAME_MAX_LEN, "username")
    _username_bytes(username)
    return LoginRequest(username)


def encode_login_response(msg: LoginResponse) -> bytes:
    token = _ascii_bytes(msg.token, TOKEN_MAX_LEN, "token")
    return encode_packet(PacketType.LOGIN_RESPONSE, bytes((msg.status & 0xFF, len(token))) + token)


def decode_login_response(payload: bytes) -> LoginResponse:
    if len(payload) < 2:
        raise PacketError("bad LOGIN_RESPONSE payload length")
    token, _ = _decode_ascii(payload, 1, TOKEN_MAX_LEN, "token")
    return LoginResponse(payload[0], token)


def encode_resume_request(msg: ResumeRequest) -> bytes:
    token = _ascii_bytes(msg.token, TOKEN_MAX_LEN, "token")
    return encode_packet(PacketType.RESUME_REQUEST, bytes((len(token),)) + token)


def decode_resume_request(payload: bytes) -> ResumeRequest:
    token, _ = _decode_ascii(payload, 0, TOKEN_MAX_LEN, "token")
    return ResumeRequest(token)


def encode_resume_response(msg: ResumeResponse) -> bytes:
    username = _username_bytes(msg.username)
    return encode_packet(PacketType.RESUME_RESPONSE, bytes((msg.status & 0xFF, len(username))) + username)


def decode_resume_response(payload: bytes) -> ResumeResponse:
    if len(payload) < 2:
        raise PacketError("bad RESUME_RESPONSE payload length")
    username, _ = _decode_ascii(payload, 1, USERNAME_MAX_LEN, "username")
    _username_bytes(username)
    return ResumeResponse(payload[0], username)


def encode_rename_request(msg: RenameRequest) -> bytes:
    token = _ascii_bytes(msg.token, TOKEN_MAX_LEN, "token")
    username = _username_bytes(msg.username)
    payload = bytes((len(token),)) + token + bytes((len(username),)) + username
    return encode_packet(PacketType.RENAME_REQUEST, payload)


def decode_rename_request(payload: bytes) -> RenameRequest:
    token, offset = _decode_ascii(payload, 0, TOKEN_MAX_LEN, "token", require_end=False)
    username, _ = _decode_ascii(payload, offset, USERNAME_MAX_LEN, "username")
    _username_bytes(username)
    return RenameRequest(token, username)


def encode_rename_response(msg: RenameResponse) -> bytes:
    return encode_packet(PacketType.RENAME_RESPONSE, bytes((msg.status & 0xFF,)))


def decode_rename_response(payload: bytes) -> RenameResponse:
    if len(payload) != 1:
        raise PacketError("bad RENAME_RESPONSE payload length")
    return RenameResponse(payload[0])


def encode_input(msg: InputIntent) -> bytes:
    return encode_packet(
        PacketType.INPUT,
        INPUT_STRUCT.pack(msg.tick, msg.direction, msg.buttons, msg.aim, msg.ack_tick),
    )


def decode_input(payload: bytes) -> InputIntent:
    if len(payload) != INPUT_STRUCT.size:
        raise PacketError("bad INPUT payload length")
    return InputIntent(*INPUT_STRUCT.unpack(payload))


def encode_welcome(msg: Welcome) -> bytes:
    return encode_packet(
        PacketType.WELCOME,
        WELCOME_STRUCT.pack(msg.player_id, msg.seed, msg.max_beavers, msg.protocol_version),
    )


def decode_welcome(payload: bytes) -> Welcome:
    if len(payload) != WELCOME_STRUCT.size:
        raise PacketError("bad WELCOME payload length")
    return Welcome(*WELCOME_STRUCT.unpack(payload))


def window_chunks(msg: Window) -> tuple[WindowChunk, ...]:
    if msg.width * msg.height <= WINDOW_W * WINDOW_CHUNK_MAX_ROWS:
        return (
            WindowChunk(
                tick=msg.tick,
                origin_x=msg.origin_x,
                origin_y=msg.origin_y,
                width=msg.width,
                height=msg.height,
                chunk_y=0,
                chunk_h=msg.height,
                tiles=msg.tiles,
            ),
        )
    chunks: list[WindowChunk] = []
    for chunk_y in range(0, msg.height, WINDOW_CHUNK_MAX_ROWS):
        chunk_h = min(WINDOW_CHUNK_MAX_ROWS, msg.height - chunk_y)
        start = chunk_y * msg.width
        end = start + chunk_h * msg.width
        chunks.append(
            WindowChunk(
                tick=msg.tick,
                origin_x=msg.origin_x,
                origin_y=msg.origin_y,
                width=msg.width,
                height=msg.height,
                chunk_y=chunk_y,
                chunk_h=chunk_h,
                tiles=msg.tiles[start:end],
            )
        )
    return tuple(chunks)


def encode_window(msg: WindowChunk) -> bytes:
    expected = msg.width * msg.chunk_h
    if len(msg.tiles) != expected:
        raise PacketError("bad WINDOW chunk tile count")
    payload = WINDOW_HEAD_STRUCT.pack(
        msg.tick,
        msg.origin_x,
        msg.origin_y,
        msg.width,
        msg.height,
        msg.chunk_y,
        msg.chunk_h,
        len(msg.tiles),
    ) + msg.tiles
    return encode_packet(PacketType.WINDOW, payload)


def decode_window(payload: bytes) -> WindowChunk:
    if len(payload) < WINDOW_HEAD_STRUCT.size:
        raise PacketError("bad WINDOW payload length")
    tick, origin_x, origin_y, width, height, chunk_y, chunk_h, tile_count = WINDOW_HEAD_STRUCT.unpack(
        payload[: WINDOW_HEAD_STRUCT.size]
    )
    tiles = payload[WINDOW_HEAD_STRUCT.size :]
    if tile_count != width * chunk_h or len(tiles) != tile_count:
        raise PacketError("bad WINDOW chunk tile count")
    if chunk_y + chunk_h > height:
        raise PacketError("bad WINDOW chunk range")
    return WindowChunk(tick, origin_x, origin_y, width, height, chunk_y, chunk_h, tiles)


def encode_snapshot(msg: Snapshot) -> bytes:
    beavers = list(msg.beavers[:MAX_BEAVERS])
    while len(beavers) < MAX_BEAVERS:
        beavers.append(BeaverSnapshot(0, 0, 0, 0))
    payload = bytearray(
        SNAPSHOT_HEAD_STRUCT.pack(msg.tick, msg.player_x, msg.player_y, msg.health, msg.score)
    )
    payload.append(min(len(msg.beavers), MAX_BEAVERS))
    for beaver in beavers:
        payload.extend(BEAVER_STRUCT.pack(beaver.x, beaver.y, beaver.hp, beaver.kind))
    payload.extend((msg.tile_x & 0xFF, msg.tile_y & 0xFF, msg.tile_id & 0xFF))
    return encode_packet(PacketType.SNAPSHOT, bytes(payload))


def decode_snapshot(payload: bytes) -> Snapshot:
    expected = SNAPSHOT_HEAD_STRUCT.size + 1 + BEAVER_STRUCT.size * MAX_BEAVERS + 3
    if len(payload) != expected:
        raise PacketError("bad SNAPSHOT payload length")
    tick, player_x, player_y, health, score = SNAPSHOT_HEAD_STRUCT.unpack(
        payload[: SNAPSHOT_HEAD_STRUCT.size]
    )
    count = min(payload[SNAPSHOT_HEAD_STRUCT.size], MAX_BEAVERS)
    offset = SNAPSHOT_HEAD_STRUCT.size + 1
    beavers: list[BeaverSnapshot] = []
    for index in range(MAX_BEAVERS):
        chunk = payload[offset + index * BEAVER_STRUCT.size : offset + (index + 1) * BEAVER_STRUCT.size]
        beaver = BeaverSnapshot(*BEAVER_STRUCT.unpack(chunk))
        if index < count:
            beavers.append(beaver)
    tile_offset = offset + BEAVER_STRUCT.size * MAX_BEAVERS
    tile_x = payload[tile_offset]
    tile_y = payload[tile_offset + 1]
    tile_id = payload[tile_offset + 2]
    return Snapshot(tick, player_x, player_y, health, score, tuple(beavers), tile_x, tile_y, tile_id)
