import unittest

from server.protocol import (
    ENTITY_ENEMY,
    ENTITY_PLAYER,
    MAP_OVERWORLD,
    MAP_STARTER_CAVE,
    PALETTE_CAVE,
    PALETTE_OVERWORLD,
    REALTIME_MAGIC,
    REALTIME_MAX_ENTITY_DELTAS,
    REALTIME_PACKET_BYTES,
    REALTIME_PATTERN,
    REALTIME_VERSION,
    TILESET_OVERWORLD,
    TILESET_CAVE,
    DIALOGUE_FLAG_LAST_PAGE,
    DIALOGUE_FLAG_QUEST_OFFER,
    REALTIME_DIALOGUE_MAX_TEXT,
    DialoguePagePacket,
    EntityDeltaPacket,
    EntityDeltaRecord,
    HudUpdatePacket,
    InventoryUpdatePacket,
    MapChangePacket,
    MessagePacket,
    PacketError,
    PlayerCommandPacket,
    PlayerCommandType,
    QuestUpdatePacket,
    RealtimeType,
    RespawnEventPacket,
    decode_dialogue_page,
    decode_entity_delta,
    decode_hud_update,
    decode_inventory_update,
    decode_map_change,
    decode_message,
    decode_player_command,
    decode_quest_update,
    decode_respawn_event,
    encode_dialogue_page,
    encode_entity_delta,
    encode_hud_update,
    encode_inventory_update,
    encode_map_change,
    encode_message,
    encode_player_command,
    encode_quest_update,
    encode_respawn_event,
    realtime_packet_size,
)


