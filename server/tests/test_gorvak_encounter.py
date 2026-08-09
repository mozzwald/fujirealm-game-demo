"""Phase 67: Pumpmaster Gorvak boss encounter and Deep Pump shutdown."""

import unittest

import server.game as game_module
from server.encounters import ENCOUNTER_ACTIVE
from server.entities import ENEMY_BAT, ENEMY_GOBLIN, ENEMY_GORVAK, ENTITY_ENEMY
from server.game import GameState
from server.items import ITEM_WARDEN_KEY
from server.quests import STORY_STAGE_GORVAK, STORY_STAGE_RETURN_NERISSA
from server.world import CAVE_FLOOR, MAP_STARTER_CAVE, World

TOKEN_A = 3001
TOKEN_B = 3002


class GorvakEncounterTest(unittest.TestCase):
    def setUp(self):
        self.game = GameState(seed=1, world=World(), create_default_player=False)
        self.cave = self.game.world_for(MAP_STARTER_CAVE)
        # Wide enough that a position outside GORVAK_LEASH_RANGE (8, from
        # the marker at x=20) is still on open floor, for tests that need a
        # genuinely unreachable "stand back and snipe" position.
        for x in range(5, 30):
            for y in range(15, 30):
                self.cave.set_tile(x, y, CAVE_FLOOR)
        self.owner = self.game.add_player(TOKEN_A, x=20, y=20, map_id=MAP_STARTER_CAVE)
        self.owner.story_stage = STORY_STAGE_GORVAK

        original = (
            game_module.GORVAK_MARKER,
            game_module.GORVAK_ROOM_REGION,
            game_module.GORVAK_SUMMON_POINTS,
            game_module.DEEP_PUMP_CONTROLS_MARKER,
        )
        game_module.GORVAK_MARKER = (MAP_STARTER_CAVE, 20, 22)
        game_module.GORVAK_ROOM_REGION = None
        game_module.GORVAK_SUMMON_POINTS = ()
        game_module.DEEP_PUMP_CONTROLS_MARKER = (MAP_STARTER_CAVE, 20, 24)
        self.addCleanup(self._restore, original)

    def _restore(self, original):
        (
            game_module.GORVAK_MARKER,
            game_module.GORVAK_ROOM_REGION,
            game_module.GORVAK_SUMMON_POINTS,
            game_module.DEEP_PUMP_CONTROLS_MARKER,
        ) = original

    def _spawn_gorvak(self):
        self.game.finish_tick()
        encounter = self.game.get_scripted_encounter(self.owner.token, "gorvak")
        self.assertIsNotNone(encounter)
        boss = self.game.entities[encounter.boss_entity_id]
        return encounter, boss

    def _clear_ambient_cave_enemies(self, boss):
        # World() seeds the real cave's ambient goblin/bat population; tests
        # that walk the boss any real distance need a clear path so an
        # unrelated ambient enemy standing in the corridor doesn't block
        # his (deliberately simple, non-pathfinding) step-toward-target AI.
        for entity in list(self.game.entities.values()):
            if entity.entity_id == boss.entity_id or entity.kind != ENTITY_ENEMY:
                continue
            if entity.map_id == boss.map_id:
                self.game.remove_entity(entity.entity_id)

    def test_gorvak_spawns_when_owner_enters_activation_radius_at_correct_stage(self):
        self.owner.x, self.owner.y = 20, 20
        encounter, boss = self._spawn_gorvak()
        self.assertEqual(encounter.phase, ENCOUNTER_ACTIVE)
        self.assertEqual((boss.x, boss.y), (20, 22))
        self.assertEqual(boss.subtype, ENEMY_GORVAK)
        self.assertEqual(boss.owner_id, self.owner.token)
        self.assertEqual((boss.home_x, boss.home_y), (20, 22))

        # It never spawns a second time for the same player.
        self.game.finish_tick()
        self.assertEqual(len(self.game.scripted_encounters), 1)

    def test_gorvak_does_not_activate_at_the_wrong_story_stage(self):
        self.owner.story_stage = STORY_STAGE_GORVAK - 1
        self.owner.x, self.owner.y = 20, 20
        self.game.finish_tick()
        self.assertIsNone(self.game.get_scripted_encounter(self.owner.token, "gorvak"))

    def test_gorvak_never_reaches_a_player_permanently_out_of_leash_range(self):
        self.owner.x, self.owner.y = 20, 20
        encounter, boss = self._spawn_gorvak()
        self._clear_ambient_cave_enemies(boss)
        # Beyond home +/- GORVAK_LEASH_RANGE in every direction: no amount
        # of waiting should ever let him close to attack range.
        self.owner.x, self.owner.y = 9, 22
        for _ in range(60):
            self.game._update_scripted_encounters()
        distance = abs(boss.x - self.owner.x) + abs(boss.y - self.owner.y)
        self.assertGreater(distance, game_module.GORVAK_ATTACK_RANGE)
        leash_distance = abs(boss.x - boss.home_x) + abs(boss.y - boss.home_y)
        self.assertLessEqual(leash_distance, game_module.GORVAK_LEASH_RANGE)

    def test_gorvak_chases_down_a_player_within_leash_range(self):
        # A player standing still at hunter max range (6 tiles) used to be
        # permanently safe -- he only ever stepped when they happened to be
        # exactly 2 tiles away. He must now actually close the distance and
        # reach attack range given enough time, as long as it's within his
        # leash.
        self.owner.x, self.owner.y = 20, 20
        encounter, boss = self._spawn_gorvak()
        self._clear_ambient_cave_enemies(boss)
        # Isolate movement from summons: his simple step-toward-target AI
        # doesn't route around obstacles, so a bat summon landing between
        # him and the owner would otherwise block his own path here.
        encounter.summon_cooldown_ticks = 10**6
        self.owner.x, self.owner.y = 14, 22
        # Break the instant he reaches attack range -- a passive owner who
        # never fights back eventually dies and respawns elsewhere, which
        # would make a distance check after a fixed tick count flaky.
        reached = False
        for _ in range(60):
            self.game._update_scripted_encounters()
            distance = abs(boss.x - self.owner.x) + abs(boss.y - self.owner.y)
            if distance <= game_module.GORVAK_ATTACK_RANGE:
                reached = True
                break
        self.assertTrue(reached, "Gorvak never reached attack range")

    def test_gorvak_attacks_only_when_adjacent(self):
        self.owner.x, self.owner.y = 20, 20
        encounter, boss = self._spawn_gorvak()
        self.owner.x, self.owner.y = 20, 21  # adjacent to (20, 22)
        start_health = self.owner.health
        self.game._update_scripted_encounters()
        self.assertLess(self.owner.health, start_health)
        self.assertGreater(boss.attack_cooldown, 0)

    def test_summons_alternate_species_and_never_exceed_one_alive(self):
        self.owner.x, self.owner.y = 20, 20
        encounter, boss = self._spawn_gorvak()
        # Keep the owner beyond GORVAK_LEASH_RANGE so this test isolates
        # summon timing from the boss's own chase/attack -- the whole test
        # runs long enough (several summon cycles) that a merely-far
        # position within leash range would eventually let him reach and
        # kill the passively-standing owner.
        self.owner.x, self.owner.y = 9, 22
        for _ in range(game_module.GORVAK_INITIAL_SUMMON_DELAY_TICKS + 1):
            self.game._update_scripted_encounters()
        self.assertNotEqual(encounter.summon_entity_id, 0)
        first_summon = self.game.entities[encounter.summon_entity_id]
        self.assertEqual(first_summon.subtype, ENEMY_BAT)

        # No second summon spawns while the first is alive, however long we wait.
        for _ in range(game_module.GORVAK_SUMMON_DELAY_MAX_TICKS + 5):
            self.game._update_scripted_encounters()
        self.assertEqual(encounter.summon_entity_id, first_summon.entity_id)

        # Killing it starts the cooldown; the next one alternates species.
        self.game._damage_entity(first_summon, first_summon.hp, "ranged", self.owner)
        self.game._update_scripted_encounters()  # notices the death, resets to 0
        self.assertEqual(encounter.summon_entity_id, 0)
        for _ in range(game_module.GORVAK_SUMMON_DELAY_MAX_TICKS + 1):
            self.game._update_scripted_encounters()
        self.assertNotEqual(encounter.summon_entity_id, 0)
        second_summon = self.game.entities[encounter.summon_entity_id]
        self.assertEqual(second_summon.subtype, ENEMY_GOBLIN)

    def test_gorvak_defeat_by_helper_credits_owner_not_helper(self):
        helper = self.game.add_player(TOKEN_B, x=21, y=22, map_id=MAP_STARTER_CAVE)
        self.owner.x, self.owner.y = 20, 20
        encounter, boss = self._spawn_gorvak()
        self.assertFalse(self.owner.gorvak_defeated)
        self.game._damage_entity(boss, boss.hp, "ranged", helper)
        self.assertTrue(self.owner.gorvak_defeated)
        self.assertFalse(helper.gorvak_defeated)
        self.game._update_scripted_encounters()  # SUCCEEDED -> CLEANUP
        self.game._update_scripted_encounters()  # CLEANUP -> popped
        self.assertIsNone(self.game.get_scripted_encounter(self.owner.token, "gorvak"))

    def test_gorvak_defeat_removes_live_summon_and_persists_immediately(self):
        self.owner.x, self.owner.y = 15, 22  # outside engagement range
        encounter, boss = self._spawn_gorvak()
        for _ in range(game_module.GORVAK_INITIAL_SUMMON_DELAY_TICKS + 1):
            self.game._update_scripted_encounters()
        summon_id = encounter.summon_entity_id
        self.assertNotEqual(summon_id, 0)
        self.game._damage_entity(boss, boss.hp, "ranged", self.owner)
        self.assertTrue(self.owner.gorvak_defeated)
        self.assertNotIn(summon_id, self.game.entities)

    def test_player_death_resets_gorvak_to_full_health_for_retry(self):
        self.owner.x, self.owner.y = 20, 20
        encounter, boss = self._spawn_gorvak()
        full_hp = boss.hp
        boss.hp = 1  # simulate a partially-fought boss
        self.owner.health = 1
        self.game.handle_player_death(self.owner)
        self.game._update_scripted_encounters()  # FAILED -> CLEANUP
        self.game._update_scripted_encounters()  # CLEANUP -> popped
        self.assertIsNone(self.game.get_scripted_encounter(self.owner.token, "gorvak"))
        self.assertNotIn(boss.entity_id, self.game.entities)
        self.assertFalse(self.owner.gorvak_defeated)
        # The story quest itself is left active -- respawning back into the
        # activation area immediately spawns a fresh, full-health Gorvak.
        self.owner.x, self.owner.y = 20, 20
        self.owner.health = self.owner.max_health
        _, new_boss = self._spawn_gorvak()
        self.assertEqual(new_boss.hp, full_hp)
        self.assertNotEqual(new_boss.entity_id, boss.entity_id)

    def test_deep_pump_controls_reject_before_gorvak_defeated_or_without_key(self):
        self.owner.x, self.owner.y = 20, 23  # adjacent to (20, 24)
        self.assertTrue(self.game._try_interact_deep_pump_controls(self.owner))
        self.assertIsNone(self.owner.active_dialogue)
        self.assertFalse(self.owner.deep_pump_shutdown)

        self.owner.gorvak_defeated = True
        self.assertTrue(self.game._try_interact_deep_pump_controls(self.owner))
        self.assertIsNone(self.owner.active_dialogue)
        self.assertFalse(self.owner.deep_pump_shutdown)

    def test_deep_pump_shutdown_with_key_completes_and_advances_story(self):
        self.owner.x, self.owner.y = 20, 23
        self.owner.gorvak_defeated = True
        self.owner.warden_key_collected = True
        self.owner.inventory.add_item(ITEM_WARDEN_KEY, 1)
        self.assertTrue(self.game._try_interact_deep_pump_controls(self.owner))
        self.assertIsNotNone(self.owner.active_dialogue)
        self.assertEqual(self.owner.active_dialogue.dialogue_id, game_module.story.DLG_PUMP_SHUTDOWN)
        for _ in range(len(self.owner.active_dialogue.pages)):
            self.game.advance_dialogue(self.owner)
        self.assertIsNone(self.owner.active_dialogue)
        self.assertTrue(self.owner.deep_pump_shutdown)
        self.assertEqual(self.owner.story_stage, STORY_STAGE_RETURN_NERISSA)

        # Re-interacting afterward is just small talk; no repeat modal.
        self.assertTrue(self.game._try_interact_deep_pump_controls(self.owner))
        self.assertIsNone(self.owner.active_dialogue)

    def test_deep_pump_shutdown_tells_player_to_return_to_nerissa(self):
        self.owner.x, self.owner.y = 20, 23
        self.owner.gorvak_defeated = True
        self.owner.warden_key_collected = True
        self.owner.inventory.add_item(ITEM_WARDEN_KEY, 1)
        self.game._try_interact_deep_pump_controls(self.owner)
        page_text = " ".join(self.owner.active_dialogue.pages)
        self.assertIn("Nerissa", page_text)
        for _ in range(len(self.owner.active_dialogue.pages)):
            self.game.advance_dialogue(self.owner)
        self.assertIn("Nerissa", self.owner.latest_activity_message)

    def test_second_player_cannot_shut_down_owners_pump(self):
        helper = self.game.add_player(TOKEN_B, x=20, y=23, map_id=MAP_STARTER_CAVE)
        self.owner.gorvak_defeated = True
        self.owner.warden_key_collected = True
        # The helper has neither flag -- their own interaction is rejected
        # regardless of the owner's progress.
        self.assertTrue(self.game._try_interact_deep_pump_controls(helper))
        self.assertIsNone(helper.active_dialogue)
        self.assertFalse(helper.deep_pump_shutdown)
        self.assertFalse(self.owner.deep_pump_shutdown)

    def _tile_at(self, window, x, y):
        local_x, local_y = x - window.origin_x, y - window.origin_y
        return window.tiles[local_y * window.width + local_x]

    def test_deep_pump_and_controls_render_as_static_props(self):
        # Landmarks, not entities: they show up in the terrain stream at the
        # Gorvak/DPC marker coordinates regardless of encounter/story state,
        # the same mechanism used for the static named-NPC overlay.
        self.owner.x, self.owner.y = 20, 22
        window = self.game.window(self.owner.token)
        self.assertEqual(
            self._tile_at(window, 20, 22), game_module.DEEP_PUMP_TILE
        )
        self.assertEqual(
            self._tile_at(window, 20, 24), game_module.PUMP_CONTROLS_TILE
        )

    def test_deep_pump_prop_still_renders_while_gorvak_is_alive(self):
        self.owner.x, self.owner.y = 20, 20
        self._spawn_gorvak()
        self.owner.x, self.owner.y = 20, 22
        window = self.game.window(self.owner.token)
        self.assertEqual(
            self._tile_at(window, 20, 22), game_module.DEEP_PUMP_TILE
        )


if __name__ == "__main__":
    unittest.main()
