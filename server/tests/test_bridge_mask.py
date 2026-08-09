"""Phase 58: per-player bridge terrain masking and collision."""

import unittest

import server.game as game_module
from server.game import GameState, MAP_OVERWORLD
from server.world import ROAD, WATER, World

BRIDGE = (40, 30)
# A window whose 32x24 rectangle contains BRIDGE.
ORIGIN_X, ORIGIN_Y = 30, 20
LOCAL = (BRIDGE[0] - ORIGIN_X, BRIDGE[1] - ORIGIN_Y)


class BridgeMaskTest(unittest.TestCase):
    def setUp(self):
        # Inject a synthetic bridge cell (the shipped map has none yet).
        self._saved_tiles = game_module.OVERWORLD_BRIDGE_TILES
        self._saved_set = game_module.OVERWORLD_BRIDGE_SET
        game_module.OVERWORLD_BRIDGE_TILES = (BRIDGE,)
        game_module.OVERWORLD_BRIDGE_SET = frozenset([BRIDGE])
        self.game = GameState(seed=1, world=World())
        self.game.world_for(MAP_OVERWORLD).set_tile(BRIDGE[0], BRIDGE[1], ROAD)
        # Two players on the overworld: one repaired, one not.
        self.unrepaired = self.game.player  # default player
        self.repaired = self.game.add_player(9001, map_id=MAP_OVERWORLD)
        self.repaired.bridge_repaired = True

    def tearDown(self):
        game_module.OVERWORLD_BRIDGE_TILES = self._saved_tiles
        game_module.OVERWORLD_BRIDGE_SET = self._saved_set

    def _cell(self, window):
        return window.tiles[LOCAL[1] * window.width + LOCAL[0]]

    def test_window_masks_bridge_as_water_until_repaired(self):
        unrepaired = self.game.window_at(ORIGIN_X, ORIGIN_Y, self.unrepaired.token)
        repaired = self.game.window_at(ORIGIN_X, ORIGIN_Y, self.repaired.token)
        self.assertEqual(self._cell(unrepaired), WATER)
        self.assertEqual(self._cell(repaired), ROAD)

    def test_row_tiles_use_the_same_per_player_mask(self):
        unrepaired_row = self.game.window_row_tiles(ORIGIN_X, BRIDGE[1], self.unrepaired.token)
        repaired_row = self.game.window_row_tiles(ORIGIN_X, BRIDGE[1], self.repaired.token)
        self.assertEqual(unrepaired_row[LOCAL[0]], WATER)
        self.assertEqual(repaired_row[LOCAL[0]], ROAD)

    def test_edge_window_uses_the_same_per_player_mask(self):
        # Scroll east: the new edge column is at old_origin_x + 32, so place the
        # old origin 32 west of the bridge column.
        old_origin_x = BRIDGE[0] - 32
        edge = self.game.edge_window(
            old_origin_x, ORIGIN_Y, old_origin_x + 1, ORIGIN_Y, self.unrepaired.token
        )
        col_local_y = BRIDGE[1] - ORIGIN_Y
        self.assertEqual(edge.tiles[col_local_y * edge.width + 0], WATER)

    def test_collision_blocks_unrepaired_and_allows_repaired(self):
        world = self.game.world_for(MAP_OVERWORLD)
        self.assertFalse(self.game._player_destination_allowed(self.unrepaired, *BRIDGE, world))
        self.assertTrue(self.game._player_destination_allowed(self.repaired, *BRIDGE, world))

    def test_two_players_see_different_terrain_at_same_cell(self):
        # The exit-gate scenario: no bridge state leaks between players.
        u = self.game.window_at(ORIGIN_X, ORIGIN_Y, self.unrepaired.token)
        r = self.game.window_at(ORIGIN_X, ORIGIN_Y, self.repaired.token)
        self.assertNotEqual(self._cell(u), self._cell(r))

    def test_complete_bridge_repair_reveals_road_and_flags_resync(self):
        self.game.complete_bridge_repair(self.unrepaired)
        self.assertTrue(self.unrepaired.bridge_repaired)
        self.assertTrue(self.game.consume_pending_terrain_resync(self.unrepaired.token))
        # Consumed once, then cleared.
        self.assertFalse(self.game.consume_pending_terrain_resync(self.unrepaired.token))
        window = self.game.window_at(ORIGIN_X, ORIGIN_Y, self.unrepaired.token)
        self.assertEqual(self._cell(window), ROAD)


if __name__ == "__main__":
    unittest.main()
