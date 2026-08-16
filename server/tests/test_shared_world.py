import unittest

from server.entities import ENTITY_ITEM
from server.game import (
    CLASS_HUNTER,
    CLIENT_AIM_DOWN_RIGHT,
    DEFAULT_PLAYER_TOKEN,
    GameState,
    HUD_FLAG_PVP_ENABLED,
    MAX_PLAYER_LEVEL,
    PLAYER_FIRE_BUTTON,
    PlayerState,
    REMOTE_PLAYER_STATE_ALIVE,
    REMOTE_PLAYER_STATE_FIRE_MASK,
    REMOTE_PLAYER_STATE_FIRE_SHIFT,
    REMOTE_PLAYER_STATE_PVP_ENABLED,
    TRANSITION_READY_GRACE_TICKS,
    deserialize_player_state,
    display_username,
    serialize_player_state,
)
from server.items import ITEM_GOLD, ITEM_STICKS
from server.protocol import PlayerStatePacket
from server.quests import (
    MSG_BEAVER_KILLED,
    MSG_NONE,
    MSG_PLAYER_ENTERED,
    MSG_PLAYER_DIED,
    MSG_PVP_ARENA_LOCKED,
    MSG_PVP_HIT,
    MSG_PVP_KILL,
    QUEST_NONE,
    QUEST_STATE_NOT_STARTED,
    MSG_RESPAWN_GRAVE,
)
from server.world import (
    MAP_OVERWORLD,
    MAP_PVP_REALM,
    MAP_STARTER_CAVE,
    OVERWORLD_RESPAWN,
    OVERWORLD_CAVE_ENTRANCE,
    OVERWORLD_PVP_REALM_ENTRANCE,
    PVP_REALM_ENTRY,
    STARTER_CAVE_ENTRY,
    World,
)
from server.zones import ZoneId


TOKEN_A = 100
TOKEN_B = 200


def state(seq, x, y, facing=3, buttons=0, fire=0, pickup=0, pvp=0):
    return PlayerStatePacket(
        seq=seq,
        x=x,
        y=y,
        facing=facing,
        buttons=buttons,
        fire_counter=fire,
        pickup_counter=pickup,
        last_server_seq=0,
        pvp_toggle_counter=pvp,
    )


