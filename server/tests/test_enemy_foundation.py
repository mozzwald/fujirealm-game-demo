"""Phase 60: enemy species, scaling, aggro, loot, and progression."""

import unittest

from server.entities import (
    ENEMY_BAT,
    ENEMY_BEAVER,
    ENEMY_GOBLIN,
    ENEMY_GORVAK,
    ENEMY_SLIME,
    ENEMY_SNAKE,
)
from server.game import (
    ENEMY_TYPES,
    GameState,
    effective_aggro_range,
    enemy_snapshot_kind,
    xp_multiplier_for_level_gap,
)
from server.items import (
    ITEM_OIL_SAMPLE,
    ITEM_RUST_SAMPLE,
    ITEM_STICKS,
    ITEM_WARDEN_KEY,
)
from server.protocol import BEAVER_STRUCT
from server.quests import (
    INITIAL_PROGRESSION_ROUTE,
    QUEST_ROAD_TROUBLE,
    QUEST_STATE_ACTIVE,
    ROAD_TROUBLE_TARGET,
)
from server.world import MAP_OVERWORLD, World
from server.zones import ZoneId


ALL_ENEMIES = (
    ENEMY_BEAVER,
    ENEMY_SNAKE,
    ENEMY_SLIME,
    ENEMY_BAT,
    ENEMY_GOBLIN,
    ENEMY_GORVAK,
)


