import unittest
from collections import deque

import server.game as game_module
from server.entities import ENTITY_ITEM, NPC_DANIEL, NPC_GRIX, NPC_LUCIAN, NPC_NERISSA
from server.game import (
    BEAVER_ATTACK_COOLDOWN,
    CLASS_HUNTER,
    DANIEL_TILE,
    ENEMY_BEAVER,
    ENEMY_SLIME,
    ENEMY_SNAKE,
    ENEMY_TYPES,
    CLIENT_AIM_LEFT,
    CLIENT_AIM_RIGHT,
    CLIENT_AIM_UP,
    CLIENT_AIM_UP_LEFT,
    CLIENT_AIM_UP_RIGHT,
    CLIENT_AIM_DOWN_LEFT,
    CLIENT_AIM_DOWN_RIGHT,
    ITEM_DESPAWN_TICKS,
    FARMER_X,
    FARMER_Y,
    GameState,
    GOBLIN_NPC_X,
    GOBLIN_NPC_Y,
    HERB_RESPAWN_TICKS,
    MAP_SUMMARY_CURRENT,
    MAP_SUMMARY_MARKER_CAVE,
    MAP_SUMMARY_MARKER_TOWN,
    MAP_SUMMARY_VISITED,
    TREE_RESPAWN_TICKS,
    max_hp_for_level,
    client_aim_delta,
    melee_damage_for_level,
    ranged_damage_for_level,
    stick_delta,
    xp_needed_for_next_level,
)
from server.items import ITEM_GOLD, ITEM_OIL_SAMPLE, ITEM_RUST_SAMPLE, ITEM_STICKS, Inventory, MAX_INVENTORY_SLOTS
from server.protocol import InputIntent, PlayerStatePacket
from server.quests import (
    BLACKWATER_REWARD_GOLD,
    BLACKWATER_REWARD_XP,
    BLACKWATER_TARGET,
    LIVING_MUD_OIL_TARGET,
    LIVING_MUD_REWARD_GOLD,
    LIVING_MUD_REWARD_XP,
    LIVING_MUD_RUST_TARGET,
    MSG_BEAVER_BITES,
    MSG_GOT_STICKS,
    MSG_LEVEL_UP,
    MSG_PVP_ARENA_LOCKED,
    MSG_RESPAWN_CAVE,
    MSG_RESPAWN_GRAVE,
    MSG_QUEST_COMPLETE,
    MSG_QUEST_READY,
    MSG_QUEST_REMINDER,
    MSG_QUEST_STARTED,
    QUEST_BLACKWATER_BITE,
    QUEST_LIVING_MUD,
    QUEST_REPAIR_BRIDGE,
    QUEST_ROAD_TROUBLE,
    QUEST_NONE,
    QUEST_STATE_ACTIVE,
    QUEST_STATE_COMPLETE,
    QUEST_STATE_NOT_STARTED,
    QUEST_STATE_READY_TO_TURN_IN,
    REPAIR_BRIDGE_REWARD_GOLD,
    REPAIR_BRIDGE_REWARD_XP,
    ROAD_TROUBLE_REWARD_GOLD,
    ROAD_TROUBLE_REWARD_XP,
    ROAD_TROUBLE_TARGET,
)
from server.world import (
    BORDER,
    BUILDING,
    CAVE_ENTRANCE,
    CAVE_EXIT,
    CAVE_FLOOR,
    CAVE_WALL,
    GRASS,
    GRAVE,
    HERB,
    MAP_OVERWORLD,
    MAP_PVP_REALM,
    MAP_STARTER_CAVE,
    OVERWORLD_CAVE_ENTRANCE,
    OVERWORLD_PVP_REALM_ENTRANCE,
    OVERWORLD_PVP_REALM_RETURN,
    OVERWORLD_CAVE_RETURN,
    OVERWORLD_RESPAWN,
    OVERWORLD_START,
    PVP_REALM_ENTRY,
    PVP_REALM_EXIT,
    PVP_REALM_RESPAWN,
    ROAD,
    STARTER_CAVE_ENTRY,
    STARTER_CAVE_EXIT,
    STARTER_CAVE_RESPAWN,
    TREE_DAMAGED,
    TREE_FULL,
    TREE_STUMP,
    WATER,
    World,
    build_seeded_world,
    build_world_map,
)
from server.zones import zone_for_tile



def finish_dialogue(game, player=None, limit=16):
    """Advance the open dialogue until it closes.

    Page counts are content, not behaviour: writing another line into an NPC's
    script should not break tests that only care about what happens when the
    conversation ends.
    """
    target = player if player is not None else game.player
    for _ in range(limit):
        if target.active_dialogue is None:
            return
        game.advance_dialogue(target)
    raise AssertionError("dialogue did not close")