class RpgProtocolTest(unittest.TestCase):
    def assert_fixed_round_trip(self, original, encode, decode):
        encoded = encode(original)
        self.assertLessEqual(len(encoded), REALTIME_PACKET_BYTES)
        self.assertEqual(decode(encoded), original)

    def test_map_change_round_trip(self):
        self.assert_fixed_round_trip(
            MapChangePacket(
                seq=7,
                map_id=MAP_OVERWORLD,
                spawn_x=12,
                spawn_y=13,
                tileset_id=TILESET_OVERWORLD,
                palette_id=PALETTE_OVERWORLD,
                flags=1,
            ),
            encode_map_change,
            decode_map_change,
        )

    def test_cave_map_change_round_trip(self):
        self.assert_fixed_round_trip(
            MapChangePacket(
                seq=8,
                map_id=MAP_STARTER_CAVE,
                spawn_x=8,
                spawn_y=10,
                tileset_id=TILESET_CAVE,
                palette_id=PALETTE_CAVE,
                flags=1,
            ),
            encode_map_change,
            decode_map_change,
        )

    def test_entity_delta_round_trip_and_max_count(self):
        records = tuple(
            EntityDeltaRecord(
                entity_id=index,
                entity_type=ENTITY_PLAYER if index == 0 else ENTITY_ENEMY,
                x=10 + index,
                y=20 + index,
                tile_id=30 + index,
                hp=5,
                flags=index & 1,
                state=2,
            )
            for index in range(REALTIME_MAX_ENTITY_DELTAS)
        )
        self.assert_fixed_round_trip(
            EntityDeltaPacket(seq=9, records=records),
            encode_entity_delta,
            decode_entity_delta,
        )
        too_many = EntityDeltaPacket(
            seq=10,
            records=records + (EntityDeltaRecord(99, ENTITY_ENEMY, 1, 2, 3, 4, 5, 6),),
        )
        with self.assertRaises(PacketError):
            encode_entity_delta(too_many)

    def test_hud_update_round_trip(self):
        self.assert_fixed_round_trip(
            HudUpdatePacket(seq=11, hp=6, max_hp=9, level=3, xp=1234, xp_next=2000, gold=77, flags=4, pvp_kills=9999),
            encode_hud_update,
            decode_hud_update,
        )

    def test_message_round_trip(self):
        self.assert_fixed_round_trip(
            MessagePacket(seq=12, message_id=44, text="FARMER DAN SAYS THANKS"),
            encode_message,
            decode_message,
        )

    def test_quest_inventory_respawn_round_trips(self):
        self.assert_fixed_round_trip(
            QuestUpdatePacket(seq=13, quest_id=2, state=1, text="ROAD TROUBLE 1/3"),
            encode_quest_update,
            decode_quest_update,
        )
        self.assert_fixed_round_trip(
            InventoryUpdatePacket(seq=14, slots=((2, 3), (3, 1)), gold=9),
            encode_inventory_update,
            decode_inventory_update,
        )
        self.assert_fixed_round_trip(
            RespawnEventPacket(seq=15, x=6, y=7, hp=4, flags=1),
            encode_respawn_event,
            decode_respawn_event,
        )

    def test_dialogue_page_round_trip(self):
        # Text is uppercased by the sanitizer; pass uppercase for an exact match.
        self.assert_fixed_round_trip(
            DialoguePagePacket(
                seq=21, dialogue_id=3, speaker_id=1, page_index=0, page_count=3,
                flags=DIALOGUE_FLAG_QUEST_OFFER, text="THE DAM BELOW IS FLOODING WILLOWCROSS.",
            ),
            encode_dialogue_page,
            decode_dialogue_page,
        )
        # A page filled to the class maximum still fits the 64-byte frame.
        self.assert_fixed_round_trip(
            DialoguePagePacket(
                seq=22, dialogue_id=9, speaker_id=7, page_index=2, page_count=3,
                flags=DIALOGUE_FLAG_LAST_PAGE, text="X" * REALTIME_DIALOGUE_MAX_TEXT,
            ),
            encode_dialogue_page,
            decode_dialogue_page,
        )

    def test_dialogue_page_rejects_wrong_type(self):
        encoded = encode_dialogue_page(DialoguePagePacket(23, 1, 1, 0, 1, 0, "HI"))
        with self.assertRaises(PacketError):
            decode_message(bytes(encoded))

    def test_player_command_round_trip(self):
        self.assert_fixed_round_trip(
            PlayerCommandPacket(
                seq=16,
                command=PlayerCommandType.PICKUP,
                direction=2,
                arg0=3,
                arg1=4,
                last_server_seq=15,
            ),
            encode_player_command,
            decode_player_command,
        )

    def test_bad_realtime_headers_are_rejected(self):
        # v3: any single damaged wire byte must fail COBS/CRC validation.
        encoded = bytearray(encode_message(MessagePacket(seq=17, message_id=1)))
        for offset in range(len(encoded) - 1):
            damaged = bytearray(encoded)
            damaged[offset] ^= 0x5A
            with self.subTest(offset=offset):
                with self.assertRaises(PacketError):
                    decode_message(bytes(damaged))

    def test_wrong_realtime_type_is_rejected(self):
        encoded = encode_message(MessagePacket(seq=18, message_id=1))
        with self.assertRaises(PacketError):
            decode_map_change(encoded)

    def test_rpg_realtime_type_values_are_stable(self):
        self.assertEqual(RealtimeType.MAP_CHANGE, 5)
        self.assertEqual(RealtimeType.ENTITY_DELTA, 6)
        self.assertEqual(RealtimeType.HUD_UPDATE, 7)
        self.assertEqual(RealtimeType.MESSAGE, 8)
        self.assertEqual(RealtimeType.QUEST_UPDATE, 9)
        self.assertEqual(RealtimeType.INVENTORY_UPDATE, 10)
        self.assertEqual(RealtimeType.RESPAWN_EVENT, 11)
        self.assertEqual(RealtimeType.PLAYER_COMMAND, 12)
        self.assertEqual(RealtimeType.DIALOGUE_PAGE, 24)


if __name__ == "__main__":
    unittest.main()
