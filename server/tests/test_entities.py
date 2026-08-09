import unittest

from server.entities import (
    ENEMY_BEAVER,
    ENTITY_ENEMY,
    ENTITY_FLAG_BLOCKING,
    ENTITY_FLAG_TEMPORARY,
    ENTITY_FLAG_VISIBLE,
    ENTITY_PLAYER,
)
from server.game import GameState, PlayerState
from server.protocol import MAX_BEAVERS
from server.world import GRASS, MAP_OVERWORLD
from server.zones import SpawnRule, ZoneId, zone_for_tile


class EntityTest(unittest.TestCase):
    def test_next_entity_id_skips_zero_and_occupied_ids(self):
        game = GameState(seed=1)
        game.next_entity_counter = 255
        first = game.next_entity_id()
        second = game.next_entity_id()
        self.assertEqual(first, 255)
        self.assertNotEqual(second, 0)
        self.assertNotIn(second, game.entities)

    def test_entity_lookup_and_window_filter_dynamic_entities(self):
        game = GameState(seed=1)
        entity = game.spawn_entity(
            kind=ENTITY_ENEMY,
            subtype=ENEMY_BEAVER,
            map_id=MAP_OVERWORLD,
            x=15,
            y=12,
            hp=2,
            max_hp=2,
            flags=ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING,
        )
        self.assertIs(game.entity_at(MAP_OVERWORLD, 15, 12), entity)
        self.assertIn(entity, game.entities_in_window(MAP_OVERWORLD, 10, 10, 10, 10))
        self.assertNotIn(entity, game.entities_in_window(MAP_OVERWORLD, 0, 0, 5, 5))

    def test_spawn_rule_creates_temporary_enemy_tied_to_zone(self):
        game = GameState(seed=1)
        zone_id = ZoneId(MAP_OVERWORLD, 2, 2)
        rule = SpawnRule(ENTITY_ENEMY, ENEMY_BEAVER, 1, 2, 1, 1, 20, (GRASS,))
        entity = game._spawn_from_rule(zone_id, rule, 32, 32)
        self.assertEqual(entity.kind, ENTITY_ENEMY)
        self.assertEqual(entity.subtype, ENEMY_BEAVER)
        self.assertEqual(entity.zone_id, zone_id)
        self.assertTrue(entity.is_temporary)
        self.assertIn(entity, game.beavers)

    def test_zone_activation_can_spawn_from_zone_definition(self):
        game = GameState(seed=1, zone_spawns_enabled=True)
        # A zone only spawns where its rule's allowed terrain actually exists.
        # Zone (2,2) is town and water in the hand-authored overworld, so its
        # beaver rule can never place; pick a zone that can.
        zone_id = next(
            candidate
            for candidate in (
                ZoneId(MAP_OVERWORLD, zx, zy) for zx in range(8) for zy in range(8)
            )
            if game.zone_definition(candidate).spawn_table
            and all(
                game._find_spawn_tile(candidate, rule) is not None
                for rule in game.zone_definition(candidate).spawn_table
            )
            # ...and is not already at its cap from world generation, or
            # activation is a no-op.
            and not any(entity.is_live for entity in game.entities_in_zone(candidate))
        )
        existing = set(game.entities)
        game.activate_zone(zone_id)
        spawned = [entity for entity_id, entity in game.entities.items() if entity_id not in existing]
        self.assertEqual(len(spawned), 1)
        self.assertEqual(spawned[0].zone_id, zone_id)
        self.assertIn(spawned[0].entity_id, game.active_zone_states[zone_id].spawned_entity_ids)

    def test_deactivate_zone_removes_temporary_entities_but_keeps_remote_players(self):
        game = GameState(seed=1, zone_spawns_enabled=True)
        zone_id = ZoneId(MAP_OVERWORLD, 2, 2)
        game.activate_zone(zone_id)
        game.add_player(44, x=33, y=33, map_id=MAP_OVERWORLD)
        remote_entity_id = game.player_entities[44]
        spawned_ids = set(game.active_zone_states[zone_id].spawned_entity_ids)
        game.deactivate_zone(zone_id)
        self.assertTrue(spawned_ids.isdisjoint(game.entities))
        self.assertIn(remote_entity_id, game.entities)
        self.assertEqual(game.entities[remote_entity_id].kind, ENTITY_PLAYER)

    def test_legacy_beaver_snapshots_are_derived_from_entities(self):
        game = GameState(seed=1)
        game.beavers[0].x = 12
        game.beavers[0].y = 10
        snapshot = game.snapshot()
        self.assertEqual(len(snapshot.beavers), MAX_BEAVERS)
        self.assertEqual((snapshot.beavers[0].x, snapshot.beavers[0].y), (12, 10))
        self.assertEqual(snapshot.beavers[0].hp, game.beavers[0].hp)

    def test_remote_players_are_generic_player_entities(self):
        game = GameState(seed=1)
        game.add_player(99, x=80, y=80, map_id=MAP_OVERWORLD)
        entity = game.entities[game.player_entities[99]]
        self.assertEqual(entity.kind, ENTITY_PLAYER)
        self.assertEqual(entity.owner_id, 99)
        self.assertEqual(entity.zone_id, zone_for_tile(MAP_OVERWORLD, 80, 80))


if __name__ == "__main__":
    unittest.main()