class WorldGameTest(unittest.TestCase):
    def _advance_ticks(self, game: GameState, ticks: int) -> None:
        for _ in range(ticks):
            game.begin_tick()
            game.finish_tick()

    def _move_player_to(self, game: GameState, x: int, y: int) -> None:
        game.player.x = x
        game.player.y = y
        game._sync_player_entity(game.player)

    def _reset_as_beaver(self, enemy) -> None:
        # Static spawns come from world_layout_data.STATIC_ENEMY_SPAWNS, whose
        # ordering and enemy types shift whenever the map CSVs are re-imported
        # (the first overworld spawn is currently a goblin, not a beaver).
        # These combat/AI tests only care that the enemy under test is a
        # beaver, so pin its subtype and HP explicitly rather than trusting
        # spawn order.
        enemy.subtype = ENEMY_BEAVER
        enemy.hp = ENEMY_TYPES[ENEMY_BEAVER].hp

    def _park_beavers(self, game: GameState) -> None:
        # Shove every beaver to a far corner so it stays outside any active
        # zone (see is_tile_in_active_zone) and cannot wander onto or
        # contest the tile under test during a long respawn wait.
        for beaver in game.beavers:
            beaver.x, beaver.y = 120, 90

    def test_world_border_blocks_player_and_enemy(self):
        world = World()
        self.assertEqual(world.tile(0, 0), BORDER)
        self.assertFalse(world.player_can_enter(0, 1))
        self.assertFalse(world.enemy_can_enter(0, 1))

    def test_player_collision_matches_client_rules(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        game = GameState(seed=1, world=world)
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (10, 10))

    def test_damaged_tree_blocks_but_stump_is_walkable(self):
        world = World()
        world.set_tile(11, 10, TREE_DAMAGED)
        game = GameState(seed=1, world=world)
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (10, 10))
        world.set_tile(11, 10, TREE_STUMP)
        game.apply_input(InputIntent(1, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (11, 10))

    def test_stick_delta_supports_8_way_movement(self):
        self.assertEqual(stick_delta(0x0A), (-1, -1))
        self.assertEqual(stick_delta(0x06), (1, -1))
        self.assertEqual(stick_delta(0x09), (-1, 1))
        self.assertEqual(stick_delta(0x05), (1, 1))

    def test_diagonal_move_reaches_open_diagonal_cell(self):
        game = GameState(seed=1, world=World())
        game.apply_input(InputIntent(0, 0x05, 0, 0, 0))
        self.assertEqual((game.player.x, game.player.y), (11, 11))

    def test_diagonal_move_slides_along_clear_axis(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        game = GameState(seed=1, world=world)
        game.apply_input(InputIntent(0, 0x05, 0, 0, 0))
        self.assertEqual((game.player.x, game.player.y), (10, 11))

    def test_diagonal_move_cannot_cut_closed_corner(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.set_tile(10, 11, TREE_FULL)
        game = GameState(seed=1, world=world)
        game.apply_input(InputIntent(0, 0x05, 0, 0, 0))
        self.assertEqual((game.player.x, game.player.y), (10, 10))

    def test_realtime_diagonal_position_cannot_cut_closed_corner(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.set_tile(10, 11, TREE_FULL)
        game = GameState(seed=1, world=world)
        accepted = game.apply_player_state(PlayerStatePacket(1, 11, 11, CLIENT_AIM_RIGHT, 0, 0, 0, 0))
        self.assertFalse(accepted)
        self.assertEqual((game.player.x, game.player.y), (10, 10))

    def test_player_cannot_enter_live_beaver_cell(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 11
        game.beavers[0].y = 10
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (10, 10))

    def test_player_consumes_herb(self):
        world = World()
        world.set_tile(11, 10, HERB)
        game = GameState(seed=1, world=world)
        game.player.health = 3
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (11, 10))
        self.assertEqual(game.player.health, 5)
        self.assertEqual(world.tile(11, 10), GRASS)
        snapshot = game.snapshot()
        self.assertEqual(snapshot.tile_x, 11)
        self.assertEqual(snapshot.tile_y, 10)
        self.assertEqual(snapshot.tile_id, GRASS)

    def test_consumed_herb_arms_respawn_cooldown(self):
        world = World()
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        game.player.health = 3
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        index = world.index(11, 10)
        self.assertEqual(world.tile(11, 10), GRASS)
        self.assertEqual(world.herb_respawn_ticks[index], HERB_RESPAWN_TICKS)

    def test_consumed_herb_respawns_after_cooldown_with_tile_update(self):
        world = World()
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        game.player.health = 3
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self._move_player_to(game, 10, 10)
        self._advance_ticks(game, HERB_RESPAWN_TICKS - 1)
        self.assertEqual(world.tile(11, 10), GRASS)
        self._advance_ticks(game, 1)
        self.assertEqual(world.tile(11, 10), HERB)
        snapshot = game.snapshot()
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (11, 10, HERB))

    def test_herb_respawn_waits_when_tile_update_is_busy(self):
        world = World()
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        game.player.health = 3
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self._move_player_to(game, 10, 10)
        index = world.index(11, 10)
        world.herb_respawn_ticks[index] = 0
        game.tile_update = (MAP_OVERWORLD, 2, 2, TREE_STUMP)
        game._respawn_herbs()
        self.assertEqual(world.tile(11, 10), GRASS)
        self.assertIn(index, world.herb_respawn_ticks)
        game.tile_update = None
        game._respawn_herbs()
        self.assertEqual(world.tile(11, 10), HERB)
        self.assertEqual(game.tile_update, (MAP_OVERWORLD, 11, 10, HERB))

    def test_herb_respawn_waits_for_player_or_entity_to_leave_tile(self):
        world = World()
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        game.player.health = 3
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        index = world.index(11, 10)
        world.herb_respawn_ticks[index] = 0
        game.tile_update = None
        game._respawn_herbs()
        self.assertEqual(world.tile(11, 10), GRASS)
        self.assertEqual(world.herb_respawn_ticks[index], 1)
        self._move_player_to(game, 10, 10)
        item = game.spawn_item(11, 10, ITEM_GOLD, map_id=MAP_OVERWORLD)
        game._respawn_herbs()
        self.assertEqual(world.tile(11, 10), GRASS)
        self.assertEqual(world.herb_respawn_ticks[index], 1)
        game.remove_entity(item.entity_id)
        game._respawn_herbs()
        self.assertEqual(world.tile(11, 10), HERB)

    def test_off_window_herb_respawn_updates_world_without_visible_snapshot_tile(self):
        world = World()
        world.set_tile(90, 90, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        index = world.index(90, 90)
        world.set_tile(90, 90, GRASS)
        world.herb_respawn_ticks[index] = 0
        game._respawn_herbs()
        snapshot = game.snapshot_for_window(0, 0)
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (0, 0, 0))
        self.assertEqual(world.tile(90, 90), HERB)

    def test_respawned_herb_can_be_consumed_again(self):
        world = World()
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        game.player.health = 3
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self._move_player_to(game, 10, 10)
        self._advance_ticks(game, HERB_RESPAWN_TICKS)
        game.player.health = 3
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        index = world.index(11, 10)
        self.assertEqual(world.tile(11, 10), GRASS)
        self.assertEqual(game.player.health, 5)
        self.assertEqual(world.herb_respawn_ticks[index], HERB_RESPAWN_TICKS)

    def test_beaver_chopping_tree_to_stump_arms_respawn_cooldown(self):
        # Drive _try_chop directly (rather than the full _move_beavers AI)
        # to verify the game.py call site forwards TREE_RESPAWN_TICKS.
        world = World()
        world.set_tile(18, 9, TREE_FULL)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        beaver = game.beavers[0]
        beaver.subtype = ENEMY_BEAVER  # ensure a chopping enemy type
        beaver.x, beaver.y = 18, 10
        index = world.index(18, 9)

        beaver.chop_cooldown = 0
        game.tile_update = None
        self.assertTrue(game._try_chop(beaver))
        self.assertEqual(world.tile(18, 9), TREE_DAMAGED)
        # FULL -> DAMAGED is still recoverable and must not arm regrowth.
        self.assertNotIn(index, world.tree_respawn_ticks)

        beaver.chop_cooldown = 0
        game.tile_update = None
        self.assertTrue(game._try_chop(beaver))
        self.assertEqual(world.tile(18, 9), TREE_STUMP)
        self.assertEqual(world.tree_respawn_ticks[index], TREE_RESPAWN_TICKS)

    def test_chopping_tree_to_damaged_does_not_arm_respawn(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.rebuild_registries()
        index = world.index(11, 10)
        result = world.chop_tree_if_present(11, 10, TREE_RESPAWN_TICKS)
        self.assertEqual(result, TREE_DAMAGED)
        self.assertEqual(world.tile(11, 10), TREE_DAMAGED)
        self.assertNotIn(index, world.tree_respawn_ticks)

    def test_unregistered_tree_chopped_to_stump_does_not_arm_respawn(self):
        world = World()
        # Tree placed after the registry was built (as via chopping-created
        # geometry): not an authored spawn, so it must not regrow.
        world.set_tile(11, 10, TREE_DAMAGED)
        index = world.index(11, 10)
        self.assertNotIn(index, world.tree_spawn_indices)
        result = world.chop_tree_if_present(11, 10, TREE_RESPAWN_TICKS)
        self.assertEqual(result, TREE_STUMP)
        self.assertNotIn(index, world.tree_respawn_ticks)

    def test_chopped_tree_respawns_after_cooldown_with_tile_update(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        self._park_beavers(game)
        self._move_player_to(game, 10, 10)
        index = world.index(11, 10)
        world.chop_tree_if_present(11, 10)  # FULL -> DAMAGED
        world.chop_tree_if_present(11, 10, TREE_RESPAWN_TICKS)  # DAMAGED -> STUMP
        self.assertEqual(world.tree_respawn_ticks[index], TREE_RESPAWN_TICKS)
        self._advance_ticks(game, TREE_RESPAWN_TICKS - 1)
        self.assertEqual(world.tile(11, 10), TREE_STUMP)
        self._advance_ticks(game, 1)
        self.assertEqual(world.tile(11, 10), TREE_FULL)
        snapshot = game.snapshot()
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (11, 10, TREE_FULL))

    def test_tree_respawn_waits_when_tile_update_is_busy(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        self._park_beavers(game)
        self._move_player_to(game, 10, 10)
        index = world.index(11, 10)
        world.set_tile(11, 10, TREE_STUMP)
        world.tree_respawn_ticks[index] = 0
        game.tile_update = (MAP_OVERWORLD, 2, 2, HERB)
        game._respawn_trees()
        self.assertEqual(world.tile(11, 10), TREE_STUMP)
        self.assertIn(index, world.tree_respawn_ticks)
        game.tile_update = None
        game._respawn_trees()
        self.assertEqual(world.tile(11, 10), TREE_FULL)
        self.assertEqual(game.tile_update, (MAP_OVERWORLD, 11, 10, TREE_FULL))

    def test_tree_respawn_waits_for_player_or_entity_to_leave_tile(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        self._park_beavers(game)
        index = world.index(11, 10)
        world.set_tile(11, 10, TREE_STUMP)
        world.tree_respawn_ticks[index] = 0
        game.tile_update = None
        # A player standing on the stump (TREE_STUMP is walkable) blocks it.
        self._move_player_to(game, 11, 10)
        game._respawn_trees()
        self.assertEqual(world.tile(11, 10), TREE_STUMP)
        self.assertEqual(world.tree_respawn_ticks[index], 1)
        self._move_player_to(game, 10, 10)
        item = game.spawn_item(11, 10, ITEM_GOLD, map_id=MAP_OVERWORLD)
        world.tree_respawn_ticks[index] = 0
        game._respawn_trees()
        self.assertEqual(world.tile(11, 10), TREE_STUMP)
        self.assertEqual(world.tree_respawn_ticks[index], 1)
        game.remove_entity(item.entity_id)
        world.tree_respawn_ticks[index] = 0
        game._respawn_trees()
        self.assertEqual(world.tile(11, 10), TREE_FULL)

    def test_off_window_tree_respawn_updates_world_without_visible_snapshot_tile(self):
        world = World()
        world.set_tile(90, 90, TREE_FULL)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        index = world.index(90, 90)
        world.set_tile(90, 90, TREE_STUMP)
        world.tree_respawn_ticks[index] = 0
        game._respawn_trees()
        snapshot = game.snapshot_for_window(0, 0)
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (0, 0, 0))
        self.assertEqual(world.tile(90, 90), TREE_FULL)

    def test_respawned_tree_can_be_chopped_down_again(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        self._park_beavers(game)
        self._move_player_to(game, 10, 10)
        index = world.index(11, 10)
        world.chop_tree_if_present(11, 10)
        world.chop_tree_if_present(11, 10, TREE_RESPAWN_TICKS)
        self._advance_ticks(game, TREE_RESPAWN_TICKS)
        self.assertEqual(world.tile(11, 10), TREE_FULL)
        self.assertEqual(world.chop_tree_if_present(11, 10, TREE_RESPAWN_TICKS), TREE_DAMAGED)
        self.assertEqual(world.chop_tree_if_present(11, 10, TREE_RESPAWN_TICKS), TREE_STUMP)
        self.assertEqual(world.tree_respawn_ticks[index], TREE_RESPAWN_TICKS)

    def test_player_cannot_walk_onto_freshly_regrown_tree(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        self._park_beavers(game)
        self._move_player_to(game, 10, 10)
        world.chop_tree_if_present(11, 10)
        world.chop_tree_if_present(11, 10, TREE_RESPAWN_TICKS)
        self._advance_ticks(game, TREE_RESPAWN_TICKS)
        self.assertEqual(world.tile(11, 10), TREE_FULL)
        # The regrown TREE_FULL is blocking again: a move into it is refused.
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (10, 10))

    def test_herb_heals_one_heart_for_current_level(self):
        world = World()
        world.set_tile(11, 10, HERB)
        game = GameState(seed=1, world=world)
        game.player.level = 10
        game.player.max_health = max_hp_for_level(game.player.level, game.player.class_id)
        game.player.health = 10
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual(game.player.max_health, 30)
        self.assertEqual(game.player.health, 15)

    def test_realtime_herb_heals_one_heart_for_current_level(self):
        world = World()
        world.set_tile(11, 10, HERB)
        game = GameState(seed=1, world=world)
        game.player.level = 10
        game.player.max_health = max_hp_for_level(game.player.level, game.player.class_id)
        game.player.health = 10
        snapshot, accepted = game.step_player_state(PlayerStatePacket(1, 11, 10, 3, 0, 0, 0, 0))
        self.assertTrue(accepted)
        self.assertEqual(game.player.health, 15)
        self.assertEqual(snapshot.health, 15)

    def test_player_health_caps_at_client_max(self):
        world = World()
        world.set_tile(11, 10, HERB)
        game = GameState(seed=1, world=world)
        game.player.health = game.player.max_health
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual(game.player.health, game.player.max_health)

    def test_full_health_player_does_not_consume_herb(self):
        world = World()
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        game.player.health = game.player.max_health
        game.apply_input(InputIntent(0, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (11, 10))
        self.assertEqual(game.player.health, game.player.max_health)
        self.assertEqual(world.tile(11, 10), HERB)
        self.assertEqual(world.herb_respawn_ticks, {})
        snapshot = game.snapshot()
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (11, 10, HERB))

    def test_full_health_realtime_move_keeps_herb_and_reports_tile(self):
        world = World()
        world.set_tile(11, 10, HERB)
        world.rebuild_registries()
        game = GameState(seed=1, world=world)
        game.player.health = game.player.max_health
        snapshot, accepted = game.step_player_state(PlayerStatePacket(1, 11, 10, 3, 0, 0, 0, 0))
        self.assertTrue(accepted)
        self.assertEqual((game.player.x, game.player.y), (11, 10))
        self.assertEqual(game.player.health, game.player.max_health)
        self.assertEqual(world.tile(11, 10), HERB)
        self.assertEqual(world.herb_respawn_ticks, {})
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (11, 10, HERB))

    def test_hunter_starting_stats_and_scaling(self):
        game = GameState(seed=1, world=World())
        self.assertEqual(game.player.class_id, CLASS_HUNTER)
        self.assertEqual(game.player.level, 1)
        self.assertEqual(game.player.xp, 0)
        self.assertEqual(game.player.xp_next, 20)
        self.assertEqual(game.player.gold, 0)
        self.assertEqual(game.player.max_health, 12)
        self.assertEqual(game.player.health, 12)
        self.assertEqual(max_hp_for_level(3, CLASS_HUNTER), 16)
        self.assertEqual(xp_needed_for_next_level(3), 70)
        self.assertEqual(ranged_damage_for_level(3, CLASS_HUNTER), 5)
        self.assertEqual(melee_damage_for_level(3, CLASS_HUNTER), 2)

    def test_award_xp_levels_up_and_restores_hp(self):
        game = GameState(seed=1, world=World())
        game.player.health = 2
        game.award_xp(20)
        self.assertEqual(game.player.level, 2)
        self.assertEqual(game.player.xp, 20)
        self.assertEqual(game.player.xp_next, 45)
        self.assertEqual(game.player.max_health, 14)
        self.assertEqual(game.player.health, 14)
        self.assertEqual(game.latest_message_id, MSG_LEVEL_UP)

    def test_award_gold_caps_and_hud_reflects_rewards(self):
        game = GameState(seed=1, world=World())
        game.award_gold(3)
        hud = game.hud_update_packet(1)
        self.assertEqual(hud.gold, 3)

    def test_inventory_stacks_items_and_capacity_limits(self):
        inventory = Inventory()
        self.assertTrue(inventory.add_item(ITEM_STICKS, 2))
        self.assertTrue(inventory.add_item(ITEM_STICKS, 3))
        self.assertEqual(inventory.count_item(ITEM_STICKS), 5)
        for item_id in range(10, 10 + MAX_INVENTORY_SLOTS - 1):
            self.assertTrue(inventory.add_item(item_id, 1))
        self.assertFalse(inventory.add_item(99, 1))

    def test_beaver_death_drops_visible_loot_without_auto_gold(self):
        game = GameState(seed=1, world=World())
        beaver = game.beavers[0]
        death_x, death_y = beaver.x, beaver.y
        game._damage_entity(beaver, beaver.hp, "ranged")
        self.assertEqual(game.player.gold, 0)
        dropped = [
            entity
            for entity in game.entities.values()
            if entity.kind == ENTITY_ITEM and entity.map_id == beaver.map_id
        ]
        self.assertGreaterEqual(len(dropped), 1)
        for item in dropped:
            self.assertIn(item.subtype, (ITEM_GOLD, ITEM_STICKS))
            self.assertEqual(item.decay_ticks, ITEM_DESPAWN_TICKS)
            distance = abs(item.x - death_x) + abs(item.y - death_y)
            self.assertLessEqual(distance, 1)

    def test_beaver_loot_drop_roll_covers_gold_sticks_and_both(self):
        game = GameState(seed=1, world=World())
        seen_combos = set()
        for _ in range(30):
            beaver = game.spawn_beaver(20, 20)
            game._damage_entity(beaver, beaver.hp, "ranged")
            dropped = tuple(
                sorted(
                    entity.subtype
                    for entity in game.entities.values()
                    if entity.kind == ENTITY_ITEM and entity.x in (20, 21, 19) and entity.y in (20, 19, 21)
                )
            )
            seen_combos.add(dropped)
            for entity in list(game.entities.values()):
                if entity.kind == ENTITY_ITEM:
                    game.remove_entity(entity.entity_id)
        self.assertEqual(seen_combos, {(ITEM_GOLD,), (ITEM_STICKS,), (ITEM_GOLD, ITEM_STICKS)})

    def test_loot_drop_positions_places_second_drop_on_empty_neighbor(self):
        game = GameState(seed=1, world=World())
        positions = game._loot_drop_positions(game.player.map_id, 30, 30, 2)
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0], (30, 30))
        self.assertNotEqual(positions[1], (30, 30))
        self.assertEqual(abs(positions[1][0] - 30) + abs(positions[1][1] - 30), 1)

    def test_loot_drop_positions_falls_back_to_death_tile_when_surrounded(self):
        game = GameState(seed=1, world=World())
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            game.spawn_beaver(30 + dx, 30 + dy, map_id=game.player.map_id)
        positions = game._loot_drop_positions(game.player.map_id, 30, 30, 2)
        self.assertEqual(positions, [(30, 30), (30, 30)])

    def test_expired_item_drop_despawns_after_timeout(self):
        game = GameState(seed=1, world=World())
        item = game.spawn_item(40, 40, ITEM_GOLD, map_id=game.player.map_id)
        self.assertEqual(item.decay_ticks, ITEM_DESPAWN_TICKS)
        item.decay_ticks = 1
        game.step()
        self.assertIn(item.entity_id, game.entities)
        game.step()
        self.assertNotIn(item.entity_id, game.entities)

    def test_item_pickup_is_not_restricted_to_a_specific_player(self):
        game = GameState(seed=1, create_default_player=False)
        killer = game.add_player(101, x=10, y=10)
        looter = game.add_player(102, x=20, y=10)
        game.spawn_item(20, 10, ITEM_GOLD, quantity=3, map_id=looter.map_id)
        self.assertTrue(game.pickup_nearby_item(looter))
        self.assertEqual(looter.gold, 3)
        self.assertEqual(killer.gold, 0)

    def test_walking_onto_gold_drop_collects_it(self):
        game = GameState(seed=1, world=World())
        item = game.spawn_item(11, 10, ITEM_GOLD, quantity=2, map_id=game.player.map_id)
        game.apply_input(InputIntent(1, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (11, 10))
        self.assertEqual(game.player.gold, 2)
        self.assertNotIn(item.entity_id, game.entities)

    def test_walking_onto_sticks_drop_collects_it(self):
        game = GameState(seed=1, world=World())
        item = game.spawn_item(11, 10, ITEM_STICKS, quantity=2, map_id=game.player.map_id)
        game.apply_input(InputIntent(1, 0x07, 0, 0x07, 0))
        self.assertEqual((game.player.x, game.player.y), (11, 10))
        self.assertEqual(game.player.inventory.count_item(ITEM_STICKS), 2)
        self.assertNotIn(item.entity_id, game.entities)

    def test_pickup_counter_adds_item_removes_entity_and_queues_message(self):
        game = GameState(seed=1, world=World())
        item = game.spawn_item(game.player.x, game.player.y, ITEM_STICKS, quantity=2)
        game.step_player_state(
            PlayerStatePacket(1, game.player.x, game.player.y, CLIENT_AIM_RIGHT, 0, 0, 1, 0)
        )
        self.assertEqual(game.player.inventory.count_item(ITEM_STICKS), 2)
        self.assertNotIn(item.entity_id, game.entities)
        self.assertEqual(game.latest_message_id, MSG_GOT_STICKS)
        self.assertEqual(game.inventory_update_packet(9).slots, ((ITEM_STICKS, 2),))

    def test_daniel_npc_offers_save_my_orchard_via_dialogue_modal(self):
        game = GameState(seed=1, world=World())
        game.player.x = FARMER_X - 1
        game.player.y = FARMER_Y
        self.assertEqual(game.player.active_quest_id, QUEST_NONE)
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertEqual(game.player.pending_quest_offer_id, QUEST_ROAD_TROUBLE)
        self.assertEqual(game.player.quest_state, QUEST_STATE_NOT_STARTED)
        self.assertIsNotNone(game.player.active_dialogue)
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_DANIEL_OFFER)
        # Acknowledging every page of the offer accepts the quest.
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.active_quest_id, QUEST_ROAD_TROUBLE)
        self.assertEqual(game.player.quest_state, QUEST_STATE_ACTIVE)
        self.assertEqual(game.player.quest_target, ROAD_TROUBLE_TARGET)

    def test_save_my_orchard_progress_ready_and_completion_rewards(self):
        game = GameState(seed=1, world=World())
        game.player.x = FARMER_X - 1
        game.player.y = FARMER_Y
        self.assertTrue(game.interact_with_adjacent_npc())
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        start_xp = game.player.xp
        start_gold = game.player.gold
        actual_beavers = [e for e in game.beavers if e.subtype == ENEMY_BEAVER]
        for index, beaver in enumerate(actual_beavers[:ROAD_TROUBLE_TARGET]):
            beaver.x = 12 + index * 2
            beaver.y = 10
            game._damage_entity(beaver, beaver.hp, "ranged")
        self.assertEqual(game.player.quest_progress, ROAD_TROUBLE_TARGET)
        self.assertEqual(game.player.quest_state, QUEST_STATE_READY_TO_TURN_IN)
        self.assertEqual(game.latest_message_id, MSG_QUEST_READY)
        self.assertTrue(game.player.inventory.count_item(ITEM_STICKS) >= 1)

        # Talking to Daniel again opens the turn-in modal; the quest and its
        # rewards resolve when the final page is acknowledged, not before.
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNotNone(game.player.active_dialogue)
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_DANIEL_COMPLETE)
        self.assertEqual(game.player.quest_state, QUEST_STATE_READY_TO_TURN_IN)
        self.assertEqual(game.player.xp, start_xp + 3 * ROAD_TROUBLE_TARGET)
        self.assertEqual(game.player.gold, start_gold)
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.quest_state, QUEST_STATE_COMPLETE)
        self.assertEqual(game.player.xp, start_xp + 3 * ROAD_TROUBLE_TARGET + ROAD_TROUBLE_REWARD_XP)
        self.assertEqual(game.player.gold, start_gold + ROAD_TROUBLE_REWARD_GOLD)
        self.assertEqual(game.latest_message_id, MSG_LEVEL_UP)
        completion_level = game.player.level
        completion_xp = game.player.xp
        completion_gold = game.player.gold

        # Re-interacting afterward does not grant the reward again.
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.xp, start_xp + 3 * ROAD_TROUBLE_TARGET + ROAD_TROUBLE_REWARD_XP)
        self.assertEqual(game.player.gold, start_gold + ROAD_TROUBLE_REWARD_GOLD)

        game.player.x = game_module.WILHELM_POS[0] - 1
        game.player.y = game_module.WILHELM_POS[1]
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNotNone(game.player.active_dialogue)
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        encounter = game.get_scripted_encounter(game.player.token, "bridge_repair")
        self.assertIsNotNone(encounter)
        for _ in range(len(game_module.WILHELM_ESCORT_PATH) * game_module.WILHELM_MOVE_INTERVAL_TICKS + 5):
            npc = game.entities[encounter.escort_entity_id]
            game.player.x, game.player.y = npc.x, npc.y
            game._sync_player_entity(game.player)
            game._update_scripted_encounters()
            if encounter.phase == game_module.ENCOUNTER_ACTIVE:
                break
        self.assertEqual(encounter.phase, game_module.ENCOUNTER_ACTIVE)
        self.assertFalse(game.player.bridge_repaired)
        self.assertEqual(encounter.countdown_ticks, game_module.BRIDGE_REPAIR_DURATION_TICKS)
        self.assertEqual((game.player.quest_progress, game.player.quest_target), (0, 4))
        npc = game.entities[encounter.escort_entity_id]
        self.assertTrue(npc.flags & game_module.ENTITY_FLAG_WORKING)
        self.assertEqual(
            game_module.dynamic_snapshot_kind(npc),
            game_module.DYNAMIC_WILHELM_WORKING_SNAPSHOT_KIND,
        )
        milestones = {}
        for _ in range(game_module.BRIDGE_REPAIR_DURATION_TICKS - 1):
            game._update_scripted_encounters()
            if game.player.quest_progress:
                milestones[game.player.quest_progress] = game.quest_update_packet(1).text
        self.assertFalse(game.player.bridge_repaired)
        self.assertEqual(encounter.countdown_ticks, 1)
        self.assertEqual(
            milestones,
            {
                1: "Repair the Bridge 1/4",
                2: "Repair the Bridge 2/4",
                3: "Repair the Bridge 3/4",
            },
        )
        game._update_scripted_encounters()
        self.assertTrue(game.player.bridge_repaired)
        self.assertEqual(game.quest_update_packet(1).text, "Repair the Bridge 4/4")
        self.assertFalse(npc.flags & game_module.ENTITY_FLAG_WORKING)
        self.assertEqual(
            game_module.dynamic_snapshot_kind(npc),
            game_module.DYNAMIC_WILHELM_SNAPSHOT_KIND,
        )
        # Save My Orchard's reward was already granted at Daniel's turn-in;
        # the bridge repair itself does not pay out a second reward.
        self.assertEqual(game.player.level, completion_level)
        self.assertEqual(game.player.xp, completion_xp)
        self.assertEqual(game.player.gold, completion_gold)

        # Repair the Bridge is its own quest: active during the escort and
        # defense, ready-to-turn-in the instant the repair finishes, and it
        # does not resolve until Wilhelm walks home and is spoken to again.
        self.assertEqual(game.player.active_quest_id, QUEST_REPAIR_BRIDGE)
        self.assertEqual(game.player.quest_state, QUEST_STATE_READY_TO_TURN_IN)
        self.assertIsNotNone(game.get_scripted_encounter(game.player.token, "bridge_repair"))

        # Catching up to walking-Wilhelm mid-route does not open the modal.
        for _ in range(len(game_module.WILHELM_ESCORT_PATH) * game_module.WILHELM_MOVE_INTERVAL_TICKS + 5):
            encounter = game.get_scripted_encounter(game.player.token, "bridge_repair")
            if encounter is None:
                break
            npc = game.entities.get(encounter.escort_entity_id)
            if npc is not None:
                game.player.x, game.player.y = npc.x, npc.y
                game._sync_player_entity(game.player)
            game._update_scripted_encounters()
        self.assertIsNone(game.get_scripted_encounter(game.player.token, "bridge_repair"))

        game.player.x = game_module.WILHELM_POS[0] - 1
        game.player.y = game_module.WILHELM_POS[1]
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNotNone(game.player.active_dialogue)
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_WILHELM_COMPLETE)
        self.assertEqual(game.player.quest_state, QUEST_STATE_READY_TO_TURN_IN)
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.quest_state, QUEST_STATE_COMPLETE)
        self.assertEqual(game.player.xp, completion_xp + REPAIR_BRIDGE_REWARD_XP)
        self.assertEqual(game.player.gold, completion_gold + REPAIR_BRIDGE_REWARD_GOLD)

        # Re-interacting afterward is just small talk; no repeat reward.
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.xp, completion_xp + REPAIR_BRIDGE_REWARD_XP)
        self.assertEqual(game.player.gold, completion_gold + REPAIR_BRIDGE_REWARD_GOLD)

    def test_lucian_marsh_chain_blackwater_bite_and_living_mud(self):
        game = GameState(seed=1, world=World())
        lucian = game.entities[game.named_npc_ids[NPC_LUCIAN]]
        game.player.map_id = lucian.map_id
        game.player.x, game.player.y = lucian.x - 1, lucian.y

        # Lucian's greeting doubles as the Blackwater Bite offer.
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNotNone(game.player.active_dialogue)
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_LUCIAN_BLACKWATER_OFFER)
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.active_quest_id, QUEST_BLACKWATER_BITE)
        self.assertEqual(game.player.quest_state, QUEST_STATE_ACTIVE)
        self.assertEqual(game.player.quest_target, BLACKWATER_TARGET)

        # Only snakes count, and only while Blackwater Bite is active.
        snakes = [e for e in game.beavers if e.subtype == ENEMY_SNAKE]
        self.assertGreaterEqual(len(snakes), BLACKWATER_TARGET)
        for snake in snakes[:BLACKWATER_TARGET]:
            game._damage_entity(snake, snake.hp, "ranged")
        self.assertEqual(game.player.quest_progress, BLACKWATER_TARGET)
        self.assertEqual(game.player.quest_state, QUEST_STATE_READY_TO_TURN_IN)
        start_xp = game.player.xp
        start_gold = game.player.gold

        # Returning to Lucian pays out Blackwater Bite and immediately offers
        # Living Mud in the same interaction.
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_LUCIAN_LIVING_MUD_OFFER)
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.xp, start_xp + BLACKWATER_REWARD_XP)
        self.assertEqual(game.player.gold, start_gold + BLACKWATER_REWARD_GOLD)
        self.assertEqual(game.player.active_quest_id, QUEST_LIVING_MUD)
        self.assertEqual(game.player.quest_state, QUEST_STATE_ACTIVE)

        # Slime kills guarantee samples -- never blocked by bad RNG -- until
        # both the oil and rust targets are met.
        slimes = [e for e in game.beavers if e.subtype == ENEMY_SLIME]
        required_kills = LIVING_MUD_OIL_TARGET + LIVING_MUD_RUST_TARGET
        self.assertGreaterEqual(len(slimes), required_kills)
        for slime in slimes[:required_kills]:
            game._damage_entity(slime, slime.hp, "ranged")
        self.assertEqual(game.player.inventory.count_item(ITEM_OIL_SAMPLE), LIVING_MUD_OIL_TARGET)
        self.assertEqual(game.player.inventory.count_item(ITEM_RUST_SAMPLE), LIVING_MUD_RUST_TARGET)
        self.assertEqual(game.player.quest_state, QUEST_STATE_READY_TO_TURN_IN)

        # Lucian doesn't understand the samples and redirects to Nerissa.
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_LUCIAN_SAMPLES_REDIRECT)
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.story_step, 1)
        # Samples are unaffected by the redirect -- still ready to hand off.
        self.assertEqual(game.player.quest_state, QUEST_STATE_READY_TO_TURN_IN)

        # Nerissa recognizes the machinery residue, takes the samples, and
        # points the player at the abandoned outpost.
        nerissa = game.entities[game.named_npc_ids[NPC_NERISSA]]
        game.player.x, game.player.y = nerissa.x - 1, nerissa.y
        mid_xp = game.player.xp
        mid_gold = game.player.gold
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_NERISSA_SAMPLES)
        finish_dialogue(game)
        self.assertIsNone(game.player.active_dialogue)
        # Living Mud is the last quest the scalar active_quest_id system
        # tracks -- it's cleared back to NONE/NOT_STARTED on completion so
        # "Living Mud done" doesn't linger as the HUD quest line for the
        # rest of the game (no later stage has a quest id to overwrite it).
        self.assertEqual(game.player.active_quest_id, QUEST_NONE)
        self.assertEqual(game.player.quest_state, QUEST_STATE_NOT_STARTED)
        self.assertEqual(game.player.xp, mid_xp + LIVING_MUD_REWARD_XP)
        self.assertEqual(game.player.gold, mid_gold + LIVING_MUD_REWARD_GOLD)
        self.assertEqual(game.player.inventory.count_item(ITEM_OIL_SAMPLE), 0)
        self.assertEqual(game.player.inventory.count_item(ITEM_RUST_SAMPLE), 0)
        self.assertEqual(game.player.story_stage, game_module.STORY_STAGE_GOBLIN_WARNED)

    def test_grix_warden_key_chain_proximity_pickup_and_turn_in(self):
        game = GameState(seed=1, world=World())
        game.player.story_stage = game_module.STORY_STAGE_GOBLIN_WARNED

        # Approaching within six tiles triggers the one-time proximity line.
        game.player.map_id = MAP_OVERWORLD
        game.player.x, game.player.y = GOBLIN_NPC_X - 6, GOBLIN_NPC_Y
        self.assertFalse(game.player.grix_callout_seen)
        game.finish_tick()
        self.assertTrue(game.player.grix_callout_seen)
        self.assertEqual(game.latest_activity_message, "Please don't hurt me! I need your help!")

        # It never re-fires once seen.
        prev_message = game.latest_activity_message
        game.finish_tick()
        self.assertEqual(game.latest_activity_message, prev_message)

        # Speaking with Grix opens the explanation; acknowledging it spawns
        # the player's personal Warden Key at the forest landmark.
        game.player.x, game.player.y = GOBLIN_NPC_X - 1, GOBLIN_NPC_Y
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNotNone(game.player.active_dialogue)
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_GRIX_EXPLAIN)
        for _ in range(len(game.player.active_dialogue.pages)):
            game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.story_stage, game_module.STORY_STAGE_WARDEN_KEY)

        map_id, key_x, key_y = game_module.WARDEN_KEY_MARKER
        key = game.item_at(map_id, key_x, key_y)
        self.assertIsNotNone(key)
        self.assertEqual(key.owner_id, game.player.token)

        # Another player can never pick up someone else's key.
        other = game.add_player(999, x=key_x, y=key_y, map_id=map_id)
        self.assertFalse(game.pickup_nearby_item(other))

        # The owner collects it; it persists immediately and a later tick
        # (the same one that would otherwise re-ensure it exists) does not
        # respawn a duplicate.
        game.player.map_id, game.player.x, game.player.y = map_id, key_x, key_y
        self.assertTrue(game.pickup_nearby_item(game.player))
        self.assertTrue(game.player.warden_key_collected)
        self.assertIsNone(game.item_at(map_id, key_x, key_y))
        game.finish_tick()
        self.assertIsNone(game.item_at(map_id, key_x, key_y))

        # Returning to Grix advances the objective to the cave/Gorvak stage.
        game.player.map_id = MAP_OVERWORLD
        game.player.x, game.player.y = GOBLIN_NPC_X - 1, GOBLIN_NPC_Y
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertEqual(game.player.active_dialogue.dialogue_id, game_module.story.DLG_GRIX_COMPLETE)
        for _ in range(len(game.player.active_dialogue.pages)):
            game.advance_dialogue(game.player)
        self.assertIsNone(game.player.active_dialogue)
        self.assertEqual(game.player.story_stage, game_module.STORY_STAGE_GORVAK)

        # Small talk afterward; Grix never re-explains or duplicates anything.
        self.assertTrue(game.interact_with_adjacent_npc())
        self.assertIsNone(game.player.active_dialogue)

    def test_overworld_death_respawns_at_grave_and_restores_hp(self):
        game = GameState(seed=1, world=World())
        game.player.x = 30
        game.player.y = 30
        game.player.health = 1
        beaver = game.beavers[0]
        beaver.x = 31
        beaver.y = 30
        game._apply_beaver_contact_damage()
        self.assertEqual((game.player.map_id, game.player.x, game.player.y), (MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1]))
        self.assertEqual(game.player.health, game.player.max_health)
        self.assertEqual(game.latest_message_id, MSG_RESPAWN_GRAVE)
        self.assertIsNotNone(game.latest_respawn_event)
        self.assertEqual(game.latest_respawn_event.x, OVERWORLD_RESPAWN[0])

    def test_stale_client_position_after_respawn_is_rejected(self):
        game = GameState(seed=1, world=World())
        game.player.x = 30
        game.player.y = 30
        game.player.health = 1
        game.beavers[0].x = 31
        game.beavers[0].y = 30
        game._apply_beaver_contact_damage()
        snapshot, accepted = game.step_player_state(
            PlayerStatePacket(1, 30, 30, CLIENT_AIM_RIGHT, 0, 0, 0, 0)
        )
        self.assertFalse(accepted)
        self.assertEqual((snapshot.player_x, snapshot.player_y), OVERWORLD_RESPAWN)
        self.assertEqual((game.player.x, game.player.y), OVERWORLD_RESPAWN)

    def test_cave_death_respawns_at_cave_entry(self):
        game = GameState(seed=1, map_id=MAP_STARTER_CAVE)
        game.player.x = 20
        game.player.y = 10
        game.player.health = 1
        beaver = game.beavers[0]
        beaver.x = 21
        beaver.y = 10
        game._apply_beaver_contact_damage()
        self.assertEqual((game.player.map_id, game.player.x, game.player.y), (MAP_STARTER_CAVE, STARTER_CAVE_ENTRY[0], STARTER_CAVE_ENTRY[1]))
        self.assertEqual(game.player.health, game.player.max_health)
        self.assertEqual(game.latest_message_id, MSG_RESPAWN_CAVE)
        self.assertEqual(game.respawn_event_packet(9).map_id, MAP_STARTER_CAVE)

    def test_hud_quest_and_message_packet_models_reflect_player_state(self):
        game = GameState(seed=1, world=World())
        game.player.x = FARMER_X - 1
        game.player.y = FARMER_Y
        game.interact_with_adjacent_npc()
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        hud = game.hud_update_packet(7)
        quest = game.quest_update_packet(8)
        message = game.message_packet(9)
        self.assertEqual((hud.hp, hud.max_hp, hud.level, hud.xp_next), (12, 12, 1, 20))
        self.assertEqual(
            (quest.quest_id, quest.state, quest.text),
            (QUEST_ROAD_TROUBLE, QUEST_STATE_ACTIVE, f"Save My Orchard 0/{ROAD_TROUBLE_TARGET}"),
        )
        self.assertEqual(message.message_id, MSG_QUEST_STARTED)

    def test_quest_update_packet_previews_pending_offer_name(self):
        game = GameState(seed=1, world=World())
        game.player.x = FARMER_X - 1
        game.player.y = FARMER_Y
        # Before any interaction, no offer is pending.
        quest = game.quest_update_packet(1)
        self.assertEqual((quest.quest_id, quest.state, quest.text), (QUEST_NONE, QUEST_STATE_NOT_STARTED, ""))
        # The first interaction sets a pending offer and opens the offer
        # modal in the same step -- the preview needs the quest's real name
        # here, not the ongoing tracker (which is still blank, since
        # nothing has been accepted yet).
        game.interact_with_adjacent_npc()
        self.assertEqual(game.player.pending_quest_offer_id, QUEST_ROAD_TROUBLE)
        quest = game.quest_update_packet(2)
        self.assertEqual(
            (quest.quest_id, quest.state, quest.text),
            (QUEST_ROAD_TROUBLE, QUEST_STATE_NOT_STARTED, "Save My Orchard"),
        )
        # Acknowledging the offer dialogue clears the preview and reverts to
        # the ongoing tracker.
        game.advance_dialogue(game.player)
        game.advance_dialogue(game.player)
        quest = game.quest_update_packet(3)
        self.assertEqual(
            (quest.quest_id, quest.state, quest.text),
            (QUEST_ROAD_TROUBLE, QUEST_STATE_ACTIVE, f"Save My Orchard 0/{ROAD_TROUBLE_TARGET}"),
        )

    def test_farmer_tile_is_overlaid_in_window_and_row_tiles(self):
        game = GameState(seed=1, world=World())
        # Daniel stands well away from the map origin in the hand-authored
        # overworld, so the window has to be opened over him.
        origin_x, origin_y = FARMER_X - 4, FARMER_Y - 4
        window = game.window_at(origin_x, origin_y)
        self.assertEqual(
            window.tiles[(FARMER_Y - origin_y) * window.width + (FARMER_X - origin_x)],
            DANIEL_TILE,
        )
        row = game.window_row_tiles(origin_x, FARMER_Y)  # default player, overworld
        self.assertEqual(row[FARMER_X - origin_x], DANIEL_TILE)
        # A player on the cave map sees no overworld-farmer overlay in its row.
        cave_token = 4242
        game.add_player(cave_token, map_id=MAP_STARTER_CAVE)
        cave_row = game.window_row_tiles(origin_x, FARMER_Y, cave_token)
        self.assertNotEqual(cave_row[FARMER_X - origin_x], DANIEL_TILE)

    def test_named_story_npcs_spawn_from_generated_layout(self):
        game = GameState(seed=1, world=World())
        self.assertNotEqual(game.farmer_entity_id, 0)
        self.assertNotEqual(game.goblin_npc_entity_id, 0)
        self.assertEqual(game.entities[game.farmer_entity_id].subtype, NPC_DANIEL)
        self.assertEqual(game.entities[game.goblin_npc_entity_id].subtype, NPC_GRIX)

    def test_enemy_can_enter_grass_herb_and_stumps(self):
        world = World()
        self.assertTrue(world.enemy_can_enter(10, 10))
        world.set_tile(11, 10, HERB)
        self.assertTrue(world.enemy_can_enter(11, 10))
        world.set_tile(12, 10, TREE_STUMP)
        self.assertTrue(world.enemy_can_enter(12, 10))

    def test_tick_output_is_deterministic(self):
        game_a = GameState(seed=0x1234, world=World())
        game_b = GameState(seed=0x1234, world=World())
        inputs = [
            InputIntent(1, 0x07, 0, 0x07, 0),
            InputIntent(2, 0x0D, 0, 0x0D, 1),
            InputIntent(3, 0x0B, 0, 0x0B, 2),
            InputIntent(4, 0x0E, 0, 0x0E, 3),
        ]
        snapshots_a = [game_a.step(intent) for intent in inputs]
        snapshots_b = [game_b.step(intent) for intent in inputs]
        self.assertEqual(snapshots_a, snapshots_b)

    def test_seeded_world_is_deterministic(self):
        world_a = build_seeded_world(0x1234)
        world_b = build_seeded_world(0x1234)
        self.assertEqual(world_a.tiles, world_b.tiles)
        self.assertGreaterEqual(sum(1 for tile in world_a.tiles if tile == TREE_FULL), 240)
        # The layout is hand-authored (see world_layout_data.py), not
        # procedurally generated, so this is a sanity floor rather than an
        # exact count tied to a specific RNG seed.
        self.assertGreaterEqual(sum(1 for tile in world_a.tiles if tile == HERB), 40)

    def test_phase8_overworld_layout_has_town_road_forest_and_cave(self):
        world = build_world_map(MAP_OVERWORLD, 0x1234)
        # `O` (the new-player spawn) and `X` (the death-respawn grave) are
        # separate markers in the map CSV -- the grave is the one that paints
        # a GRAVE tile, and a player must be able to stand on its spawn.
        self.assertEqual(world.tile(*OVERWORLD_RESPAWN), GRAVE)
        self.assertTrue(world.player_can_enter(*OVERWORLD_START))
        self.assertEqual(world.tile(*OVERWORLD_CAVE_ENTRANCE), CAVE_ENTRANCE)
        # Daniel has to stand somewhere a player can reach him; what grows
        # beside him is the map author's business.
        self.assertIn(world.tile(FARMER_X, FARMER_Y), (GRASS, ROAD))
        self.assertTrue(world.player_can_enter(FARMER_X, FARMER_Y))
        self.assertEqual(world.tile(*OVERWORLD_CAVE_ENTRANCE), CAVE_ENTRANCE)
        self.assertGreaterEqual(sum(1 for tile in world.tiles if tile == TREE_FULL), 240)

    def test_phase8_starter_cave_layout_has_floor_walls_and_exit(self):
        world = build_world_map(MAP_STARTER_CAVE, 0x1234)
        self.assertEqual(world.tile(*STARTER_CAVE_ENTRY), CAVE_FLOOR)
        self.assertEqual(world.tile(*STARTER_CAVE_EXIT), CAVE_EXIT)
        self.assertEqual(world.tile(2, 2), CAVE_WALL)
        self.assertEqual(world.tile(0, 0), BORDER)
        self.assertTrue(world.player_can_enter(*STARTER_CAVE_ENTRY))
        self.assertFalse(world.player_can_enter(2, 2))
        # HERB counts as walkable floor too (same as the BFS below, via
        # player_can_enter) -- the cave layout has a handful of them.
        floor_tiles = sum(1 for tile in world.tiles if tile in (CAVE_FLOOR, CAVE_EXIT, HERB))
        self.assertGreaterEqual(floor_tiles, 2500)
        visited = {STARTER_CAVE_ENTRY}
        queue = deque([STARTER_CAVE_ENTRY])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) not in visited and world.player_can_enter(nx, ny):
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        self.assertEqual(len(visited), floor_tiles)
        self.assertIn(STARTER_CAVE_EXIT, visited)

    def test_phase25_pvp_realm_layout_has_grass_border_and_exit(self):
        world = build_world_map(MAP_PVP_REALM, 0x1234)
        self.assertEqual(world.tile(0, 0), BORDER)
        self.assertEqual(world.tile(2, 2), GRASS)
        self.assertEqual(world.tile(*PVP_REALM_ENTRY), GRASS)
        self.assertEqual(world.tile(*PVP_REALM_EXIT), CAVE_EXIT)
        self.assertEqual(world.tile(126, 94), GRASS)

    def test_phase25_player_transitions_to_pvp_realm_and_sets_respawn(self):
        game = GameState(seed=1)
        game.player.level = 10
        game.player.pvp_unlocked = True
        game.player.pvp_enabled = False
        game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=OVERWORLD_PVP_REALM_ENTRANCE[0],
                y=OVERWORLD_PVP_REALM_ENTRANCE[1],
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertEqual(game.player.map_id, MAP_PVP_REALM)
        self.assertEqual((game.player.x, game.player.y), PVP_REALM_ENTRY)
        self.assertEqual(game.player.respawn_map_id, MAP_PVP_REALM)
        self.assertEqual((game.player.respawn_x, game.player.respawn_y), PVP_REALM_RESPAWN)
        self.assertTrue(game.player.pvp_enabled)
        self.assertIsNotNone(game.pending_map_change)

    def test_phase25_player_transitions_back_from_pvp_realm_and_clears_forced_pvp(self):
        game = GameState(seed=1, map_id=MAP_PVP_REALM)
        game.player.x, game.player.y = PVP_REALM_ENTRY
        game.player.pvp_enabled = True
        game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=PVP_REALM_EXIT[0],
                y=PVP_REALM_EXIT[1],
                facing=CLIENT_AIM_LEFT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertEqual(game.player.map_id, MAP_OVERWORLD)
        self.assertEqual((game.player.x, game.player.y), OVERWORLD_PVP_REALM_RETURN)
        self.assertFalse(game.player.pvp_enabled)

    def test_phase68_pvp_realm_entry_requires_story_completion(self):
        game = GameState(seed=1)
        game.player.level = 10
        self.assertFalse(game.player.pvp_unlocked)
        accepted = game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=OVERWORLD_PVP_REALM_ENTRANCE[0],
                y=OVERWORLD_PVP_REALM_ENTRANCE[1],
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertTrue(accepted)
        self.assertEqual(game.player.map_id, MAP_OVERWORLD)
        self.assertEqual((game.player.x, game.player.y), OVERWORLD_PVP_REALM_ENTRANCE)
        self.assertIsNone(game.pending_map_change)
        self.assertEqual(
            game.latest_activity_message,
            "Defeat Gorvak, then see Nerissa.",
        )
        self.assertEqual(game.latest_message_id, MSG_PVP_ARENA_LOCKED)

    def test_phase25_pvp_realm_entry_requires_level_5(self):
        game = GameState(seed=1)
        game.player.level = 4
        game.player.pvp_unlocked = True
        accepted = game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=OVERWORLD_PVP_REALM_ENTRANCE[0],
                y=OVERWORLD_PVP_REALM_ENTRANCE[1],
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertTrue(accepted)
        self.assertEqual(game.player.map_id, MAP_OVERWORLD)
        self.assertEqual((game.player.x, game.player.y), OVERWORLD_PVP_REALM_ENTRANCE)
        self.assertIsNone(game.pending_map_change)
        self.assertEqual(
            game.latest_activity_message,
            "You must be lvl 5 for PvP.",
        )
        self.assertEqual(game.latest_message_id, MSG_PVP_ARENA_LOCKED)

    def test_map_summary_marks_current_zone_and_hides_unvisited(self):
        game = GameState(seed=1)
        packet = game.map_summary_packet(seq=1)
        self.assertEqual((packet.width, packet.height), (8, 6))
        current = packet.cells[0]
        self.assertTrue(current & MAP_SUMMARY_VISITED)
        self.assertTrue(current & MAP_SUMMARY_CURRENT)
        current_zone = zone_for_tile(game.player.map_id, game.player.x, game.player.y)
        self.assertEqual(current & 0xC0, game._map_marker_flags(current_zone))
        self.assertEqual(packet.cells[1], 0)

    def test_map_summary_tracks_maps_separately_and_discovers_cave_marker(self):
        game = GameState(seed=1)
        game.player.x, game.player.y = OVERWORLD_CAVE_ENTRANCE
        game.update_active_zones()
        overworld = game.map_summary_packet(seq=1)
        cave_zone_index = (OVERWORLD_CAVE_ENTRANCE[1] // 16) * 8 + (OVERWORLD_CAVE_ENTRANCE[0] // 16)
        self.assertEqual(overworld.cells[cave_zone_index] & 0xC0, MAP_SUMMARY_MARKER_CAVE)
        game.player.map_id = MAP_STARTER_CAVE
        game.player.x, game.player.y = STARTER_CAVE_ENTRY
        game.update_active_zones()
        cave = game.map_summary_packet(seq=2)
        self.assertEqual(cave.map_id, MAP_STARTER_CAVE)
        self.assertTrue(cave.cells[0] & MAP_SUMMARY_CURRENT)
        self.assertEqual(cave.cells[1], 0)

    def test_phase8_player_transitions_to_cave_and_sets_respawn(self):
        game = GameState(seed=1)
        game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=OVERWORLD_CAVE_ENTRANCE[0],
                y=OVERWORLD_CAVE_ENTRANCE[1],
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertEqual(game.player.map_id, MAP_STARTER_CAVE)
        self.assertEqual((game.player.x, game.player.y), STARTER_CAVE_ENTRY)
        self.assertEqual(game.player.respawn_map_id, MAP_STARTER_CAVE)
        self.assertEqual((game.player.respawn_x, game.player.respawn_y), STARTER_CAVE_RESPAWN)
        self.assertIsNotNone(game.pending_map_change)
        self.assertEqual(game.world.tile(*STARTER_CAVE_ENTRY), CAVE_FLOOR)

    def test_phase8_player_transitions_back_to_overworld(self):
        game = GameState(seed=1, map_id=MAP_STARTER_CAVE)
        game.player.x, game.player.y = STARTER_CAVE_ENTRY
        game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=STARTER_CAVE_EXIT[0],
                y=STARTER_CAVE_EXIT[1],
                facing=CLIENT_AIM_LEFT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertEqual(game.player.map_id, MAP_OVERWORLD)
        self.assertEqual((game.player.x, game.player.y), OVERWORLD_CAVE_RETURN)
        self.assertIsNotNone(game.pending_map_change)

    def test_phase8_cave_entry_does_not_immediately_bounce_to_overworld(self):
        game = GameState(seed=1)
        game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=OVERWORLD_CAVE_ENTRANCE[0],
                y=OVERWORLD_CAVE_ENTRANCE[1],
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        game.consume_pending_map_change()
        # Play is paused until the client reports MAP_READY (the hybrid
        # server re-sends MAP_CHANGE until then); model the ready client.
        self.assertTrue(game.mark_player_map_ready(game.player.token))
        # The transition holds the player at the spawn until the client
        # echoes it (stale old-map coords must not teleport the player).
        snapshot, accepted = game.step_player_state(
            PlayerStatePacket(
                seq=2,
                x=STARTER_CAVE_ENTRY[0],
                y=STARTER_CAVE_ENTRY[1],
                facing=CLIENT_AIM_LEFT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=1,
            )
        )
        self.assertTrue(accepted)
        snapshot, accepted = game.step_player_state(
            PlayerStatePacket(
                seq=3,
                x=STARTER_CAVE_EXIT[0],
                y=STARTER_CAVE_EXIT[1],
                facing=CLIENT_AIM_LEFT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=2,
            )
        )
        self.assertTrue(accepted)
        self.assertEqual(game.player.map_id, MAP_STARTER_CAVE)
        self.assertEqual((snapshot.player_x, snapshot.player_y), STARTER_CAVE_EXIT)
        self.assertIsNone(game.pending_map_change)

    def test_world_window_tiles_are_row_major_and_border_filled(self):
        world = World()
        world.set_tile(2, 2, HERB)
        tiles = world.window_tiles(-1, 1, 4, 3)
        self.assertEqual(len(tiles), 12)
        self.assertEqual(tiles[0], BORDER)
        self.assertEqual(tiles[7], HERB)

    def test_game_window_centers_near_player(self):
        game = GameState(seed=1, world=World())
        game.player.x = 20
        game.player.y = 20
        window = game.window()
        self.assertEqual((window.width, window.height), (32, 24))
        self.assertEqual((window.origin_x, window.origin_y), (4, 8))
        self.assertEqual(len(window.tiles), 768)

    def test_game_needs_window_near_window_edge(self):
        game = GameState(seed=1, world=World())
        old_origin = game.window_origin()
        self.assertFalse(game.needs_window(*old_origin))
        game.player.x = old_origin[0] + 29
        self.assertTrue(game.needs_window(*old_origin))
        self.assertEqual(game.next_window_origin(*old_origin), (1, old_origin[1]))
        edge = game.edge_window(*old_origin, *game.next_window_origin(*old_origin))
        self.assertEqual((edge.origin_x, edge.origin_y, edge.width, edge.height), (32, 0, 1, 24))

    def test_game_bottom_edge_not_masked_by_left_boundary(self):
        game = GameState(seed=1, world=World())
        old_origin = game.window_origin()
        game.player.x = old_origin[0] + 10
        game.player.y = old_origin[1] + 18
        self.assertTrue(game.needs_window(*old_origin))
        self.assertEqual(game.next_window_origin(*old_origin), (old_origin[0], old_origin[1] + 1))
        edge = game.edge_window(*old_origin, *game.next_window_origin(*old_origin))
        self.assertEqual((edge.origin_x, edge.origin_y, edge.width, edge.height), (0, 24, 32, 1))

    def test_realtime_window_origin_advances_without_oscillation(self):
        game = GameState(seed=1, world=World())
        game.player.x = 31
        game.player.y = 24
        origin = (12, 12)
        origins = []
        for _ in range(8):
            origin = game.next_window_origin_toward_player(*origin)
            origins.append(origin)
        self.assertEqual(origins[0], (13, 12))
        self.assertEqual(origins[-1], (15, 12))
        self.assertNotIn((12, 12), origins)

    def test_held_direction_remains_responsive(self):
        game = GameState(seed=1, world=World())
        for tick in range(1, 4):
            game.step(InputIntent(tick, 0x07, 0, 0x07, tick - 1))
        self.assertEqual((game.player.x, game.player.y), (13, 10))

    def test_beaver_chops_adjacent_tree_to_damage_then_stump(self):
        world = World()
        world.set_tile(18, 9, TREE_FULL)
        game = GameState(seed=1, world=world)
        game.beavers[0].x = 18
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        snapshot = game.step(InputIntent(1, 0x0F, 0, 0, 0))
        self.assertEqual(world.tile(18, 9), TREE_DAMAGED)
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (18, 9, TREE_DAMAGED))

        game.beavers[0].chop_cooldown = 0
        snapshot = game.step(InputIntent(2, 0x0F, 0, 0, 1))
        self.assertEqual(world.tile(18, 9), TREE_STUMP)
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (18, 9, TREE_STUMP))

    def test_snapshot_reports_at_most_one_tile_update_per_tick(self):
        world = World()
        world.set_tile(18, 9, TREE_FULL)
        world.set_tile(24, 13, TREE_FULL)
        game = GameState(seed=1, world=world)
        game.beavers[0].x = 18
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        snapshot = game.step(InputIntent(1, 0x0F, 0, 0, 0))
        self.assertEqual((snapshot.tile_x, snapshot.tile_y), (18, 9))
        self.assertEqual(world.tile(18, 9), TREE_DAMAGED)
        self.assertEqual(world.tile(24, 13), TREE_FULL)

    def test_snapshot_for_window_filters_entities_and_tile_updates(self):
        world = World()
        game = GameState(seed=1, world=world)
        # Every other static-spawned beaver needs to be well outside the
        # window under test, not just the three this test repositions
        # on purpose -- otherwise whichever beavers keep their default
        # STATIC_ENEMY_SPAWNS position may coincidentally fall inside it.
        for beaver in game.beavers:
            beaver.x, beaver.y = 90, 90
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        game.beavers[1].x = 40
        game.beavers[1].y = 40
        game.beavers[1].hp = 0
        game.beavers[2].x = 41
        game.beavers[2].y = 41
        game.tile_update = (40, 40, TREE_STUMP)
        snapshot = game.snapshot_for_window(0, 4)
        self.assertEqual([(beaver.x, beaver.y, beaver.hp) for beaver in snapshot.beavers], [(12, 10, 4)])
        self.assertEqual((snapshot.tile_x, snapshot.tile_y, snapshot.tile_id), (0, 0, 0))

    def test_fire_intent_damages_and_kills_beaver(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        snapshot = game.step(InputIntent(1, 0x0F, 1, 3, 0))
        self.assertEqual(snapshot.beavers[0].hp, 1)
        self.assertEqual(snapshot.score, 0)
        self.assertIn("You shoot the beaver.", game.activity_messages)

        game.step(InputIntent(2, 0x0F, 0, 4, 1))
        snapshot = game.step(InputIntent(3, 0x0F, 1, 3, 2))
        self.assertNotIn((12, 10, 0), [(beaver.x, beaver.y, beaver.hp) for beaver in snapshot.beavers])
        self.assertEqual(snapshot.score, 10)
        self.assertEqual(game.player.xp, 3)
        self.assertEqual(game.player.gold, 0)
        self.assertEqual(game.latest_activity_message, "You killed a beaver.")

    def test_hunter_ranged_attack_stops_on_blocking_terrain(self):
        world = World()
        world.set_tile(11, 10, TREE_FULL)
        game = GameState(seed=1, world=world)
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        snapshot = game.step(InputIntent(1, 0x0F, 1, 3, 0))
        self.assertEqual(snapshot.beavers[0].hp, 4)
        self.assertEqual(game.latest_activity_message, "")

    def test_hunter_adjacent_melee_fallback_damages_enemy(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 11
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        snapshot = game.step(InputIntent(1, 0x0F, 1, 3, 0))
        self.assertEqual(snapshot.beavers[0].hp, 3)
        self.assertIn("You hit the beaver.", game.activity_messages)

    def test_repeated_fire_intents_damage_again(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        game.step(InputIntent(1, 0x0F, 1, 3, 0))
        snapshot = game.step(InputIntent(2, 0x0F, 1, 3, 1))
        self.assertNotIn((12, 10, 0), [(beaver.x, beaver.y, beaver.hp) for beaver in snapshot.beavers])

    def test_realtime_fire_counter_damages_beaver_with_facing_direction(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        snapshot, accepted = game.step_player_state(
            PlayerStatePacket(
                seq=1,
                x=10,
                y=10,
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=1,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertTrue(accepted)
        self.assertEqual(snapshot.beavers[0].hp, 1)

    def test_client_aim_delta_supports_four_diagonal_shots(self):
        self.assertEqual(client_aim_delta(CLIENT_AIM_UP_LEFT), (-1, -1))
        self.assertEqual(client_aim_delta(CLIENT_AIM_UP_RIGHT), (1, -1))
        self.assertEqual(client_aim_delta(CLIENT_AIM_DOWN_LEFT), (-1, 1))
        self.assertEqual(client_aim_delta(CLIENT_AIM_DOWN_RIGHT), (1, 1))
        for invalid in (8, 9, 255):
            with self.subTest(invalid=invalid):
                self.assertEqual(client_aim_delta(invalid), (0, 0))

    def test_realtime_diagonal_shots_hit_first_enemy_on_each_clear_ray(self):
        cases = (
            (CLIENT_AIM_UP_LEFT, 8, 8),
            (CLIENT_AIM_UP_RIGHT, 12, 8),
            (CLIENT_AIM_DOWN_LEFT, 8, 12),
            (CLIENT_AIM_DOWN_RIGHT, 12, 12),
        )
        for facing, target_x, target_y in cases:
            with self.subTest(facing=facing):
                game = GameState(seed=1, world=World())
                self._park_beavers(game)
                target = game.beavers[0]
                target.x, target.y = target_x, target_y
                self._reset_as_beaver(target)
                start_hp = target.hp
                _, accepted = game.step_player_state(
                    PlayerStatePacket(1, 10, 10, facing, 0, 1, 0, 0)
                )
                self.assertTrue(accepted)
                self.assertLess(target.hp, start_hp)

    def test_diagonal_shot_cannot_hit_through_either_corner_side(self):
        for blocker_x, blocker_y in ((11, 10), (10, 11)):
            with self.subTest(blocker=(blocker_x, blocker_y)):
                world = World()
                world.set_tile(blocker_x, blocker_y, TREE_FULL)
                game = GameState(seed=1, world=world)
                self._park_beavers(game)
                target = game.beavers[0]
                target.x, target.y = 11, 11
                self._reset_as_beaver(target)
                start_hp = target.hp
                game.step_player_state(
                    PlayerStatePacket(1, 10, 10, CLIENT_AIM_DOWN_RIGHT, 0, 1, 0, 0)
                )
                self.assertEqual(target.hp, start_hp)

    def test_diagonal_corner_uses_existing_static_blocker_set(self):
        for tile in (TREE_FULL, TREE_DAMAGED, BORDER, WATER, BUILDING, CAVE_WALL):
            with self.subTest(tile=tile):
                world = World()
                world.set_tile(11, 10, tile)
                game = GameState(seed=1, world=world)
                self._park_beavers(game)
                target = game.beavers[0]
                target.x, target.y = 12, 12
                self._reset_as_beaver(target)
                start_hp = target.hp
                game.step_player_state(
                    PlayerStatePacket(1, 10, 10, CLIENT_AIM_DOWN_RIGHT, 0, 1, 0, 0)
                )
                self.assertEqual(target.hp, start_hp)

    def test_diagonal_shot_passes_stump_corner_and_respects_six_step_range(self):
        world = World()
        world.set_tile(11, 10, TREE_STUMP)
        game = GameState(seed=1, world=world)
        self._park_beavers(game)
        target = game.beavers[0]
        target.x, target.y = 16, 16
        self._reset_as_beaver(target)
        start_hp = target.hp
        game.step_player_state(
            PlayerStatePacket(1, 10, 10, CLIENT_AIM_DOWN_RIGHT, 0, 1, 0, 0)
        )
        self.assertLess(target.hp, start_hp)

        target.x, target.y = 17, 17
        target.hp = start_hp
        game.step_player_state(
            PlayerStatePacket(2, 10, 10, CLIENT_AIM_DOWN_RIGHT, 0, 2, 0, 0)
        )
        self.assertEqual(target.hp, start_hp)

    def test_ranged_fire_passes_through_stump(self):
        world = World()
        world.set_tile(11, 10, TREE_STUMP)
        game = GameState(seed=1, world=world)
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        start_hp = game.beavers[0].hp
        snapshot, accepted = game.step_player_state(
            PlayerStatePacket(1, 10, 10, CLIENT_AIM_RIGHT, 0, 1, 0, 0)
        )
        self.assertTrue(accepted)
        self.assertLess(snapshot.beavers[0].hp, start_hp)

    def test_ranged_fire_still_stops_on_full_and_damaged_trees(self):
        for tile in (TREE_FULL, TREE_DAMAGED):
            with self.subTest(tile=tile):
                world = World()
                world.set_tile(11, 10, tile)
                game = GameState(seed=1, world=world)
                game.beavers[0].x = 12
                game.beavers[0].y = 10
                start_hp = game.beavers[0].hp
                snapshot, accepted = game.step_player_state(
                    PlayerStatePacket(1, 10, 10, CLIENT_AIM_RIGHT, 0, 1, 0, 0)
                )
                self.assertTrue(accepted)
                self.assertEqual(snapshot.beavers[0].hp, start_hp)

    def test_realtime_fire_counter_is_not_replayed(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        packet = PlayerStatePacket(
            seq=1,
            x=10,
            y=10,
            facing=CLIENT_AIM_RIGHT,
            buttons=0,
            fire_counter=1,
            pickup_counter=0,
            last_server_seq=0,
        )
        game.step_player_state(packet)
        snapshot, accepted = game.step_player_state(packet)
        self.assertTrue(accepted)
        self.assertEqual(snapshot.beavers[0].hp, 1)

    def test_realtime_pickup_counter_is_detected_once_per_change(self):
        game = GameState(seed=1, world=World())
        game.player.x = 50
        game.player.y = 50
        game._sync_player_entity(game.player)
        packet = PlayerStatePacket(
            seq=1,
            x=50,
            y=50,
            facing=CLIENT_AIM_RIGHT,
            buttons=0,
            fire_counter=0,
            pickup_counter=1,
            last_server_seq=0,
        )
        game.step_player_state(packet)
        self.assertEqual(game.player_pickup_events, 1)
        game.step_player_state(packet)
        self.assertEqual(game.player_pickup_events, 1)
        game.step_player_state(
            PlayerStatePacket(
                seq=2,
                x=50,
                y=50,
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=2,
                last_server_seq=0,
            )
        )
        self.assertEqual(game.player_pickup_events, 2)

    def test_realtime_pickup_counter_wraparound_is_detected(self):
        game = GameState(seed=1, world=World())
        game.player.x = 50
        game.player.y = 50
        game._sync_player_entity(game.player)
        game.step_player_state(
            PlayerStatePacket(
                seq=1,
                x=50,
                y=50,
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=255,
                last_server_seq=0,
            )
        )
        game.step_player_state(
            PlayerStatePacket(
                seq=2,
                x=50,
                y=50,
                facing=CLIENT_AIM_RIGHT,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertEqual(game.player_pickup_events, 2)

    def test_realtime_fire_button_edge_damages_beaver_without_counter(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 10
        game.beavers[0].y = 9
        self._reset_as_beaver(game.beavers[0])
        snapshot, accepted = game.step_player_state(
            PlayerStatePacket(
                seq=1,
                x=10,
                y=10,
                facing=CLIENT_AIM_UP,
                buttons=1,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertTrue(accepted)
        self.assertEqual(snapshot.beavers[0].hp, 3)

    def test_held_fire_new_aim_hits_adjacent_beaver(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 9
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        game.step(InputIntent(1, 0x0F, 1, 3, 0))
        snapshot = game.step(InputIntent(2, 0x0F, 1, 2, 1))
        self.assertEqual(snapshot.beavers[0].hp, 3)

    def test_fire_intent_does_not_move_player(self):
        game = GameState(seed=1, world=World())
        game.step(InputIntent(1, 0x07, 1, 3, 0))
        self.assertEqual((game.player.x, game.player.y), (10, 10))

    def test_adjacent_beaver_damages_player_with_cooldown(self):
        game = GameState(seed=1, world=World())
        game.beavers[0].x = 11
        game.beavers[0].y = 10
        self._reset_as_beaver(game.beavers[0])
        snapshot = game.step(InputIntent(1, 0x0F, 0, 0, 0))
        self.assertEqual(snapshot.health, 11)
        self.assertEqual(game.latest_message_id, MSG_BEAVER_BITES)
        snapshot = game.step(InputIntent(2, 0x0F, 0, 0, 1))
        self.assertEqual(snapshot.health, 11)
        for tick in range(BEAVER_ATTACK_COOLDOWN):
            snapshot = game.step(InputIntent(3 + tick, 0x0F, 0, 0, 2 + tick))
        self.assertEqual(snapshot.health, 10)

    def test_damaged_beaver_chases_from_outside_normal_aggro_range(self):
        game = GameState(seed=1, world=World())
        beaver = game.beavers[0]
        beaver.x = 20
        beaver.y = 10
        # Movement is gated to the beaver's home zone; pin home to the test
        # position rather than relying on wherever this beaver's static
        # spawn point happens to be.
        beaver.home_x = 20
        beaver.home_y = 10
        beaver.aggro_ticks = 2
        beaver.move_cooldown = 0
        game._move_beavers()
        self.assertEqual((beaver.x, beaver.y), (19, 10))


if __name__ == "__main__":
    unittest.main()
