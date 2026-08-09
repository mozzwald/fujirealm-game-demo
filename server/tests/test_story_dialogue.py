"""Phase 57: generic NPC dispatch and server-driven paged dialogue."""

import types
import unittest

import server.game as game_module
from server.entities import (
    ENTITY_NPC,
    NPC_DANIEL,
    NPC_GRIX,
    NPC_LUCIAN,
    NPC_NERISSA,
    NPC_WILHELM,
)
from server.game import (
    DIALOGUE_PAGE_MAX_CHARS,
    DIALOGUE_RESEND_INTERVAL_TICKS,
    NERISSA_TILE,
    PLAYER_DIALOGUE_DECLINE_BUTTON,
    GameState,
    dialogue_page_chunks,
    paginate_dialogue_text,
)
from server.items import ITEM_OIL_SAMPLE, ITEM_RUST_SAMPLE, ITEM_STICKS
from server.protocol import REALTIME_DIALOGUE_MAX_TEXT
from server.protocol import (
    DIALOGUE_FLAG_ACK_ONLY,
    DIALOGUE_FLAG_CHUNK_END,
    DIALOGUE_FLAG_LAST_PAGE,
    DIALOGUE_FLAG_QUEST_OFFER,
)
from server.quests import (
    QUEST_BLACKWATER_BITE,
    QUEST_LIVING_MUD,
    QUEST_NONE,
    QUEST_REPAIR_BRIDGE,
    QUEST_ROAD_TROUBLE,
    QUEST_STATE_ACTIVE,
    QUEST_STATE_COMPLETE,
    QUEST_STATE_NOT_STARTED,
    QUEST_STATE_READY_TO_TURN_IN,
    STORY_STAGE_BEYOND_ROAD,
    STORY_STAGE_BLACKWATER,
    STORY_STAGE_BRIDGE,
    STORY_STAGE_COMPLETE,
    STORY_STAGE_GOBLIN_WARNED,
    STORY_STAGE_LIVING_MUD,
    STORY_STAGE_RETURN_NERISSA,
    STORY_STAGE_WARDEN_KEY,
    STORY_STAGE_WELCOME,
    WILLOWCROSS_SAVED_REWARD_GOLD,
    WILLOWCROSS_SAVED_REWARD_XP,
)


def _pickup(counter, buttons=0):
    return types.SimpleNamespace(pickup_counter=counter, buttons=buttons)


