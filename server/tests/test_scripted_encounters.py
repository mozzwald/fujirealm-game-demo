"""Phase 59: player-owned entities and generic scripted encounters."""

import unittest

import server.game as game_module
from server.encounters import (
    ENCOUNTER_ACTIVE,
    ENCOUNTER_ESCORTING,
    ENCOUNTER_FAILED,
    ENCOUNTER_INACTIVE,
    ENCOUNTER_SUCCEEDED,
    EncounterRegion,
)
from server.entities import (
    ENEMY_BEAVER,
    ENTITY_FLAG_BLOCKING,
    ENTITY_FLAG_NAMED,
    ENTITY_FLAG_PERSONAL,
    ENTITY_FLAG_VISIBLE,
    ENTITY_FLAG_WORKING,
    ENTITY_NPC,
    NPC_WILHELM,
)
from server.game import (
    DYNAMIC_WILHELM_SNAPSHOT_KIND,
    DYNAMIC_WILHELM_WORKING_SNAPSHOT_KIND,
    GameState,
    PlayerState,
    deserialize_player_state,
    serialize_player_state,
)
from server.items import ITEM_STICKS
from server.quests import STORY_STAGE_BRIDGE
from server.world import MAP_OVERWORLD, World


TOKEN_A = 1001
TOKEN_B = 2002


class PlayerOwnedEntityTest(unittest.TestCase):
    def setUp(self):
        self.game = GameState(seed=1, world=World(), create_default_player=False)
        self.owner = self.game.add_player(TOKEN_A, x=10, y=10)
        self.helper = self.game.add_player(TOKEN_B, x=12, y=10)

    def test_personal_item_snapshot_and_collection_are_owner_only(self):
        item = self.game.spawn_personal_item(
            self.owner,
            x=11,
            y=10,
            item_id=ITEM_STICKS,
            map_id=MAP_OVERWORLD,
        )
        owner_drops = self.game.item_drops_near(TOKEN_A, 0, 0)
        helper_drops = self.game.item_drops_near(TOKEN_B, 0, 0)
        self.assertEqual([(drop.x, drop.y) for drop in owner_drops], [(11, 10)])
        self.assertEqual(helper_drops, ())
        self.assertFalse(self.game.collect_item(self.helper, item))
        self.assertIn(item.entity_id, self.game.entities)
        self.assertEqual(self.helper.inventory.count_item(ITEM_STICKS), 0)
        self.assertTrue(self.game.collect_item(self.owner, item))
        self.assertNotIn(item.entity_id, self.game.entities)

    def test_owned_encounter_enemy_is_visible_to_helpers_but_only_blocks_owner(self):
        encounter = self.game.create_scripted_encounter(
            self.owner, "defense", map_id=MAP_OVERWORLD
        )
        enemy = self.game.spawn_encounter_enemy(
            encounter, ENEMY_BEAVER, 11, 10, hp=2
        )
        owner_records = self.game.legacy_beaver_snapshots_for_window(0, 0, TOKEN_A)
        helper_records = self.game.legacy_beaver_snapshots_for_window(0, 0, TOKEN_B)
        self.assertIn((enemy.x, enemy.y), [(record.x, record.y) for record in owner_records])
        self.assertIn((enemy.x, enemy.y), [(record.x, record.y) for record in helper_records])
        self.assertTrue(self.game.entity_blocks_player(enemy, self.owner))
        self.assertFalse(self.game.entity_blocks_player(enemy, self.helper))
        world = self.game.world_for(MAP_OVERWORLD)
        self.assertFalse(
            self.game._player_destination_allowed(self.owner, enemy.x, enemy.y, world)
        )
        self.assertTrue(
            self.game._player_destination_allowed(self.helper, enemy.x, enemy.y, world)
        )

    def test_personal_blocking_entity_is_invisible_to_other_players(self):
        trigger = self.game.spawn_entity(
            kind=ENTITY_NPC,
            subtype=NPC_WILHELM,
            map_id=MAP_OVERWORLD,
            x=11,
            y=10,
            flags=(
                ENTITY_FLAG_VISIBLE
                | ENTITY_FLAG_BLOCKING
                | ENTITY_FLAG_NAMED
                | ENTITY_FLAG_PERSONAL
            ),
            owner_id=TOKEN_A,
        )
        self.assertTrue(self.game.entity_visible_to_player(trigger, self.owner))
        self.assertFalse(self.game.entity_visible_to_player(trigger, self.helper))
        self.assertTrue(self.game.entity_blocks_player(trigger, self.owner))
        self.assertFalse(self.game.entity_blocks_player(trigger, self.helper))
        self.assertIn(
            trigger,
            self.game.entities_in_window(
                MAP_OVERWORLD, 0, 0, token=self.owner.token
            ),
        )
        self.assertNotIn(
            trigger,
            self.game.entities_in_window(
                MAP_OVERWORLD, 0, 0, token=self.helper.token
            ),
        )

    def test_helper_kill_records_progress_for_encounter_owner(self):
        encounter = self.game.create_scripted_encounter(
            self.owner, "defense", map_id=MAP_OVERWORLD
        )
        enemy = self.game.spawn_encounter_enemy(
            encounter, ENEMY_BEAVER, 11, 10, hp=1
        )
        self.assertIs(self.game.entity_progress_owner(enemy, self.helper), self.owner)
        self.game._damage_entity(enemy, 1, "ranged", self.helper)
        self.assertEqual(encounter.kill_count, 1)
        self.assertEqual(encounter.last_attacker_token, TOKEN_B)
        self.assertEqual(self.owner.xp, 0)
        self.assertGreater(self.helper.xp, 0)

    def test_owned_enemy_targets_owner_instead_of_nearer_helper(self):
        encounter = self.game.create_scripted_encounter(
            self.owner,
            "targeting",
            map_id=MAP_OVERWORLD,
            region=EncounterRegion(8, 8, 14, 14),
        )
        enemy = self.game.spawn_encounter_enemy(
            encounter, ENEMY_BEAVER, 13, 10, hp=2
        )
        self.assertIs(
            self.game._nearest_live_player(enemy.map_id, enemy.x, enemy.y, enemy),
            self.owner,
        )
        self.owner.x, self.owner.y = 20, 20
        self.game._sync_player_entity(self.owner)
        self.assertIsNone(
            self.game._nearest_live_player(enemy.map_id, enemy.x, enemy.y, enemy)
        )


