import unittest

from server.protocol import (
    RealtimeFrameDecoder,
    decode_cobs,
    encode_cobs,
    crc16_ccitt,
    _normalize_realtime,
    AuthPacket,
    BeaverSnapshot,
    EntityDeltaPacket,
    ItemDropRecord,
    ItemDropsPacket,
    MapChangePacket,
    MapReadyPacket,
    MapSummaryPacket,
    PacketError,
    REALTIME_MAX_ITEM_DROPS,
    REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED,
    REALTIME_REMOTE_PLAYERS_LARGE_CAPACITY,
    REALTIME_SMALL_TYPES,
    RemotePlayerRecord,
    RemotePlayersPacket,
    ResyncRequestPacket,
    WINDOW_W,
    WindowRowPacket,
    decode_auth,
    decode_entity_delta,
    decode_item_drops,
    decode_map_summary,
    decode_map_ready,
    decode_remote_players,
    decode_resync_request,
    decode_window_row,
    encode_auth,
    encode_entity_delta,
    encode_item_drops,
    encode_map_summary,
    encode_map_ready,
    encode_remote_players,
    encode_resync_request,
    encode_window_row,
    Hello,
    HudUpdatePacket,
    InputIntent,
    InventoryUpdatePacket,
    MessagePacket,
    PacketStreamDecoder,
    PacketType,
    PlayerStatePacket,
    PlayerCommandPacket,
    QuestUpdatePacket,
    REALTIME_PACKET_BYTES,
    REALTIME_SMALL_PACKET_BYTES,
    RealtimeType,
    RespawnEventPacket,
    TerrainEdgePacket,
    Snapshot,
    Window,
    WorldStatePacket,
    decode_player_state,
    decode_hello,
    decode_input,
    decode_hud_update,
    decode_inventory_update,
    decode_message,
    decode_packet,
    decode_snapshot,
    decode_terrain_edge,
    decode_quest_update,
    decode_respawn_event,
    decode_world_state,
    encode_player_state,
    encode_map_change,
    decode_welcome,
    decode_window,
    encode_hello,
    encode_input,
    encode_hud_update,
    encode_inventory_update,
    encode_message,
    encode_snapshot,
    encode_terrain_edge,
    encode_quest_update,
    encode_respawn_event,
    encode_welcome,
    encode_window,
    encode_world_state,
    encode_player_command,
    encode_realtime_bye,
    realtime_packet_size,
    seq_delta,
    window_chunks,
    Welcome,
)