class NpcDispatchTest(unittest.TestCase):

    def _finish_dialogue(self, limit=16):
        """Advance the open dialogue until it closes.

        Page counts are content, not behaviour: adding a line to an NPC's
        script should not break a test about what happens when the
        conversation ends.
        """
        for _ in range(limit):
            if self.player.active_dialogue is None:
                return
            self.game.advance_dialogue(self.player)
        raise AssertionError("dialogue did not close")

    def setUp(self):
        self.game = GameState()
        self.token = 1
        self.player = self.game.player_for(self.token)
        self.player.map_id = 0
        self.player.x, self.player.y = 30, 30

    def _place(self, subtype, dx=1, dy=0):
        return self.game.spawn_named_npc(subtype, 0, self.player.x + dx, self.player.y + dy)

    def _patch_bridge_layout(self):
        original = (
            game_module.WILHELM_POS,
            game_module.WILHELM_BRIDGE_DESTINATION,
            game_module.WILHELM_ESCORT_PATH,
            game_module.BRIDGE_DEFENSE_REGION,
        )
        game_module.WILHELM_POS = (31, 30)
        game_module.WILHELM_BRIDGE_DESTINATION = (0, 33, 30)
        game_module.WILHELM_ESCORT_PATH = ((31, 30), (32, 30), (33, 30))
        game_module.BRIDGE_DEFENSE_REGION = (0, 30, 29, 34, 31)
        self.addCleanup(self._restore_bridge_layout, original)

    def _restore_bridge_layout(self, original):
        (
            game_module.WILHELM_POS,
            game_module.WILHELM_BRIDGE_DESTINATION,
            game_module.WILHELM_ESCORT_PATH,
            game_module.BRIDGE_DEFENSE_REGION,
        ) = original

    def test_lucian_offers_blackwater_bite_through_a_dialogue_modal(self):
        self._place(NPC_LUCIAN)
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertIsNotNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_LUCIAN_BLACKWATER_OFFER)
        self.game.advance_dialogue(self.player)
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_quest_id, QUEST_BLACKWATER_BITE)
        self.assertEqual(self.player.quest_state, QUEST_STATE_ACTIVE)
        self.assertEqual(self.player.story_stage, STORY_STAGE_BLACKWATER)

    def test_lucian_offers_living_mud_after_blackwater_bite_is_ready(self):
        self._place(NPC_LUCIAN)
        self.player.active_quest_id = QUEST_BLACKWATER_BITE
        self.player.quest_state = QUEST_STATE_READY_TO_TURN_IN
        self.player.story_stage = STORY_STAGE_BLACKWATER
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_LUCIAN_LIVING_MUD_OFFER)
        self.game.advance_dialogue(self.player)
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_quest_id, QUEST_LIVING_MUD)
        self.assertEqual(self.player.quest_state, QUEST_STATE_ACTIVE)
        self.assertEqual(self.player.story_stage, STORY_STAGE_LIVING_MUD)

    def test_lucian_redirects_completed_samples_to_nerissa(self):
        self._place(NPC_LUCIAN)
        self.player.active_quest_id = QUEST_LIVING_MUD
        self.player.quest_state = QUEST_STATE_READY_TO_TURN_IN
        self.player.story_stage = STORY_STAGE_LIVING_MUD
        self.player.story_step = 0
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_LUCIAN_SAMPLES_REDIRECT)
        self.game.advance_dialogue(self.player)
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertEqual(self.player.story_step, 1)

    def test_nerissa_completes_living_mud_and_points_to_the_outpost(self):
        self._place(NPC_NERISSA)
        self.player.active_quest_id = QUEST_LIVING_MUD
        self.player.quest_state = QUEST_STATE_READY_TO_TURN_IN
        self.player.story_stage = STORY_STAGE_LIVING_MUD
        self.player.story_step = 1
        self.assertTrue(self.player.inventory.add_item(ITEM_OIL_SAMPLE, 2))
        self.assertTrue(self.player.inventory.add_item(ITEM_RUST_SAMPLE, 2))
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_NERISSA_SAMPLES)
        self._finish_dialogue()
        self.assertIsNone(self.player.active_dialogue)
        # Living Mud is the last quest the scalar active_quest_id system
        # tracks, so it's cleared back to NONE/NOT_STARTED on completion
        # instead of leaving "Living Mud done" as a permanent HUD line.
        self.assertEqual(self.player.active_quest_id, QUEST_NONE)
        self.assertEqual(self.player.quest_state, QUEST_STATE_NOT_STARTED)
        self.assertEqual(self.player.story_stage, STORY_STAGE_GOBLIN_WARNED)
        self.assertEqual(self.player.inventory.count_item(ITEM_OIL_SAMPLE), 0)
        self.assertEqual(self.player.inventory.count_item(ITEM_RUST_SAMPLE), 0)

    def test_daniel_offers_save_my_orchard_through_a_dialogue_modal(self):
        self._place(NPC_DANIEL)
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertIsNotNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_DANIEL_OFFER)
        self.assertEqual(self.player.pending_quest_offer_id, QUEST_ROAD_TROUBLE)
        self.game.advance_dialogue(self.player)
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_quest_id, QUEST_ROAD_TROUBLE)
        self.assertEqual(self.player.quest_state, QUEST_STATE_ACTIVE)

    def test_nerissa_intro_advances_story_stage_when_dialogue_closes(self):
        self._place(NPC_NERISSA)
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertIsNotNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_NERISSA_INTRO)
        self.game.advance_dialogue(self.player)
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertEqual(self.player.story_stage, STORY_STAGE_WELCOME)

    def test_nerissa_post_bridge_dialogue_advances_to_lucian_stage(self):
        self._place(NPC_NERISSA)
        self.player.bridge_repaired = True
        self.player.story_stage = STORY_STAGE_BRIDGE
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_NERISSA_POST_BRIDGE)
        self.game.advance_dialogue(self.player)
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertEqual(self.player.story_stage, STORY_STAGE_BEYOND_ROAD)

    def test_nerissa_ending_unlocks_pvp_exactly_once(self):
        self._place(NPC_NERISSA)
        self.player.story_stage = STORY_STAGE_RETURN_NERISSA
        start_xp = self.player.xp
        start_gold = self.player.gold

        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_NERISSA_ENDING)
        for _ in range(len(self.player.active_dialogue.pages)):
            self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertTrue(self.player.pvp_unlocked)
        self.assertEqual(self.player.story_stage, STORY_STAGE_COMPLETE)
        self.assertEqual(self.player.xp, start_xp + WILLOWCROSS_SAVED_REWARD_XP)
        self.assertEqual(self.player.gold, start_gold + WILLOWCROSS_SAVED_REWARD_GOLD)

        # The ending is safe to review again -- no repeat reward.
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_NERISSA_ENDING)
        for _ in range(len(self.player.active_dialogue.pages)):
            self.game.advance_dialogue(self.player)
        self.assertEqual(self.player.xp, start_xp + WILLOWCROSS_SAVED_REWARD_XP)
        self.assertEqual(self.player.gold, start_gold + WILLOWCROSS_SAVED_REWARD_GOLD)

    def test_grix_is_only_small_talk_before_the_goblin_warned_stage(self):
        self._place(NPC_GRIX)
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertIsNone(self.player.active_dialogue)

    def test_grix_explains_the_warden_key_at_the_goblin_warned_stage(self):
        self._place(NPC_GRIX)
        self.player.story_stage = STORY_STAGE_GOBLIN_WARNED
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertIsNotNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_GRIX_EXPLAIN)
        for _ in range(len(self.player.active_dialogue.pages)):
            self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        self.assertEqual(self.player.story_stage, STORY_STAGE_WARDEN_KEY)

    def test_wilhelm_starts_bridge_repair_when_player_has_sticks(self):
        self._patch_bridge_layout()
        self.player.x, self.player.y = 30, 30
        self.game.entities = {eid: e for eid, e in self.game.entities.items() if e.kind != ENTITY_NPC}
        self.game.named_npc_ids.clear()
        self._place(NPC_WILHELM)
        self.player.active_quest_id = QUEST_ROAD_TROUBLE
        self.player.quest_state = QUEST_STATE_COMPLETE
        self.assertTrue(self.player.inventory.add_item(ITEM_STICKS, 2))
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertIsNotNone(self.player.active_dialogue)
        self.assertEqual(self.player.active_dialogue.dialogue_id, game_module.story.DLG_WILHELM_BRIDGE_START)
        self.game.advance_dialogue(self.player)
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)
        encounter = self.game.get_scripted_encounter(self.token, "bridge_repair")
        self.assertIsNotNone(encounter)
        self.assertEqual(encounter.phase, game_module.ENCOUNTER_ESCORTING)
        self.assertTrue(self.player.pending_terrain_resync)
        self.assertTrue(self.player.bridge_materials_staged)
        self.assertEqual(self.player.inventory.count_item(ITEM_STICKS), 0)
        # Repair the Bridge is its own quest, started fresh here.
        self.assertEqual(self.player.active_quest_id, QUEST_REPAIR_BRIDGE)
        self.assertEqual(self.player.quest_state, QUEST_STATE_ACTIVE)

    def test_nearest_adjacent_npc_is_deterministic(self):
        # Two NPCs, both adjacent: the nearer (or lower id on a tie) wins.
        first = self._place(NPC_NERISSA, dx=1, dy=0)
        self._place(NPC_DANIEL, dx=0, dy=1)
        npc = self.game._nearest_adjacent_npc(self.player)
        self.assertEqual(npc.entity_id, first)  # equal distance -> lower id

    def test_non_adjacent_npc_is_ignored(self):
        self._place(NPC_NERISSA, dx=3, dy=0)
        self.assertFalse(self.game.interact_with_adjacent_npc(self.token))

    def test_daniel_still_offers_quest_via_the_default_map_spawn(self):
        # The default game already spawned Daniel; stand next to it.
        farmer = self.game.entities[self.game.farmer_entity_id]
        self.player.map_id = farmer.map_id
        self.player.x, self.player.y = farmer.x - 1, farmer.y
        self.assertTrue(self.game.interact_with_adjacent_npc(self.token))
        self.assertEqual(self.player.pending_quest_offer_id, QUEST_ROAD_TROUBLE)
        self.assertIsNotNone(self.player.active_dialogue)

    def test_static_overlay_paints_named_npc_tile(self):
        self._place(NPC_NERISSA, dx=1, dy=0)
        base = bytes(64)
        painted = self.game._tiles_with_static_npcs(self.player, self.player.x, self.player.y - 1, 8, 8, base)
        self.assertIn(NERISSA_TILE, painted)


