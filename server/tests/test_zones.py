import unittest

from server.game import GameState, PlayerState
from server.protocol import PlayerStatePacket
from server.world import MAP_OVERWORLD, MAP_STARTER_CAVE, OVERWORLD_CAVE_ENTRANCE
from server.zones import (
    ACTIVE_ZONE_RADIUS,
    ZONE_CAVE,
    ZONE_SIZE,
    ZoneId,
    zone_for_tile,
    zones_near_tile,
)


class ZoneTest(unittest.TestCase):
    def test_zone_for_tile_maps_coordinates(self):
        self.assertEqual(zone_for_tile(MAP_OVERWORLD, 0, 0), ZoneId(MAP_OVERWORLD, 0, 0))
        self.assertEqual(zone_for_tile(MAP_OVERWORLD, ZONE_SIZE - 1, 0), ZoneId(MAP_OVERWORLD, 0, 0))
        self.assertEqual(zone_for_tile(MAP_OVERWORLD, ZONE_SIZE, 31), ZoneId(MAP_OVERWORLD, 1, 1))

    def test_zones_near_tile_returns_3x3_set_away_from_edges(self):
        zones = zones_near_tile(MAP_OVERWORLD, 32, 32, ACTIVE_ZONE_RADIUS)
        self.assertEqual(len(zones), 9)
        self.assertIn(ZoneId(MAP_OVERWORLD, 2, 2), zones)
        self.assertIn(ZoneId(MAP_OVERWORLD, 1, 1), zones)
        self.assertIn(ZoneId(MAP_OVERWORLD, 3, 3), zones)

    def test_game_initializes_active_zones_from_player(self):
        game = GameState(seed=1)
        self.assertEqual(game.active_zones, zones_near_tile(MAP_OVERWORLD, game.player.x, game.player.y))
        self.assertEqual(set(game.active_zone_states), game.active_zones)

    def test_moving_across_zone_boundary_activates_and_deactivates(self):
        game = GameState(seed=1)
        game.zone_events.clear()
        game.player.x = 33
        game.player.y = 10
        activated, deactivated = game.update_active_zones()
        self.assertTrue(activated)
        self.assertTrue(deactivated)
        self.assertEqual(game.active_zones, zones_near_tile(MAP_OVERWORLD, 33, 10))

    def test_map_change_replaces_old_map_zones_with_cave_zones(self):
        game = GameState(seed=1)
        game.apply_player_state(
            PlayerStatePacket(
                seq=1,
                x=OVERWORLD_CAVE_ENTRANCE[0],
                y=OVERWORLD_CAVE_ENTRANCE[1],
                facing=0,
                buttons=0,
                fire_counter=0,
                pickup_counter=0,
                last_server_seq=0,
            )
        )
        self.assertTrue(game.active_zones)
        self.assertTrue(all(zone.map_id == MAP_STARTER_CAVE for zone in game.active_zones))
        self.assertEqual(game.zone_definition(next(iter(game.active_zones))).zone_type, ZONE_CAVE)

    def test_active_zones_are_union_of_local_and_remote_players(self):
        game = GameState(seed=1)
        remote = game.add_player(1234, x=80, y=80, map_id=MAP_OVERWORLD)
        expected = zones_near_tile(MAP_OVERWORLD, game.player.x, game.player.y)
        expected.update(zones_near_tile(MAP_OVERWORLD, remote.x, remote.y))
        self.assertEqual(game.active_zones, expected)
        game.remove_player(1234)
        self.assertEqual(game.active_zones, zones_near_tile(MAP_OVERWORLD, game.player.x, game.player.y))


if __name__ == "__main__":
    unittest.main()