class ScriptedEncounterTest(unittest.TestCase):
    def setUp(self):
        self.game = GameState(seed=1, world=World(), create_default_player=False)
        self.owner = self.game.add_player(TOKEN_A, x=10, y=10)
        self.helper = self.game.add_player(TOKEN_B, x=12, y=10)

    def _patch_bridge_layout(
        self,
        *,
        start=(10, 10),
        dest=(0, 12, 10),
        path=((10, 10), (11, 10), (12, 10)),
        region=(0, 9, 9, 13, 11),
    ):
        original = (
            game_module.WILHELM_POS,
            game_module.WILHELM_BRIDGE_DESTINATION,
            game_module.WILHELM_ESCORT_PATH,
            game_module.BRIDGE_DEFENSE_REGION,
        )
        game_module.WILHELM_POS = start
        game_module.WILHELM_BRIDGE_DESTINATION = dest
        game_module.WILHELM_ESCORT_PATH = path
        game_module.BRIDGE_DEFENSE_REGION = region
        self.addCleanup(self._restore_bridge_layout, original)

    def _restore_bridge_layout(self, original):
        (
            game_module.WILHELM_POS,
            game_module.WILHELM_BRIDGE_DESTINATION,
            game_module.WILHELM_ESCORT_PATH,
            game_module.BRIDGE_DEFENSE_REGION,
        ) = original

    def test_timer_runs_in_region_pauses_outside_and_fails_after_absence(self):
        encounter = self.game.create_scripted_encounter(
            self.owner,
            "timed",
            map_id=MAP_OVERWORLD,
            region=EncounterRegion(8, 8, 12, 12),
            countdown_ticks=3,
            fail_after_absent_ticks=2,
        )
        self.game.activate_scripted_encounter(encounter)
        self.game._update_scripted_encounters()
        self.assertEqual(encounter.countdown_ticks, 2)
        self.owner.x = 20
        self.owner.y = 20
        self.game._sync_player_entity(self.owner)
        self.game._update_scripted_encounters()
        self.assertEqual(encounter.countdown_ticks, 2)
        self.game._update_scripted_encounters()
        self.assertEqual(encounter.phase, ENCOUNTER_FAILED)
        self.assertEqual(encounter.failure_reason, "owner_absent")

    def test_countdown_success_uses_stable_handoff_callback_and_cleans_entities(self):
        def handoff(game, player, encounter):
            player.story_stage = STORY_STAGE_BRIDGE
            player.story_step = 9

        encounter = self.game.create_scripted_encounter(
            self.owner,
            "success",
            map_id=MAP_OVERWORLD,
            countdown_ticks=1,
            on_success=handoff,
        )
        enemy = self.game.spawn_encounter_enemy(encounter, ENEMY_BEAVER, 11, 10)
        self.game.activate_scripted_encounter(encounter)
        self.game._update_scripted_encounters()
        self.assertEqual(encounter.phase, ENCOUNTER_SUCCEEDED)
        self.assertEqual((self.owner.story_stage, self.owner.story_step), (STORY_STAGE_BRIDGE, 9))
        self.assertNotIn(enemy.entity_id, self.game.entities)

    def test_player_death_fails_encounter_without_changing_stable_story_flags(self):
        self.owner.story_stage = STORY_STAGE_BRIDGE
        self.owner.story_step = 7
        self.owner.bridge_materials_staged = True
        encounter = self.game.create_scripted_encounter(
            self.owner, "death", map_id=MAP_OVERWORLD, countdown_ticks=20
        )
        enemy = self.game.spawn_encounter_enemy(encounter, ENEMY_BEAVER, 11, 10)
        self.game.activate_scripted_encounter(encounter)
        self.game.handle_player_death(self.owner)
        self.assertEqual(encounter.phase, ENCOUNTER_FAILED)
        self.assertEqual(encounter.failure_reason, "owner_died")
        self.assertNotIn(enemy.entity_id, self.game.entities)
        self.assertTrue(self.owner.bridge_materials_staged)
        self.assertFalse(self.owner.bridge_repaired)
        self.assertEqual(self.owner.story_step, 0)

    def test_disconnect_removes_owned_entities_and_resumes_at_stable_retry(self):
        self.owner.story_stage = STORY_STAGE_BRIDGE
        self.owner.story_step = 7
        encounter = self.game.create_scripted_encounter(
            self.owner, "disconnect", map_id=MAP_OVERWORLD
        )
        enemy = self.game.spawn_encounter_enemy(encounter, ENEMY_BEAVER, 11, 10)
        self.game.activate_scripted_encounter(encounter)
        self.game.detach_player(TOKEN_A)
        self.assertNotIn(enemy.entity_id, self.game.entities)
        self.assertIsNone(self.game.get_scripted_encounter(TOKEN_A, "disconnect"))
        resumed = self.game.ensure_player(TOKEN_A)
        self.assertEqual(resumed.story_step, 0)

    def test_dummy_escort_moves_owned_npc_along_waypoints(self):
        self.helper.x, self.helper.y = 20, 20
        self.game._sync_player_entity(self.helper)
        npc = self.game.spawn_entity(
            kind=ENTITY_NPC,
            subtype=NPC_WILHELM,
            map_id=MAP_OVERWORLD,
            x=10,
            y=10,
            flags=ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING | ENTITY_FLAG_NAMED,
            owner_id=TOKEN_A,
        )
        encounter = self.game.create_scripted_encounter(
            self.owner, "escort", map_id=MAP_OVERWORLD
        )
        self.game.start_scripted_escort(
            encounter, npc, ((11, 10), (12, 10)), move_interval_ticks=1
        )
        self.assertEqual(encounter.phase, ENCOUNTER_ESCORTING)
        self.game._update_scripted_encounters()
        self.assertEqual((npc.x, npc.y), (11, 10))
        self.game._update_scripted_encounters()
        self.assertEqual((npc.x, npc.y), (12, 10))
        self.assertEqual(encounter.phase, ENCOUNTER_SUCCEEDED)

    def test_escort_pauses_until_owner_catches_up(self):
        npc = self.game.spawn_entity(
            kind=ENTITY_NPC,
            subtype=NPC_WILHELM,
            map_id=MAP_OVERWORLD,
            x=10,
            y=10,
            flags=ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING | ENTITY_FLAG_NAMED,
            owner_id=TOKEN_A,
        )
        encounter = self.game.create_scripted_encounter(
            self.owner, "follow_distance", map_id=MAP_OVERWORLD
        )
        self.game.start_scripted_escort(
            encounter,
            npc,
            ((11, 10), (12, 10)),
            escort_follow_distance=2,
        )
        self.owner.x, self.owner.y = 20, 20
        self.game._update_scripted_encounters()
        self.assertEqual((npc.x, npc.y), (10, 10))
        self.owner.x, self.owner.y = 10, 10
        self.game._update_scripted_encounters()
        self.assertEqual((npc.x, npc.y), (11, 10))

    def test_dummy_defense_spawn_and_failure_cleanup(self):
        encounter = self.game.create_scripted_encounter(
            self.owner, "defense", map_id=MAP_OVERWORLD
        )
        first = self.game.spawn_encounter_enemy(encounter, ENEMY_BEAVER, 11, 10)
        second = self.game.spawn_encounter_enemy(encounter, ENEMY_BEAVER, 10, 11)
        self.assertEqual(encounter.spawned_entity_ids, {first.entity_id, second.entity_id})
        self.game.fail_scripted_encounter(encounter, "dummy_failure")
        self.assertNotIn(first.entity_id, self.game.entities)
        self.assertNotIn(second.entity_id, self.game.entities)
        self.assertEqual(encounter.spawned_entity_ids, set())

    def test_failed_encounter_can_be_reset_for_retry(self):
        encounter = self.game.create_scripted_encounter(
            self.owner, "retry", map_id=MAP_OVERWORLD, countdown_ticks=5
        )
        self.game.activate_scripted_encounter(encounter)
        self.game.fail_scripted_encounter(encounter, "abandoned")
        self.game.reset_scripted_encounter(encounter)
        self.assertEqual(encounter.phase, ENCOUNTER_INACTIVE)
        self.assertEqual(encounter.countdown_ticks, 5)
        self.assertEqual(encounter.failure_reason, "")

    def test_two_players_run_independent_encounters_without_cleanup_crosstalk(self):
        first = self.game.create_scripted_encounter(
            self.owner, "defense", map_id=MAP_OVERWORLD
        )
        second = self.game.create_scripted_encounter(
            self.helper, "defense", map_id=MAP_OVERWORLD
        )
        first_enemy = self.game.spawn_encounter_enemy(first, ENEMY_BEAVER, 11, 10)
        second_enemy = self.game.spawn_encounter_enemy(second, ENEMY_BEAVER, 11, 10)
        self.game.fail_scripted_encounter(first, "owner_died")
        self.assertNotIn(first_enemy.entity_id, self.game.entities)
        self.assertIn(second_enemy.entity_id, self.game.entities)
        self.assertEqual(second.spawned_entity_ids, {second_enemy.entity_id})

    def test_restart_persists_only_stable_state_and_normalizes_transient_step(self):
        self.owner.story_stage = STORY_STAGE_BRIDGE
        self.owner.story_step = 8
        self.owner.bridge_materials_staged = True
        encounter = self.game.create_scripted_encounter(
            self.owner, "restart", map_id=MAP_OVERWORLD
        )
        self.game.spawn_encounter_enemy(encounter, ENEMY_BEAVER, 11, 10)
        payload = serialize_player_state(self.owner)
        restored = deserialize_player_state(TOKEN_A, "Owner", payload)
        restarted = GameState(seed=1, world=World(), create_default_player=False)
        restarted._normalize_story_state(restored)
        self.assertEqual(restored.story_step, 0)
        self.assertTrue(restored.bridge_materials_staged)
        self.assertEqual(restarted.scripted_encounters, {})

    def test_bridge_repair_layout_requires_explicit_nonempty_path(self):
        self._patch_bridge_layout(path=())
        with self.assertRaisesRegex(ValueError, "escort path is empty"):
            self.game.bridge_repair_waypoints()

    def test_bridge_repair_encounter_consumes_generated_layout_waypoints(self):
        self._patch_bridge_layout()
        self.helper.x, self.helper.y = 20, 20
        self.game._sync_player_entity(self.helper)
        encounter = self.game.create_bridge_repair_encounter(
            self.owner,
            countdown_ticks=5,
            fail_after_absent_ticks=7,
            move_interval_ticks=1,
        )
        self.assertEqual(encounter.phase, ENCOUNTER_ESCORTING)
        self.assertEqual(encounter.region, EncounterRegion(9, 9, 13, 11))
        self.assertEqual(encounter.waypoints, ((11, 10), (12, 10)))
        self.assertEqual(encounter.countdown_ticks, 5)
        npc = self.game.entities[encounter.escort_entity_id]
        self.assertEqual((npc.x, npc.y), (10, 10))
        self.assertEqual(npc.owner_id, self.owner.token)
        self.assertTrue((npc.flags & ENTITY_FLAG_PERSONAL) != 0)
        owner_records = self.game.legacy_beaver_snapshots_for_window(0, 0, TOKEN_A)
        helper_records = self.game.legacy_beaver_snapshots_for_window(0, 0, TOKEN_B)
        self.assertIn(
            (npc.x, npc.y, DYNAMIC_WILHELM_SNAPSHOT_KIND),
            [(record.x, record.y, record.kind) for record in owner_records],
        )
        self.assertNotIn(
            (npc.x, npc.y, DYNAMIC_WILHELM_SNAPSHOT_KIND),
            [(record.x, record.y, record.kind) for record in helper_records],
        )
        self.game._update_scripted_encounters()
        self.assertEqual((npc.x, npc.y), (11, 10))
        self.game._update_scripted_encounters()
        self.assertEqual((npc.x, npc.y), (12, 10))
        self.assertEqual(encounter.phase, ENCOUNTER_ACTIVE)
        npc.flags |= ENTITY_FLAG_WORKING
        self.assertEqual(
            game_module.dynamic_snapshot_kind(npc),
            DYNAMIC_WILHELM_WORKING_SNAPSHOT_KIND,
        )


if __name__ == "__main__":
    unittest.main()