class DialoguePaginationTest(unittest.TestCase):
    def test_long_paragraph_splits_into_bounded_word_display_pages(self):
        text = " ".join(f"word{i:02}" for i in range(40))  # ~240 chars, > one page
        pages = paginate_dialogue_text([text])
        self.assertGreater(len(pages), 1)
        for page in pages:
            self.assertLessEqual(len(page), DIALOGUE_PAGE_MAX_CHARS)
            self.assertFalse(page.startswith(" ") or page.endswith(" "))
        # No word is broken across pages (rejoining with spaces == original).
        self.assertEqual(" ".join(pages).split(), text.split())

    def test_each_paragraph_starts_a_fresh_page(self):
        pages = paginate_dialogue_text(["Short one.", "Short two."])
        self.assertEqual(pages, ("Short one.", "Short two."))

    def test_overlong_word_is_hard_split_to_page_width(self):
        word = "X" * (DIALOGUE_PAGE_MAX_CHARS + 10)
        pages = paginate_dialogue_text([word])
        self.assertTrue(all(len(p) <= DIALOGUE_PAGE_MAX_CHARS for p in pages))
        self.assertEqual("".join(pages), word)

    def test_display_page_splits_into_bounded_chunks(self):
        page = "A" * DIALOGUE_PAGE_MAX_CHARS
        chunks = dialogue_page_chunks(page)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), REALTIME_DIALOGUE_MAX_TEXT)
        self.assertEqual("".join(chunks), page)  # lossless reassembly