class EnemyFoundationTest(unittest.TestCase):
    def setUp(self):
        self.game = GameState(seed=1, world=World(), create_default_player=False)
        self.player = self.game.add_player(6001, x=10, y=10)

    def test_all_species_have_explicit_data_and_gorvak_is_scripted_boss(self):
        self.assertEqual(set(ENEMY_TYPES), set(ALL_ENEMIES))
        self.assertTrue(ENEMY_TYPES[ENEMY_GORVAK].is_boss)
        self.assertFalse(ENEMY_TYPES[ENEMY_GORVAK].uses_generic_ai)
        self.assertFalse(ENEMY_TYPES[ENEMY_GOBLIN].is_boss)

    def test_spawn_preserves_level_and_scales_hp_immediately(self):
        for enemy_kind in ALL_ENEMIES:
            with self.subTest(enemy_kind=enemy_kind):
                spec = ENEMY_TYPES[enemy_kind]
                low = self.game.spawn_enemy(
                    enemy_kind, 20, 20, map_id=MAP_OVERWORLD, level=1
                )
                high = self.game.spawn_enemy(
                    enemy_kind, 22, 20, map_id=MAP_OVERWORLD, level=4
                )
                self.assertEqual(high.level, 4)
                self.assertEqual(high.hp, spec.hp_for_level(4))
                self.assertEqual(high.max_hp, high.hp)
                self.assertGreaterEqual(high.hp, low.hp)

    def test_source_test_arena_spawns_every_species_at_multiple_levels(self):
        spawned = self.game.spawn_enemy_test_arena(
            map_id=MAP_OVERWORLD, origin_x=30, origin_y=20, levels=(1, 4)
        )
        self.assertEqual(len(spawned), len(ALL_ENEMIES) * 2)
        self.assertEqual({enemy.subtype for enemy in spawned}, set(ALL_ENEMIES))
        self.assertEqual({enemy.level for enemy in spawned}, {1, 4})

    def test_zone_spawn_passes_level_into_scaling(self):
        zone = ZoneId(MAP_OVERWORLD, 2, 2)
        spawned = self.game.spawn_enemy(
            ENEMY_SLIME, 33, 33, zone_id=zone, level=3
        )
        self.assertEqual(spawned.level, 3)
        self.assertEqual(spawned.hp, ENEMY_TYPES[ENEMY_SLIME].hp_for_level(3))

    def test_relative_level_aggro_thresholds_and_alert_override(self):
        spec = ENEMY_TYPES[ENEMY_GOBLIN]
        enemy = self.game.spawn_enemy(
            ENEMY_GOBLIN, 20, 10, map_id=MAP_OVERWORLD, level=5
        )
        expected = (
            (5, spec.aggro_range),
            (6, max(1, spec.aggro_range * 2 // 3)),
            (7, max(1, spec.aggro_range // 3)),
            (8, 1),
        )
        for player_level, aggro in expected:
            with self.subTest(player_level=player_level):
                self.player.level = player_level
                self.assertEqual(effective_aggro_range(enemy, self.player, spec), aggro)
        enemy.aggro_ticks = 1
        self.player.level = 20
        self.assertEqual(
            effective_aggro_range(enemy, self.player, spec), spec.aggro_range
        )

    def test_owned_encounter_enemy_uses_full_aggro_override(self):
        encounter = self.game.create_scripted_encounter(
            self.player, "scripted", map_id=MAP_OVERWORLD
        )
        enemy = self.game.spawn_encounter_enemy(
            encounter, ENEMY_BEAVER, 15, 10, level=1
        )
        self.player.level = 10
        spec = ENEMY_TYPES[ENEMY_BEAVER]
        self.assertEqual(
            effective_aggro_range(enemy, self.player, spec), spec.aggro_range
        )

    def test_xp_multiplier_for_level_gap_thresholds(self):
        expected = (
            (0, (1, 1)),
            (2, (1, 1)),
            (3, (2, 3)),
            (4, (2, 3)),
            (5, (1, 2)),
            (7, (1, 2)),
            (8, (1, 4)),
            (12, (1, 4)),
            (13, (1, 10)),
            (49, (1, 10)),
        )
        for level_gap, multiplier in expected:
            with self.subTest(level_gap=level_gap):
                self.assertEqual(xp_multiplier_for_level_gap(level_gap), multiplier)

    def test_enemy_kill_xp_diminishes_as_player_outlevels_ambient_enemy(self):
        spec = ENEMY_TYPES[ENEMY_GOBLIN]
        base = spec.xp_for_level(1)
        expected = (
            (1, base),
            (5, base * 2 // 3),
            (8, base // 2),
            (13, base // 4),
            (30, max(1, base // 10)),
        )
        for player_level, xp in expected:
            with self.subTest(player_level=player_level):
                enemy = self.game.spawn_enemy(
                    ENEMY_GOBLIN, 20, 10, map_id=MAP_OVERWORLD, level=1
                )
                self.player.level = player_level
                self.assertEqual(
                    self.game._enemy_kill_xp(spec, enemy, self.player), xp
                )

    def test_boss_kill_xp_is_never_diminished(self):
        spec = ENEMY_TYPES[ENEMY_GORVAK]
        enemy = self.game.spawn_enemy(
            ENEMY_GORVAK, 20, 10, map_id=MAP_OVERWORLD, level=5
        )
        self.player.level = 50
        self.assertEqual(
            self.game._enemy_kill_xp(spec, enemy, self.player),
            spec.xp_for_level(5),
        )

    def test_bridge_defense_wave_beaver_grants_no_xp(self):
        encounter = self.game.create_scripted_encounter(
            self.player, "bridge_repair", map_id=MAP_OVERWORLD
        )
        wave_beaver = self.game.spawn_encounter_enemy(
            encounter, ENEMY_BEAVER, 15, 10, level=1
        )
        self.assertEqual(
            self.game._enemy_kill_xp(ENEMY_TYPES[ENEMY_BEAVER], wave_beaver, self.player),
            0,
        )
        # Same owned-beaver shape under a different encounter id still earns
        # XP -- the exemption is scoped to "bridge_repair" specifically, not
        # "any owner-owned beaver" (see test_scripted_encounters.py's
        # PlayerOwnedEntityTest for the generic ScriptedEncounter case this
        # must not break).
        other_encounter = self.game.create_scripted_encounter(
            self.player, "some_other_encounter", map_id=MAP_OVERWORLD
        )
        other_beaver = self.game.spawn_encounter_enemy(
            other_encounter, ENEMY_BEAVER, 16, 10, level=1
        )
        self.assertGreater(
            self.game._enemy_kill_xp(ENEMY_TYPES[ENEMY_BEAVER], other_beaver, self.player),
            0,
        )

    def test_ambient_beaver_still_grants_xp(self):
        beaver = self.game.spawn_enemy(
            ENEMY_BEAVER, 20, 10, map_id=MAP_OVERWORLD, level=1
        )
        self.assertGreater(
            self.game._enemy_kill_xp(ENEMY_TYPES[ENEMY_BEAVER], beaver, self.player),
            0,
        )

    def test_species_speed_damage_and_chopping_are_data_driven(self):
        self.assertLess(
            ENEMY_TYPES[ENEMY_SNAKE].move_cooldown,
            ENEMY_TYPES[ENEMY_BEAVER].move_cooldown,
        )
        self.assertGreater(
            ENEMY_TYPES[ENEMY_SLIME].move_cooldown,
            ENEMY_TYPES[ENEMY_SNAKE].move_cooldown,
        )
        self.assertTrue(ENEMY_TYPES[ENEMY_BEAVER].can_chop)
        for kind in (ENEMY_SNAKE, ENEMY_SLIME, ENEMY_BAT, ENEMY_GOBLIN):
            self.assertFalse(ENEMY_TYPES[kind].can_chop)
        self.assertGreater(
            ENEMY_TYPES[ENEMY_GORVAK].damage_for_level(5),
            ENEMY_TYPES[ENEMY_GOBLIN].damage_for_level(5),
        )

    def test_low_level_enemy_still_deals_contact_damage_when_adjacent(self):
        self.player.level = 10
        enemy = self.game.spawn_enemy(
            ENEMY_SNAKE, 11, 10, map_id=MAP_OVERWORLD, level=1
        )
        enemy.attack_cooldown = 0
        before = self.player.health
        self.game._apply_enemy_contact_damage()
        self.assertLess(self.player.health, before)

    def test_attacking_enemy_sets_temporary_full_aggro(self):
        enemy = self.game.spawn_enemy(
            ENEMY_SLIME, 11, 10, map_id=MAP_OVERWORLD, level=1
        )
        self.player.level = 10
        self.game._damage_entity(enemy, 1, "melee", self.player)
        self.assertGreater(enemy.aggro_ticks, 0)
        self.assertEqual(
            effective_aggro_range(enemy, self.player, ENEMY_TYPES[ENEMY_SLIME]),
            ENEMY_TYPES[ENEMY_SLIME].aggro_range,
        )

    def test_shared_enemy_stays_leashed_to_home_zone(self):
        self.player.x, self.player.y = 33, 10
        self.game._sync_player_entity(self.player)
        self.game.update_active_zones()
        enemy = self.game.spawn_enemy(
            ENEMY_GOBLIN, 31, 10, map_id=MAP_OVERWORLD, level=5
        )
        enemy.move_cooldown = 0
        self.game._move_enemies()
        self.assertEqual((enemy.x, enemy.y), (31, 10))

    def test_species_deaths_award_scaled_xp_and_configured_loot(self):
        for index, kind in enumerate(
            (ENEMY_SNAKE, ENEMY_SLIME, ENEMY_BAT, ENEMY_GOBLIN)
        ):
            with self.subTest(kind=kind):
                game = GameState(seed=index + 1, world=World())
                enemy = game.spawn_enemy(
                    kind, 20, 20, map_id=MAP_OVERWORLD, level=3
                )
                xp_before = game.player.xp
                game._damage_entity(enemy, enemy.hp, "ranged", game.player)
                self.assertEqual(
                    game.player.xp - xp_before,
                    ENEMY_TYPES[kind].xp_for_level(3),
                )
                drops = [
                    entity
                    for entity in game.entities.values()
                    if entity.kind == 4 and entity.x == 20 and entity.y == 20
                ]
                if ENEMY_TYPES[kind].drop_mode == "gold":
                    self.assertTrue(drops)
                else:
                    self.assertFalse(drops)

    def test_final_road_trouble_beaver_guarantees_personal_sticks(self):
        self.player.active_quest_id = QUEST_ROAD_TROUBLE
        self.player.quest_state = QUEST_STATE_ACTIVE
        self.player.quest_target = ROAD_TROUBLE_TARGET
        self.player.quest_progress = ROAD_TROUBLE_TARGET - 1
        enemy = self.game.spawn_enemy(
            ENEMY_BEAVER, 11, 10, map_id=MAP_OVERWORLD, level=1
        )
        self.game._damage_entity(enemy, enemy.hp, "ranged", self.player)
        sticks = [
            entity
            for entity in self.game.entities.values()
            if entity.subtype == ITEM_STICKS and entity.owner_id == self.player.token
        ]
        self.assertTrue(
            self.player.inventory.count_item(ITEM_STICKS) > 0 or sticks
        )

    def test_oil_and_rust_grants_are_personal_and_bounded(self):
        for item_id in (ITEM_OIL_SAMPLE, ITEM_RUST_SAMPLE):
            self.assertEqual(self.game.grant_personal_sample(self.player, item_id, 2), 1)
            self.assertEqual(self.game.grant_personal_sample(self.player, item_id, 2), 1)
            self.assertEqual(self.game.grant_personal_sample(self.player, item_id, 2), 0)
            self.assertEqual(self.player.inventory.count_item(item_id), 2)

    def test_warden_key_is_personal_and_cannot_leak(self):
        other = self.game.add_player(6002, x=12, y=10)
        key = self.game.spawn_warden_key(self.player, 11, 10, MAP_OVERWORLD)
        self.assertEqual(key.subtype, ITEM_WARDEN_KEY)
        self.assertFalse(self.game.collect_item(other, key))
        self.assertTrue(self.game.collect_item(self.player, key))
        self.assertTrue(self.player.warden_key_collected)
        self.assertEqual(self.player.inventory.count_item(ITEM_WARDEN_KEY), 1)

    def test_hit_signal_reserves_kind_bit_without_changing_record_size(self):
        enemy = self.game.spawn_enemy(
            ENEMY_BAT, 11, 10, map_id=MAP_OVERWORLD, level=2
        )
        enemy.hit_pulse_ticks = 1
        self.assertEqual(enemy_snapshot_kind(enemy, include_hit_pulse=False), ENEMY_BAT)
        self.assertEqual(
            enemy_snapshot_kind(enemy, include_hit_pulse=True), ENEMY_BAT | 0x80
        )
        snapshot = self.game.legacy_beaver_snapshots_for_window(token=self.player.token)
        self.assertEqual(snapshot[0].kind, ENEMY_BAT | 0x80)
        self.assertEqual(BEAVER_STRUCT.size, 4)


class ProgressionFoundationTest(unittest.TestCase):
    def test_initial_no_grind_route_reaches_level_six(self):
        game = GameState(seed=1, world=World())
        for name, xp, expected_level in INITIAL_PROGRESSION_ROUTE:
            with self.subTest(name=name):
                game.award_xp(xp)
                self.assertEqual(game.player.level, expected_level)


if __name__ == "__main__":
    unittest.main()