class ProtocolTest(unittest.TestCase):
    def test_hello_round_trip(self):
        packet = decode_packet(encode_hello(Hello(flags=0x12, seed=0x3456)))
        self.assertEqual(packet.packet_type, PacketType.HELLO)
        self.assertEqual(decode_hello(packet.payload), Hello(flags=0x12, seed=0x3456))

    def test_input_round_trip(self):
        original = InputIntent(tick=7, direction=0x07, buttons=1, aim=3, ack_tick=6)
        packet = decode_packet(encode_input(original))
        self.assertEqual(packet.packet_type, PacketType.INPUT)
        self.assertEqual(decode_input(packet.payload), original)

    def test_welcome_round_trip(self):
        packet = decode_packet(encode_welcome(Welcome(player_id=1, seed=0x2222)))
        self.assertEqual(packet.packet_type, PacketType.WELCOME)
        self.assertEqual(decode_welcome(packet.payload), Welcome(player_id=1, seed=0x2222))

    def test_snapshot_round_trip_pads_to_six_beavers(self):
        original = Snapshot(
            tick=9,
            player_x=10,
            player_y=11,
            health=4,
            score=123,
            beavers=(BeaverSnapshot(20, 21, 2, 1),),
            tile_x=12,
            tile_y=13,
            tile_id=4,
        )
        packet = decode_packet(encode_snapshot(original))
        decoded = decode_snapshot(packet.payload)
        self.assertEqual(decoded, original)

    def test_window_round_trip(self):
        tiles = bytes((index & 0xFF) for index in range(32 * 24))
        window = Window(tick=7, origin_x=4, origin_y=5, width=32, height=24, tiles=tiles)
        chunks = window_chunks(window)
        self.assertEqual([chunk.chunk_h for chunk in chunks], [3, 3, 3, 3, 3, 3, 3, 3])
        decoded_tiles = bytearray()
        for original in chunks:
            packet = decode_packet(encode_window(original))
            self.assertEqual(packet.packet_type, PacketType.WINDOW)
            decoded = decode_window(packet.payload)
            self.assertEqual(decoded, original)
            decoded_tiles.extend(decoded.tiles)
        self.assertEqual(bytes(decoded_tiles), tiles)

    def test_stream_decoder_skips_register_noise(self):
        stream = PacketStreamDecoder()
        encoded = encode_hello(Hello(flags=1, seed=2))
        packets = []
        for byte in b"REGISTER" + encoded[:3]:
            packets.extend(stream.feed(bytes((byte,))))
        self.assertEqual(packets, [])
        packets.extend(stream.feed(encoded[3:]))
        self.assertEqual(len(packets), 1)
        self.assertEqual(decode_hello(packets[0].payload), Hello(flags=1, seed=2))

    def test_realtime_player_state_round_trip_is_fixed_size(self):
        original = PlayerStatePacket(
            seq=12,
            x=40,
            y=41,
            facing=3,
            buttons=1,
            fire_counter=7,
            pickup_counter=9,
            last_server_seq=11,
            rx_drops=2,
            pvp_toggle_counter=5,
        )
        encoded = encode_player_state(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(decode_player_state(encoded), original)

    def test_realtime_rejects_bad_checksum(self):
        original = PlayerStatePacket(
            seq=12,
            x=40,
            y=41,
            facing=3,
            buttons=1,
            fire_counter=7,
            pickup_counter=9,
            last_server_seq=11,
            rx_drops=2,
        )
        encoded = bytearray(encode_player_state(original))
        encoded[6] ^= 0x01
        with self.assertRaises(PacketError):
            decode_player_state(bytes(encoded))

    def test_realtime_rejects_corrupted_frame(self):
        encoded = bytearray(encode_auth(AuthPacket(seq=7, token=0x12345678)))
        encoded[3] ^= 0x40  # one damaged wire byte must fail the CRC-16
        with self.assertRaises(PacketError):
            decode_auth(bytes(encoded))

    def test_realtime_world_state_round_trip_packs_beavers(self):
        original = WorldStatePacket(
            seq=99,
            player_x=10,
            player_y=11,
            health=3,
            correction_flags=1,
            beavers=(BeaverSnapshot(20, 21, 2, 1), BeaverSnapshot(22, 23, 1, 1)),
            tile_x=24,
            tile_y=25,
            tile_id=4,
            echo_client_seq=98,
        )
        encoded = encode_world_state(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(decode_world_state(encoded), original)

    def test_realtime_terrain_edge_round_trip(self):
        original = TerrainEdgePacket(seq=5, origin_x=32, origin_y=8, width=1, height=24, tiles=bytes(range(24)))
        encoded = encode_terrain_edge(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(decode_terrain_edge(encoded), original)

    def test_realtime_hud_message_and_quest_round_trip(self):
        hud = HudUpdatePacket(seq=1, hp=11, max_hp=12, level=1, xp=5, xp_next=20, gold=3, pvp_kills=456)
        encoded_hud = encode_hud_update(hud)
        self.assertLessEqual(len(encoded_hud), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded_hud)[16], 456 & 0xFF)
        self.assertEqual(_normalize_realtime(encoded_hud)[17], 456 >> 8)
        self.assertEqual(decode_hud_update(encoded_hud), hud)
        message = MessagePacket(seq=2, message_id=4, text="HELLO")
        self.assertEqual(decode_message(encode_message(message)), message)
        quest = QuestUpdatePacket(seq=3, quest_id=1, state=2, text="ROAD TROUBLE 1/3")
        self.assertEqual(decode_quest_update(encode_quest_update(quest)), quest)
        respawn = RespawnEventPacket(seq=4, map_id=1, x=8, y=10, hp=14, max_hp=14, message_id=13)
        self.assertEqual(decode_respawn_event(encode_respawn_event(respawn)), respawn)

    def test_realtime_inventory_update_round_trip(self):
        inventory = InventoryUpdatePacket(seq=5, slots=((2, 3), (3, 1)), gold=7)
        encoded = encode_inventory_update(inventory)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 10)
        self.assertEqual(decode_inventory_update(encoded), inventory)

    def test_realtime_auth_round_trip_is_fixed_size(self):
        original = AuthPacket(seq=3, token=0xDEADBEEF)
        encoded = encode_auth(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 13)
        self.assertEqual(decode_auth(encoded), original)

    def test_realtime_remote_players_round_trip(self):
        original = RemotePlayersPacket(
            seq=7,
            players=(
                RemotePlayerRecord(x=10, y=11, facing=2, state=1),
                RemotePlayerRecord(x=12, y=13, facing=0, state=1),
            ),
        )
        encoded = encode_remote_players(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 14)
        self.assertEqual(_normalize_realtime(encoded)[3], 2)
        self.assertEqual(decode_remote_players(encoded), original)

    def test_realtime_remote_player_state_preserves_shot_bits(self):
        original = RemotePlayersPacket(
            seq=8,
            players=(RemotePlayerRecord(x=10, y=11, facing=2, state=0b1101),),
        )
        self.assertEqual(decode_remote_players(encode_remote_players(original)), original)

    def test_realtime_remote_players_accepts_twelve_records(self):
        records = tuple(RemotePlayerRecord(x=i, y=i + 1, facing=i & 3, state=1) for i in range(12))
        encoded = encode_remote_players(RemotePlayersPacket(seq=9, players=records))
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[3], 12)
        self.assertEqual(decode_remote_players(encoded), RemotePlayersPacket(seq=9, players=records))

    def test_realtime_item_drops_round_trip(self):
        original = ItemDropsPacket(
            seq=3,
            items=(
                ItemDropRecord(x=15, y=9, item_id=1, quantity=1),
                ItemDropRecord(x=16, y=9, item_id=2, quantity=1),
            ),
        )
        encoded = encode_item_drops(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 17)
        self.assertEqual(_normalize_realtime(encoded)[3], 2)
        self.assertEqual(decode_item_drops(encoded), original)

    def test_realtime_item_drops_empty_and_overflow(self):
        empty = ItemDropsPacket(seq=1, items=())
        self.assertEqual(decode_item_drops(encode_item_drops(empty)), empty)
        too_many = ItemDropsPacket(
            seq=2,
            items=tuple(
                ItemDropRecord(x=i, y=i, item_id=1, quantity=1) for i in range(REALTIME_MAX_ITEM_DROPS + 1)
            ),
        )
        with self.assertRaises(PacketError):
            encode_item_drops(too_many)

    def test_realtime_map_summary_round_trip_and_overflow(self):
        original = MapSummaryPacket(
            seq=4,
            map_id=1,
            origin_zx=0,
            origin_zy=0,
            width=8,
            height=6,
            cells=bytes(range(48)),
        )
        encoded = encode_map_summary(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 18)
        self.assertEqual(_normalize_realtime(encoded)[3], 48)
        self.assertEqual(decode_map_summary(encoded), original)
        with self.assertRaises(PacketError):
            encode_map_summary(MapSummaryPacket(5, 0, 0, 0, 8, 7, bytes(range(56))))

    def test_realtime_remote_players_empty_and_overflow(self):
        empty = RemotePlayersPacket(seq=1, players=())
        self.assertEqual(decode_remote_players(encode_remote_players(empty)), empty)
        too_many = RemotePlayersPacket(
            seq=2,
            players=tuple(
                RemotePlayerRecord(x=i, y=i, facing=0, state=1)
                for i in range(REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED + 1)
            ),
        )
        with self.assertRaises(PacketError):
            encode_remote_players(too_many)
        self.assertGreaterEqual(REALTIME_REMOTE_PLAYERS_LARGE_CAPACITY, 12)
        self.assertNotIn(RealtimeType.REMOTE_PLAYERS, REALTIME_SMALL_TYPES)

    def test_realtime_resync_request_round_trip(self):
        original = ResyncRequestPacket(
            seq=21, origin_x=31, origin_y=7, fill_origin_x=4, fill_origin_y=9, rows_have=0xA5F1C3
        )
        encoded = encode_resync_request(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 15)
        self.assertEqual(_normalize_realtime(encoded)[6], 31)
        self.assertEqual(_normalize_realtime(encoded)[7], 7)
        self.assertEqual(_normalize_realtime(encoded)[8], 4)
        self.assertEqual(_normalize_realtime(encoded)[9], 9)
        self.assertEqual(_normalize_realtime(encoded)[10], 0xC3)
        self.assertEqual(_normalize_realtime(encoded)[11], 0xF1)
        self.assertEqual(_normalize_realtime(encoded)[12], 0xA5)
        self.assertEqual(decode_resync_request(encoded), original)

    def test_realtime_resync_request_zero_bitmap_decodes_as_full_fill(self):
        # An old client leaves the NACK bytes zero: decode must yield
        # rows_have == 0 so the server falls back to a full 24-row fill.
        legacy = ResyncRequestPacket(seq=3, origin_x=200, origin_y=0)
        decoded = decode_resync_request(encode_resync_request(legacy))
        self.assertEqual(decoded.rows_have, 0)
        self.assertEqual(decoded.fill_origin_x, 0)
        self.assertEqual(decoded.fill_origin_y, 0)

    def test_realtime_map_ready_round_trip(self):
        original = MapReadyPacket(seq=22, map_id=2, origin_x=33, origin_y=9)
        encoded = encode_map_ready(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 19)
        self.assertEqual(_normalize_realtime(encoded)[6], 2)
        self.assertEqual(_normalize_realtime(encoded)[7], 33)
        self.assertEqual(_normalize_realtime(encoded)[8], 9)
        self.assertEqual(decode_map_ready(encoded), original)

    def test_realtime_type_size_classes_are_pinned(self):
        samples = {
            RealtimeType.PLAYER_STATE: encode_player_state(PlayerStatePacket(1, 1, 2, 3, 0, 0, 0, 0)),
            RealtimeType.WORLD_STATE: encode_world_state(WorldStatePacket(1, 1, 2, 3, 0, ())),
            RealtimeType.TERRAIN_EDGE: encode_terrain_edge(TerrainEdgePacket(1, 0, 0, 1, 1, b"\x00")),
            RealtimeType.BYE: encode_realtime_bye(1),
            RealtimeType.MAP_CHANGE: encode_map_change(MapChangePacket(1, 0, 1, 2, 0, 0)),
            RealtimeType.ENTITY_DELTA: encode_entity_delta(EntityDeltaPacket(1, ())),
            RealtimeType.HUD_UPDATE: encode_hud_update(HudUpdatePacket(1, 1, 2, 3, 4, 5, 6)),
            RealtimeType.MESSAGE: encode_message(MessagePacket(1, 1, "HI")),
            RealtimeType.QUEST_UPDATE: encode_quest_update(QuestUpdatePacket(1, 1, 2, "HI")),
            RealtimeType.INVENTORY_UPDATE: encode_inventory_update(InventoryUpdatePacket(1, ())),
            RealtimeType.RESPAWN_EVENT: encode_respawn_event(RespawnEventPacket(1, 1, 2, 3)),
            RealtimeType.PLAYER_COMMAND: encode_player_command(PlayerCommandPacket(1, 1, 2)),
            RealtimeType.AUTH: encode_auth(AuthPacket(1, 0x12345678)),
            RealtimeType.REMOTE_PLAYERS: encode_remote_players(RemotePlayersPacket(1, ())),
            RealtimeType.RESYNC_REQUEST: encode_resync_request(ResyncRequestPacket(1, 0, 0)),
            RealtimeType.WINDOW_ROW: encode_window_row(WindowRowPacket(1, 0, 0, 0, bytes(WINDOW_W))),
            RealtimeType.ITEM_DROPS: encode_item_drops(ItemDropsPacket(1, ())),
            RealtimeType.MAP_SUMMARY: encode_map_summary(MapSummaryPacket(1, 0, 0, 0, 1, 1, b"\x00")),
            RealtimeType.MAP_READY: encode_map_ready(MapReadyPacket(1, 0, 0, 0)),
        }
        for packet_type, encoded in samples.items():
            with self.subTest(packet_type=packet_type):
                self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
                raw = _normalize_realtime(encoded)
                self.assertEqual(raw[1], 3)
                self.assertEqual(raw[2], int(packet_type))

    def test_realtime_window_row_round_trip(self):
        original = WindowRowPacket(seq=8, origin_x=40, origin_y=25, row_index=5, tiles=bytes(range(WINDOW_W)))
        encoded = encode_window_row(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(_normalize_realtime(encoded)[2], 16)
        self.assertEqual(_normalize_realtime(encoded)[3], WINDOW_W)
        self.assertEqual(decode_window_row(encoded), original)

    def test_realtime_window_row_rejects_bad_tile_count(self):
        with self.assertRaises(PacketError):
            encode_window_row(WindowRowPacket(seq=1, origin_x=0, origin_y=0, row_index=0, tiles=bytes(8)))

    def test_realtime_sequence_delta_handles_wrap(self):
        self.assertGreater(seq_delta(1, 0), 0)
        self.assertGreater(seq_delta(0, 0xFFFF), 0)
        self.assertLessEqual(seq_delta(7, 7), 0)
        self.assertLess(seq_delta(7, 8), 0)


class RealtimeV3CodecTest(unittest.TestCase):
    def test_crc16_standard_vector(self):
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)
        self.assertEqual(crc16_ccitt(b""), 0xFFFF)

    def test_cobs_round_trips(self):
        vectors = [
            b"",
            b"\x00",
            b"\x00\x00",
            b"\x11\x22\x00\x33",
            b"\x11\x00\x00\x00",
            bytes(range(256)),
            bytes(62),
            bytes(range(1, 63)),
        ]
        for data in vectors:
            with self.subTest(data=data[:8]):
                encoded = encode_cobs(data)
                self.assertNotIn(0, encoded)
                self.assertEqual(decode_cobs(encoded), data)

    def test_cobs_standard_vectors(self):
        self.assertEqual(encode_cobs(b"\x00"), b"\x01\x01")
        self.assertEqual(encode_cobs(b"\x11\x22\x00\x33"), b"\x03\x11\x22\x02\x33")
        self.assertEqual(encode_cobs(b"\x11\x22\x33\x44"), b"\x05\x11\x22\x33\x44")

    def test_frame_rejects_bad_version_length_and_crc(self):
        good = _normalize_realtime(encode_auth(AuthPacket(seq=1, token=42)))
        bad_version = bytearray(good)
        bad_version[1] = 2
        with self.assertRaises(PacketError):
            _normalize_realtime(bytes(bad_version))
        bad_length = bytearray(good)
        bad_length[0] += 1
        with self.assertRaises(PacketError):
            _normalize_realtime(bytes(bad_length))
        bad_crc = bytearray(good)
        bad_crc[-1] ^= 0xFF
        with self.assertRaises(PacketError):
            _normalize_realtime(bytes(bad_crc))

    def test_max_payload_fits_and_oversize_rejected(self):
        # MAP_SUMMARY at the full 8x6 zone grid is exactly the 54-byte max.
        cells = bytes(range(1, 49))
        encoded = encode_map_summary(MapSummaryPacket(1, 0, 0, 0, 8, 6, cells))
        raw = _normalize_realtime(encoded)
        self.assertEqual(raw[0], 54)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(decode_map_summary(encoded).cells, cells)