class DialoguePagingTest(unittest.TestCase):
    def setUp(self):
        self.game = GameState()
        self.token = 1
        self.player = self.game.player_for(self.token)

    def test_pages_advance_only_on_ack_and_carry_flags(self):
        self.game.open_dialogue(self.player, 5, NPC_GRIX, ("PAGE ONE", "PAGE TWO", "PAGE THREE"))
        p0 = self.game.dialogue_page_to_send(1, self.token)
        self.assertEqual((p0.page_index, p0.page_count), (0, 3))
        # Single-chunk page: CHUNK_END set, but not the final-page flags.
        self.assertTrue(p0.flags & DIALOGUE_FLAG_CHUNK_END)
        self.assertFalse(p0.flags & DIALOGUE_FLAG_LAST_PAGE)
        # No new page until acked.
        self.assertIsNone(self.game.dialogue_page_to_send(2, self.token))
        self.game.advance_dialogue(self.player)
        p1 = self.game.dialogue_page_to_send(3, self.token)
        self.assertEqual(p1.page_index, 1)
        self.game.advance_dialogue(self.player)
        p2 = self.game.dialogue_page_to_send(4, self.token)
        self.assertTrue(p2.flags & DIALOGUE_FLAG_LAST_PAGE)
        self.assertTrue(p2.flags & DIALOGUE_FLAG_ACK_ONLY)
        # Ack the final page -> dialogue closes.
        self.game.advance_dialogue(self.player)
        self.assertIsNone(self.player.active_dialogue)

    def test_multi_chunk_page_streams_in_order_with_chunk_end(self):
        long_page = "A" * DIALOGUE_PAGE_MAX_CHARS  # forces multiple chunks
        self.game.open_dialogue(self.player, 1, NPC_NERISSA, [long_page])
        chunks = dialogue_page_chunks(long_page)
        self.assertGreater(len(chunks), 1)
        seen = []
        for i in range(len(chunks)):
            pkt = self.game.dialogue_page_to_send(i + 1, self.token)
            self.assertIsNotNone(pkt)
            self.assertEqual(pkt.chunk_index, i)
            seen.append(pkt.text)
            is_last = i == len(chunks) - 1
            self.assertEqual(bool(pkt.flags & DIALOGUE_FLAG_CHUNK_END), is_last)
        # Reassembled chunks reproduce the page; no further chunk until acked.
        self.assertEqual("".join(seen), long_page)
        self.assertIsNone(self.game.dialogue_page_to_send(99, self.token))

    def test_retransmit_of_multi_chunk_final_page_restarts_at_chunk_zero_unflagged(self):
        # Client contract this locks in: a page retransmit always restarts
        # at chunk 0, and only the chunk actually carrying CHUNK_END may
        # ever carry LAST_PAGE. A multi-chunk final page's retransmitted
        # chunk 0 must NOT carry LAST_PAGE, even though the page as a whole
        # is the dialogue's last -- the Atari client's chunk reassembly
        # must not treat a mid-stream chunk's flags as authoritative (see
        # fujirealm.asm's netstream_apply_dialogue_page, which commits
        # dialogue_flags only on the CHUNK_END chunk for exactly this
        # reason -- a client that committed flags per-chunk would see
        # LAST_PAGE flicker off during every retransmit of this page).
        long_page = "A" * DIALOGUE_PAGE_MAX_CHARS
        self.game.open_dialogue(self.player, 1, NPC_NERISSA, ("FIRST", long_page))
        self.game.dialogue_page_to_send(1, self.token)
        self.game.advance_dialogue(self.player)  # move to the long final page
        chunks = dialogue_page_chunks(long_page)
        self.assertGreater(len(chunks), 1, "test requires a multi-chunk final page")
        for i in range(len(chunks)):
            pkt = self.game.dialogue_page_to_send(i + 10, self.token)
            self.assertEqual(pkt.chunk_index, i)
        last_sent = self.game.dialogue_page_to_send(99, self.token)
        self.assertIsNone(last_sent)  # fully sent, waiting on the ack
        retransmit_chunk0 = None
        for tick in range(DIALOGUE_RESEND_INTERVAL_TICKS + 1):
            retransmit_chunk0 = self.game.dialogue_page_to_send(100 + tick, self.token)
            if retransmit_chunk0 is not None:
                break
        self.assertIsNotNone(retransmit_chunk0, "resend timer never fired")
        self.assertEqual(retransmit_chunk0.chunk_index, 0)
        self.assertFalse(retransmit_chunk0.flags & DIALOGUE_FLAG_CHUNK_END)
        self.assertFalse(retransmit_chunk0.flags & DIALOGUE_FLAG_LAST_PAGE)

    def test_reopen_while_active_does_not_restart(self):
        self.game.open_dialogue(self.player, 1, NPC_NERISSA, ("A", "B"))
        self.game.advance_dialogue(self.player)  # now on page 1
        self.game.open_dialogue(self.player, 1, NPC_NERISSA, ("A", "B"))
        self.assertEqual(self.player.active_dialogue.index, 1)  # unchanged

    def test_bounded_retransmit_until_ack(self):
        self.game.open_dialogue(self.player, 1, NPC_NERISSA, ("ONLY PAGE",))
        self.assertIsNotNone(self.game.dialogue_page_to_send(1, self.token))
        # Nothing for the next (interval-1) ticks...
        for _ in range(DIALOGUE_RESEND_INTERVAL_TICKS - 1):
            self.assertIsNone(self.game.dialogue_page_to_send(2, self.token))
        # ...then a retransmit fires.
        self.assertIsNotNone(self.game.dialogue_page_to_send(3, self.token))

    def test_pickup_bump_advances_open_dialogue(self):
        self.game.open_dialogue(self.player, 1, NPC_NERISSA, ("A", "B"))
        self.player.last_pickup_counter = 0
        self.game._apply_player_state_pickup(self.player, _pickup(1))
        self.assertEqual(self.player.active_dialogue.index, 1)

    def test_quest_offer_accept_and_decline(self):
        # Accept path: final quest-offer ack accepts the matching pending offer.
        self.player.pending_quest_offer_id = QUEST_ROAD_TROUBLE
        self.game.open_dialogue(self.player, 2, NPC_DANIEL, ("OFFER",), quest_offer_id=QUEST_ROAD_TROUBLE)
        last = self.game.dialogue_page_to_send(1, self.token)
        self.assertTrue(last.flags & DIALOGUE_FLAG_QUEST_OFFER)
        self.player.last_pickup_counter = 0
        self.game._apply_player_state_pickup(self.player, _pickup(1, buttons=0))
        self.assertEqual(self.player.active_quest_id, QUEST_ROAD_TROUBLE)
        self.assertEqual(self.player.quest_state, QUEST_STATE_ACTIVE)

    def test_quest_offer_decline_does_not_accept(self):
        self.player.pending_quest_offer_id = QUEST_ROAD_TROUBLE
        self.game.open_dialogue(self.player, 2, NPC_DANIEL, ("OFFER",), quest_offer_id=QUEST_ROAD_TROUBLE)
        self.player.last_pickup_counter = 0
        self.game._apply_player_state_pickup(
            self.player, _pickup(1, buttons=PLAYER_DIALOGUE_DECLINE_BUTTON)
        )
        self.assertEqual(self.player.active_quest_id, 0)
        self.assertIsNone(self.player.active_dialogue)


if __name__ == "__main__":
    unittest.main()
