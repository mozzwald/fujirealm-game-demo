import unittest

from server.game import (
    CLASS_HUNTER,
    MAP_PVP_REALM,
    REMOTE_PLAYER_STATE_FIRE_MASK,
    GameState,
    max_hp_for_level,
    ranged_damage_for_level,
)
from server.pvp_bots import (
    DEFAULT_PVP_BOT_TOKEN_BASE,
    PVP_BOT_LEVEL,
    PVP_BOT_PATH,
    PVP_BOT_PATHS,
    PvpBotConfig,
    PvpBotController,
)
from server.world_layout_data import PVP_REALM_RESPAWN


class PvpBotControllerTest(unittest.TestCase):
    def test_formation_slots_do_not_rotate_while_stepping(self):
        game = GameState(seed=1, create_default_player=False)
        anchor = game.add_player(100, x=PVP_REALM_RESPAWN[0] + 6, y=PVP_REALM_RESPAWN[1], map_id=MAP_PVP_REALM)
        anchor.pvp_enabled = True
        controller = PvpBotController(
            game,
            PvpBotConfig(enabled=True, count=3, move_every_ticks=1, fire_cooldown_ticks=99),
        )
        before = {token: runtime.formation_index for token, runtime in controller.runtimes.items()}
        for tick in range(1, 8):
            controller.step(tick, [100])
        after = {token: runtime.formation_index for token, runtime in controller.runtimes.items()}
        self.assertEqual(after, before)

    def test_orbit_mode_advances_target_without_changing_formation_slot(self):
        game = GameState(seed=1, create_default_player=False)
        anchor_x, anchor_y = PVP_REALM_RESPAWN[0] + 6, PVP_REALM_RESPAWN[1]
        anchor = game.add_player(100, x=anchor_x, y=anchor_y, map_id=MAP_PVP_REALM)
        anchor.pvp_enabled = True
        controller = PvpBotController(
            game,
            PvpBotConfig(enabled=True, count=1, mode="orbit", orbit_every_ticks=2),
        )
        runtime = controller.runtimes[DEFAULT_PVP_BOT_TOKEN_BASE]
        first = controller._formation_target(anchor_x, anchor_y, runtime.formation_index, tick=0)
        second = controller._formation_target(anchor_x, anchor_y, runtime.formation_index, tick=2)
        self.assertNotEqual(first, second)
        self.assertEqual(runtime.formation_index, 0)

    def test_path_mode_waypoints_are_walkable_on_current_pvp_map(self):
        game = GameState(seed=1, create_default_player=False)
        world = game.world_for(MAP_PVP_REALM)
        for path in PVP_BOT_PATHS:
            for x, y in path:
                self.assertTrue(world.player_can_enter(x, y), (x, y))

    def test_path_mode_advances_to_next_waypoint(self):
        game = GameState(seed=1, create_default_player=False)
        anchor = game.add_player(100, x=PVP_REALM_RESPAWN[0], y=PVP_REALM_RESPAWN[1], map_id=MAP_PVP_REALM)
        anchor.pvp_enabled = True
        controller = PvpBotController(
            game,
            PvpBotConfig(enabled=True, count=1, mode="path", move_every_ticks=1, can_fire=False),
        )
        runtime = controller.runtimes[DEFAULT_PVP_BOT_TOKEN_BASE]
        bot = game.players[DEFAULT_PVP_BOT_TOKEN_BASE]
        bot.x, bot.y = PVP_BOT_PATH[0]
        runtime.path_index = 0
        controller.step(1, [100])
        self.assertEqual(runtime.path_index, 1)
        self.assertNotEqual((bot.x, bot.y), PVP_BOT_PATH[0])

    def test_path_mode_spreads_bots_across_multiple_lanes(self):
        game = GameState(seed=1, create_default_player=False)
        anchor = game.add_player(100, x=PVP_REALM_RESPAWN[0], y=PVP_REALM_RESPAWN[1], map_id=MAP_PVP_REALM)
        anchor.pvp_enabled = True
        controller = PvpBotController(
            game,
            PvpBotConfig(enabled=True, count=12, mode="path", move_every_ticks=1, can_fire=False),
        )
        self.assertGreater(len({runtime.path_id for runtime in controller.runtimes.values()}), 1)
        start_positions = {
            token: (game.players[token].x, game.players[token].y)
            for token in controller.bot_tokens
        }
        for tick in range(1, 31):
            controller.step(tick, [100])
        moved = sum(
            1
            for token in controller.bot_tokens
            if (game.players[token].x, game.players[token].y) != start_positions[token]
        )
        self.assertGreaterEqual(moved, 8)
        self.assertGreater(len({(game.players[token].x, game.players[token].y) for token in controller.bot_tokens}), 4)

    def test_bots_do_not_anchor_on_other_bots(self):
        game = GameState(seed=1, create_default_player=False)
        controller = PvpBotController(game, PvpBotConfig(enabled=True, count=2))
        controller.step(1, [DEFAULT_PVP_BOT_TOKEN_BASE])
        self.assertIsNone(controller._anchor_player([DEFAULT_PVP_BOT_TOKEN_BASE]))

    def test_bots_keep_level_five_stats_without_healing_each_tick(self):
        game = GameState(seed=1, create_default_player=False)
        controller = PvpBotController(game, PvpBotConfig(enabled=True, count=1))
        bot = game.players[DEFAULT_PVP_BOT_TOKEN_BASE]
        self.assertEqual(bot.level, PVP_BOT_LEVEL)
        self.assertEqual(bot.class_id, CLASS_HUNTER)
        self.assertEqual(bot.max_health, max_hp_for_level(PVP_BOT_LEVEL, CLASS_HUNTER))
        bot.health -= 3
        damaged = bot.health
        controller.step(1, [])
        self.assertEqual(bot.health, damaged)

    def test_bots_can_be_damaged_killed_and_respawned(self):
        game = GameState(seed=1, create_default_player=False)
        attacker = game.add_player(100, x=PVP_REALM_RESPAWN[0] + 1, y=PVP_REALM_RESPAWN[1], map_id=MAP_PVP_REALM)
        attacker.pvp_enabled = True
        attacker.level = PVP_BOT_LEVEL
        attacker.max_health = max_hp_for_level(PVP_BOT_LEVEL, CLASS_HUNTER)
        attacker.health = attacker.max_health
        PvpBotController(game, PvpBotConfig(enabled=True, count=1))
        bot = game.players[DEFAULT_PVP_BOT_TOKEN_BASE]
        damage = ranged_damage_for_level(attacker.level, attacker.class_id)
        game._damage_player(bot, damage, attacker)
        self.assertEqual(bot.health, bot.max_health - damage)
        for _ in range(10):
            game._damage_player(bot, damage, attacker)
            if bot.respawn_counter:
                break
        self.assertEqual(bot.health, bot.max_health)
        self.assertEqual(bot.map_id, MAP_PVP_REALM)
        self.assertEqual((bot.x, bot.y), PVP_REALM_RESPAWN)
        self.assertEqual(bot.respawn_counter, 1)

    def test_no_fire_config_keeps_bots_from_shooting(self):
        game = GameState(seed=1, create_default_player=False)
        anchor = game.add_player(100, x=PVP_REALM_RESPAWN[0] + 1, y=PVP_REALM_RESPAWN[1], map_id=MAP_PVP_REALM)
        anchor.pvp_enabled = True
        controller = PvpBotController(
            game,
            PvpBotConfig(enabled=True, count=1, move_every_ticks=99, fire_cooldown_ticks=1, can_fire=False),
        )
        bot = game.players[DEFAULT_PVP_BOT_TOKEN_BASE]
        bot.x = PVP_REALM_RESPAWN[0]
        bot.y = PVP_REALM_RESPAWN[1]
        bot.pvp_enabled = True
        before_health = anchor.health
        for tick in range(1, 5):
            controller.step(tick, [100])
        runtime = controller.runtimes[DEFAULT_PVP_BOT_TOKEN_BASE]
        self.assertEqual(runtime.fire_counter, 0)
        self.assertEqual(anchor.health, before_health)

    def test_bot_fire_advances_remote_player_shot_bits(self):
        game = GameState(seed=1, create_default_player=False)
        anchor = game.add_player(
            100,
            x=PVP_REALM_RESPAWN[0] + 1,
            y=PVP_REALM_RESPAWN[1],
            map_id=MAP_PVP_REALM,
        )
        anchor.pvp_enabled = True
        controller = PvpBotController(
            game,
            PvpBotConfig(
                enabled=True,
                count=1,
                move_every_ticks=99,
                fire_cooldown_ticks=1,
            ),
        )
        bot = game.players[DEFAULT_PVP_BOT_TOKEN_BASE]
        bot.x = PVP_REALM_RESPAWN[0]
        bot.y = PVP_REALM_RESPAWN[1]
        bot.pvp_enabled = True

        controller.step(1, [100])

        record = game.remote_players_near(100, *game.window_origin(100))[0]
        self.assertEqual(bot.shot_counter, 1)
        self.assertNotEqual(record.state & REMOTE_PLAYER_STATE_FIRE_MASK, 0)


if __name__ == "__main__":
    unittest.main()