class RealtimeV3StreamRecoveryTest(unittest.TestCase):
    def _frames(self, count=5):
        return [encode_auth(AuthPacket(seq=i + 1, token=0x1000 + i)) for i in range(count)]

    def _decode_all(self, decoder, wire, chunk=None):
        frames = []
        if chunk is None:
            frames.extend(decoder.feed(wire))
        else:
            for i in range(0, len(wire), chunk):
                frames.extend(decoder.feed(wire[i : i + chunk]))
        return frames

    def _tokens(self, frames):
        return [decode_auth(frame).token for frame in frames]

    def test_intact_stream_all_chunk_sizes(self):
        wire = b"".join(self._frames())
        for chunk in (1, 2, 7, None):
            decoder = RealtimeFrameDecoder()
            frames = self._decode_all(decoder, wire, chunk)
            self.assertEqual(self._tokens(frames), [0x1000 + i for i in range(5)])
            self.assertEqual(decoder.bad_frames, 0)

    def test_recovery_after_single_byte_damage(self):
        base = self._frames()
        for description, mutate in (
            ("delete", lambda w: w[:1] + w[2:]),
            ("insert", lambda w: w[:1] + b"\x55" + w[1:]),
            ("flip", lambda w: bytes((w[0] ^ 0x20,)) + w[1:]),
        ):
            with self.subTest(damage=description):
                damaged = mutate(base[2])
                wire = b"".join(base[:2] + [damaged] + base[3:])
                decoder = RealtimeFrameDecoder()
                frames = self._decode_all(decoder, wire, chunk=3)
                tokens = self._tokens(frames)
                self.assertNotIn(0x1002, tokens)
                for token in (0x1000, 0x1001, 0x1003, 0x1004):
                    self.assertIn(token, tokens)
                self.assertEqual(decoder.bad_frames, 1)

    def test_recovery_after_lost_delimiter_merges_two_frames(self):
        base = self._frames()
        merged = base[2][:-1] + base[3]  # drop frame 2's delimiter
        wire = b"".join(base[:2] + [merged] + base[4:])
        decoder = RealtimeFrameDecoder()
        tokens = self._tokens(self._decode_all(decoder, wire, chunk=5))
        # The first frame of the merged pair is prefix-valid (its declared
        # length and CRC are intact) and is recovered; the second is the
        # merge's casualty. Later frames decode normally.
        self.assertEqual(tokens, [0x1000, 0x1001, 0x1002, 0x1004])

    def test_extra_delimiters_and_whole_frame_loss(self):
        base = self._frames()
        wire = b"\x00\x00" + base[0] + b"\x00\x00\x00" + b"".join(base[2:])
        decoder = RealtimeFrameDecoder()
        tokens = self._tokens(self._decode_all(decoder, wire, chunk=1))
        self.assertEqual(tokens, [0x1000, 0x1002, 0x1003, 0x1004])
        self.assertEqual(decoder.bad_frames, 0)

    def test_oversized_encoded_frame_discards_until_delimiter(self):
        decoder = RealtimeFrameDecoder()
        frames = decoder.feed(b"\x01" * 200 + b"\x00" + self._frames(1)[0])
        self.assertEqual(self._tokens(frames), [0x1000])
        self.assertEqual(decoder.overflows, 1)


if __name__ == "__main__":
    unittest.main()