class SharedWorldTest(unittest.TestCase):
    def _two_player_game(self):
        game = GameState(seed=1, create_default_player=False)
        a = game.add_player(TOKEN_A, x=10, y=10)
        b = game.add_player(TOKEN_B, x=12, y=10)
        return game, a, b

    def _two_player_game_on_open_ground(self):
        """``_two_player_game`` with both players stood on walkable tiles.

        The default (10,10)/(12,10) spots are town buildings in the
        hand-authored overworld. That is fine for tests that only read state,
        but ``apply_player_state`` refuses any move onto a blocking tile --
        including a "stay put" one -- so a test that sends position updates
        needs open ground. Row 16 is clear from x=10 eastward.
        """
        game, a, b = self._two_player_game()
        a.x, a.y = 10, 16
        b.x, b.y = 12, 16
        game._sync_player_entity(a)
        game._sync_player_entity(b)
        return game, a, b

    def test_players_share_one_world_object(self):
        game, a, b = self._two_player_game()
        self.assertIs(game.world_for(a.map_id), game.world_for(b.map_id))
        self.assertEqual(len(game.players), 2)

    def test_kill_credit_and_messages_go_to_killer_only(self):
        game, a, b = self._two_player_game()
        # Row 10 has a tree at x=12 in the current hand-authored map, so
        # this test's shot needs a clear lane; use the open row 16 instead
        # of the (10,10)/(12,10) spots _two_player_game sets up.
        a.x, a.y = 10, 16
        game._sync_player_entity(a)
        beaver = game.spawn_beaver(13, 16, map_id=MAP_OVERWORLD)
        # A is at (10,16); B stands aside at (12,17) so the shot passes.
        b.x, b.y = 12, 17
        game._sync_player_entity(b)
        while beaver.hp > 0:
            game._hunter_attack(a, 1, 0)
        self.assertEqual(a.latest_message_id, MSG_BEAVER_KILLED)
        self.assertEqual(a.xp, 3)
        self.assertEqual(a.score, 10)
        self.assertEqual(a.gold, 0)
        self.assertEqual(b.latest_message_id, MSG_NONE)
        self.assertEqual(b.xp, 0)
        self.assertEqual(b.score, 0)

    def test_loot_from_a_kill_can_be_collected_by_a_different_player(self):
        game, a, b = self._two_player_game()
        beaver = game.spawn_beaver(11, 10, map_id=MAP_OVERWORLD)
        b.x, b.y = 12, 11
        game._sync_player_entity(b)
        while beaver.hp > 0:
            game._hunter_attack(a, 1, 0)
        self.assertEqual(a.gold, 0)
        dropped = [
            entity
            for entity in game.entities.values()
            if entity.kind == ENTITY_ITEM and entity.map_id == MAP_OVERWORLD
        ]
        self.assertGreaterEqual(len(dropped), 1)
        item = dropped[0]
        # B (not the killer) walks up and collects it.
        b.x, b.y = item.x, item.y
        game._sync_player_entity(b)
        self.assertTrue(game.pickup_nearby_item(b))
        self.assertNotIn(item.entity_id, game.entities)
        if item.subtype == ITEM_GOLD:
            self.assertEqual(b.gold, item.hp)
        else:
            self.assertEqual(b.inventory.count_item(ITEM_STICKS), 1)

    def test_shot_does_not_pass_through_or_damage_players(self):
        game, a, b = self._two_player_game()
        # B stands between A and the beaver.
        beaver = game.spawn_beaver(14, 10, map_id=MAP_OVERWORLD)
        hp_before = beaver.hp
        game._hunter_attack(a, 1, 0)
        self.assertEqual(beaver.hp, hp_before)
        self.assertEqual(b.health, b.max_health)

    def test_players_block_each_other_no_damage(self):
        game, a, b = self._two_player_game()
        accepted = game.apply_player_state(state(seq=1, x=12, y=10), TOKEN_A)
        self.assertFalse(accepted)
        self.assertEqual((a.x, a.y), (10, 10))
        self.assertEqual(b.health, b.max_health)

    def test_pvp_melee_requires_both_players_opted_in(self):
        game, a, b = self._two_player_game()
        game.set_player_username(TOKEN_A, "Alice")
        game.set_player_username(TOKEN_B, "Bob")
        b.x, b.y = 11, 10
        game._sync_player_entity(b)
        start_hp = b.health

        game._hunter_attack(a, 1, 0)
        self.assertEqual(b.health, start_hp, "neither enabled: no damage")

        a.pvp_enabled = True
        game._hunter_attack(a, 1, 0)
        self.assertEqual(b.health, start_hp, "only attacker enabled: still no damage")

        b.pvp_enabled = True
        game._hunter_attack(a, 1, 0)
        self.assertLess(b.health, start_hp, "both enabled: damage applies")
        self.assertEqual(b.latest_message_id, MSG_PVP_HIT)
        self.assertEqual(b.latest_activity_message, "Alice hit you.")
        self.assertEqual(a.latest_message_id, MSG_PVP_HIT)
        self.assertEqual(a.latest_activity_message, "You hit Bob.")

    def test_pvp_ranged_requires_both_players_opted_in(self):
        game, a, b = self._two_player_game()
        # a=(10,10), b=(12,10) from _two_player_game: 2 tiles apart, within
        # ranged range, with a clear line between them.
        start_hp = b.health

        game._hunter_attack(a, 1, 0)
        self.assertEqual(b.health, start_hp)

        a.pvp_enabled = True
        b.pvp_enabled = True
        game._hunter_attack(a, 1, 0)
        self.assertLess(b.health, start_hp)

    def test_transition_loading_blocks_pvp_damage_until_ready_grace_expires(self):
        game, a, b = self._two_player_game()
        a.pvp_enabled = True
        b.pvp_enabled = True
        b.transition_loading = True
        start_hp = b.health

        game._hunter_attack(a, 1, 0)
        self.assertEqual(b.health, start_hp)
        self.assertTrue(game.mark_player_map_ready(TOKEN_B))
        self.assertFalse(b.transition_loading)
        self.assertEqual(b.transition_grace_ticks, TRANSITION_READY_GRACE_TICKS)

        game._hunter_attack(a, 1, 0)
        self.assertEqual(b.health, start_hp)
        b.transition_grace_ticks = 0
        game._hunter_attack(a, 1, 0)
        self.assertLess(b.health, start_hp)

    def test_transition_loading_never_expires_and_pauses_movement(self):
        game, a, b = self._two_player_game()
        a.pvp_enabled = True
        b.pvp_enabled = True
        b.transition_loading = True
        start_hp = b.health
        start_pos = (b.x, b.y)

        # Loading no longer times out on its own: the hybrid server re-sends
        # MAP_CHANGE until the client reports MAP_READY, and play stays
        # paused/protected the whole time.
        for _ in range(200):
            game.begin_tick()
        self.assertTrue(b.transition_loading)
        game._hunter_attack(a, 1, 0)
        self.assertEqual(b.health, start_hp)

        # Position reports are ignored while paused (they may still carry
        # old-map coordinates).
        self.assertFalse(game.apply_player_state(state(1, b.x + 1, b.y), TOKEN_B))
        self.assertEqual((b.x, b.y), start_pos)

        self.assertTrue(game.mark_player_map_ready(TOKEN_B))
        self.assertFalse(b.transition_loading)
        self.assertTrue(game.apply_player_state(state(2, b.x + 1, b.y), TOKEN_B))
        self.assertEqual((b.x, b.y), (start_pos[0] + 1, start_pos[1]))

    def test_pvp_kill_respawns_target_like_any_other_death(self):
        game, a, b = self._two_player_game()
        game.set_player_username(TOKEN_A, "Alice")
        game.set_player_username(TOKEN_B, "Bob")
        b.x, b.y = 11, 10
        game._sync_player_entity(b)
        a.pvp_enabled = True
        b.pvp_enabled = True
        b.health = 1
        game._hunter_attack(a, 1, 0)
        self.assertEqual(a.pvp_kills, 1)
        self.assertEqual(game.hud_update_packet(1, TOKEN_A).pvp_kills, 1)
        self.assertEqual(game.hud_state_tuple(TOKEN_A)[-1], 1)
        self.assertEqual(b.health, b.max_health)
        self.assertEqual(b.latest_message_id, MSG_RESPAWN_GRAVE)
        self.assertEqual(a.latest_message_id, MSG_PVP_KILL)
        self.assertEqual(a.latest_activity_message, "You defeated Bob.")
        self.assertEqual(game.next_message_packet(1, TOKEN_B).text, "Alice defeated you.")
        self.assertEqual(game.next_message_packet(2, TOKEN_B).message_id, MSG_PLAYER_DIED)
        self.assertEqual(game.next_message_packet(3, TOKEN_B).message_id, MSG_RESPAWN_GRAVE)

    def test_pvp_kill_count_saturates_and_persists(self):
        saved = {}

        def save_player(token, username, state):
            saved[token] = state

        game = GameState(seed=1, create_default_player=False, player_state_saver=save_player)
        a = game.add_player(TOKEN_A, x=10, y=10)
        b = game.add_player(TOKEN_B, x=11, y=10)
        a.pvp_enabled = True
        b.pvp_enabled = True
        a.pvp_kills = 9999
        b.health = 1
        game._hunter_attack(a, 1, 0)
        self.assertEqual(a.pvp_kills, 9999)
        self.assertEqual(saved[TOKEN_A]["pvp_kills"], 9999)

        a.pvp_kills = 42
        payload = serialize_player_state(a)
        self.assertEqual(payload["pvp_kills"], 42)
        restored = deserialize_player_state(TOKEN_A, "Alice", payload)
        self.assertEqual(restored.pvp_kills, 42)
        restored = deserialize_player_state(TOKEN_A, "Alice", {**payload, "pvp_kills": 99999})
        self.assertEqual(restored.pvp_kills, 9999)
        restored = deserialize_player_state(TOKEN_A, "Alice", {key: value for key, value in payload.items() if key != "pvp_kills"})
        self.assertEqual(restored.pvp_kills, 0)

    def test_pvp_toggle_counter_is_edge_triggered_and_updates_hud_flag(self):
        game, a, b = self._two_player_game_on_open_ground()
        self.assertFalse(a.pvp_enabled)
        self.assertEqual(game.hud_update_packet(1, TOKEN_A).flags, 0)

        game.apply_player_state(state(seq=2, x=a.x, y=a.y, pvp=1), TOKEN_A)
        self.assertTrue(a.pvp_enabled)
        self.assertEqual(game.hud_update_packet(2, TOKEN_A).flags, HUD_FLAG_PVP_ENABLED)

        # Repeating the same counter value must not toggle again.
        game.apply_player_state(state(seq=3, x=a.x, y=a.y, pvp=1), TOKEN_A)
        self.assertTrue(a.pvp_enabled)

        # A new counter value toggles it back off.
        game.apply_player_state(state(seq=4, x=a.x, y=a.y, pvp=2), TOKEN_A)
        self.assertFalse(a.pvp_enabled)
        self.assertEqual(game.hud_update_packet(3, TOKEN_A).flags, 0)

    def test_pvp_state_reflected_in_remote_players_near(self):
        game, a, b = self._two_player_game()
        records = game.remote_players_near(TOKEN_B, 0, 0)
        self.assertEqual(records[0].state, REMOTE_PLAYER_STATE_ALIVE)

        a.pvp_enabled = True
        records = game.remote_players_near(TOKEN_B, 0, 0)
        self.assertEqual(records[0].state, REMOTE_PLAYER_STATE_ALIVE | REMOTE_PLAYER_STATE_PVP_ENABLED)

    def test_accepted_fire_advances_remote_player_shot_bits(self):
        game, a, _ = self._two_player_game_on_open_ground()
        a.pvp_enabled = True
        base_state = REMOTE_PLAYER_STATE_ALIVE | REMOTE_PLAYER_STATE_PVP_ENABLED
        self.assertEqual(game.remote_players_near(TOKEN_B, 0, 0)[0].state, base_state)

        self.assertTrue(game.apply_player_state(state(1, a.x, a.y, facing=3, fire=1), TOKEN_A))
        fired_state = game.remote_players_near(TOKEN_B, 0, 0)[0].state
        self.assertEqual(fired_state & 0b11, base_state)
        self.assertEqual(
            fired_state & REMOTE_PLAYER_STATE_FIRE_MASK,
            1 << REMOTE_PLAYER_STATE_FIRE_SHIFT,
        )

        self.assertTrue(game.apply_player_state(state(2, a.x, a.y, facing=3, fire=1), TOKEN_A))
        self.assertEqual(game.remote_players_near(TOKEN_B, 0, 0)[0].state, fired_state)

    def test_diagonal_fire_preserves_remote_facing_and_advances_shot_bits(self):
        game = GameState(seed=1, world=World(), create_default_player=False)
        a = game.add_player(TOKEN_A, x=10, y=10)
        game.add_player(TOKEN_B, x=12, y=10)
        self.assertTrue(
            game.apply_player_state(
                state(1, a.x, a.y, facing=CLIENT_AIM_DOWN_RIGHT, fire=1),
                TOKEN_A,
            )
        )
        record = game.remote_players_near(TOKEN_B, 0, 0)[0]
        self.assertEqual(record.facing, CLIENT_AIM_DOWN_RIGHT)
        self.assertEqual(
            record.state & REMOTE_PLAYER_STATE_FIRE_MASK,
            1 << REMOTE_PLAYER_STATE_FIRE_SHIFT,
        )

    def test_diagonal_pvp_shot_requires_both_players_to_opt_in(self):
        for target_opted_in, should_damage in ((False, False), (True, True)):
            with self.subTest(target_opted_in=target_opted_in):
                game = GameState(seed=1, world=World(), create_default_player=False)
                attacker = game.add_player(TOKEN_A, x=10, y=10)
                target = game.add_player(TOKEN_B, x=12, y=12)
                attacker.pvp_enabled = True
                target.pvp_enabled = target_opted_in
                starting_hp = target.health
                self.assertTrue(
                    game.apply_player_state(
                        state(
                            1,
                            attacker.x,
                            attacker.y,
                            facing=CLIENT_AIM_DOWN_RIGHT,
                            fire=1,
                        ),
                        TOKEN_A,
                    )
                )
                self.assertEqual(target.health < starting_hp, should_damage)

    def test_remote_player_shot_bits_wrap_after_four_accepted_fires(self):
        game, a, _ = self._two_player_game_on_open_ground()
        starting_bits = game.remote_players_near(TOKEN_B, 0, 0)[0].state & REMOTE_PLAYER_STATE_FIRE_MASK
        for fire_counter in range(1, 5):
            self.assertTrue(
                game.apply_player_state(
                    state(fire_counter, a.x, a.y, facing=3, fire=fire_counter),
                    TOKEN_A,
                )
            )
        ending_bits = game.remote_players_near(TOKEN_B, 0, 0)[0].state & REMOTE_PLAYER_STATE_FIRE_MASK
        self.assertEqual(ending_bits, starting_bits)

    def test_directionless_fire_does_not_advance_remote_player_shot_bits(self):
        game, a, _ = self._two_player_game_on_open_ground()
        self.assertTrue(game.apply_player_state(state(1, a.x, a.y, facing=255, fire=1), TOKEN_A))
        self.assertEqual(a.shot_counter, 0)
        self.assertEqual(
            game.remote_players_near(TOKEN_B, 0, 0)[0].state & REMOTE_PLAYER_STATE_FIRE_MASK,
            0,
        )

    def test_refused_step_still_consumes_the_fire_on_the_same_packet(self):
        """A blocked move must not defer the shot it was carrying.

        hybrid_server._tick re-applies session.latest every tick, so an edge
        left un-acked here goes off later -- when the blocker steps aside, or
        on the client's next accepted packet. Both read as a phantom shot: the
        other player moves and you fire.
        """
        game, a, b = self._two_player_game_on_open_ground()
        # A tries to walk onto B while holding fire; the step is refused.
        blocked = state(1, b.x, b.y, facing=3, buttons=PLAYER_FIRE_BUTTON, fire=1)
        self.assertFalse(game.apply_player_state(blocked, TOKEN_A))
        self.assertEqual(a.shot_counter, 1)
        self.assertEqual((a.x, a.y), (10, 16))

        # Re-applying the cached packet is idempotent...
        self.assertFalse(game.apply_player_state(blocked, TOKEN_A))
        self.assertEqual(a.shot_counter, 1)

        # ...and B stepping aside does not resurrect the shot.
        b.x = 15
        game._sync_player_entity(b)
        self.assertTrue(game.apply_player_state(blocked, TOKEN_A))
        self.assertEqual(a.shot_counter, 1)

    def test_refused_step_consumes_pickup_and_pvp_edges_too(self):
        game, a, b = self._two_player_game_on_open_ground()
        blocked = state(1, b.x, b.y, facing=3, pickup=1, pvp=1)
        self.assertFalse(game.apply_player_state(blocked, TOKEN_A))
        self.assertTrue(a.pvp_enabled)
        pickups = a.pickup_events
        b.x = 15
        game._sync_player_entity(b)
        self.assertTrue(game.apply_player_state(blocked, TOKEN_A))
        self.assertTrue(a.pvp_enabled)
        self.assertEqual(a.pickup_events, pickups)

    def test_transition_loading_drops_rather_than_defers_button_edges(self):
        game, a, _ = self._two_player_game_on_open_ground()
        a.transition_loading = True
        self.assertFalse(
            game.apply_player_state(
                state(1, a.x, a.y, facing=3, buttons=PLAYER_FIRE_BUTTON, fire=1), TOKEN_A
            )
        )
        self.assertEqual(a.shot_counter, 0)
        a.transition_loading = False
        # The next accepted packet carries the same counter and must stay quiet.
        self.assertTrue(game.apply_player_state(state(2, a.x, a.y, facing=3, fire=1), TOKEN_A))
        self.assertEqual(a.shot_counter, 0)

    def test_pvp_realm_transition_forces_pvp_and_rejects_toggle_off(self):
        game, a, _ = self._two_player_game()
        a.level = 10
        a.pvp_unlocked = True
        accepted = game.apply_player_state(
            state(seq=1, x=OVERWORLD_PVP_REALM_ENTRANCE[0], y=OVERWORLD_PVP_REALM_ENTRANCE[1]), TOKEN_A
        )
        self.assertTrue(accepted)
        self.assertEqual(a.map_id, MAP_PVP_REALM)
        self.assertEqual((a.x, a.y), PVP_REALM_ENTRY)
        self.assertTrue(a.pvp_enabled)
        self.assertEqual(game.hud_update_packet(1, TOKEN_A).flags, HUD_FLAG_PVP_ENABLED)

        game.apply_player_state(state(seq=2, x=a.x, y=a.y, pvp=1), TOKEN_A)
        self.assertTrue(a.pvp_enabled)

    def test_pvp_realm_transition_rejects_story_incomplete_player_with_message(self):
        game, a, _ = self._two_player_game()
        a.level = 10
        self.assertFalse(a.pvp_unlocked)
        accepted = game.apply_player_state(
            state(seq=1, x=OVERWORLD_PVP_REALM_ENTRANCE[0], y=OVERWORLD_PVP_REALM_ENTRANCE[1]), TOKEN_A
        )
        self.assertTrue(accepted)
        self.assertEqual(a.map_id, MAP_OVERWORLD)
        self.assertIsNone(a.pending_map_change)
        self.assertEqual(a.latest_activity_message, "Defeat Gorvak, then see Nerissa.")
        self.assertEqual(a.latest_message_id, MSG_PVP_ARENA_LOCKED)

    def test_pvp_realm_transition_rejects_low_level_player_even_if_story_complete(self):
        game, a, _ = self._two_player_game()
        a.level = 4
        a.pvp_unlocked = True
        accepted = game.apply_player_state(
            state(seq=1, x=OVERWORLD_PVP_REALM_ENTRANCE[0], y=OVERWORLD_PVP_REALM_ENTRANCE[1]), TOKEN_A
        )
        self.assertTrue(accepted)
        self.assertEqual(a.map_id, MAP_OVERWORLD)
        self.assertIsNone(a.pending_map_change)
        self.assertEqual(a.latest_activity_message, "You must be lvl 5 for PvP.")
        self.assertEqual(a.latest_message_id, MSG_PVP_ARENA_LOCKED)

    def test_players_inside_pvp_realm_always_appear_as_pvp_enabled_remotes(self):
        game = GameState(seed=1, create_default_player=False)
        a = game.add_player(TOKEN_A, x=PVP_REALM_ENTRY[0], y=PVP_REALM_ENTRY[1], map_id=MAP_PVP_REALM)
        b = game.add_player(TOKEN_B, x=PVP_REALM_ENTRY[0] + 2, y=PVP_REALM_ENTRY[1], map_id=MAP_PVP_REALM)
        a.pvp_enabled = True
        b.pvp_enabled = True
        records = game.remote_players_near(TOKEN_B, *game.window_origin(TOKEN_B))
        self.assertEqual(records[0].state, REMOTE_PLAYER_STATE_ALIVE | REMOTE_PLAYER_STATE_PVP_ENABLED)

    def test_beaver_targets_nearest_player(self):
        game, a, b = self._two_player_game()
        a.x, a.y = 5, 8
        game._sync_player_entity(a)
        beaver = game.spawn_beaver(11, 8, map_id=MAP_OVERWORLD)
        beaver.move_cooldown = 0
        b.x, b.y = 15, 8
        game._sync_player_entity(b)
        game.update_active_zones()
        game._move_beavers()
        # B (distance 4) is nearer than A (distance 6): the beaver moved toward B.
        self.assertEqual((beaver.x, beaver.y), (12, 8))

    def test_beaver_bites_only_the_adjacent_player(self):
        game, a, b = self._two_player_game()
        beaver = game.spawn_beaver(13, 10, map_id=MAP_OVERWORLD)
        beaver.attack_cooldown = 0
        game._apply_beaver_contact_damage()
        self.assertEqual(b.health, b.max_health - 1)
        self.assertEqual(a.health, a.max_health)

    def test_players_on_different_maps_are_isolated(self):
        game, a, b = self._two_player_game()
        accepted = game.apply_player_state(
            state(seq=1, x=OVERWORLD_CAVE_ENTRANCE[0], y=OVERWORLD_CAVE_ENTRANCE[1]), TOKEN_A
        )
        self.assertTrue(accepted)
        self.assertEqual(a.map_id, MAP_STARTER_CAVE)
        self.assertEqual((a.x, a.y), STARTER_CAVE_ENTRY)
        self.assertIsNotNone(a.pending_map_change)
        self.assertIsNone(b.pending_map_change)
        self.assertEqual(b.map_id, MAP_OVERWORLD)
        # Both worlds exist simultaneously; snapshots are per-map.
        self.assertIn(MAP_OVERWORLD, game.worlds)
        self.assertIn(MAP_STARTER_CAVE, game.worlds)
        cave_beavers = game.legacy_beaver_snapshots_for_window(token=TOKEN_A)
        overworld_beavers = game.legacy_beaver_snapshots_for_window(token=TOKEN_B)
        self.assertEqual(len(cave_beavers), 6)
        self.assertEqual(len(overworld_beavers), 6)
        # A is no longer a remote player for B.
        self.assertEqual(game.remote_players_near(TOKEN_B, 0, 0), ())

    def test_remote_players_near_orders_by_distance_and_uses_configured_cap(self):
        game = GameState(seed=1, create_default_player=False)
        game.add_player(1, x=10, y=10)
        for token in range(2, 15):
            game.add_player(token, x=10 + token, y=10)
        records = game.remote_players_near(1, 0, 0)
        self.assertEqual(len(records), 3)
        self.assertEqual([r.x for r in records], [12, 13, 14])
        records = game.remote_players_near(1, 0, 0, limit=12)
        self.assertEqual(len(records), 12)
        self.assertEqual([r.x for r in records[:3]], [12, 13, 14])

    def test_remote_players_near_excludes_outside_window(self):
        game = GameState(seed=1, create_default_player=False)
        game.add_player(1, x=10, y=10)
        game.add_player(2, x=40, y=10)
        self.assertEqual(game.remote_players_near(1, 0, 0), ())
        self.assertEqual(len(game.remote_players_near(1, 9, 0)), 1)

    def test_item_drops_near_orders_by_distance_and_caps_at_four(self):
        game = GameState(seed=1, create_default_player=False)
        player = game.add_player(1, x=10, y=10)
        game.spawn_item(12, 10, ITEM_GOLD, map_id=player.map_id)
        game.spawn_item(11, 10, ITEM_STICKS, map_id=player.map_id)
        game.spawn_item(16, 10, ITEM_GOLD, map_id=player.map_id)
        game.spawn_item(14, 10, ITEM_GOLD, map_id=player.map_id)
        game.spawn_item(13, 10, ITEM_GOLD, map_id=player.map_id)
        records = game.item_drops_near(1, 0, 0)
        self.assertEqual(len(records), 4)
        self.assertEqual([r.x for r in records], [11, 12, 13, 14])

    def test_item_drops_near_excludes_outside_window_and_other_maps(self):
        game = GameState(seed=1, create_default_player=False)
        player = game.add_player(1, x=10, y=10)
        game.spawn_item(40, 10, ITEM_GOLD, map_id=player.map_id)
        self.assertEqual(game.item_drops_near(1, 0, 0), ())
        self.assertEqual(len(game.item_drops_near(1, 9, 0)), 1)

    def test_detach_parks_state_and_ensure_resumes_it(self):
        game, a, b = self._two_player_game()
        a.xp = 15
        a.x, a.y = 14, 10
        game.detach_player(TOKEN_A)
        self.assertNotIn(TOKEN_A, game.players)
        self.assertEqual(game.remote_players_near(TOKEN_B, 0, 0), ())
        resumed = game.ensure_player(TOKEN_A)
        self.assertIs(resumed, a)
        self.assertEqual(resumed.xp, 15)
        self.assertEqual((resumed.x, resumed.y), (14, 10))
        entities = [
            entity for entity in game.entities.values() if entity.is_player and entity.owner_id == TOKEN_A
        ]
        self.assertEqual(len(entities), 1)

    def test_ensure_player_restores_persistent_state_from_loader(self):
        record = {
            "username": "Alice",
            "player_state": {
                "class_id": CLASS_HUNTER,
                "level": 7,
                "xp": 140,
                "health": 12,
                "gold": 23,
                "inventory": [[ITEM_STICKS, 2]],
                "active_quest_id": QUEST_NONE,
                "quest_state": QUEST_STATE_NOT_STARTED,
                "pending_quest_offer_id": QUEST_NONE,
                "map_id": MAP_STARTER_CAVE,
                "x": STARTER_CAVE_ENTRY[0],
                "y": STARTER_CAVE_ENTRY[1],
                "respawn_map_id": MAP_STARTER_CAVE,
                "respawn_x": STARTER_CAVE_ENTRY[0],
                "respawn_y": STARTER_CAVE_ENTRY[1],
                "pvp_enabled": False,
                "visited_zones": [[MAP_OVERWORLD, 1, 2]],
            },
        }
        game = GameState(
            seed=1,
            create_default_player=False,
            player_state_loader=lambda token: record if token == TOKEN_A else None,
        )
        player = game.ensure_player(TOKEN_A)
        self.assertEqual(player.username, "Alice")
        self.assertEqual(player.level, 7)
        self.assertEqual(player.gold, 23)
        self.assertEqual(player.inventory.count_item(ITEM_STICKS), 2)
        self.assertEqual((player.map_id, player.x, player.y), (MAP_STARTER_CAVE, STARTER_CAVE_ENTRY[0], STARTER_CAVE_ENTRY[1]))
        self.assertIn(TOKEN_A, game.players)
        self.assertIn(ZoneId(MAP_OVERWORLD, 1, 2), player.visited_zones)

    def test_ensure_player_clamps_invalid_persistent_state(self):
        record = {
            "username": "Alice",
            "player_state": {
                "class_id": 99,
                "level": 999,
                "xp": 99999,
                "health": 0,
                "map_id": 99,
                "x": -5,
                "y": -5,
                "respawn_map_id": 99,
                "respawn_x": -1,
                "respawn_y": -1,
                "active_quest_id": 99,
                "quest_state": 99,
                "inventory": [[ITEM_STICKS, 1]],
            },
        }
        game = GameState(
            seed=1,
            create_default_player=False,
            player_state_loader=lambda token: record if token == TOKEN_A else None,
        )
        player = game.ensure_player(TOKEN_A)
        self.assertEqual(player.class_id, CLASS_HUNTER)
        self.assertEqual(player.level, MAX_PLAYER_LEVEL)
        self.assertEqual((player.map_id, player.x, player.y), (MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1]))
        self.assertEqual(player.active_quest_id, QUEST_NONE)
        self.assertEqual(player.quest_state, QUEST_STATE_NOT_STARTED)
        self.assertEqual(player.health, 1)

    def test_hud_quest_message_state_is_per_player(self):
        game, a, b = self._two_player_game()
        game.award_xp(7, a)
        game.award_gold(3, a)
        self.assertNotEqual(game.hud_state_tuple(TOKEN_A), game.hud_state_tuple(TOKEN_B))
        game.queue_activity_message(a, "You killed a beaver.", MSG_BEAVER_KILLED)
        self.assertEqual(game.message_packet(1, TOKEN_A).message_id, MSG_BEAVER_KILLED)
        self.assertEqual(game.message_packet(1, TOKEN_B).message_id, MSG_NONE)
        self.assertEqual(a.message_counter, 1)
        self.assertEqual(b.message_counter, 0)

    def test_display_username_is_ascii_trimmed_and_clamped(self):
        self.assertEqual(display_username("  JosephineLongName  ", TOKEN_A), "JosephineLon")
        self.assertEqual(display_username("Zoë", TOKEN_A), "Zo")
        self.assertEqual(display_username("", TOKEN_A), "Player0064")

    def test_set_player_username_and_server_message_queue(self):
        game, a, b = self._two_player_game()
        game.set_player_username(TOKEN_A, "Alice")
        self.assertEqual(a.username, "Alice")
        game.queue_server_message("Bob has entered the realm!", MSG_PLAYER_ENTERED, exclude_token=TOKEN_B)
        self.assertEqual(a.latest_message_id, MSG_PLAYER_ENTERED)
        self.assertEqual(a.pending_messages[0], (MSG_PLAYER_ENTERED, "Bob has entered the realm!"))
        self.assertEqual(b.latest_message_id, MSG_NONE)

    def test_queued_messages_are_sent_in_order_one_at_a_time(self):
        game, a, b = self._two_player_game()
        game.queue_activity_message(a, "First", MSG_PVP_HIT)
        game.queue_activity_message(a, "Second", MSG_PVP_KILL)
        self.assertEqual(game.next_message_packet(1, TOKEN_A).text, "First")
        self.assertEqual(game.next_message_packet(2, TOKEN_A).text, "Second")
        self.assertIsNone(game.next_message_packet(3, TOKEN_A))

    def test_dead_beavers_decay_and_free_their_slot(self):
        game = GameState(seed=1)
        beaver = game.beavers[0]
        game._damage_entity(beaver, beaver.hp, "ranged")
        self.assertEqual(beaver.hp, 0)
        self.assertIn(beaver, game.beavers)
        for _ in range(12):
            game.step()
        self.assertIn(beaver, game.beavers)
        self.assertEqual(beaver.hp, 0)
        self.assertGreater(beaver.respawn_ticks, 0)

    def test_default_player_compat_alias(self):
        game = GameState(seed=1)
        self.assertIs(game.player, game.players[DEFAULT_PLAYER_TOKEN])
        snapshot = game.step()
        self.assertEqual((snapshot.player_x, snapshot.player_y), (game.player.x, game.player.y))


if __name__ == "__main__":
    unittest.main()
