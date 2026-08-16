"""Authoritative shared-world server state and deterministic tick loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .entities import (
    ENEMY_BAT,
    ENEMY_BEAVER,
    ENEMY_GOBLIN,
    ENEMY_GORVAK,
    ENEMY_SLIME,
    ENEMY_SNAKE,
    ENTITY_ENEMY,
    ENTITY_FLAG_BLOCKING,
    ENTITY_FLAG_BLOCKS_OTHERS,
    ENTITY_FLAG_HOSTILE,
    ENTITY_FLAG_NAMED,
    ENTITY_FLAG_PERSONAL,
    ENTITY_FLAG_TEMPORARY,
    ENTITY_FLAG_VISIBLE,
    ENTITY_FLAG_WORKING,
    ENTITY_ITEM,
    ENTITY_NPC,
    ENTITY_PLAYER,
    Entity,
    NPC_DANIEL,
    NPC_FARMER,
    NPC_GOBLIN,
    NPC_GRIX,
    NPC_LUCIAN,
    NPC_NERISSA,
    NPC_WILHELM,
)
from .encounters import (
    ENCOUNTER_ACTIVE,
    ENCOUNTER_CLEANUP,
    ENCOUNTER_ESCORTING,
    ENCOUNTER_FAILED,
    ENCOUNTER_INACTIVE,
    ENCOUNTER_RETURNING,
    ENCOUNTER_SUCCEEDED,
    EncounterCallback,
    EncounterRegion,
    ScriptedEncounter,
)
from .protocol import (
    BeaverSnapshot,
    DIALOGUE_FLAG_ACK_ONLY,
    DIALOGUE_FLAG_CHUNK_END,
    DIALOGUE_FLAG_LAST_PAGE,
    DIALOGUE_FLAG_QUEST_OFFER,
    REALTIME_DIALOGUE_MAX_TEXT,
    DialoguePagePacket,
    HudUpdatePacket,
    InputIntent,
    InventoryUpdatePacket,
    ItemDropRecord,
    MapSummaryPacket,
    MAX_BEAVERS,
    MessagePacket,
    PlayerStatePacket,
    QuestUpdatePacket,
    REALTIME_MAX_ITEM_DROPS,
    REALTIME_DEFAULT_REMOTE_PLAYERS,
    REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED,
    RemotePlayerRecord,
    RespawnEventPacket,
    Snapshot,
    WINDOW_H,
    WINDOW_W,
    Window,
)
from .items import (
    ITEM_GOLD,
    ITEM_LOST_CHARM,
    ITEM_OIL_SAMPLE,
    ITEM_RUST_SAMPLE,
    ITEM_STICKS,
    ITEM_WARDEN_KEY,
    Inventory,
)
from .world_layout_data import (
    BRIDGE_DEFENSE_REGION,
    DANIEL_X,
    DANIEL_Y,
    DEEP_PUMP_CONTROLS_MARKER,
    FARMER_X,
    FARMER_Y,
    GOBLIN_NPC_X,
    GOBLIN_NPC_Y,
    GORVAK_MARKER,
    GORVAK_ROOM_REGION,
    GORVAK_SUMMON_POINTS,
    NAMED_NPC_SPAWNS,
    OVERWORLD_BRIDGE_TILES,
    STATIC_ENEMY_SPAWNS,
    WARDEN_KEY_MARKER,
    WILHELM_BRIDGE_DESTINATION,
    WILHELM_ESCORT_PATH,
    WILHELM_POS,
)
from .quests import (
    BLACKWATER_REWARD_GOLD,
    BLACKWATER_REWARD_XP,
    BLACKWATER_TARGET,
    LIVING_MUD_OIL_TARGET,
    LIVING_MUD_REWARD_GOLD,
    LIVING_MUD_REWARD_XP,
    LIVING_MUD_RUST_TARGET,
    LIVING_MUD_TARGET,
    LOST_CHARM_REWARD_GOLD,
    LOST_CHARM_TARGET,
    MSG_BEAVER_BITES,
    MSG_BEAVER_KILLED,
    MSG_FARMER_THANKS,
    MSG_GOBLIN_BITES,
    MSG_GOBLIN_KILLED,
    MSG_GOBLIN_THANKS,
    MSG_GOT_GOLD,
    MSG_GOT_STICKS,
    MSG_LEVEL_UP,
    MSG_NONE,
    MSG_PLAYER_ENTERED,
    MSG_PLAYER_DIED,
    MSG_PLAYER_LEFT,
    MSG_PVP_ARENA_LOCKED,
    MSG_PVP_HIT,
    MSG_PVP_KILL,
    MSG_QUEST_COMPLETE,
    MSG_QUEST_OFFER,
    MSG_QUEST_PROGRESS,
    MSG_QUEST_READY,
    MSG_QUEST_REMINDER,
    MSG_QUEST_STARTED,
    MSG_RESPAWN_CAVE,
    MSG_RESPAWN_GRAVE,
    QUEST_BLACKWATER_BITE,
    QUEST_LIVING_MUD,
    QUEST_LOST_CHARM,
    QUEST_NAMES,
    QUEST_NONE,
    QUEST_REPAIR_BRIDGE,
    QUEST_ROAD_TROUBLE,
    QUEST_STATE_ACTIVE,
    QUEST_STATE_COMPLETE,
    QUEST_STATE_NOT_STARTED,
    QUEST_STATE_READY_TO_TURN_IN,
    REPAIR_BRIDGE_REWARD_GOLD,
    REPAIR_BRIDGE_REWARD_XP,
    REPAIR_BRIDGE_TARGET,
    ROAD_TROUBLE_REWARD_GOLD,
    ROAD_TROUBLE_REWARD_XP,
    ROAD_TROUBLE_TARGET,
    STORY_STAGE_BEYOND_ROAD,
    STORY_STAGE_ROAD_TROUBLE,
    STORY_STAGE_WELCOME,
    STORY_STAGE_BLACKWATER,
    STORY_STAGE_BRIDGE,
    STORY_STAGE_COMPLETE,
    STORY_STAGE_GOBLIN_WARNED,
    STORY_STAGE_GORVAK,
    STORY_STAGE_LIVING_MUD,
    STORY_STAGE_NONE,
    STORY_STAGE_RETURN_NERISSA,
    STORY_STAGE_WARDEN_KEY,
    VALID_STORY_STAGES,
    WILLOWCROSS_SAVED_REWARD_GOLD,
    WILLOWCROSS_SAVED_REWARD_XP,
    quest_status_text,
)
from .world import (
    BORDER,
    BUILDING,
    CAVE_FLOOR,
    CAVE_WALL,
    GRASS,
    HERB,
    LOST_CHARM_X,
    LOST_CHARM_Y,
    MAP_OVERWORLD,
    MAP_PVP_REALM,
    MAP_STARTER_CAVE,
    OVERWORLD_CAVE_ENTRANCE,
    OVERWORLD_CAVE_RETURN,
    OVERWORLD_PVP_REALM_ENTRANCE,
    OVERWORLD_PVP_REALM_RETURN,
    OVERWORLD_RESPAWN,
    OVERWORLD_START,
    PALETTE_CAVE,
    PALETTE_OVERWORLD,
    PALETTE_PVP_REALM,
    PVP_REALM_ENTRY,
    PVP_REALM_EXIT,
    PVP_REALM_RESPAWN,
    STARTER_CAVE_ENTRY,
    STARTER_CAVE_EXIT,
    STARTER_CAVE_RESPAWN,
    TILESET_CAVE,
    TILESET_OVERWORLD,
    TILESET_PVP_REALM,
    ROAD,
    TREE_DAMAGED,
    TREE_FULL,
    TREE_STUMP,
    WATER,
    WORLD_H,
    WORLD_W,
    DeterministicRng,
    World,
    build_seeded_world,
    build_world_map,
)
from .schema import PLAYER_SCHEMA_VERSION
from .zones import (
    ZONE_CAVE,
    ZONE_FOREST,
    ZONE_ROAD,
    ZONE_SIZE,
    ZONE_TOWN,
    ActiveZoneState,
    SpawnRule,
    ZoneDefinition,
    ZoneId,
    zone_for_tile,
    zones_near_tile,
)
from . import story


# Fast per-cell lookup for bridge collision; the window mask iterates the tuple.
OVERWORLD_BRIDGE_SET = frozenset(OVERWORLD_BRIDGE_TILES)

DIR_NONE = 0
DIR_UP = 1
DIR_DOWN = 2
DIR_LEFT = 3
DIR_RIGHT = 4
CLIENT_AIM_UP = 0
CLIENT_AIM_DOWN = 1
CLIENT_AIM_LEFT = 2
CLIENT_AIM_RIGHT = 3
CLIENT_AIM_UP_LEFT = 4
CLIENT_AIM_UP_RIGHT = 5
CLIENT_AIM_DOWN_LEFT = 6
CLIENT_AIM_DOWN_RIGHT = 7

CLASS_HUNTER = 1
CLASS_KNIGHT = 2
CLASS_WIZARD = 3

PLAYER_MAX_HEALTH = 12
BEAVER_MOVE_COOLDOWN = 4
BEAVER_AGGRO_RANGE = 6
BEAVER_ALERT_TICKS = 60
BEAVER_CHOP_COOLDOWN = 8
BEAVER_ATTACK_DAMAGE = 1
BEAVER_ATTACK_COOLDOWN = 10
BEAVER_DECAY_TICKS = 10
PLAYER_BULLET_RANGE = 6
HUNTER_RANGE = 6
PLAYER_FIRE_BUTTON = 1
# Spare button bit the client sets when it dismisses a quest-offer dialogue with
# "decline" instead of "accept" (Phase 57). Only meaningful on the final page.
PLAYER_DIALOGUE_DECLINE_BUTTON = 0x02
# Paged dialogue reliability: a page is retransmitted a bounded number of times
# until the client acks it (via a pickup bump), covering a CRC-dropped page
# without turning dialogue into continuous traffic.
DIALOGUE_RESEND_INTERVAL_TICKS = 20
DIALOGUE_MAX_RESENDS = 6
BEAVER_KILL_SCORE = 10
BEAVER_KILL_XP = 5
BEAVER_KILL_GOLD = 1
GOBLIN_KILL_SCORE = 20
GOBLIN_KILL_XP = 10
GOBLIN_KILL_GOLD = 2
MAX_PLAYER_LEVEL = 50
FARMER_TILE = 37
GOBLIN_NPC_TILE = 38
DANIEL_TILE = 40
WILHELM_TILE = 41
LUCIAN_TILE = 42
NERISSA_TILE = 43
# Old Floodworks props (Phase 67): static cave landmarks, not entities -- like
# the named NPC tiles below, these are stamped into the outgoing terrain
# stream at a fixed marker coordinate rather than spawned as combat/dialogue
# entities. Gorvak's boss sprite draws over DEEP_PUMP_TILE while he's alive;
# once he's defeated the machine shows through underneath.
DEEP_PUMP_TILE = 49
PUMP_CONTROLS_TILE = 50
# Logical tile per NPC subtype for the static overlay. The named cast reuses the
# dedicated client logical tiles allocated in Phase 61.
NPC_STATIC_TILES = {
    NPC_FARMER: FARMER_TILE,
    NPC_GOBLIN: GOBLIN_NPC_TILE,
    NPC_NERISSA: NERISSA_TILE,
    NPC_DANIEL: DANIEL_TILE,
    NPC_WILHELM: WILHELM_TILE,
    NPC_LUCIAN: LUCIAN_TILE,
    NPC_GRIX: GOBLIN_NPC_TILE,
}
# 10s at the ~10Hz tick loop.
LOST_CHARM_RESPAWN_TICKS = 100
# 2 minutes at the ~10Hz tick loop.
HERB_RESPAWN_TICKS = 1200
# 15 minutes at the ~10Hz tick loop.
TREE_RESPAWN_TICKS = 9000
WINDOW_EDGE_MARGIN = 12
TRANSITION_COOLDOWN_TICKS = 8
RESPAWN_CORRECTION_TICKS = 20
TRANSITION_READY_GRACE_TICKS = 5
TRANSITION_LOADING_TIMEOUT_TICKS = 100
MAX_PENDING_MESSAGES = 4
# 60s of world-drop lifetime, assuming the ~10 Hz tick loop every other
# duration constant here assumes (BEAVER_DECAY_TICKS, etc).
ITEM_DESPAWN_TICKS = 600
LOOT_DROP_NEIGHBOR_OFFSETS = ((0, -1), (0, 1), (-1, 0), (1, 0))
DEFAULT_PLAYER_TOKEN = 1
REMOTE_PLAYER_STATE_ALIVE = 1
REMOTE_PLAYER_STATE_PVP_ENABLED = 2
REMOTE_PLAYER_STATE_FIRE_SHIFT = 2
REMOTE_PLAYER_STATE_FIRE_MASK = 0b1100
HUD_FLAG_PVP_ENABLED = 1
LINE_OF_SIGHT_BLOCKING = {TREE_FULL, TREE_DAMAGED, BORDER, BUILDING, WATER, CAVE_WALL}
MAP_SUMMARY_VISITED = 0x10
MAP_SUMMARY_CURRENT = 0x20
MAP_SUMMARY_MARKER_TOWN = 0x40
MAP_SUMMARY_MARKER_GRAVE = 0x80
MAP_SUMMARY_MARKER_CAVE = 0xC0
MAP_SUMMARY_WIDTH = WORLD_W // ZONE_SIZE
MAP_SUMMARY_HEIGHT = WORLD_H // ZONE_SIZE
VALID_MAP_IDS = {MAP_OVERWORLD, MAP_STARTER_CAVE, MAP_PVP_REALM}
VALID_CLASS_IDS = {CLASS_HUNTER, CLASS_KNIGHT, CLASS_WIZARD}
VALID_QUEST_IDS = {
    QUEST_NONE,
    QUEST_ROAD_TROUBLE,
    QUEST_LOST_CHARM,
    QUEST_REPAIR_BRIDGE,
    QUEST_BLACKWATER_BITE,
    QUEST_LIVING_MUD,
}
VALID_QUEST_STATES = {
    QUEST_STATE_NOT_STARTED,
    QUEST_STATE_ACTIVE,
    QUEST_STATE_READY_TO_TURN_IN,
    QUEST_STATE_COMPLETE,
}


@dataclass(frozen=True)
class EnemyType:
    name: str
    hp: int
    hp_per_level: int
    aggro_range: int
    move_cooldown: int
    attack_damage: int
    damage_per_levels: int
    attack_cooldown: int
    kill_xp: int
    xp_per_level: int
    kill_gold: int
    kill_score: int
    can_chop: bool
    drop_mode: str
    uses_generic_ai: bool = True
    is_boss: bool = False

    def hp_for_level(self, level: int) -> int:
        return self.hp + max(0, level - 1) * self.hp_per_level

    def damage_for_level(self, level: int) -> int:
        if self.damage_per_levels <= 0:
            return self.attack_damage
        return self.attack_damage + max(0, level - 1) // self.damage_per_levels

    def xp_for_level(self, level: int) -> int:
        return self.kill_xp + max(0, level - 1) * self.xp_per_level

    def gold_for_level(self, level: int) -> int:
        return self.kill_gold + max(0, level - 1) // 2


ENEMY_RESPAWN_TICKS = 900
ENEMY_TYPES = {
    # kill_xp (index 8) roughly halved from the original 5/4/6/5/8 -- the
    # overworld's 67 ambient spawns plus the cave's 27 gave a single clean
    # clear (574 XP) more XP than the entire intended level-6-by-Gorvak
    # budget, before counting respawns or the Wilhelm bridge-defense wave.
    # See xp_multiplier_for_level_gap() for the other half of the fix
    # (diminishing XP as the player outlevels the enemy).
    ENEMY_BEAVER: EnemyType("beaver", 4, 1, 6, 4, 1, 3, 10, 3, 0, 1, 10, True, "beaver"),
    ENEMY_SNAKE: EnemyType("snake", 3, 1, 7, 2, 1, 3, 8, 2, 1, 0, 12, False, "none"),
    ENEMY_SLIME: EnemyType("slime", 7, 2, 5, 6, 2, 3, 12, 3, 1, 0, 16, False, "samples"),
    # hp raised a bit (4 -> 10, 8 -> 16): both were one-shot kills for a
    # level-7+ hunter (9 ranged dmg at that level), which felt trivial en
    # route to Gorvak in the cave. Now take 2 solid hits instead of 1.
    # Level/xp_per_level untouched -- they still spawn at level 1, so this
    # doesn't fight the level-gap XP diminishing above. Goblins also spawn
    # on the overworld, not just the cave, so they get a bit tougher there
    # too (there's no per-map stat split; it's one shared species entry).
    ENEMY_BAT: EnemyType("bat", 10, 1, 8, 2, 1, 2, 7, 3, 1, 0, 14, False, "none"),
    ENEMY_GOBLIN: EnemyType("goblin", 16, 2, 9, 4, 2, 2, 10, 4, 2, 2, 20, False, "gold"),
    # hp/hp_per_level raised (40/8 -> 100/15, ~160 HP at GORVAK_LEVEL=5) so
    # the fight lasts a real number of exchanges once he can actually reach
    # the player -- at 40 HP a level-7+ hunter killed him in ~9 ranged hits.
    # kill_xp/xp_per_level trimmed (75/10 -> 50/8) since the ambient-XP
    # tuning above already does most of the work keeping pre-Gorvak levels
    # in check; a single kill shouldn't still be able to jump several
    # levels on its own. Exempt from xp_multiplier_for_level_gap (is_boss),
    # deliberately -- a one-time fixed encounter isn't farmable the way
    # ambient enemies are.
    ENEMY_GORVAK: EnemyType(
        "Pumpmaster Gorvak", 100, 15, 2, 6, 4, 1, 8, 50, 8, 20, 100,
        False, "boss", uses_generic_ai=False, is_boss=True,
    ),
}


ENEMY_KIND_HIT_PULSE = 0x80
DYNAMIC_WILHELM_SNAPSHOT_KIND = 7
DYNAMIC_WILHELM_WORKING_SNAPSHOT_KIND = 8

# The production server runs at roughly 10 Hz. Wilhelm advances at a visible
# walking pace, waits when the owner is more than eight tiles away, and spends
# two minutes working after reaching the bridge.
WILHELM_MOVE_INTERVAL_TICKS = 4
WILHELM_FOLLOW_DISTANCE = 8
BRIDGE_REPAIR_DURATION_TICKS = 1200

# Encounter-owned bridge-defense beaver waves: an initial pair as soon as
# Wilhelm starts working, replenished toward a live cap of three about every
# 20 seconds (200 ticks at 10 Hz), independent of ambient map spawn density.
BRIDGE_WAVE_INITIAL_COUNT = 2
BRIDGE_WAVE_MAX_LIVE = 3
BRIDGE_WAVE_REPLENISH_INTERVAL_TICKS = 200
BRIDGE_WAVE_SPAWN_MIN_DISTANCE = 5
BRIDGE_WAVE_SPAWN_MAX_DISTANCE = 8

# Grix's one-time "please don't hurt me" proximity callout, plan section 4.
GRIX_PROXIMITY_RANGE = 6

# Pumpmaster Gorvak: leashed boss fight, plan sections 6 / 17.11.
GORVAK_ACTIVATION_RADIUS = 6
# Raised from 2: at 2, he could only ever reach a player standing within 2
# tiles of his home spot, so backing off to HUNTER_RANGE (6) and sniping
# left him permanently stuck out of reach. 8 comfortably covers a hunter's
# max range plus margin, while still keeping him tied to his own room once
# the cave gets a real encounter region.
GORVAK_LEASH_RANGE = 8
GORVAK_ATTACK_RANGE = 1
GORVAK_LEVEL = 5
GORVAK_SUMMON_LEVEL = 4
GORVAK_INITIAL_SUMMON_DELAY_TICKS = 10
# Tightened from 40-60 (4-6s) to 25-40 (2.5-4s): with the HP increase above
# the fight runs longer, so summons should keep pace throughout instead of
# mostly landing just the one early bat before the old fight was already over.
GORVAK_SUMMON_DELAY_MIN_TICKS = 25
GORVAK_SUMMON_DELAY_MAX_TICKS = 40


def effective_aggro_range(
    enemy: Entity, target: PlayerState, spec: EnemyType
) -> int:
    """Species range reduced by level gap, with alert/script overrides."""
    if enemy.aggro_ticks > 0 or enemy.owner_id != 0 or spec.is_boss:
        return spec.aggro_range
    level_gap = target.level - enemy.level
    if level_gap <= 0:
        return spec.aggro_range
    if level_gap == 1:
        return max(1, spec.aggro_range * 2 // 3)
    if level_gap == 2:
        return max(1, spec.aggro_range // 3)
    return 1


def xp_multiplier_for_level_gap(level_gap: int) -> tuple[int, int]:
    """Numerator/denominator XP scale for a (player level - enemy level) gap.

    Same philosophy as effective_aggro_range (Phase 60) -- outleveled
    content is worth less -- but needs more/wider bands: aggro range only
    ever spans a couple of tiers before flooring out, while an ambient
    level-1 spawn can sit anywhere from "just right" to 49 levels below a
    maxed-out player. Never reaches zero on its own; a floored kill is
    still worth token XP unless a caller decides to award none outright
    (e.g. Wilhelm's bridge-defense wave).
    """
    if level_gap <= 2:
        return (1, 1)
    if level_gap <= 4:
        return (2, 3)
    if level_gap <= 7:
        return (1, 2)
    if level_gap <= 12:
        return (1, 4)
    return (1, 10)


def enemy_snapshot_kind(entity: Entity, *, include_hit_pulse: bool = False) -> int:
    """Keep the four-byte enemy record; bit 7 is reserved for Phase 61."""
    kind = entity.subtype & 0x7F
    if include_hit_pulse and entity.hit_pulse_ticks > 0:
        kind |= ENEMY_KIND_HIT_PULSE
    return kind


def dynamic_snapshot_kind(entity: Entity, *, include_hit_pulse: bool = False) -> int:
    if entity.kind == ENTITY_NPC and entity.subtype == NPC_WILHELM:
        return (
            DYNAMIC_WILHELM_WORKING_SNAPSHOT_KIND
            if entity.flags & ENTITY_FLAG_WORKING
            else DYNAMIC_WILHELM_SNAPSHOT_KIND
        )
    return enemy_snapshot_kind(entity, include_hit_pulse=include_hit_pulse)


@dataclass
class ActiveDialogue:
    """Transient per-player state for an open paged dialogue modal (Phase 57).

    Never persisted: an interrupted conversation simply resets when the player
    disconnects. Each entry in ``pages`` is a display page (already word-wrapped
    to fit one screen); it is transmitted as one or more <=47-char chunk packets
    that the client reassembles. ``index`` is the display page being shown and
    ``chunk`` the next chunk to send; the resend counters give a bounded retry so
    a CRC-dropped chunk still reaches the client.
    """

    dialogue_id: int
    speaker_id: int
    pages: tuple[str, ...]
    quest_offer_id: int = 0
    index: int = 0
    chunk: int = 0
    resend_timer: int = 0
    resends_left: int = 0


@dataclass(frozen=True)
class MapTransition:
    from_map: int
    from_x: int
    from_y: int
    to_map: int
    to_x: int
    to_y: int
    required_level: int = 1
    tileset_id: int = TILESET_OVERWORLD
    palette_id: int = PALETTE_OVERWORLD


@dataclass
class PlayerState:
    token: int = DEFAULT_PLAYER_TOKEN
    username: str = ""
    x: int = 10
    y: int = 10
    health: int = PLAYER_MAX_HEALTH
    max_health: int = PLAYER_MAX_HEALTH
    score: int = 0
    class_id: int = CLASS_HUNTER
    level: int = 1
    xp: int = 0
    xp_next: int = 20
    gold: int = 0
    inventory: Inventory = field(default_factory=Inventory)
    facing: int = CLIENT_AIM_RIGHT
    active_quest_id: int = QUEST_NONE
    quest_state: int = QUEST_STATE_NOT_STARTED
    quest_progress: int = 0
    quest_target: int = 0
    pending_quest_offer_id: int = QUEST_NONE
    # --- The Dam Below: persistent main-story milestones --------------------
    # These are durable and never inferred from active_quest_id (plan 17.1).
    story_stage: int = STORY_STAGE_NONE
    story_step: int = 0
    bridge_materials_staged: bool = False
    bridge_repaired: bool = False
    grix_callout_seen: bool = False
    warden_key_collected: bool = False
    gorvak_defeated: bool = False
    deep_pump_shutdown: bool = False
    pvp_unlocked: bool = False
    map_id: int = MAP_OVERWORLD
    respawn_map_id: int = MAP_OVERWORLD
    respawn_x: int = OVERWORLD_RESPAWN[0]
    respawn_y: int = OVERWORLD_RESPAWN[1]
    pending_map_change: MapTransition | None = None
    transition_cooldown: int = 0
    last_fire_counter: int = 0
    shot_counter: int = 0
    last_pickup_counter: int = 0
    pickup_events: int = 0
    pvp_enabled: bool = False
    pvp_kills: int = 0
    last_pvp_toggle_counter: int = 0
    last_buttons: int = 0
    activity_messages: list[str] = field(default_factory=list)
    pending_messages: list[tuple[int, str]] = field(default_factory=list)
    latest_activity_message: str = ""
    latest_message_id: int = MSG_NONE
    message_counter: int = 0
    respawn_counter: int = 0
    latest_respawn_event: RespawnEventPacket | None = None
    respawn_correction_ticks: int = 0
    transition_loading: bool = False
    transition_loading_ticks: int = 0
    transition_grace_ticks: int = 0
    visited_zones: set[ZoneId] = field(default_factory=set)
    active_dialogue: "ActiveDialogue | None" = None
    # Transient: set when per-player terrain changes (e.g. bridge repair) so the
    # session forces a terrain resync; the hybrid server consumes and clears it.
    pending_terrain_resync: bool = False


# A display page is word-wrapped to this many characters, then split into
# <=REALTIME_DIALOGUE_MAX_TEXT chunk packets. Bounded by the client's dialogue
# text buffer in the reclaimed $7C00 region (must stay < 256 for 8-bit offsets).
DIALOGUE_PAGE_MAX_CHARS = 141


def dialogue_page_chunks(page_text: str) -> list[str]:
    """Split a display page into transmit chunks of <=REALTIME_DIALOGUE_MAX_TEXT.

    Chunk boundaries are byte splits (not word boundaries) -- the client
    reassembles chunks into the full page text before word-wrapping for display,
    so a chunk may end mid-word without any visible effect.
    """
    if not page_text:
        return [""]
    width = REALTIME_DIALOGUE_MAX_TEXT
    return [page_text[i : i + width] for i in range(0, len(page_text), width)]


def paginate_dialogue_text(
    paragraphs, width: int = DIALOGUE_PAGE_MAX_CHARS
) -> tuple[str, ...]:
    """Greedily word-wrap each paragraph into <=width-char display pages.

    Each input string is a logical paragraph and always starts a fresh page, so
    paragraph breaks stay clean. An over-long single word is hard-split so it can
    never exceed a page's character budget.
    """
    pages: list[str] = []
    for paragraph in paragraphs:
        words = str(paragraph).split()
        if not words:
            continue
        current = ""
        for word in words:
            while len(word) > width:
                if current:
                    pages.append(current)
                    current = ""
                pages.append(word[:width])
                word = word[width:]
            candidate = word if not current else f"{current} {word}"
            if len(candidate) <= width:
                current = candidate
            else:
                pages.append(current)
                current = word
        if current:
            pages.append(current)
    return tuple(pages)


def serialize_player_state(player: PlayerState) -> dict[str, object]:
    return {
        # Stamped on every save so a record can be told apart from one written
        # by an older generation of the game (see server/schema.py).
        "schema_version": PLAYER_SCHEMA_VERSION,
        "class_id": player.class_id,
        "level": player.level,
        "xp": player.xp,
        "xp_next": player.xp_next,
        "health": player.health,
        "max_health": player.max_health,
        "gold": player.gold,
        "inventory": [list(slot) for slot in player.inventory.as_tuple()],
        "active_quest_id": player.active_quest_id,
        "quest_state": player.quest_state,
        "quest_progress": player.quest_progress,
        "quest_target": player.quest_target,
        "pending_quest_offer_id": player.pending_quest_offer_id,
        "story_stage": player.story_stage,
        "story_step": player.story_step,
        "bridge_materials_staged": player.bridge_materials_staged,
        "bridge_repaired": player.bridge_repaired,
        "grix_callout_seen": player.grix_callout_seen,
        "warden_key_collected": player.warden_key_collected,
        "gorvak_defeated": player.gorvak_defeated,
        "deep_pump_shutdown": player.deep_pump_shutdown,
        "pvp_unlocked": player.pvp_unlocked,
        "map_id": player.map_id,
        "x": player.x,
        "y": player.y,
        "respawn_map_id": player.respawn_map_id,
        "respawn_x": player.respawn_x,
        "respawn_y": player.respawn_y,
        "pvp_enabled": player.pvp_enabled,
        "pvp_kills": player.pvp_kills,
        "visited_zones": [[zone.map_id, zone.zx, zone.zy] for zone in sorted(player.visited_zones)],
    }


def _record_int(record: dict[str, object], key: str, default: int) -> int:
    value = record.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _record_bool(record: dict[str, object], key: str, default: bool) -> bool:
    value = record.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def player_state_is_current(payload: dict[str, object]) -> bool:
    """True when this saved state was written by the current game generation.

    An unstamped payload reads as version 0 and is therefore stale.
    ``deserialize_player_state`` still loads either kind without complaint --
    this predicate only decides whether the save is worth *keeping*.
    """
    return _record_int(payload, "schema_version", 0) == PLAYER_SCHEMA_VERSION


def deserialize_player_state(token: int, username: str, payload: dict[str, object]) -> PlayerState:
    class_id = _record_int(payload, "class_id", CLASS_HUNTER)
    if class_id not in VALID_CLASS_IDS:
        class_id = CLASS_HUNTER
    level = max(1, min(MAX_PLAYER_LEVEL, _record_int(payload, "level", 1)))
    max_health = max_hp_for_level(level, class_id)
    player = PlayerState(token=token, username=display_username(username, token), class_id=class_id, level=level)
    player.max_health = max_health
    player.xp = max(0, min(9999, _record_int(payload, "xp", 0)))
    player.xp_next = xp_needed_for_next_level(player.level)
    player.health = max(1, min(player.max_health, _record_int(payload, "health", player.max_health)))
    player.gold = max(0, min(9999, _record_int(payload, "gold", 0)))
    player.active_quest_id = _record_int(payload, "active_quest_id", QUEST_NONE)
    if player.active_quest_id not in VALID_QUEST_IDS:
        player.active_quest_id = QUEST_NONE
    player.quest_state = _record_int(payload, "quest_state", QUEST_STATE_NOT_STARTED)
    if player.quest_state not in VALID_QUEST_STATES:
        player.quest_state = QUEST_STATE_NOT_STARTED
    player.pending_quest_offer_id = _record_int(payload, "pending_quest_offer_id", QUEST_NONE)
    if player.pending_quest_offer_id not in VALID_QUEST_IDS:
        player.pending_quest_offer_id = QUEST_NONE
    if player.active_quest_id == QUEST_NONE:
        player.quest_state = QUEST_STATE_NOT_STARTED
        player.quest_progress = 0
        player.quest_target = 0
    else:
        player.quest_target = QUEST_TARGETS.get(player.active_quest_id, 0)
        player.quest_progress = max(0, min(player.quest_target, _record_int(payload, "quest_progress", 0)))
    player.story_stage = _record_int(payload, "story_stage", STORY_STAGE_NONE)
    if player.story_stage not in VALID_STORY_STAGES:
        player.story_stage = STORY_STAGE_NONE
    # The scalar active_quest_id/quest_state system only covers the first
    # five quests (Road Trouble through Living Mud); later story stages
    # (goblin warned, warden key, Gorvak, return to Nerissa) have no quest
    # id of their own, so nothing ever overwrites a stale "Living Mud done"
    # once the story moves past it. A save from well beyond that point
    # would otherwise keep resurfacing it as the HUD quest line forever.
    if player.story_stage > STORY_STAGE_LIVING_MUD and player.active_quest_id == QUEST_LIVING_MUD:
        player.active_quest_id = QUEST_NONE
        player.quest_state = QUEST_STATE_NOT_STARTED
        player.quest_progress = 0
        player.quest_target = 0
    player.story_step = max(0, _record_int(payload, "story_step", 0))
    player.bridge_materials_staged = _record_bool(payload, "bridge_materials_staged", False)
    player.bridge_repaired = _record_bool(payload, "bridge_repaired", False)
    player.grix_callout_seen = _record_bool(payload, "grix_callout_seen", False)
    player.warden_key_collected = _record_bool(payload, "warden_key_collected", False)
    player.gorvak_defeated = _record_bool(payload, "gorvak_defeated", False)
    player.deep_pump_shutdown = _record_bool(payload, "deep_pump_shutdown", False)
    player.pvp_unlocked = _record_bool(payload, "pvp_unlocked", False)
    player.map_id = _record_int(payload, "map_id", MAP_OVERWORLD)
    player.x = _record_int(payload, "x", OVERWORLD_RESPAWN[0])
    player.y = _record_int(payload, "y", OVERWORLD_RESPAWN[1])
    player.respawn_map_id = _record_int(payload, "respawn_map_id", player.map_id)
    player.respawn_x = _record_int(payload, "respawn_x", player.x)
    player.respawn_y = _record_int(payload, "respawn_y", player.y)
    player.pvp_enabled = _record_bool(payload, "pvp_enabled", False)
    player.pvp_kills = max(0, min(9999, _record_int(payload, "pvp_kills", 0)))
    player.inventory = Inventory()
    raw_inventory = payload.get("inventory", ())
    if isinstance(raw_inventory, list):
        for entry in raw_inventory:
            if (
                isinstance(entry, (list, tuple))
                and len(entry) == 2
                and isinstance(entry[0], int)
                and isinstance(entry[1], int)
            ):
                player.inventory.add_item(entry[0], entry[1])
    raw_zones = payload.get("visited_zones", ())
    if isinstance(raw_zones, list):
        for entry in raw_zones:
            if (
                isinstance(entry, (list, tuple))
                and len(entry) == 3
                and isinstance(entry[0], int)
                and isinstance(entry[1], int)
                and isinstance(entry[2], int)
            ):
                player.visited_zones.add(ZoneId(entry[0], entry[1], entry[2]))
    return player


@dataclass(frozen=True)
class RespawnPoint:
    map_id: int
    x: int
    y: int
    name_id: int = 0
    flags: int = 0


RESPAWN_POINTS = (
    RespawnPoint(MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1]),
)


def display_username(username: str, token: int) -> str:
    cleaned = "".join(ch for ch in username if 32 <= ord(ch) <= 126).strip()
    if not cleaned:
        cleaned = f"Player{token & 0xFFFF:04X}"
    return cleaned[:12]


MAP_TRANSITIONS = (
    MapTransition(
        from_map=MAP_OVERWORLD,
        from_x=OVERWORLD_CAVE_ENTRANCE[0],
        from_y=OVERWORLD_CAVE_ENTRANCE[1],
        to_map=MAP_STARTER_CAVE,
        to_x=STARTER_CAVE_ENTRY[0],
        to_y=STARTER_CAVE_ENTRY[1],
        tileset_id=TILESET_CAVE,
        palette_id=PALETTE_CAVE,
    ),
    MapTransition(
        from_map=MAP_STARTER_CAVE,
        from_x=STARTER_CAVE_EXIT[0],
        from_y=STARTER_CAVE_EXIT[1],
        to_map=MAP_OVERWORLD,
        to_x=OVERWORLD_CAVE_RETURN[0],
        to_y=OVERWORLD_CAVE_RETURN[1],
        tileset_id=TILESET_OVERWORLD,
        palette_id=PALETTE_OVERWORLD,
    ),
    MapTransition(
        from_map=MAP_OVERWORLD,
        from_x=OVERWORLD_PVP_REALM_ENTRANCE[0],
        from_y=OVERWORLD_PVP_REALM_ENTRANCE[1],
        to_map=MAP_PVP_REALM,
        to_x=PVP_REALM_ENTRY[0],
        to_y=PVP_REALM_ENTRY[1],
        required_level=5,
        tileset_id=TILESET_PVP_REALM,
        palette_id=PALETTE_PVP_REALM,
    ),
    MapTransition(
        from_map=MAP_PVP_REALM,
        from_x=PVP_REALM_EXIT[0],
        from_y=PVP_REALM_EXIT[1],
        to_map=MAP_OVERWORLD,
        to_x=OVERWORLD_PVP_REALM_RETURN[0],
        to_y=OVERWORLD_PVP_REALM_RETURN[1],
        tileset_id=TILESET_OVERWORLD,
        palette_id=PALETTE_OVERWORLD,
    ),
)

# Generic accept-quest-offer dispatch: target count and the flavor text
# shown the moment the offer is accepted, keyed by quest id. Every quest
# past the first goes here instead of growing another hardcoded branch.
#
# QUEST_TARGETS must list *every* quest id that can ever land in
# ``active_quest_id``, not just the ones that go through the generic offer
# path: ``_normalize_restored_player()`` looks up the target here for
# whatever quest is active on every save/load, and a missing entry silently
# zeroes ``quest_target`` for a player restored mid-quest.
QUEST_TARGETS = {
    QUEST_ROAD_TROUBLE: ROAD_TROUBLE_TARGET,
    QUEST_LOST_CHARM: LOST_CHARM_TARGET,
    QUEST_REPAIR_BRIDGE: REPAIR_BRIDGE_TARGET,
    QUEST_BLACKWATER_BITE: BLACKWATER_TARGET,
    QUEST_LIVING_MUD: LIVING_MUD_TARGET,
}
QUEST_START_TEXT = {
    QUEST_ROAD_TROUBLE: "Their dams keep flooding the road out.",
    QUEST_LOST_CHARM: "Lost my charm in the cave to the east.",
}


class GameState:
    """One shared world set; every player is a token-keyed PlayerState."""

    def __init__(
        self,
        seed: int = 1,
        world: World | None = None,
        map_id: int = MAP_OVERWORLD,
        zone_spawns_enabled: bool = False,
        create_default_player: bool = True,
        player_state_loader: Callable[[int], dict[str, object] | None] | None = None,
        player_state_saver: Callable[[int, str, dict[str, object]], None] | None = None,
    ) -> None:
        self.seed = seed & 0xFFFF
        self.rng = DeterministicRng(self.seed)
        self.tick = 0
        self.zone_spawns_enabled = zone_spawns_enabled
        # tile_update is world-level: (map_id, x, y, tile_id)
        self.tile_update: tuple[int, int, int, int] | None = None
        self.worlds: dict[int, World] = {}
        self._statics_spawned: set[int] = set()
        self.players: dict[int, PlayerState] = {}
        self.offline_players: dict[int, PlayerState] = {}
        self.player_entities: dict[int, int] = {}
        self.active_zones: set[ZoneId] = set()
        self.active_zone_states: dict[ZoneId, ActiveZoneState] = {}
        self.zone_events: list[tuple[str, ZoneId]] = []
        self.entities: dict[int, Entity] = {}
        self.next_entity_counter = 1
        self.beavers: list[Entity] = []
        # Live static NPC entities keyed by subtype, for generic interaction and
        # tile overlay. Populated as each named NPC is spawned.
        self.named_npc_ids: dict[int, int] = {}
        # Temporary, per-owner encounter instances. These are intentionally not
        # serialized; only stable PlayerState milestones survive a restart.
        self.scripted_encounters: dict[tuple[int, str], ScriptedEncounter] = {}
        self.player_state_loader = player_state_loader
        self.player_state_saver = player_state_saver
        if create_default_player:
            # Reserve entity id 1 for the default player before the farmer,
            # matching the historical single-player id layout.
            self.players[DEFAULT_PLAYER_TOKEN] = PlayerState(token=DEFAULT_PLAYER_TOKEN, map_id=map_id)
            if map_forces_pvp(map_id):
                self.players[DEFAULT_PLAYER_TOKEN].pvp_enabled = True
            self.player_entities[DEFAULT_PLAYER_TOKEN] = self._spawn_player_entity(
                self.players[DEFAULT_PLAYER_TOKEN]
            )
        self.farmer_entity_id = 0
        self.goblin_npc_entity_id = 0
        self.lost_charm_entity_id = self.spawn_lost_charm_item()
        if world is not None:
            self.worlds[map_id] = world
            self._spawn_static_entities_for_map(map_id)
        if create_default_player:
            self.world_for(map_id)
            self.update_active_zones()

    # ------------------------------------------------------------------
    # Players and worlds

    @property
    def player(self) -> PlayerState:
        """Single-player compatibility alias for the default player."""
        return self.players[DEFAULT_PLAYER_TOKEN]

    @property
    def world(self) -> World:
        return self.world_for(self.player.map_id)

    @world.setter
    def world(self, value: World) -> None:
        self.worlds[self.player.map_id] = value

    @property
    def player_entity_id(self) -> int:
        return self.player_entities[DEFAULT_PLAYER_TOKEN]

    def world_for(self, map_id: int) -> World:
        world = self.worlds.get(map_id)
        if world is None:
            world = build_world_map(map_id, self.seed)
            self.worlds[map_id] = world
        self._spawn_static_entities_for_map(map_id)
        return world

    def _spawn_static_entities_for_map(self, map_id: int) -> None:
        if map_id in self._statics_spawned:
            return
        self._statics_spawned.add(map_id)
        self._spawn_named_npcs_for_map(map_id)
        for x, y, enemy_kind in STATIC_ENEMY_SPAWNS.get(map_id, ()):
            spawn = self._validated_enemy_spawn(map_id, x, y)
            if spawn is None:
                continue
            self.spawn_enemy(enemy_kind, spawn[0], spawn[1], map_id=map_id, home_x=spawn[0], home_y=spawn[1])

    def _spawn_named_npcs_for_map(self, map_id: int) -> None:
        world = self.worlds.get(map_id)
        if world is None:
            return
        for subtype, spawn_map_id, x, y in NAMED_NPC_SPAWNS:
            if spawn_map_id != map_id or subtype in self.named_npc_ids:
                continue
            if not world.player_can_enter(x, y):
                raise ValueError(f"named NPC spawn {subtype} is not walkable at ({x},{y}) on map {map_id}")
            if self.entity_at(map_id, x, y, blocking_only=False) is not None:
                raise ValueError(f"named NPC spawn {subtype} is occupied at ({x},{y}) on map {map_id}")
            entity_id = self.spawn_named_npc(subtype, map_id, x, y)
            if subtype == NPC_DANIEL:
                self.farmer_entity_id = entity_id
            elif subtype == NPC_GRIX:
                self.goblin_npc_entity_id = entity_id

    def _validated_enemy_spawn(self, map_id: int, x: int, y: int) -> tuple[int, int] | None:
        world = self.worlds[map_id]
        candidates = (
            (x, y),
            (x + 1, y),
            (x - 1, y),
            (x, y + 1),
            (x, y - 1),
            (x + 1, y + 1),
            (x - 1, y + 1),
            (x + 1, y - 1),
            (x - 1, y - 1),
            (x + 2, y),
            (x - 2, y),
            (x, y + 2),
            (x, y - 2),
        )
        for sx, sy in candidates:
            if world.enemy_can_enter(sx, sy) and self.entity_at(map_id, sx, sy, blocking_only=False) is None:
                return (sx, sy)
        return None

    def add_player(
        self,
        token: int,
        x: int | None = None,
        y: int | None = None,
        map_id: int = MAP_OVERWORLD,
    ) -> PlayerState:
        existing = self.players.get(token)
        if existing is not None:
            return existing
        player = PlayerState(token=token, map_id=map_id)
        if map_forces_pvp(map_id):
            player.pvp_enabled = True
        # A brand-new player (no explicit position given) starts at the
        # map-generated overworld start marker, not the PlayerState dataclass
        # default -- that default exists only as an arbitrary placeholder for
        # tests/fixtures that don't care where the player is.
        if x is None and map_id == MAP_OVERWORLD:
            x = OVERWORLD_START[0]
        if y is None and map_id == MAP_OVERWORLD:
            y = OVERWORLD_START[1]
        if x is not None:
            player.x = x
        if y is not None:
            player.y = y
        return self._attach_player(player)

    def ensure_player(self, token: int) -> PlayerState:
        player = self.players.get(token)
        if player is not None:
            return player
        parked = self.offline_players.pop(token, None)
        if parked is not None:
            return self._attach_player(parked, require_position_sync=True)
        if self.player_state_loader is not None:
            record = self.player_state_loader(token)
            restored = self._restore_player_from_record(token, record)
            if restored is not None:
                return restored
        return self.add_player(token)

    def set_player_username(self, token: int, username: str) -> PlayerState:
        player = self.ensure_player(token)
        player.username = display_username(username, token)
        self._mark_player_state_dirty(player)
        return player

    def player_display_name(self, token: int) -> str:
        player = self.players.get(token) or self.offline_players.get(token)
        if player is None:
            return display_username("", token)
        return display_username(player.username, token)

    def remove_player(self, token: int) -> tuple[set[ZoneId], set[ZoneId]]:
        self.cleanup_scripted_encounters_for_owner(token)
        self.players.pop(token, None)
        self.offline_players.pop(token, None)
        entity_id = self.player_entities.pop(token, None)
        if entity_id is not None:
            self.entities.pop(entity_id, None)
        return self.update_active_zones()

    def detach_player(self, token: int) -> tuple[set[ZoneId], set[ZoneId]]:
        """Remove a player from the world but keep their state for resume."""
        self.cleanup_scripted_encounters_for_owner(token)
        player = self.players.pop(token, None)
        if player is not None:
            player.active_dialogue = None
            self._normalize_story_state(player)
            self.offline_players[token] = player
            self._mark_player_state_dirty(player)
        entity_id = self.player_entities.pop(token, None)
        if entity_id is not None:
            self.entities.pop(entity_id, None)
        return self.update_active_zones()

    def _attach_player(self, player: PlayerState, require_position_sync: bool = False) -> PlayerState:
        self.players[player.token] = player
        self.world_for(player.map_id)
        self.player_entities[player.token] = self._spawn_player_entity(player)
        if require_position_sync:
            player.respawn_correction_ticks = RESPAWN_CORRECTION_TICKS
        self.update_active_zones()
        return player

    def _restore_player_from_record(self, token: int, record: dict[str, object] | None) -> PlayerState | None:
        if not isinstance(record, dict):
            return None
        payload = record.get("player_state")
        if not isinstance(payload, dict):
            return None
        player = deserialize_player_state(token, str(record.get("username", "")), payload)
        self._normalize_restored_player(player)
        return self._attach_player(player, require_position_sync=True)

    def _fallback_respawn(self, map_id: int, x: int, y: int) -> RespawnPoint:
        if map_id not in VALID_MAP_IDS:
            return RespawnPoint(MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1])
        return self.nearest_respawn_point(map_id, x, y)

    def _position_is_enterable(self, map_id: int, x: int, y: int) -> bool:
        if map_id not in VALID_MAP_IDS:
            return False
        world = self.world_for(map_id)
        return world.in_bounds(x, y) and world.player_can_enter(x, y)

    def _normalize_restored_player(self, player: PlayerState) -> None:
        if player.map_id not in VALID_MAP_IDS:
            player.map_id = MAP_OVERWORLD
            player.x, player.y = OVERWORLD_RESPAWN
        if player.respawn_map_id == MAP_PVP_REALM:
            player.respawn_x, player.respawn_y = PVP_REALM_RESPAWN
        if player.respawn_map_id not in VALID_MAP_IDS:
            player.respawn_map_id = player.map_id
            player.respawn_x = player.x
            player.respawn_y = player.y
        if not self._position_is_enterable(player.respawn_map_id, player.respawn_x, player.respawn_y):
            fallback = self._fallback_respawn(player.respawn_map_id, player.respawn_x, player.respawn_y)
            player.respawn_map_id = fallback.map_id
            player.respawn_x = fallback.x
            player.respawn_y = fallback.y
        if not self._position_is_enterable(player.map_id, player.x, player.y):
            player.map_id = player.respawn_map_id
            player.x = player.respawn_x
            player.y = player.respawn_y
        if not self._position_is_enterable(player.map_id, player.x, player.y):
            fallback = self._fallback_respawn(player.map_id, player.x, player.y)
            player.map_id = fallback.map_id
            player.x = fallback.x
            player.y = fallback.y
            player.respawn_map_id = fallback.map_id
            player.respawn_x = fallback.x
            player.respawn_y = fallback.y
        player.max_health = max_hp_for_level(player.level, player.class_id)
        player.health = max(1, min(player.max_health, player.health))
        player.xp_next = xp_needed_for_next_level(player.level)
        if player.active_quest_id == QUEST_NONE:
            player.quest_state = QUEST_STATE_NOT_STARTED
            player.quest_progress = 0
            player.quest_target = 0
        else:
            player.quest_target = QUEST_TARGETS.get(player.active_quest_id, 0)
            player.quest_progress = min(player.quest_target, player.quest_progress)
        self._normalize_story_state(player)
        if map_forces_pvp(player.map_id):
            player.pvp_enabled = True

    def _normalize_story_state(self, player: PlayerState) -> None:
        """Repair impossible main-story milestone combinations on restore.

        Milestones form a prerequisite chain, so a later milestone forces every
        earlier one true, and ``story_stage`` is raised to at least the floor
        implied by the furthest milestone reached. Transient encounters (bridge
        defense, Gorvak fight) are never persisted, so a save captured mid-fight
        is rewound to the stable start-of-encounter checkpoint; the durable
        ``bridge_repaired`` / ``gorvak_defeated`` flags remain the sole record of
        whether the encounter was actually finished (plan section 17.1).
        """
        if player.pvp_unlocked:
            player.deep_pump_shutdown = True
        if player.deep_pump_shutdown:
            player.gorvak_defeated = True
            player.warden_key_collected = True

        floor = STORY_STAGE_NONE
        if player.warden_key_collected:
            floor = max(floor, STORY_STAGE_WARDEN_KEY)
        if player.gorvak_defeated:
            floor = max(floor, STORY_STAGE_GORVAK)
        if player.deep_pump_shutdown:
            floor = max(floor, STORY_STAGE_RETURN_NERISSA)
        if player.pvp_unlocked:
            floor = max(floor, STORY_STAGE_COMPLETE)
        if player.story_stage < floor:
            player.story_stage = floor

        # Rewind interrupted transient encounters to their stable retry point.
        if player.story_stage == STORY_STAGE_BRIDGE and not player.bridge_repaired:
            player.story_step = 0
        if player.story_stage == STORY_STAGE_GORVAK and not player.gorvak_defeated:
            player.story_step = 0

    def _mark_player_state_dirty(self, player: PlayerState) -> None:
        if self.player_state_saver is None:
            return
        self.player_state_saver(player.token, player.username, serialize_player_state(player))

    def player_for(self, token: int | None) -> PlayerState:
        if token is None:
            return self.player
        return self.players[token]

    def players_on_map(self, map_id: int) -> list[PlayerState]:
        return [player for player in self.players.values() if player.map_id == map_id]

    # ------------------------------------------------------------------
    # Player-owned entity policy

    def entity_visible_to_player(self, entity: Entity, player: PlayerState) -> bool:
        """Whether an entity belongs in this player's view/lookup results."""
        if not entity.is_live or (entity.flags & ENTITY_FLAG_VISIBLE) == 0:
            return False
        if (
            entity.kind == ENTITY_NPC
            and entity.subtype == NPC_WILHELM
            and entity.owner_id == 0
            and self._player_has_owned_wilhelm(player)
        ):
            return False
        if entity.owner_id == 0 or entity.owner_id == player.token:
            return True
        return (entity.flags & ENTITY_FLAG_PERSONAL) == 0

    def entity_blocks_player(self, entity: Entity, player: PlayerState) -> bool:
        """Owned story entities do not cross-block unrelated encounter owners."""
        if not entity.is_blocking or not self.entity_visible_to_player(entity, player):
            return False
        if entity.kind == ENTITY_PLAYER:
            return entity.owner_id != player.token
        if entity.owner_id == 0 or entity.owner_id == player.token:
            return True
        return (entity.flags & ENTITY_FLAG_BLOCKS_OTHERS) != 0

    def _player_has_owned_wilhelm(self, player: PlayerState) -> bool:
        encounter = self.get_scripted_encounter(player.token, "bridge_repair")
        if encounter is None or encounter.escort_entity_id == 0:
            return False
        npc = self.entities.get(encounter.escort_entity_id)
        return (
            npc is not None
            and npc.is_live
            and npc.kind == ENTITY_NPC
            and npc.subtype == NPC_WILHELM
            and npc.owner_id == player.token
        )

    def entity_collectible_by_player(self, entity: Entity, player: PlayerState) -> bool:
        """Shared drops are public; owned quest items remain with their owner."""
        return (
            entity.kind == ENTITY_ITEM
            and self.entity_visible_to_player(entity, player)
            and (entity.owner_id == 0 or entity.owner_id == player.token)
        )

    def entity_progress_owner(
        self, entity: Entity, attacker: PlayerState
    ) -> PlayerState | None:
        """Resolve scripted progress separately from ordinary attacker rewards."""
        if entity.owner_id == 0:
            return attacker
        return self.players.get(entity.owner_id)

    def _spawn_player_entity(self, player: PlayerState) -> int:
        entity_id = self.next_entity_id()
        self.entities[entity_id] = Entity(
            entity_id=entity_id,
            kind=ENTITY_PLAYER,
            subtype=0,
            map_id=player.map_id,
            x=player.x,
            y=player.y,
            hp=player.health,
            max_hp=player.max_health,
            flags=ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING,
            owner_id=player.token,
            zone_id=zone_for_tile(player.map_id, player.x, player.y),
        )
        return entity_id

    def _sync_player_entity(self, player: PlayerState | None = None) -> None:
        players = (player,) if player is not None else tuple(self.players.values())
        for target in players:
            entity = self.entities.get(self.player_entities.get(target.token, 0))
            if entity is None:
                continue
            entity.map_id = target.map_id
            entity.x = target.x
            entity.y = target.y
            entity.hp = target.health
            entity.max_hp = target.max_health
            entity.zone_id = zone_for_tile(target.map_id, target.x, target.y)

    def _apply_map_pvp_policy(self, player: PlayerState, previous_map_id: int | None = None) -> None:
        if map_forces_pvp(player.map_id):
            player.pvp_enabled = True
        elif previous_map_id == MAP_PVP_REALM:
            player.pvp_enabled = False

    # ------------------------------------------------------------------
    # Input application

    def apply_input(self, intent: InputIntent, token: int | None = None) -> None:
        player = self.player_for(token)
        if self._apply_fire(player, intent):
            return
        dx, dy = stick_delta(intent.direction)
        if dx == 0 and dy == 0:
            return
        if dx != 0 and dy != 0:
            if self._try_move_player(player, player.x + dx, player.y + dy):
                return
            if self._try_move_player(player, player.x, player.y + dy):
                return
            self._try_move_player(player, player.x + dx, player.y)
            return
        self._try_move_player(player, player.x + dx, player.y + dy)

    def _try_move_player(self, player: PlayerState, nx: int, ny: int) -> bool:
        world = self.world_for(player.map_id)
        if not self._player_destination_allowed(player, nx, ny, world):
            return False
        if player.health < player.max_health and world.consume_herb_if_present(nx, ny, HERB_RESPAWN_TICKS):
            self._heal_player_from_herb(player)
            self.tile_update = (player.map_id, nx, ny, 0)
            self._mark_player_state_dirty(player)
        player.x = nx
        player.y = ny
        self.pickup_current_item(player)
        self._apply_transition_if_present(player)
        self._sync_player_entity(player)
        self.update_active_zones()
        return True

    def apply_player_state(self, state: PlayerStatePacket, token: int | None = None) -> bool:
        player = self.player_for(token)
        player.facing = state.facing
        if player.transition_loading:
            # Paused until MAP_READY: the reported coordinates may still be
            # the old map's. Hold the player at the transition spawn. The
            # button edges are dropped rather than deferred -- they were aimed
            # at a world that is being replaced.
            self._discard_player_state_inputs(player, state)
            return False
        if player.respawn_correction_ticks > 0:
            if state.x != player.x or state.y != player.y:
                player.respawn_correction_ticks -= 1
                self._discard_player_state_inputs(player, state)
                return False
            player.respawn_correction_ticks = 0
        world = self.world_for(player.map_id)
        if not self._player_destination_allowed(player, state.x, state.y, world):
            # The step is refused, but the buttons on it are not: the player is
            # still standing where the server thinks, so a fire/pickup/PvP edge
            # in this packet has to be consumed here. Returning early used to
            # leave the edge un-acked, and the session re-applies its last
            # packet every tick (hybrid_server._tick keeps session.latest), so
            # the shot went off later -- the moment the blocker moved, or on
            # whatever the client's next accepted packet happened to be. That
            # is the phantom "the other player moved and I fired" shot.
            self._apply_player_state_inputs(player, state)
            return False
        if player.health < player.max_health and world.consume_herb_if_present(state.x, state.y, HERB_RESPAWN_TICKS):
            self._heal_player_from_herb(player)
            self.tile_update = (player.map_id, state.x, state.y, 0)
            self._mark_player_state_dirty(player)
        old_x = player.x
        old_y = player.y
        player.x = state.x
        player.y = state.y
        # A fast client (the Lynx runs its move cadence at the 10 Hz tick and
        # coalesces a right-then-down pair into one diagonal delta) can report a
        # position two tiles away from where it last was. pickup_current_item
        # only checks the destination, so the corner tile the player actually
        # walked through was silently skipped -- items "wouldn't pick up" unless
        # you stopped exactly on them. Collect along the whole traversed path.
        self._pickup_items_along_path(player, old_x, old_y, state.x, state.y)
        self._apply_transition_if_present(player)
        self._sync_player_entity(player)
        self.update_active_zones()
        self._apply_player_state_inputs(player, state)
        return True

    def _apply_player_state_inputs(self, player: PlayerState, state: PlayerStatePacket) -> None:
        """Act on the button/counter edges carried by a PLAYER_STATE.

        Every exit from apply_player_state has to run either this or
        _discard_player_state_inputs, or the edge stays pending and replays on
        a later packet.
        """
        self._apply_player_state_fire(player, state)
        self._apply_player_state_pickup(player, state)
        self._apply_player_state_pvp_toggle(player, state)
        player.last_buttons = state.buttons

    def _discard_player_state_inputs(self, player: PlayerState, state: PlayerStatePacket) -> None:
        """Ack the edges without acting on them (see apply_player_state)."""
        player.last_fire_counter = state.fire_counter
        player.last_pickup_counter = state.pickup_counter
        player.last_pvp_toggle_counter = state.pvp_toggle_counter
        player.last_buttons = state.buttons

    def complete_bridge_repair(self, player: PlayerState) -> None:
        """Mark this player's bridge repaired: reveal the road and persist it.

        Idempotent. The Wilhelm bridge-defense event (Phase 59) calls this on
        success; the terrain-resync flag makes the session re-send the now-road
        cells so the player stops seeing water (plan 17.5).
        """
        if player.bridge_repaired:
            return
        player.bridge_repaired = True
        player.pending_terrain_resync = True
        self._mark_player_state_dirty(player)

    def consume_pending_terrain_resync(self, token: int | None = None) -> bool:
        """Return and clear a player's pending terrain-resync flag (Phase 58)."""
        player = self.players.get(token if token is not None else DEFAULT_PLAYER_TOKEN)
        if player is None or not player.pending_terrain_resync:
            return False
        player.pending_terrain_resync = False
        return True

    def _bridge_blocks(self, player: PlayerState, x: int, y: int) -> bool:
        """True if an unrepaired bridge cell blocks this player at (x, y).

        Mirrors the WATER mask in _patch_story_terrain so a client cannot walk
        the still-hidden road by submitting coordinates directly (plan 17.5).
        """
        return (
            player.map_id == MAP_OVERWORLD
            and not player.bridge_repaired
            and (x, y) in OVERWORLD_BRIDGE_SET
        )

    def _player_destination_allowed(self, player: PlayerState, nx: int, ny: int, world: World) -> bool:
        if self._bridge_blocks(player, nx, ny):
            return False
        if not world.player_can_enter(nx, ny) or self._blocked_by_entity(player, nx, ny):
            return False
        dx = nx - player.x
        dy = ny - player.y
        if abs(dx) != 1 or abs(dy) != 1:
            return True
        side_x = player.x + dx
        side_y = player.y
        vertical_x = player.x
        vertical_y = player.y + dy
        return (
            world.player_can_enter(side_x, side_y)
            and not self._blocked_by_entity(player, side_x, side_y)
            and not self._bridge_blocks(player, side_x, side_y)
            and world.player_can_enter(vertical_x, vertical_y)
            and not self._blocked_by_entity(player, vertical_x, vertical_y)
            and not self._bridge_blocks(player, vertical_x, vertical_y)
        )

    def _heal_player_from_herb(self, player: PlayerState) -> None:
        heal_amount = max(1, player.max_health // 6)
        player.health = min(player.max_health, player.health + heal_amount)

    def _apply_player_state_pvp_toggle(self, player: PlayerState, state: PlayerStatePacket) -> None:
        if state.pvp_toggle_counter == player.last_pvp_toggle_counter:
            return
        player.last_pvp_toggle_counter = state.pvp_toggle_counter
        if player.map_id == MAP_PVP_REALM:
            player.pvp_enabled = True
            return
        player.pvp_enabled = not player.pvp_enabled
        self._mark_player_state_dirty(player)

    def _apply_player_state_fire(self, player: PlayerState, state: PlayerStatePacket) -> None:
        fire_pressed = (state.buttons & PLAYER_FIRE_BUTTON) != 0
        fire_was_pressed = (player.last_buttons & PLAYER_FIRE_BUTTON) != 0
        fire_counter_changed = state.fire_counter != player.last_fire_counter
        player.last_fire_counter = state.fire_counter
        if not fire_counter_changed and not (fire_pressed and not fire_was_pressed):
            return
        dx, dy = client_aim_delta(state.facing)
        if dx == 0 and dy == 0:
            return
        player.facing = state.facing
        self._hunter_attack(player, dx, dy)

    def _apply_player_state_pickup(self, player: PlayerState, state: PlayerStatePacket) -> None:
        if state.pickup_counter == player.last_pickup_counter:
            return
        player.last_pickup_counter = state.pickup_counter
        # While a dialogue is open the interact bump acks the current page
        # instead of picking up / re-interacting. The decline bit only matters
        # on a final quest-offer page; it is harmless elsewhere.
        if player.active_dialogue is not None:
            accept = (state.buttons & PLAYER_DIALOGUE_DECLINE_BUTTON) == 0
            self.advance_dialogue(player, accept=accept)
            return
        player.pickup_events += 1
        if not self.pickup_nearby_item(player):
            if not self.interact_with_adjacent_npc(player.token):
                self._try_interact_deep_pump_controls(player)

    def _apply_fire(self, player: PlayerState, intent: InputIntent) -> bool:
        fire_down = (intent.buttons & PLAYER_FIRE_BUTTON) != 0
        if not fire_down:
            return False
        player.facing = intent.aim
        dx, dy = aim_delta(intent.aim)
        if dx == 0 and dy == 0:
            return True
        self._hunter_attack(player, dx, dy)
        return True

    # ------------------------------------------------------------------
    # Combat

    @staticmethod
    def _shot_terrain_blocks(world: World, x: int, y: int) -> bool:
        if not world.in_bounds(x, y):
            return True
        return not world.player_can_enter(x, y) or world.tile(x, y) in LINE_OF_SIGHT_BLOCKING

    def _diagonal_shot_corner_blocks(
        self, world: World, x: int, y: int, dx: int, dy: int
    ) -> bool:
        if dx == 0 or dy == 0:
            return False
        return self._shot_terrain_blocks(world, x + dx, y) or self._shot_terrain_blocks(
            world, x, y + dy
        )

    def _hunter_attack(self, player: PlayerState, dx: int, dy: int) -> None:
        player.shot_counter = (player.shot_counter + 1) & 0xFF
        world = self.world_for(player.map_id)
        if self._diagonal_shot_corner_blocks(world, player.x, player.y, dx, dy):
            return
        target = self.hostile_entity_at(
            player.map_id, player.x + dx, player.y + dy, player
        )
        if target is not None:
            self._damage_entity(target, melee_damage_for_level(player.level, player.class_id), "melee", player)
            return
        other = self.player_at(player.map_id, player.x + dx, player.y + dy, exclude_token=player.token)
        if other is not None:
            if player.pvp_enabled and other.pvp_enabled:
                self._damage_player(other, melee_damage_for_level(player.level, player.class_id), player)
            return
        self._damage_beaver_in_line(player, dx, dy)

    def _damage_beaver_in_line(self, player: PlayerState, dx: int, dy: int) -> None:
        world = self.world_for(player.map_id)
        x = player.x
        y = player.y
        for _ in range(hunter_range_for_level(player.level, player.class_id)):
            if self._diagonal_shot_corner_blocks(world, x, y, dx, dy):
                return
            x += dx
            y += dy
            target = self.hostile_entity_at(player.map_id, x, y, player)
            if target is not None:
                self._damage_entity(target, ranged_damage_for_level(player.level, player.class_id), "ranged", player)
                return
            other = self.player_at(player.map_id, x, y, exclude_token=player.token)
            if other is not None:
                if player.pvp_enabled and other.pvp_enabled:
                    self._damage_player(other, ranged_damage_for_level(player.level, player.class_id), player)
                return
            if self._shot_terrain_blocks(world, x, y):
                return

    def _damage_player(self, target: PlayerState, damage: int, attacker: PlayerState) -> None:
        if self._transition_protected(target) or self._transition_protected(attacker):
            return
        if target.health <= 0 or damage <= 0:
            return
        target.health = max(0, target.health - damage)
        attacker_name = self.player_display_name(attacker.token)
        target_name = self.player_display_name(target.token)
        if target.health <= 0:
            attacker.pvp_kills = min(9999, attacker.pvp_kills + 1)
            self._mark_player_state_dirty(attacker)
            self.queue_activity_message(target, f"{attacker_name} defeated you.", MSG_PVP_KILL)
            self.queue_activity_message(attacker, f"You defeated {target_name}.", MSG_PVP_KILL)
            self.handle_player_death(target)
            return
        self.queue_activity_message(target, f"{attacker_name} hit you.", MSG_PVP_HIT)
        self.queue_activity_message(attacker, f"You hit {target_name}.", MSG_PVP_HIT)

    def _enemy_kill_xp(
        self, enemy_type: EnemyType, entity: Entity, attacker: PlayerState
    ) -> int:
        if entity.subtype == ENEMY_BEAVER and entity.owner_id != 0:
            encounter = self._encounter_for_entity(entity.entity_id)
            if encounter is not None and encounter.encounter_id == "bridge_repair":
                # Wilhelm's bridge-defense wave: scripted, unavoidable
                # content tied to the main quest (not optional ambient
                # grinding), so it shouldn't feed the level curve the way a
                # farmed beaver would. Scoped to this specific encounter id
                # (not just "any owned beaver") so other owned-entity uses
                # of the ScriptedEncounter framework are unaffected.
                return 0
        base = enemy_type.xp_for_level(entity.level)
        if enemy_type.is_boss:
            return base
        numerator, denominator = xp_multiplier_for_level_gap(attacker.level - entity.level)
        return max(1, base * numerator // denominator)

    def _damage_entity(
        self,
        entity: Entity,
        damage: int,
        damage_type: str,
        attacker: PlayerState | None = None,
    ) -> None:
        if entity.hp <= 0 or damage <= 0:
            return
        if attacker is None:
            attacker = self.player
        if not self.entity_visible_to_player(entity, attacker):
            return
        entity.hp = max(0, entity.hp - damage)
        entity.aggro_ticks = BEAVER_ALERT_TICKS
        entity.hit_pulse_ticks = 1
        enemy_type = ENEMY_TYPES.get(entity.subtype) if entity.kind == ENTITY_ENEMY else None
        if entity.hp == 0:
            entity.state = 0
            entity.decay_ticks = BEAVER_DECAY_TICKS
            self._record_encounter_entity_death(entity, attacker)
            if enemy_type is not None:
                if (entity.home_x or entity.home_y) and not enemy_type.is_boss:
                    entity.respawn_ticks = ENEMY_RESPAWN_TICKS
                attacker.score = min(9999, attacker.score + enemy_type.kill_score)
                self._drop_loot(
                    entity,
                    enemy_type.drop_mode,
                    enemy_type.gold_for_level(entity.level),
                )
                if entity.subtype == ENEMY_BEAVER:
                    self._guarantee_road_trouble_sticks(attacker, entity)
                    if not self._advance_road_trouble_progress(attacker):
                        self.queue_activity_message(attacker, "You killed a beaver.", MSG_BEAVER_KILLED)
                elif entity.subtype == ENEMY_SNAKE:
                    if not self._advance_blackwater_progress(attacker):
                        self.queue_activity_message(attacker, "You killed a snake.", MSG_NONE)
                elif entity.subtype == ENEMY_SLIME:
                    if not self._grant_living_mud_sample(attacker):
                        self.queue_activity_message(attacker, "You killed a slime.", MSG_NONE)
                elif entity.subtype == ENEMY_GORVAK:
                    self.queue_activity_message(attacker, "You defeated Pumpmaster Gorvak!", MSG_NONE)
                    self._resolve_gorvak_defeat(entity)
                else:
                    message_id = MSG_GOBLIN_KILLED if entity.subtype == ENEMY_GOBLIN else MSG_NONE
                    self.queue_activity_message(
                        attacker, f"You killed a {enemy_type.name}.", message_id
                    )
                # award_xp (and the level-up message it may queue via
                # check_level_up) must run last: queue_activity_message
                # only keeps the most recent message, so anything queued
                # here would otherwise silently overwrite -- or be
                # overwritten by -- the kill/quest message above.
                self.award_xp(self._enemy_kill_xp(enemy_type, entity, attacker), attacker)
            return
        entity.state = 2 if damage_type == "melee" else 1
        if enemy_type is not None:
            target_name = (
                enemy_type.name
                if enemy_type.is_boss
                else f"the {enemy_type.name}"
            )
            if damage_type == "melee":
                self.queue_activity_message(attacker, f"You hit {target_name}.")
            else:
                self.queue_activity_message(attacker, f"You shoot {target_name}.")

    def _drop_loot(self, entity: Entity, drop_mode: str = "beaver", gold_quantity: int = BEAVER_KILL_GOLD) -> None:
        if drop_mode == "gold":
            drops = [ITEM_GOLD]
        elif drop_mode == "beaver":
            roll = self.rng.next_byte() % 3
            drops = []
            if roll in (0, 2):
                drops.append(ITEM_GOLD)
            if roll in (1, 2):
                drops.append(ITEM_STICKS)
        else:
            drops = []
        positions = self._loot_drop_positions(entity.map_id, entity.x, entity.y, len(drops))
        for item_id, (x, y) in zip(drops, positions):
            quantity = gold_quantity if item_id == ITEM_GOLD else 1
            self.spawn_item(x, y, item_id, quantity, map_id=entity.map_id)

    def _guarantee_road_trouble_sticks(
        self, player: PlayerState, enemy: Entity
    ) -> None:
        if (
            player.active_quest_id != QUEST_ROAD_TROUBLE
            or player.quest_state != QUEST_STATE_ACTIVE
            or player.quest_progress + 1 < player.quest_target
            or player.inventory.count_item(ITEM_STICKS) > 0
        ):
            return
        if player.inventory.add_item(ITEM_STICKS, 1):
            self._mark_player_state_dirty(player)
            return
        item = self.spawn_personal_item(
            player,
            x=enemy.x,
            y=enemy.y,
            item_id=ITEM_STICKS,
            map_id=enemy.map_id,
        )
        item.decay_ticks = ITEM_DESPAWN_TICKS

    def _loot_drop_positions(self, map_id: int, x: int, y: int, count: int) -> list[tuple[int, int]]:
        if count <= 0:
            return []
        positions = [(x, y)]
        if count > 1:
            world = self.world_for(map_id)
            for dx, dy in LOOT_DROP_NEIGHBOR_OFFSETS:
                if len(positions) >= count:
                    break
                nx, ny = x + dx, y + dy
                if not world.player_can_enter(nx, ny):
                    continue
                if self.entity_at(map_id, nx, ny, blocking_only=False) is not None:
                    continue
                positions.append((nx, ny))
            # No empty neighbor available (e.g. a tight cave corridor): stack
            # the remaining drops on the death tile rather than lose them.
            while len(positions) < count:
                positions.append((x, y))
        return positions

    # ------------------------------------------------------------------
    # Messages, quests, progression (all per player)

    def queue_activity_message(
        self,
        player: PlayerState,
        message: str,
        message_id: int = MSG_NONE,
    ) -> None:
        if len(player.pending_messages) >= MAX_PENDING_MESSAGES:
            player.pending_messages.pop(0)
        player.pending_messages.append((message_id, message))
        player.latest_activity_message = message
        player.latest_message_id = message_id
        player.message_counter = (player.message_counter + 1) & 0xFFFF
        player.activity_messages.append(message)
        if len(player.activity_messages) > 8:
            player.activity_messages.pop(0)

    def queue_server_message(
        self,
        message: str,
        message_id: int,
        exclude_token: int | None = None,
    ) -> None:
        for token, player in tuple(self.players.items()):
            if token == exclude_token:
                continue
            self.queue_activity_message(player, message, message_id)

    def next_message_packet(self, seq: int, token: int | None = None) -> MessagePacket | None:
        player = self.player_for(token)
        if not player.pending_messages:
            return None
        message_id, message = player.pending_messages.pop(0)
        return MessagePacket(seq, message_id, message)

    def interact_with_adjacent_npc(self, token: int | None = None) -> bool:
        player = self.player_for(token)
        npc = self._nearest_adjacent_npc(player)
        if npc is None:
            return False
        return story.interact(self, player, npc)

    def _nearest_adjacent_npc(self, player: PlayerState) -> Entity | None:
        # Scan every live NPC on the player's map (plan 17.2). Nearest wins;
        # ties break on entity id so overlapping NPCs resolve deterministically.
        best: Entity | None = None
        best_key: tuple[int, int] | None = None
        for npc in self.entities.values():
            if (
                npc.kind != ENTITY_NPC
                or npc.map_id != player.map_id
                or not npc.is_live
                or not self.entity_visible_to_player(npc, player)
            ):
                continue
            distance = abs(npc.x - player.x) + abs(npc.y - player.y)
            if distance > 1:
                continue
            key = (distance, npc.entity_id)
            if best_key is None or key < best_key:
                best_key = key
                best = npc
        return best

    # ------------------------------------------------------------------
    # Paged story dialogue (Phase 57)

    def open_dialogue(
        self,
        player: PlayerState,
        dialogue_id: int,
        speaker_id: int,
        pages,
        quest_offer_id: int = 0,
    ) -> bool:
        """Open a paged dialogue modal for a player.

        Each supplied string is a logical paragraph; it is auto-paginated into
        chunks that fit one DIALOGUE_PAGE packet so authored prose never gets
        truncated by the 48-char page limit. No-op if a dialogue is already open
        (re-interacting must not restart or duplicate a scene). Pages advance
        only on the client's ack.
        """
        pages = paginate_dialogue_text(pages)
        if not pages:
            return False
        if player.active_dialogue is not None:
            return True
        player.active_dialogue = ActiveDialogue(
            dialogue_id=dialogue_id,
            speaker_id=speaker_id,
            pages=pages,
            quest_offer_id=quest_offer_id,
            resend_timer=DIALOGUE_RESEND_INTERVAL_TICKS,
            resends_left=DIALOGUE_MAX_RESENDS,
        )
        return True

    def advance_dialogue(self, player: PlayerState, accept: bool = True) -> bool:
        """Acknowledge the current page: show the next one, or close the scene."""
        dialogue = player.active_dialogue
        if dialogue is None:
            return False
        if dialogue.index < len(dialogue.pages) - 1:
            dialogue.index += 1
            dialogue.chunk = 0
            dialogue.resend_timer = DIALOGUE_RESEND_INTERVAL_TICKS
            dialogue.resends_left = DIALOGUE_MAX_RESENDS
            return True
        self._close_dialogue(player, accept)
        return True

    def _close_dialogue(self, player: PlayerState, accept: bool) -> None:
        dialogue = player.active_dialogue
        player.active_dialogue = None
        if dialogue is None:
            return
        if dialogue.quest_offer_id and accept and player.pending_quest_offer_id == dialogue.quest_offer_id:
            self.accept_pending_quest_offer(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_NERISSA_INTRO:
            player.story_stage = max(player.story_stage, STORY_STAGE_WELCOME)
            player.story_step = 0
            self._mark_player_state_dirty(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_NERISSA_POST_BRIDGE:
            player.story_stage = max(player.story_stage, STORY_STAGE_BEYOND_ROAD)
            player.story_step = 0
            self.queue_activity_message(player, "Follow the road and find Lucian.", MSG_QUEST_STARTED)
            self._mark_player_state_dirty(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_WILHELM_BRIDGE_START:
            self._commit_wilhelm_bridge_start(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_DANIEL_COMPLETE:
            self._complete_save_my_orchard(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_WILHELM_COMPLETE:
            self._complete_repair_the_bridge(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_LUCIAN_BLACKWATER_OFFER:
            self._start_blackwater_bite(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_LUCIAN_LIVING_MUD_OFFER:
            self._complete_blackwater_and_start_living_mud(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_LUCIAN_SAMPLES_REDIRECT:
            player.story_step = 1
            self.queue_activity_message(player, "Take the samples to Nerissa.", MSG_QUEST_REMINDER)
            self._mark_player_state_dirty(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_NERISSA_SAMPLES:
            self._complete_living_mud(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_GRIX_EXPLAIN:
            player.story_stage = max(player.story_stage, STORY_STAGE_WARDEN_KEY)
            player.story_step = 0
            self._ensure_warden_key_spawned(player)
            self.queue_activity_message(player, "Find the Warden Key in the forest.", MSG_QUEST_STARTED)
            self._mark_player_state_dirty(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_GRIX_COMPLETE:
            player.story_stage = max(player.story_stage, STORY_STAGE_GORVAK)
            player.story_step = 0
            self.queue_activity_message(player, "Find Gorvak in the Old Floodworks cave", MSG_QUEST_STARTED)
            self._mark_player_state_dirty(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_PUMP_SHUTDOWN:
            self._complete_deep_pump_shutdown(player)
            return
        if accept and dialogue.dialogue_id == story.DLG_NERISSA_ENDING:
            self._complete_willowcross_saved(player)

    def _build_dialogue_packet(
        self, seq: int, dialogue: ActiveDialogue, chunks: list[str], chunk_index: int
    ) -> DialoguePagePacket:
        page_count = len(dialogue.pages)
        is_last_page = dialogue.index >= page_count - 1
        is_last_chunk = chunk_index >= len(chunks) - 1
        flags = 0
        if is_last_chunk:
            flags |= DIALOGUE_FLAG_CHUNK_END
            if is_last_page:
                flags |= DIALOGUE_FLAG_LAST_PAGE
                flags |= DIALOGUE_FLAG_QUEST_OFFER if dialogue.quest_offer_id else DIALOGUE_FLAG_ACK_ONLY
        return DialoguePagePacket(
            seq,
            dialogue.dialogue_id,
            dialogue.speaker_id,
            dialogue.index,
            page_count,
            flags,
            chunks[chunk_index],
            chunk_index,
        )

    def dialogue_page_to_send(self, seq: int, token: int | None = None) -> DialoguePagePacket | None:
        """Return the next dialogue chunk to transmit this tick, or None.

        Streams the current display page one chunk per tick; once every chunk is
        sent, it waits for the client ack (a pickup bump) and, on a bounded
        schedule, retransmits the whole page from chunk 0 so a CRC-dropped chunk
        still arrives (plan 17.13 / 15.1) without continuous traffic.
        """
        player = self.player_for(token)
        dialogue = player.active_dialogue
        if dialogue is None:
            return None
        chunks = dialogue_page_chunks(dialogue.pages[dialogue.index])
        if dialogue.chunk >= len(chunks):
            # Whole page sent; wait for the ack, then retransmit from chunk 0 on
            # a bounded schedule so a CRC-dropped chunk still reaches the client.
            if dialogue.resends_left <= 0:
                return None
            dialogue.resend_timer -= 1
            if dialogue.resend_timer > 0:
                return None
            dialogue.resend_timer = DIALOGUE_RESEND_INTERVAL_TICKS
            dialogue.resends_left -= 1
            dialogue.chunk = 0
        packet = self._build_dialogue_packet(seq, dialogue, chunks, dialogue.chunk)
        dialogue.chunk += 1
        return packet

    def _can_offer_quest(self, player: PlayerState) -> bool:
        # A player may only chase one quest at a time, but once it's
        # complete (whichever quest it was), a different NPC can offer
        # the next one -- quest state is scalar, not a completed-quests
        # set, so "complete" is the only signal that the slot is free.
        return player.active_quest_id == QUEST_NONE or player.quest_state == QUEST_STATE_COMPLETE

    def _interact_farmer(self, player: PlayerState) -> bool:
        if player.pending_quest_offer_id == QUEST_ROAD_TROUBLE:
            return self.accept_pending_quest_offer(player)
        if player.active_quest_id == QUEST_ROAD_TROUBLE:
            if player.quest_state == QUEST_STATE_ACTIVE:
                self.queue_activity_message(
                    player,
                    f"Clear {player.quest_target} beavers from the dam.",
                    MSG_QUEST_REMINDER,
                )
                return True
            if player.quest_state == QUEST_STATE_READY_TO_TURN_IN:
                player.story_stage = max(player.story_stage, STORY_STAGE_ROAD_TROUBLE)
                player.story_step = 0
                if player.inventory.count_item(ITEM_STICKS) > 0:
                    self.queue_activity_message(player, "Take those sticks to Wilhelm in town.", MSG_QUEST_READY)
                else:
                    self.queue_activity_message(player, "You still need a bundle of sticks for Wilhelm.", MSG_QUEST_REMINDER)
                self._mark_player_state_dirty(player)
                return True
            self.queue_activity_message(player, "Farmer Dan waves from his orchard", MSG_FARMER_THANKS)
            return True
        if self._can_offer_quest(player):
            player.pending_quest_offer_id = QUEST_ROAD_TROUBLE
            self.queue_activity_message(player, "Beavers keep flooding my road. Help?", MSG_QUEST_OFFER)
            self._mark_player_state_dirty(player)
            return True
        self.queue_activity_message(player, "Farmer Dan nods at you.", MSG_FARMER_THANKS)
        return True

    def _interact_daniel(self, player: PlayerState) -> bool:
        if player.active_quest_id == QUEST_ROAD_TROUBLE:
            if player.quest_state == QUEST_STATE_ACTIVE:
                self.queue_activity_message(
                    player,
                    f"Beavers cleared: {player.quest_progress}/{player.quest_target}.",
                    MSG_QUEST_REMINDER,
                )
                return True
            if player.quest_state == QUEST_STATE_READY_TO_TURN_IN:
                return self.open_dialogue(
                    player,
                    story.DLG_DANIEL_COMPLETE,
                    NPC_DANIEL,
                    (
                        "You saved my orchard. Thank you!",
                        "Take those sticks to Wilhelm the Carpenter in "
                        "town. He needs them to repair the washed-out "
                        "bridge.",
                    ),
                )
            self.queue_activity_message(player, "Farmer Daniel waves from his porch.", MSG_FARMER_THANKS)
            return True
        if player.pending_quest_offer_id == QUEST_ROAD_TROUBLE:
            return self.open_dialogue(
                player,
                story.DLG_DANIEL_OFFER,
                NPC_DANIEL,
                (
                    "Beavers are chopping down my orchard and using "
                    "the logs to dam the streams.",
                    "Please take care of them before I lose the whole "
                    "orchard.",
                ),
                quest_offer_id=QUEST_ROAD_TROUBLE,
            )
        if self._can_offer_quest(player):
            player.pending_quest_offer_id = QUEST_ROAD_TROUBLE
            self._mark_player_state_dirty(player)
            return self._interact_daniel(player)
        self.queue_activity_message(player, "Farmer Daniel nods at you.", MSG_FARMER_THANKS)
        return True

    def _complete_save_my_orchard(self, player: PlayerState) -> None:
        player.quest_state = QUEST_STATE_COMPLETE
        player.story_stage = max(player.story_stage, STORY_STAGE_ROAD_TROUBLE)
        player.story_step = 0
        self.award_gold(ROAD_TROUBLE_REWARD_GOLD, player)
        self.award_xp(ROAD_TROUBLE_REWARD_XP, player)
        self._mark_player_state_dirty(player)

    def _complete_repair_the_bridge(self, player: PlayerState) -> None:
        player.quest_state = QUEST_STATE_COMPLETE
        self.award_gold(REPAIR_BRIDGE_REWARD_GOLD, player)
        self.award_xp(REPAIR_BRIDGE_REWARD_XP, player)
        self._mark_player_state_dirty(player)

    def _interact_goblin(self, player: PlayerState) -> bool:
        if player.pending_quest_offer_id == QUEST_LOST_CHARM:
            return self.accept_pending_quest_offer(player)
        if player.active_quest_id == QUEST_LOST_CHARM:
            if player.quest_state == QUEST_STATE_ACTIVE:
                self.queue_activity_message(player, "Find my charm in the cave east.", MSG_QUEST_REMINDER)
                return True
            if player.quest_state == QUEST_STATE_READY_TO_TURN_IN:
                player.quest_state = QUEST_STATE_COMPLETE
                self.award_gold(LOST_CHARM_REWARD_GOLD, player)
                self.queue_activity_message(player, "Grix hugs you and gives 25 gold.", MSG_QUEST_COMPLETE)
                return True
            self.queue_activity_message(player, "Grix waves happily.", MSG_GOBLIN_THANKS)
            return True
        if self._can_offer_quest(player):
            player.pending_quest_offer_id = QUEST_LOST_CHARM
            self.queue_activity_message(player, "Grix lost his charm in the cave. Help?", MSG_QUEST_OFFER)
            self._mark_player_state_dirty(player)
            return True
        self.queue_activity_message(player, "Grix waits quietly.", MSG_GOBLIN_THANKS)
        return True

    def _interact_grix(self, player: PlayerState) -> bool:
        if player.story_stage == STORY_STAGE_GOBLIN_WARNED:
            return self.open_dialogue(
                player,
                story.DLG_GRIX_EXPLAIN,
                NPC_GRIX,
                (
                    "Please, do not hurt me! I am Grix, and I am not your enemy.",
                    "Pumpmaster Gorvak restarted the Deep Pump to drain the "
                    "lower tunnels. The water has nowhere to go but up, into "
                    "Willowcross.",
                    "I stole the Warden Key so he could not lock everyone "
                    "else out of the controls. I hoped to shut the pump "
                    "down myself.",
                    "His raiders chased me through the forest and I dropped "
                    "it before I could escape. I am hurt, and I cannot go "
                    "back for it.",
                    "Find it for me, and we can put an end to this together.",
                ),
            )
        if player.story_stage == STORY_STAGE_WARDEN_KEY:
            if player.warden_key_collected:
                return self.open_dialogue(
                    player,
                    story.DLG_GRIX_COMPLETE,
                    NPC_GRIX,
                    (
                        "You found it! Gorvak's raiders never expected "
                        "anyone to make it back out of that forest.",
                        "He guards the route to the Deep Pump now. Get past "
                        "him, then use the key on the emergency controls.",
                    ),
                )
            self.queue_activity_message(player, "Find the Warden Key in the forest.", MSG_QUEST_REMINDER)
            return True
        if player.story_stage >= STORY_STAGE_GORVAK:
            self.queue_activity_message(player, "Grix watches the tree line nervously.", MSG_NONE)
            return True
        self.queue_activity_message(player, "A goblin watches you from a distance.", MSG_NONE)
        return True

    def _ensure_warden_key_spawned(self, player: PlayerState) -> None:
        if player.warden_key_collected or player.story_stage != STORY_STAGE_WARDEN_KEY:
            return
        for entity in self.entities.values():
            if (
                entity.kind == ENTITY_ITEM
                and entity.subtype == ITEM_WARDEN_KEY
                and entity.owner_id == player.token
                and entity.is_live
            ):
                return
        map_id, x, y = WARDEN_KEY_MARKER
        self.spawn_warden_key(player, x, y, map_id)

    def _update_grix_story_state(self) -> None:
        grix = self.entities.get(self.named_npc_ids.get(NPC_GRIX, 0))
        for player in self.players.values():
            if (
                grix is not None
                and not player.grix_callout_seen
                and player.story_stage == STORY_STAGE_GOBLIN_WARNED
                and player.map_id == grix.map_id
                and abs(player.x - grix.x) + abs(player.y - grix.y) <= GRIX_PROXIMITY_RANGE
            ):
                player.grix_callout_seen = True
                self.queue_activity_message(player, "Please don't hurt me! I need your help!", MSG_NONE)
                self._mark_player_state_dirty(player)
            self._ensure_warden_key_spawned(player)

    # ------------------------------------------------------------------
    # Pumpmaster Gorvak boss encounter

    def _gorvak_activation_region(self) -> EncounterRegion | None:
        if GORVAK_ROOM_REGION is None:
            return None
        map_id, left, top, right, bottom = GORVAK_ROOM_REGION
        if map_id != MAP_STARTER_CAVE:
            raise ValueError("Gorvak room region must be on the starter cave map")
        return EncounterRegion(left, top, right, bottom)

    def _update_gorvak_encounter_state(self) -> None:
        if GORVAK_MARKER is None:
            return
        map_id, gx, gy = GORVAK_MARKER
        region = self._gorvak_activation_region()
        for player in self.players.values():
            if (
                player.story_stage != STORY_STAGE_GORVAK
                or player.gorvak_defeated
                or player.map_id != map_id
                or player.health <= 0
            ):
                continue
            if self.get_scripted_encounter(player.token, "gorvak") is not None:
                continue
            in_region = (
                region.contains(player.x, player.y)
                if region is not None
                else abs(player.x - gx) + abs(player.y - gy) <= GORVAK_ACTIVATION_RADIUS
            )
            if in_region:
                self._spawn_gorvak_encounter(player)

    def _spawn_gorvak_encounter(self, player: PlayerState) -> None:
        map_id, gx, gy = GORVAK_MARKER
        encounter = self.create_scripted_encounter(
            player,
            "gorvak",
            map_id=map_id,
            region=self._gorvak_activation_region(),
            on_success=self._gorvak_encounter_success,
            on_failure=self._gorvak_encounter_failure,
        )
        boss = self.spawn_enemy(
            ENEMY_GORVAK, gx, gy, map_id=map_id, home_x=gx, home_y=gy,
            owner_id=player.token, level=GORVAK_LEVEL,
        )
        encounter.boss_entity_id = boss.entity_id
        encounter.spawned_entity_ids.add(boss.entity_id)
        encounter.next_summon_kind = ENEMY_BAT
        encounter.summon_cooldown_ticks = GORVAK_INITIAL_SUMMON_DELAY_TICKS
        self.activate_scripted_encounter(encounter)
        self.queue_activity_message(player, "Pumpmaster Gorvak blocks the way!", MSG_NONE)

    def _gorvak_encounter_success(
        self, _game: "GameState", player: PlayerState, _encounter: ScriptedEncounter
    ) -> None:
        player.gorvak_defeated = True
        player.story_step = 3
        self.queue_activity_message(player, "Gorvak falls! Find the Deep Pump.", MSG_QUEST_READY)
        self._mark_player_state_dirty(player)

    def _gorvak_encounter_failure(
        self, _game: "GameState", player: PlayerState, _encounter: ScriptedEncounter
    ) -> None:
        self.queue_activity_message(player, "Gorvak resets. Try again.", MSG_QUEST_REMINDER)

    def _gorvak_summon_delay(self) -> int:
        span = GORVAK_SUMMON_DELAY_MAX_TICKS - GORVAK_SUMMON_DELAY_MIN_TICKS + 1
        return GORVAK_SUMMON_DELAY_MIN_TICKS + self.rng.next_byte() % span

    def _gorvak_summon_point(
        self, encounter: ScriptedEncounter, boss: Entity
    ) -> tuple[int, int] | None:
        world = self.world_for(encounter.map_id)
        candidates = [
            (x, y)
            for x, y in GORVAK_SUMMON_POINTS
            if world.enemy_can_enter(x, y) and self.entity_at(encounter.map_id, x, y) is None
        ]
        if not candidates:
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    distance = abs(dx) + abs(dy)
                    if not (1 <= distance <= 3):
                        continue
                    x, y = boss.x + dx, boss.y + dy
                    if world.enemy_can_enter(x, y) and self.entity_at(encounter.map_id, x, y) is None:
                        candidates.append((x, y))
        if not candidates:
            return None
        return candidates[self.rng.next_byte() % len(candidates)]

    def _spawn_gorvak_summon(self, encounter: ScriptedEncounter, boss: Entity) -> None:
        point = self._gorvak_summon_point(encounter, boss)
        if point is None:
            return
        kind = encounter.next_summon_kind or ENEMY_BAT
        summon = self.spawn_enemy(
            kind, point[0], point[1], map_id=encounter.map_id,
            owner_id=encounter.owner_id, level=GORVAK_SUMMON_LEVEL,
        )
        encounter.summon_entity_id = summon.entity_id
        encounter.spawned_entity_ids.add(summon.entity_id)
        encounter.next_summon_kind = ENEMY_GOBLIN if kind == ENEMY_BAT else ENEMY_BAT

    def _advance_gorvak_boss_ai(self, encounter: ScriptedEncounter, boss: Entity) -> None:
        if boss.attack_cooldown > 0:
            boss.attack_cooldown -= 1
        owner = self.players.get(encounter.owner_id)
        if owner is None or owner.map_id != boss.map_id or owner.health <= 0:
            return
        distance = abs(boss.x - owner.x) + abs(boss.y - owner.y)
        enemy_type = ENEMY_TYPES[ENEMY_GORVAK]
        if distance <= GORVAK_ATTACK_RANGE:
            if boss.attack_cooldown <= 0 and not self._transition_protected(owner):
                owner.health = max(0, owner.health - enemy_type.damage_for_level(boss.level))
                boss.attack_cooldown = enemy_type.attack_cooldown
                self.queue_activity_message(owner, "Gorvak strikes you!", MSG_NONE)
                if owner.health <= 0:
                    self.handle_player_death(owner)
            return
        # Chase whenever not already adjacent, not just from exactly one
        # tile past attack range -- previously he only ever took a step
        # when the player happened to be at distance 2, so standing still
        # anywhere farther out (e.g. a hunter's max ranged distance) left
        # him permanently stationary and harmless.
        if boss.move_cooldown > 0:
            boss.move_cooldown -= 1
            return
        boss.move_cooldown = enemy_type.move_cooldown
        step_x = (owner.x > boss.x) - (owner.x < boss.x)
        step_y = 0 if step_x else (owner.y > boss.y) - (owner.y < boss.y)
        nx, ny = boss.x + step_x, boss.y + step_y
        if abs(nx - boss.home_x) + abs(ny - boss.home_y) > GORVAK_LEASH_RANGE:
            return
        world = self.world_for(boss.map_id)
        if world.enemy_can_enter(nx, ny) and self.entity_at(boss.map_id, nx, ny) is None:
            boss.x, boss.y = nx, ny
            boss.zone_id = zone_for_tile(boss.map_id, boss.x, boss.y)

    def _advance_gorvak_encounter(self, encounter: ScriptedEncounter) -> None:
        boss = self.entities.get(encounter.boss_entity_id)
        if boss is None or not boss.is_live:
            return
        self._advance_gorvak_boss_ai(encounter, boss)
        summon = self.entities.get(encounter.summon_entity_id) if encounter.summon_entity_id else None
        if summon is not None and not summon.is_live:
            encounter.summon_entity_id = 0
            summon = None
            encounter.summon_cooldown_ticks = self._gorvak_summon_delay()
        if summon is None:
            if encounter.summon_cooldown_ticks > 0:
                encounter.summon_cooldown_ticks -= 1
            else:
                self._spawn_gorvak_summon(encounter, boss)

    def _resolve_gorvak_defeat(self, boss: Entity) -> None:
        encounter = self._encounter_for_entity(boss.entity_id)
        if encounter is None:
            return
        if encounter.summon_entity_id:
            self.remove_entity(encounter.summon_entity_id)
            encounter.spawned_entity_ids.discard(encounter.summon_entity_id)
            encounter.summon_entity_id = 0
        self.succeed_scripted_encounter(encounter)

    # ------------------------------------------------------------------
    # Deep Pump controls

    def _try_interact_deep_pump_controls(self, player: PlayerState) -> bool:
        if DEEP_PUMP_CONTROLS_MARKER is None:
            return False
        map_id, x, y = DEEP_PUMP_CONTROLS_MARKER
        if player.map_id != map_id or abs(player.x - x) + abs(player.y - y) > 1:
            return False
        return self._interact_deep_pump_controls(player)

    def _interact_deep_pump_controls(self, player: PlayerState) -> bool:
        if player.deep_pump_shutdown:
            self.queue_activity_message(player, "The pump lies silent.", MSG_NONE)
            return True
        if not player.gorvak_defeated:
            self.queue_activity_message(player, "The controls are locked.", MSG_NONE)
            return True
        if not player.warden_key_collected:
            self.queue_activity_message(player, "You need the Warden Key.", MSG_NONE)
            return True
        return self.open_dialogue(
            player,
            story.DLG_PUMP_SHUTDOWN,
            0,
            (
                "You turn the Warden Key in the emergency lock. Down "
                "below, the Deep Pump groans and begins to slow.",
                "Gears grind to a stop. The rushing water fades to a "
                "trickle, then silence. THE DEEP PUMP FALLS SILENT.",
                "Return to Nerissa in Willowcross and tell her the "
                "water is receding.",
            ),
        )

    def _complete_deep_pump_shutdown(self, player: PlayerState) -> None:
        player.deep_pump_shutdown = True
        player.story_stage = max(player.story_stage, STORY_STAGE_RETURN_NERISSA)
        player.story_step = 0
        self.queue_activity_message(
            player, "The Deep Pump falls silent. Return to Nerissa.", MSG_QUEST_READY
        )
        self._mark_player_state_dirty(player)

    def _bridge_repair_success(self, _game: "GameState", player: PlayerState, encounter: ScriptedEncounter) -> None:
        escort = self.entities.get(encounter.escort_entity_id)
        if escort is not None:
            escort.flags &= ~ENTITY_FLAG_WORKING
        self.complete_bridge_repair(player)
        player.story_stage = max(player.story_stage, STORY_STAGE_BRIDGE)
        player.story_step = 1
        if player.active_quest_id == QUEST_REPAIR_BRIDGE:
            player.quest_state = QUEST_STATE_READY_TO_TURN_IN
            player.quest_progress = player.quest_target
        self.queue_activity_message(player, "Bridge repaired! Road is open.", MSG_QUEST_COMPLETE)
        # Beavers stop the instant the repair finishes; Wilhelm's own escort
        # entity survives so he can walk the route back to town.
        self._clear_bridge_wave_beavers(encounter)
        self._start_wilhelm_return_walk(encounter)

    def _bridge_repair_started(
        self, _game: "GameState", player: PlayerState, encounter: ScriptedEncounter
    ) -> None:
        player.story_step = 1
        player.quest_progress = 0
        escort = self.entities.get(encounter.escort_entity_id)
        if escort is not None:
            escort.flags |= ENTITY_FLAG_WORKING
        self._spawn_bridge_wave(encounter, BRIDGE_WAVE_INITIAL_COUNT)
        self.queue_activity_message(player, "Wilhelm works. Watch for beavers!", MSG_QUEST_PROGRESS)
        self._mark_player_state_dirty(player)

    def _bridge_repair_progress(
        self, _game: "GameState", player: PlayerState, encounter: ScriptedEncounter
    ) -> None:
        ticks_elapsed = encounter.initial_countdown_ticks - encounter.countdown_ticks
        if (
            encounter.countdown_ticks > 0
            and ticks_elapsed > 0
            and ticks_elapsed % BRIDGE_WAVE_REPLENISH_INTERVAL_TICKS == 0
        ):
            live = self._live_bridge_wave_beaver_count(encounter)
            if live < BRIDGE_WAVE_MAX_LIVE:
                self._spawn_bridge_wave(encounter, BRIDGE_WAVE_MAX_LIVE - live)
        messages = {
            BRIDGE_REPAIR_DURATION_TICKS * 3 // 4: "Bridge repair: one quarter complete.",
            BRIDGE_REPAIR_DURATION_TICKS // 2: "Bridge repair: halfway complete.",
            BRIDGE_REPAIR_DURATION_TICKS // 4: "Bridge repair: nearly complete.",
        }
        message = messages.get(encounter.countdown_ticks)
        if message is not None:
            player.quest_progress = min(
                player.quest_target,
                (ticks_elapsed * player.quest_target) // BRIDGE_REPAIR_DURATION_TICKS,
            )
            self.queue_activity_message(player, message, MSG_QUEST_PROGRESS)
            self._mark_player_state_dirty(player)

    def _bridge_repair_failure(self, _game: "GameState", player: PlayerState, _encounter: ScriptedEncounter) -> None:
        # The personal moving Wilhelm is removed on failure, so rebuild the
        # terrain cache to restore the shared workshop copy.
        player.pending_terrain_resync = True
        self.queue_activity_message(player, "Wilhelm resets. Try again with sticks.", MSG_QUEST_REMINDER)

    def _bridge_return_complete(
        self, _game: "GameState", player: PlayerState, _encounter: ScriptedEncounter
    ) -> None:
        # The personal moving Wilhelm is removed once he reaches town; the
        # static overlay takes over from the same tile, so refresh the
        # cached window the same way the outbound leg does.
        player.pending_terrain_resync = True
        self.queue_activity_message(player, "Wilhelm is back. Go speak to him.", MSG_QUEST_READY)

    def _spawn_bridge_wave(self, encounter: ScriptedEncounter, count: int) -> None:
        for _ in range(max(0, count)):
            point = self._bridge_wave_spawn_point(encounter)
            if point is None:
                break
            beaver = self.spawn_enemy(
                ENEMY_BEAVER,
                point[0],
                point[1],
                map_id=encounter.map_id,
                owner_id=encounter.owner_id,
                level=1,
            )
            encounter.spawned_entity_ids.add(beaver.entity_id)

    def _live_bridge_wave_beaver_count(self, encounter: ScriptedEncounter) -> int:
        count = 0
        for entity_id in encounter.spawned_entity_ids:
            if entity_id == encounter.escort_entity_id:
                continue
            entity = self.entities.get(entity_id)
            if entity is not None and entity.is_live:
                count += 1
        return count

    def _bridge_wave_spawn_point(self, encounter: ScriptedEncounter) -> tuple[int, int] | None:
        npc = self.entities.get(encounter.escort_entity_id)
        if npc is None:
            return None
        world = self.world_for(encounter.map_id)
        region = encounter.region
        candidates: list[tuple[int, int]] = []
        for dx in range(-BRIDGE_WAVE_SPAWN_MAX_DISTANCE, BRIDGE_WAVE_SPAWN_MAX_DISTANCE + 1):
            for dy in range(-BRIDGE_WAVE_SPAWN_MAX_DISTANCE, BRIDGE_WAVE_SPAWN_MAX_DISTANCE + 1):
                distance = abs(dx) + abs(dy)
                if not (BRIDGE_WAVE_SPAWN_MIN_DISTANCE <= distance <= BRIDGE_WAVE_SPAWN_MAX_DISTANCE):
                    continue
                x, y = npc.x + dx, npc.y + dy
                if region is not None and not region.contains(x, y):
                    continue
                if not world.enemy_can_enter(x, y):
                    continue
                if self.entity_at(encounter.map_id, x, y) is not None:
                    continue
                candidates.append((x, y))
        if not candidates:
            return None
        return candidates[self.rng.next_byte() % len(candidates)]

    def _clear_bridge_wave_beavers(self, encounter: ScriptedEncounter) -> None:
        for entity_id in tuple(encounter.spawned_entity_ids):
            if entity_id == encounter.escort_entity_id:
                continue
            self.remove_entity(entity_id)
            encounter.spawned_entity_ids.discard(entity_id)

    def _start_wilhelm_return_walk(self, encounter: ScriptedEncounter) -> None:
        self.start_scripted_escort(
            encounter,
            self.entities[encounter.escort_entity_id],
            self.bridge_return_waypoints(),
            move_interval_ticks=WILHELM_MOVE_INTERVAL_TICKS,
            escort_follow_distance=0,
        )
        encounter.phase = ENCOUNTER_RETURNING
        encounter.is_return_leg = True
        encounter.pause_when_owner_absent = False
        encounter.fail_after_absent_ticks = 0
        encounter.on_success = None
        encounter.on_return_complete = self._bridge_return_complete

    def _start_bridge_repair_for_player(self, player: PlayerState) -> bool:
        encounter = self.get_scripted_encounter(player.token, "bridge_repair")
        if encounter is not None and encounter.phase not in (ENCOUNTER_FAILED, ENCOUNTER_CLEANUP):
            self.queue_activity_message(player, "Stay close to Wilhelm.", MSG_QUEST_REMINDER)
            return True
        if encounter is not None:
            self.cleanup_scripted_encounter(encounter)
            self.scripted_encounters.pop(encounter.key, None)
        self.create_bridge_repair_encounter(
            player,
            countdown_ticks=BRIDGE_REPAIR_DURATION_TICKS,
            fail_after_absent_ticks=40,
            move_interval_ticks=WILHELM_MOVE_INTERVAL_TICKS,
            escort_follow_distance=WILHELM_FOLLOW_DISTANCE,
            on_active=self._bridge_repair_started,
            on_progress=self._bridge_repair_progress,
            on_success=self._bridge_repair_success,
            on_failure=self._bridge_repair_failure,
        )
        # The cached window still contains the static workshop tile. Refill it
        # now that the shared Wilhelm is hidden by the realtime escort entity,
        # otherwise a stationary ghost remains behind.
        player.pending_terrain_resync = True
        player.story_stage = max(player.story_stage, STORY_STAGE_BRIDGE)
        player.story_step = 0
        self.queue_activity_message(player, "Heading to the bridge. Stay close!", MSG_QUEST_STARTED)
        self._mark_player_state_dirty(player)
        return True

    def _commit_wilhelm_bridge_start(self, player: PlayerState) -> bool:
        if player.bridge_repaired:
            self.queue_activity_message(player, "The bridge holds. The road is open.", MSG_QUEST_COMPLETE)
            return True
        if player.bridge_materials_staged:
            return self._start_bridge_repair_for_player(player)
        stick_count = player.inventory.count_item(ITEM_STICKS)
        if stick_count <= 0:
            self.queue_activity_message(player, "Bring Wilhelm some sticks first.", MSG_QUEST_REMINDER)
            return True
        if not player.inventory.remove_item(ITEM_STICKS, stick_count):
            self.queue_activity_message(player, "Wilhelm can't take the sticks now.", MSG_QUEST_REMINDER)
            return True
        player.bridge_materials_staged = True
        player.active_quest_id = QUEST_REPAIR_BRIDGE
        player.quest_state = QUEST_STATE_ACTIVE
        player.quest_progress = 0
        player.quest_target = REPAIR_BRIDGE_TARGET
        self._mark_player_state_dirty(player)
        return self._start_bridge_repair_for_player(player)

    def _interact_wilhelm(self, player: PlayerState) -> bool:
        encounter = self.get_scripted_encounter(player.token, "bridge_repair")
        if encounter is not None and encounter.phase in (ENCOUNTER_ESCORTING, ENCOUNTER_ACTIVE):
            self.queue_activity_message(player, "Stay close to Wilhelm.", MSG_QUEST_REMINDER)
            return True
        if encounter is not None and encounter.phase == ENCOUNTER_RETURNING:
            self.queue_activity_message(player, "Wilhelm is heading to town.", MSG_QUEST_REMINDER)
            return True
        if (
            player.active_quest_id == QUEST_REPAIR_BRIDGE
            and player.quest_state == QUEST_STATE_READY_TO_TURN_IN
        ):
            return self.open_dialogue(
                player,
                story.DLG_WILHELM_COMPLETE,
                NPC_WILHELM,
                (
                    "The bridge is sound again. Thank you for "
                    "keeping those beavers off me.",
                    "Go tell Nerissa the road is open.",
                ),
            )
        if player.bridge_repaired:
            self.queue_activity_message(player, "The bridge holds. The road is open.", MSG_QUEST_COMPLETE)
            return True
        if player.bridge_materials_staged:
            return self._start_bridge_repair_for_player(player)
        stick_count = player.inventory.count_item(ITEM_STICKS)
        if (
            stick_count > 0
            and player.active_quest_id == QUEST_ROAD_TROUBLE
            and player.quest_state == QUEST_STATE_COMPLETE
        ):
            return self.open_dialogue(
                player,
                story.DLG_WILHELM_BRIDGE_START,
                NPC_WILHELM,
                (
                    "Good. These sticks will do. I will take them to the washed-out bridge now.",
                    "Stay close and keep the road clear while I work.",
                ),
            )
        if player.active_quest_id == QUEST_ROAD_TROUBLE and player.quest_state == QUEST_STATE_ACTIVE:
            self.queue_activity_message(player, "Finish Daniel's quest, bring sticks.", MSG_QUEST_REMINDER)
            return True
        if stick_count > 0:
            self.queue_activity_message(player, "Talk to Daniel before helping Wilhelm.", MSG_QUEST_REMINDER)
            return True
        return self.open_dialogue(
            player,
            story.DLG_WILHELM_INTRO,
            NPC_WILHELM,
            (
                "I need wood to repair the bridge.",
                "Daniel knows how to get some. Come back after talking with him.",
            ),
        )

    def _interact_nerissa(self, player: PlayerState) -> bool:
        if player.bridge_repaired and player.story_stage <= STORY_STAGE_BRIDGE:
            return self.open_dialogue(
                player,
                story.DLG_NERISSA_POST_BRIDGE,
                NPC_NERISSA,
                (
                    "The bridge is open again, but the flooding is getting worse.",
                    "Follow the repaired road east and speak with Lucian at the marsh lookout.",
                ),
            )
        if player.story_stage == STORY_STAGE_NONE:
            return self.open_dialogue(
                player,
                story.DLG_NERISSA_INTRO,
                NPC_NERISSA,
                (
                    "Welcome to Willowcross, traveler. The river keeps rising and the roads are washing out.",
                    "Speak with Daniel the Farmer east of the town at his orchard. He needs your help.",
                ),
            )
        if player.story_stage == STORY_STAGE_WELCOME:
            self.queue_activity_message(player, "Daniel is waiting east at the orchard", MSG_QUEST_REMINDER)
            return True
        if player.story_stage <= STORY_STAGE_ROAD_TROUBLE and not player.bridge_repaired:
            self.queue_activity_message(player, "Bring Wilhelm the sticks so he can repair the bridge.", MSG_QUEST_REMINDER)
            return True
        if (
            player.active_quest_id == QUEST_LIVING_MUD
            and player.quest_state == QUEST_STATE_READY_TO_TURN_IN
            and player.story_step == 1
        ):
            return self.open_dialogue(
                player,
                story.DLG_NERISSA_SAMPLES,
                NPC_NERISSA,
                (
                    "Oil and rust? This came from machinery, not the marsh. A goblin",
                    "was seen near the abandoned outpost northeast of the marsh lookout.",
                    "Find him and use any means necessary to learn what",
                    "nefarious plans they've cooked up."
                ),
            )
        if player.story_stage >= STORY_STAGE_RETURN_NERISSA:
            return self.open_dialogue(
                player,
                story.DLG_NERISSA_ENDING,
                NPC_NERISSA,
                (
                    "With the Deep Pump silent, the floodwaters have begun "
                    "to fall. Willowcross is safe...for now.",
                    "You have done what none of us could, and the town "
                    "owes you its thanks.",
                    "The Willowcross proving grounds are open to you now, "
                    "champion, whenever you wish to test your skill "
                    "against others.",
                ),
            )
        self.queue_activity_message(player, "Nerissa watches the rising water.", MSG_NONE)
        return True

    def _complete_willowcross_saved(self, player: PlayerState) -> None:
        if player.pvp_unlocked:
            return
        player.pvp_unlocked = True
        player.story_stage = max(player.story_stage, STORY_STAGE_COMPLETE)
        player.story_step = 0
        self.award_gold(WILLOWCROSS_SAVED_REWARD_GOLD, player)
        self.award_xp(WILLOWCROSS_SAVED_REWARD_XP, player)
        # Queued last, deliberately overriding any level-up message: this is
        # the story's climactic beat and must stay the visible HUD line.
        self.queue_activity_message(player, "Willowcross is safe! PvP unlocked.", MSG_QUEST_COMPLETE)
        self._mark_player_state_dirty(player)

    def _interact_lucian(self, player: PlayerState) -> bool:
        if (
            player.active_quest_id == QUEST_LIVING_MUD
            and player.quest_state == QUEST_STATE_READY_TO_TURN_IN
        ):
            if player.story_step == 0:
                return self.open_dialogue(
                    player,
                    story.DLG_LUCIAN_SAMPLES_REDIRECT,
                    NPC_LUCIAN,
                    (
                        "Oil and rust? I do not know what to make of this.",
                        "Take it to Nerissa. She may know more than I do.",
                    ),
                )
            self.queue_activity_message(player, "Take the samples to Nerissa.", MSG_QUEST_REMINDER)
            return True
        if player.active_quest_id == QUEST_LIVING_MUD and player.quest_state == QUEST_STATE_ACTIVE:
            oil = player.inventory.count_item(ITEM_OIL_SAMPLE)
            rust = player.inventory.count_item(ITEM_RUST_SAMPLE)
            self.queue_activity_message(
                player, f"Oil {oil}/{LIVING_MUD_OIL_TARGET}  Rust {rust}/{LIVING_MUD_RUST_TARGET}", MSG_QUEST_REMINDER
            )
            return True
        if (
            player.active_quest_id == QUEST_BLACKWATER_BITE
            and player.quest_state == QUEST_STATE_READY_TO_TURN_IN
        ):
            return self.open_dialogue(
                player,
                story.DLG_LUCIAN_LIVING_MUD_OFFER,
                NPC_LUCIAN,
                (
                    "Good work. The snakes should thin out for a while.",
                    "There is worse in the deep marsh. Investigate the "
                    "slimy abominations that have appeared there.",
                ),
            )
        if player.active_quest_id == QUEST_BLACKWATER_BITE and player.quest_state == QUEST_STATE_ACTIVE:
            self.queue_activity_message(
                player,
                f"Snakes cleared: {player.quest_progress}/{player.quest_target}.",
                MSG_QUEST_REMINDER,
            )
            return True
        if player.story_stage >= STORY_STAGE_BLACKWATER:
            self.queue_activity_message(player, "Lucian watches the marsh road.", MSG_NONE)
            return True
        return self.open_dialogue(
            player,
            story.DLG_LUCIAN_BLACKWATER_OFFER,
            NPC_LUCIAN,
            (
                "Guard Lucian, at the marsh lookout. Glad the bridge held.",
                "Rising water is pushing snakes north along the road. "
                "Clear five of them and return to me.",
            ),
        )

    def _start_blackwater_bite(self, player: PlayerState) -> None:
        player.active_quest_id = QUEST_BLACKWATER_BITE
        player.quest_state = QUEST_STATE_ACTIVE
        player.quest_progress = 0
        player.quest_target = BLACKWATER_TARGET
        player.story_stage = max(player.story_stage, STORY_STAGE_BLACKWATER)
        player.story_step = 0
        self._mark_player_state_dirty(player)

    def _advance_blackwater_progress(self, player: PlayerState) -> bool:
        if player.active_quest_id != QUEST_BLACKWATER_BITE or player.quest_state != QUEST_STATE_ACTIVE:
            return False
        player.quest_progress = min(player.quest_target, player.quest_progress + 1)
        if player.quest_progress >= player.quest_target:
            player.quest_state = QUEST_STATE_READY_TO_TURN_IN
            self.queue_activity_message(
                player, f"All {player.quest_target} cleared! See Lucian.", MSG_QUEST_READY
            )
        else:
            self.queue_activity_message(
                player,
                f"{player.quest_progress}/{player.quest_target} snakes cleared.",
                MSG_QUEST_PROGRESS,
            )
        self._mark_player_state_dirty(player)
        return True

    def _complete_blackwater_and_start_living_mud(self, player: PlayerState) -> None:
        self.award_gold(BLACKWATER_REWARD_GOLD, player)
        self.award_xp(BLACKWATER_REWARD_XP, player)
        player.active_quest_id = QUEST_LIVING_MUD
        player.quest_state = QUEST_STATE_ACTIVE
        player.quest_progress = 0
        player.quest_target = LIVING_MUD_TARGET
        player.story_stage = max(player.story_stage, STORY_STAGE_LIVING_MUD)
        player.story_step = 0
        self._mark_player_state_dirty(player)

    def _grant_living_mud_sample(self, player: PlayerState) -> bool:
        if player.active_quest_id != QUEST_LIVING_MUD or player.quest_state != QUEST_STATE_ACTIVE:
            return False
        oil = player.inventory.count_item(ITEM_OIL_SAMPLE)
        rust = player.inventory.count_item(ITEM_RUST_SAMPLE)
        oil_needed = max(0, LIVING_MUD_OIL_TARGET - oil)
        rust_needed = max(0, LIVING_MUD_RUST_TARGET - rust)
        if oil_needed <= 0 and rust_needed <= 0:
            return False
        if oil_needed >= rust_needed:
            granted = self.grant_personal_sample(player, ITEM_OIL_SAMPLE, LIVING_MUD_OIL_TARGET)
        else:
            granted = self.grant_personal_sample(player, ITEM_RUST_SAMPLE, LIVING_MUD_RUST_TARGET)
        if granted <= 0:
            return False
        oil = player.inventory.count_item(ITEM_OIL_SAMPLE)
        rust = player.inventory.count_item(ITEM_RUST_SAMPLE)
        player.quest_progress = min(player.quest_target, oil + rust)
        if oil >= LIVING_MUD_OIL_TARGET and rust >= LIVING_MUD_RUST_TARGET:
            player.quest_state = QUEST_STATE_READY_TO_TURN_IN
            self.queue_activity_message(player, "Got both samples! See Lucian.", MSG_QUEST_READY)
        else:
            self.queue_activity_message(player, f"Oil {oil}/2  Rust {rust}/2", MSG_QUEST_PROGRESS)
        self._mark_player_state_dirty(player)
        return True

    def _complete_living_mud(self, player: PlayerState) -> None:
        player.inventory.remove_item(ITEM_OIL_SAMPLE, player.inventory.count_item(ITEM_OIL_SAMPLE))
        player.inventory.remove_item(ITEM_RUST_SAMPLE, player.inventory.count_item(ITEM_RUST_SAMPLE))
        self.award_gold(LIVING_MUD_REWARD_GOLD, player)
        self.award_xp(LIVING_MUD_REWARD_XP, player)
        player.story_stage = max(player.story_stage, STORY_STAGE_GOBLIN_WARNED)
        player.story_step = 0
        # Living Mud is the last quest the scalar active_quest_id/quest_state
        # HUD line tracks -- the goblin-warned/warden-key/Gorvak/return-to-
        # Nerissa stages that follow have no quest id of their own to
        # overwrite it, so a lingering QUEST_STATE_COMPLETE here would show
        # "Living Mud done" as the persistent quest line for the rest of the
        # game. Clear it instead of leaving stale text behind.
        player.active_quest_id = QUEST_NONE
        player.quest_state = QUEST_STATE_NOT_STARTED
        player.quest_progress = 0
        player.quest_target = 0
        self._mark_player_state_dirty(player)

    def accept_pending_quest_offer(self, player: PlayerState) -> bool:
        quest_id = player.pending_quest_offer_id
        if quest_id not in QUEST_TARGETS:
            return False
        player.pending_quest_offer_id = QUEST_NONE
        player.active_quest_id = quest_id
        player.quest_state = QUEST_STATE_ACTIVE
        player.quest_progress = 0
        player.quest_target = QUEST_TARGETS[quest_id]
        self.queue_activity_message(player, QUEST_START_TEXT[quest_id], MSG_QUEST_STARTED)
        self._mark_player_state_dirty(player)
        return True

    def _advance_road_trouble_progress(self, player: PlayerState) -> bool:
        if player.active_quest_id != QUEST_ROAD_TROUBLE or player.quest_state != QUEST_STATE_ACTIVE:
            return False
        player.quest_progress = min(player.quest_target, player.quest_progress + 1)
        if player.quest_progress >= player.quest_target:
            player.quest_state = QUEST_STATE_READY_TO_TURN_IN
            self.queue_activity_message(
                player,
                f"All {player.quest_target} cleared! Go tell Daniel.",
                MSG_QUEST_READY,
            )
        else:
            self.queue_activity_message(
                player,
                f"{player.quest_progress}/{player.quest_target} beavers cleared. Keep going!",
                MSG_QUEST_PROGRESS,
            )
        self._mark_player_state_dirty(player)
        return True

    def award_xp(self, amount: int, player: PlayerState | None = None) -> None:
        if amount <= 0:
            return
        if player is None:
            player = self.player
        player.xp = min(9999, player.xp + amount)
        self.check_level_up(player)
        self._mark_player_state_dirty(player)

    def award_gold(self, amount: int, player: PlayerState | None = None) -> None:
        if amount <= 0:
            return
        if player is None:
            player = self.player
        player.gold = min(9999, player.gold + amount)
        self._mark_player_state_dirty(player)

    def pickup_nearby_item(self, player: PlayerState) -> bool:
        candidates = (
            (player.x, player.y),
            (player.x + 1, player.y),
            (player.x - 1, player.y),
            (player.x, player.y + 1),
            (player.x, player.y - 1),
        )
        for x, y in candidates:
            item = self.item_at(player.map_id, x, y, player)
            if item is None:
                continue
            return self.collect_item(player, item)
        return False

    def pickup_current_item(self, player: PlayerState) -> bool:
        item = self.item_at(player.map_id, player.x, player.y, player)
        if item is None:
            return False
        return self.collect_item(player, item)

    def _pickup_item_at(self, player: PlayerState, x: int, y: int) -> None:
        item = self.item_at(player.map_id, x, y, player)
        if item is not None:
            self.collect_item(player, item)

    def _pickup_items_along_path(
        self, player: PlayerState, from_x: int, from_y: int, to_x: int, to_y: int
    ) -> None:
        x, y = from_x, from_y
        # 64 is a generous guard: a single tick never legitimately moves the
        # player more than a couple of tiles, so any longer "path" is a
        # teleport/desync we do not want to sweep.
        for _ in range(64):
            self._pickup_item_at(player, x, y)
            if x == to_x and y == to_y:
                return
            step_x = (to_x > x) - (to_x < x)
            step_y = (to_y > y) - (to_y < y)
            if step_x and step_y:
                # Diagonal batch: the client walked an L-path through one of the
                # two corner tiles but we cannot know which, so sweep both.
                self._pickup_item_at(player, x + step_x, y)
                self._pickup_item_at(player, x, y + step_y)
            x += step_x
            y += step_y

    def collect_item(self, player: PlayerState, item: Entity) -> bool:
        if not self.entity_collectible_by_player(item, player):
            return False
        if item.subtype == ITEM_WARDEN_KEY and item.owner_id != 0:
            if not player.inventory.add_item(ITEM_WARDEN_KEY, 1):
                self.queue_activity_message(player, "Inventory full.")
                return True
            player.warden_key_collected = True
            self.remove_entity(item.entity_id)
            self.queue_activity_message(player, "Got the Warden Key! Return to Grix.", MSG_QUEST_READY)
            self._mark_player_state_dirty(player)
            return True
        if item.subtype == ITEM_LOST_CHARM:
            if player.active_quest_id != QUEST_LOST_CHARM or player.quest_state != QUEST_STATE_ACTIVE:
                self.queue_activity_message(player, "The charm isn't yours to take.")
                return True
            player.quest_progress = LOST_CHARM_TARGET
            player.quest_state = QUEST_STATE_READY_TO_TURN_IN
            self.queue_activity_message(player, "Found it! Return to Grix.", MSG_QUEST_READY)
            # Hide-and-respawn, like a killed enemy, rather than
            # removing the entity -- two players can run this quest
            # together, so the charm needs to come back for the second one.
            item.hp = 0
            item.respawn_ticks = LOST_CHARM_RESPAWN_TICKS
            self._mark_player_state_dirty(player)
            return True
        quantity = max(1, item.hp)
        if item.subtype == ITEM_GOLD:
            self.award_gold(quantity, player)
            self.queue_activity_message(player, f"You got {quantity} gold.", MSG_GOT_GOLD)
        elif player.inventory.add_item(item.subtype, quantity):
            if item.subtype == ITEM_STICKS:
                self.queue_activity_message(player, "You got sticks.", MSG_GOT_STICKS)
            else:
                self.queue_activity_message(player, "You got an item.", MSG_GOT_STICKS)
            self._mark_player_state_dirty(player)
        else:
            self.queue_activity_message(player, "Inventory full.")
            return True
        self.remove_entity(item.entity_id)
        return True

    def check_level_up(self, player: PlayerState | None = None) -> None:
        if player is None:
            player = self.player
        while player.level < MAX_PLAYER_LEVEL and player.xp >= player.xp_next:
            player.level += 1
            player.max_health = max_hp_for_level(player.level, player.class_id)
            player.health = player.max_health
            player.xp_next = xp_needed_for_next_level(player.level)
            self.queue_activity_message(player, f"You reached level {player.level}!", MSG_LEVEL_UP)

    # ------------------------------------------------------------------
    # Death and respawn

    def nearest_respawn_point(self, map_id: int, x: int, y: int) -> RespawnPoint:
        if map_id == MAP_STARTER_CAVE:
            return RespawnPoint(MAP_STARTER_CAVE, STARTER_CAVE_ENTRY[0], STARTER_CAVE_ENTRY[1])
        if map_id == MAP_PVP_REALM:
            return RespawnPoint(MAP_PVP_REALM, PVP_REALM_RESPAWN[0], PVP_REALM_RESPAWN[1])
        candidates = [point for point in RESPAWN_POINTS if point.map_id == map_id]
        if not candidates:
            return RespawnPoint(MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1])
        return min(candidates, key=lambda point: abs(point.x - x) + abs(point.y - y))

    def handle_player_death(self, player: PlayerState | None = None) -> None:
        if player is None:
            player = self.player
        for encounter in tuple(self.scripted_encounters.values()):
            if encounter.owner_id == player.token:
                self.fail_scripted_encounter(encounter, "owner_died")
        self._normalize_story_state(player)
        previous_map_id = player.map_id
        self.queue_activity_message(player, "You fall in battle.", MSG_PLAYER_DIED)
        respawn = self.nearest_respawn_point(player.map_id, player.x, player.y)
        player.map_id = respawn.map_id
        player.x = respawn.x
        player.y = respawn.y
        player.respawn_map_id = respawn.map_id
        player.respawn_x = respawn.x
        player.respawn_y = respawn.y
        self.world_for(respawn.map_id)
        self._apply_map_pvp_policy(player, previous_map_id)
        player.health = player.max_health
        for entity in self.beavers:
            if entity.map_id == player.map_id:
                entity.aggro_ticks = 0
                entity.attack_cooldown = 0
        self._sync_player_entity(player)
        self.update_active_zones()
        if respawn.map_id == MAP_PVP_REALM:
            message_id = MSG_RESPAWN_CAVE
            message = "You wake at the arena gate."
        elif respawn.map_id == MAP_STARTER_CAVE:
            message_id = MSG_RESPAWN_CAVE
            message = "You wake at the cave entry."
        else:
            message_id = MSG_RESPAWN_GRAVE
            message = "You wake at a grave."
        self.queue_activity_message(player, message, message_id)
        player.respawn_counter = (player.respawn_counter + 1) & 0xFFFF
        player.latest_respawn_event = self.respawn_event_packet(player.respawn_counter, player.token)
        player.respawn_correction_ticks = RESPAWN_CORRECTION_TICKS
        self._mark_player_state_dirty(player)

    # ------------------------------------------------------------------
    # Tick loop

    def begin_tick(self) -> None:
        self.tick = (self.tick + 1) & 0xFFFF
        self.tile_update = None
        for enemy in self.beavers:
            if enemy.hit_pulse_ticks > 0:
                enemy.hit_pulse_ticks -= 1
        for player in self.players.values():
            if player.transition_cooldown > 0:
                player.transition_cooldown -= 1
            if player.transition_loading:
                # Play stays paused until the client reports MAP_READY; the
                # hybrid server re-sends MAP_CHANGE while this is set, so a
                # transition packet lost on the serial link heals instead of
                # expiring into an exposed fight against enemies the client
                # cannot see (it is still rendering the old map).
                player.transition_loading_ticks += 1
            elif player.transition_grace_ticks > 0:
                player.transition_grace_ticks -= 1

    def finish_tick(self) -> None:
        self._update_scripted_encounters()
        self._update_grix_story_state()
        self._update_gorvak_encounter_state()
        self._decay_dead_beavers()
        self._decay_expired_items()
        self._respawn_dead_enemies()
        self._respawn_lost_charm()
        self._respawn_herbs()
        self._respawn_trees()
        self._move_enemies()
        self._apply_enemy_contact_damage()

    def step(self, intent: InputIntent | None = None) -> Snapshot:
        self.begin_tick()
        if intent is not None:
            self.apply_input(intent)
        if self.player.pending_map_change is not None:
            return self.snapshot()
        self.finish_tick()
        return self.snapshot()

    def step_player_state(self, state: PlayerStatePacket | None = None) -> tuple[Snapshot, bool]:
        self.begin_tick()
        accepted = True
        if state is not None:
            accepted = self.apply_player_state(state)
        if self.player.pending_map_change is not None:
            return self.snapshot(), accepted
        self.finish_tick()
        return self.snapshot(), accepted

    def consume_pending_map_change(self, token: int | None = None) -> MapTransition | None:
        player = self.player_for(token)
        transition = player.pending_map_change
        player.pending_map_change = None
        return transition

    @staticmethod
    def map_art_ids(map_id: int) -> tuple[int, int]:
        # Tileset/palette for a map, for rebuilding a MAP_CHANGE outside a
        # live transition (e.g. a reconnect while the player is still
        # waiting to become map-ready).
        for transition in MAP_TRANSITIONS:
            if transition.to_map == map_id:
                return transition.tileset_id, transition.palette_id
        return TILESET_OVERWORLD, PALETTE_OVERWORLD

    @property
    def pending_map_change(self) -> MapTransition | None:
        return self.player.pending_map_change

    def _apply_transition_if_present(self, player: PlayerState) -> None:
        if player.transition_cooldown > 0:
            return
        for transition in MAP_TRANSITIONS:
            if (
                transition.from_map == player.map_id
                and transition.from_x == player.x
                and transition.from_y == player.y
            ):
                if transition.to_map == MAP_PVP_REALM and not player.pvp_unlocked:
                    player.transition_cooldown = TRANSITION_COOLDOWN_TICKS
                    self.queue_activity_message(
                        player,
                        "Defeat Gorvak, then see Nerissa.",
                        MSG_PVP_ARENA_LOCKED,
                    )
                    return
                if player.level < transition.required_level:
                    player.transition_cooldown = TRANSITION_COOLDOWN_TICKS
                    self.queue_activity_message(
                        player,
                        f"You must be lvl {transition.required_level} for PvP.",
                        MSG_PVP_ARENA_LOCKED,
                    )
                    return
                previous_map_id = player.map_id
                player.map_id = transition.to_map
                player.x = transition.to_x
                player.y = transition.to_y
                if transition.to_map == MAP_STARTER_CAVE:
                    player.respawn_map_id = MAP_STARTER_CAVE
                    player.respawn_x, player.respawn_y = STARTER_CAVE_RESPAWN
                elif transition.to_map == MAP_PVP_REALM:
                    player.respawn_map_id = MAP_PVP_REALM
                    player.respawn_x, player.respawn_y = PVP_REALM_RESPAWN
                self.world_for(transition.to_map)
                self._apply_map_pvp_policy(player, previous_map_id)
                player.pending_map_change = transition
                player.transition_loading = True
                player.transition_loading_ticks = 0
                player.transition_grace_ticks = 0
                player.transition_cooldown = TRANSITION_COOLDOWN_TICKS
                # The session stays connected across the transition; hold the
                # player at the spawn until the client echoes it, so stale
                # in-flight PLAYER_STATE coords from the old map cannot
                # teleport the player around the new one.
                player.respawn_correction_ticks = RESPAWN_CORRECTION_TICKS
                self._sync_player_entity(player)
                self.update_active_zones()
                self._mark_player_state_dirty(player)
                return

    def mark_player_map_ready(self, token: int) -> bool:
        player = self.players.get(token)
        if player is None:
            return False
        player.transition_loading = False
        player.transition_loading_ticks = 0
        player.transition_grace_ticks = TRANSITION_READY_GRACE_TICKS
        return True

    def _transition_protected(self, player: PlayerState) -> bool:
        return player.transition_loading or player.transition_grace_ticks > 0

    # ------------------------------------------------------------------
    # Zones

    def zone_definition(self, zone_id: ZoneId) -> ZoneDefinition:
        if zone_id.map_id == MAP_STARTER_CAVE:
            return ZoneDefinition(
                zone_id,
                zone_type=ZONE_CAVE,
                danger_level=1,
                spawn_table=(
                    SpawnRule(ENTITY_ENEMY, ENEMY_BEAVER, 1, 1, 1, 1, 30, (CAVE_FLOOR,)),
                ),
            )
        if zone_id.map_id == MAP_PVP_REALM:
            return ZoneDefinition(zone_id, zone_type=ZONE_FOREST, danger_level=0)
        if zone_id.zx == 0 and zone_id.zy == 0:
            return ZoneDefinition(zone_id, zone_type=ZONE_TOWN, danger_level=0)
        if zone_id.zy == 0:
            return ZoneDefinition(zone_id, zone_type=ZONE_ROAD, danger_level=0)
        return ZoneDefinition(
            zone_id,
            zone_type=ZONE_FOREST,
            danger_level=1,
            spawn_table=(
                SpawnRule(ENTITY_ENEMY, ENEMY_BEAVER, 1, 1, 1, 1, 30, (GRASS, ROAD)),
            ),
        )

    def player_active_zones(self, player: PlayerState) -> set[ZoneId]:
        return zones_near_tile(player.map_id, player.x, player.y)

    def desired_active_zones(self) -> set[ZoneId]:
        active: set[ZoneId] = set()
        for player in self.players.values():
            active.update(self.player_active_zones(player))
        return active

    def update_active_zones(self) -> tuple[set[ZoneId], set[ZoneId]]:
        for player in self.players.values():
            self.mark_current_zone_visited(player)
        new_active = self.desired_active_zones()
        activated = new_active - self.active_zones
        deactivated = self.active_zones - new_active
        for zone_id in sorted(activated):
            self.activate_zone(zone_id)
        for zone_id in sorted(deactivated):
            self.deactivate_zone(zone_id)
        self.active_zones = new_active
        return activated, deactivated

    def mark_current_zone_visited(self, player: PlayerState) -> None:
        zone_id = zone_for_tile(player.map_id, player.x, player.y)
        if zone_id in player.visited_zones:
            return
        player.visited_zones.add(zone_id)
        self._mark_player_state_dirty(player)

    def map_summary_packet(self, seq: int, token: int | None = None) -> MapSummaryPacket:
        player = self.player_for(token)
        self.mark_current_zone_visited(player)
        current_zone = zone_for_tile(player.map_id, player.x, player.y)
        cells = bytearray()
        for zy in range(MAP_SUMMARY_HEIGHT):
            for zx in range(MAP_SUMMARY_WIDTH):
                zone_id = ZoneId(player.map_id, zx, zy)
                cell = self.zone_definition(zone_id).zone_type & 0x0F
                if zone_id in player.visited_zones:
                    cell |= MAP_SUMMARY_VISITED
                    cell |= self._map_marker_flags(zone_id)
                else:
                    cell = 0
                if zone_id == current_zone:
                    cell |= MAP_SUMMARY_CURRENT | MAP_SUMMARY_VISITED
                cells.append(cell)
        return MapSummaryPacket(seq, player.map_id, 0, 0, MAP_SUMMARY_WIDTH, MAP_SUMMARY_HEIGHT, bytes(cells))

    def map_summary_state_tuple(self, token: int | None = None) -> tuple[int, int, int, bytes]:
        packet = self.map_summary_packet(0, token)
        return (packet.map_id, packet.width, packet.height, packet.cells)

    def _map_marker_flags(self, zone_id: ZoneId) -> int:
        if zone_id.map_id == MAP_STARTER_CAVE:
            return 0
        flags = 0
        if zone_id == zone_for_tile(MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1]):
            flags = MAP_SUMMARY_MARKER_GRAVE
        if zone_id == zone_for_tile(MAP_OVERWORLD, OVERWORLD_CAVE_ENTRANCE[0], OVERWORLD_CAVE_ENTRANCE[1]):
            flags = MAP_SUMMARY_MARKER_CAVE
        if zone_id == zone_for_tile(MAP_OVERWORLD, FARMER_X, FARMER_Y):
            flags = MAP_SUMMARY_MARKER_TOWN
        return flags

    def activate_zone(self, zone_id: ZoneId) -> None:
        if zone_id not in self.active_zone_states:
            self.active_zone_states[zone_id] = ActiveZoneState(zone_id, self.tick)
        self.zone_events.append(("activate", zone_id))
        if self.zone_spawns_enabled:
            self.fill_zone_spawns(zone_id)

    def deactivate_zone(self, zone_id: ZoneId) -> None:
        state = self.active_zone_states.get(zone_id)
        if state is not None:
            for entity_id in tuple(state.spawned_entity_ids):
                entity = self.entities.get(entity_id)
                if entity is not None and entity.is_temporary and not entity.is_player:
                    self.remove_entity(entity_id)
        self.active_zone_states.pop(zone_id, None)
        self.zone_events.append(("deactivate", zone_id))

    def is_tile_in_active_zone(self, map_id: int, x: int, y: int) -> bool:
        return zone_for_tile(map_id, x, y) in self.active_zones

    # ------------------------------------------------------------------
    # Snapshots and per-player packets

    def snapshot(self, token: int | None = None) -> Snapshot:
        player = self.player_for(token)
        self._sync_player_entity(player)
        tile_x, tile_y, tile_id = self._snapshot_tile_update(player)
        return Snapshot(
            tick=self.tick,
            player_x=player.x,
            player_y=player.y,
            health=player.health,
            score=player.score,
            beavers=self.legacy_beaver_snapshots_for_window(token=player.token),
            tile_x=tile_x,
            tile_y=tile_y,
            tile_id=tile_id,
        )

    def snapshot_for_window(self, origin_x: int, origin_y: int, token: int | None = None) -> Snapshot:
        player = self.player_for(token)
        self._sync_player_entity(player)
        beavers = self.legacy_beaver_snapshots_for_window(origin_x, origin_y, token=player.token)
        tile_x, tile_y, tile_id = self._snapshot_tile_update(player, origin_x, origin_y)
        return Snapshot(
            tick=self.tick,
            player_x=player.x,
            player_y=player.y,
            health=player.health,
            score=player.score,
            beavers=beavers,
            tile_x=tile_x,
            tile_y=tile_y,
            tile_id=tile_id,
        )

    def _tile_update_on_map(self, map_id: int) -> bool:
        return self.tile_update is not None and self.tile_update[0] == map_id

    def _snapshot_tile_update(
        self,
        player: PlayerState,
        origin_x: int | None = None,
        origin_y: int | None = None,
    ) -> tuple[int, int, int]:
        tile_x = tile_y = tile_id = 0
        if self._tile_update_on_map(player.map_id):
            _, tx, ty, tid = self.tile_update
            if origin_x is None or self._in_window(tx, ty, origin_x, origin_y):
                return tx, ty, tid
            return 0, 0, 0
        world = self.world_for(player.map_id)
        if world.tile(player.x, player.y) != HERB:
            return 0, 0, 0
        if origin_x is not None and not self._in_window(player.x, player.y, origin_x, origin_y):
            return 0, 0, 0
        return player.x, player.y, HERB

    def remote_players_near(
        self,
        token: int,
        origin_x: int,
        origin_y: int,
        limit: int = REALTIME_DEFAULT_REMOTE_PLAYERS,
    ) -> tuple[RemotePlayerRecord, ...]:
        limit = max(0, min(limit, REALTIME_MAX_REMOTE_PLAYERS_SUPPORTED))
        me = self.players[token]
        candidates = [
            player
            for other_token, player in self.players.items()
            if other_token != token
            and player.map_id == me.map_id
            and self._in_window(player.x, player.y, origin_x, origin_y)
        ]
        candidates.sort(key=lambda p: (abs(p.x - me.x) + abs(p.y - me.y), p.token))

        def state_for(p: PlayerState) -> int:
            state = REMOTE_PLAYER_STATE_ALIVE
            if p.pvp_enabled:
                state |= REMOTE_PLAYER_STATE_PVP_ENABLED
            state |= (p.shot_counter & 3) << REMOTE_PLAYER_STATE_FIRE_SHIFT
            return state

        return tuple(
            RemotePlayerRecord(x=p.x, y=p.y, facing=p.facing, state=state_for(p))
            for p in candidates[:limit]
        )

    def item_drops_near(self, token: int, origin_x: int, origin_y: int) -> tuple[ItemDropRecord, ...]:
        player = self.players[token]
        candidates = [
            entity
            for entity in self.entities.values()
            if entity.kind == ENTITY_ITEM
            and entity.map_id == player.map_id
            and entity.is_live
            and self.entity_visible_to_player(entity, player)
            and self._in_window(entity.x, entity.y, origin_x, origin_y)
        ]
        candidates.sort(key=lambda e: (abs(e.x - player.x) + abs(e.y - player.y), e.entity_id))
        return tuple(
            ItemDropRecord(x=e.x, y=e.y, item_id=e.subtype, quantity=min(e.hp, 255))
            for e in candidates[:REALTIME_MAX_ITEM_DROPS]
        )

    def hud_state_tuple(self, token: int | None = None) -> tuple[int, ...]:
        player = self.player_for(token)
        return (
            player.health,
            player.max_health,
            player.level,
            player.xp,
            player.xp_next,
            player.gold,
            player.pvp_enabled,
            max(0, min(9999, player.pvp_kills)),
        )

    def quest_state_tuple(self, token: int | None = None) -> tuple[int, ...]:
        player = self.player_for(token)
        return (
            player.active_quest_id,
            player.quest_state,
            player.quest_progress,
            player.quest_target,
            player.pending_quest_offer_id,
        )

    def inventory_state_tuple(self, token: int | None = None) -> tuple[int, ...]:
        player = self.player_for(token)
        flattened: list[int] = [player.gold]
        for item_id, quantity in player.inventory.as_tuple():
            flattened.extend((item_id, quantity))
        return tuple(flattened)

    def hud_update_packet(self, seq: int, token: int | None = None) -> HudUpdatePacket:
        player = self.player_for(token)
        return HudUpdatePacket(
            seq=seq,
            hp=player.health,
            max_hp=player.max_health,
            level=player.level,
            xp=player.xp,
            xp_next=player.xp_next,
            gold=player.gold,
            flags=HUD_FLAG_PVP_ENABLED if player.pvp_enabled else 0,
            pvp_kills=max(0, min(9999, player.pvp_kills)),
        )

    def quest_update_packet(self, seq: int, token: int | None = None) -> QuestUpdatePacket:
        player = self.player_for(token)
        if player.pending_quest_offer_id != QUEST_NONE:
            # Between an NPC extending an offer and the player accepting or
            # walking away, preview the offered quest's name -- this is
            # what the accept modal reads instead of the ongoing tracker.
            quest_id = player.pending_quest_offer_id
            state = QUEST_STATE_NOT_STARTED
            text = QUEST_NAMES.get(quest_id, "")
        else:
            quest_id = player.active_quest_id
            state = player.quest_state
            text = quest_status_text(quest_id, state, player.quest_progress, player.quest_target)
        return QuestUpdatePacket(
            seq=seq,
            quest_id=quest_id,
            state=state,
            text=text,
        )

    def inventory_update_packet(self, seq: int, token: int | None = None) -> InventoryUpdatePacket:
        player = self.player_for(token)
        return InventoryUpdatePacket(seq=seq, slots=player.inventory.as_tuple(), gold=player.gold)

    def message_packet(self, seq: int, token: int | None = None) -> MessagePacket:
        player = self.player_for(token)
        return MessagePacket(seq, player.latest_message_id, player.latest_activity_message)

    def respawn_event_packet(self, seq: int, token: int | None = None) -> RespawnEventPacket:
        player = self.player_for(token)
        return RespawnEventPacket(
            seq=seq,
            map_id=player.map_id,
            x=player.x,
            y=player.y,
            hp=player.health,
            max_hp=player.max_health,
            message_id=player.latest_message_id,
        )

    # Single-player compatibility aliases over the default player's
    # per-player message/respawn state.
    @property
    def latest_message_id(self) -> int:
        return self.player.latest_message_id

    @property
    def latest_activity_message(self) -> str:
        return self.player.latest_activity_message

    @property
    def activity_messages(self) -> list[str]:
        return self.player.activity_messages

    @property
    def message_counter(self) -> int:
        return self.player.message_counter

    @property
    def respawn_counter(self) -> int:
        return self.player.respawn_counter

    @property
    def latest_respawn_event(self) -> RespawnEventPacket | None:
        return self.player.latest_respawn_event

    @property
    def respawn_correction_ticks(self) -> int:
        return self.player.respawn_correction_ticks

    @property
    def player_pickup_events(self) -> int:
        return self.player.pickup_events

    # ------------------------------------------------------------------
    # Terrain windows (per player)

    def window(self, token: int | None = None) -> Window:
        origin_x, origin_y = self.window_origin(token)
        return self.window_at(origin_x, origin_y, token)

    def window_at(self, origin_x: int, origin_y: int, token: int | None = None) -> Window:
        player = self.player_for(token)
        world = self.world_for(player.map_id)
        tiles = world.window_tiles(origin_x, origin_y, WINDOW_W, WINDOW_H)
        return Window(
            tick=self.tick,
            origin_x=origin_x,
            origin_y=origin_y,
            width=WINDOW_W,
            height=WINDOW_H,
            tiles=self._tiles_with_static_npcs(player, origin_x, origin_y, WINDOW_W, WINDOW_H, tiles),
        )

    def window_row_tiles(self, origin_x: int, origin_y: int, token: int | None = None) -> bytes:
        # Takes token, not map_id: a resync row must reflect the player's own
        # bridge state, so map_id alone cannot decide water vs road (plan 17.5).
        player = self.player_for(token)
        world = self.world_for(player.map_id)
        tiles = world.window_tiles(origin_x, origin_y, WINDOW_W, 1)
        return self._tiles_with_static_npcs(player, origin_x, origin_y, WINDOW_W, 1, tiles)

    def window_origin(self, token: int | None = None) -> tuple[int, int]:
        player = self.player_for(token)
        world = self.world_for(player.map_id)
        origin_x = player.x - (WINDOW_W // 2)
        origin_y = player.y - (WINDOW_H // 2)
        origin_x = max(0, min(origin_x, world.width - WINDOW_W))
        origin_y = max(0, min(origin_y, world.height - WINDOW_H))
        return origin_x, origin_y

    def needs_window(self, origin_x: int, origin_y: int, token: int | None = None) -> bool:
        player = self.player_for(token)
        if self.next_window_origin(origin_x, origin_y, token) == (origin_x, origin_y):
            return False
        local_x = player.x - origin_x
        local_y = player.y - origin_y
        return (
            local_x < WINDOW_EDGE_MARGIN
            or local_x >= WINDOW_W - WINDOW_EDGE_MARGIN
            or local_y < WINDOW_EDGE_MARGIN
            or local_y >= WINDOW_H - WINDOW_EDGE_MARGIN
        )

    def next_window_origin(self, origin_x: int, origin_y: int, token: int | None = None) -> tuple[int, int]:
        player = self.player_for(token)
        world = self.world_for(player.map_id)
        max_x = world.width - WINDOW_W
        max_y = world.height - WINDOW_H
        local_x = player.x - origin_x
        local_y = player.y - origin_y
        if local_x < WINDOW_EDGE_MARGIN and origin_x > 0:
            return origin_x - 1, origin_y
        if local_x >= WINDOW_W - WINDOW_EDGE_MARGIN and origin_x < max_x:
            return origin_x + 1, origin_y
        if local_y < WINDOW_EDGE_MARGIN and origin_y > 0:
            return origin_x, origin_y - 1
        if local_y >= WINDOW_H - WINDOW_EDGE_MARGIN and origin_y < max_y:
            return origin_x, origin_y + 1
        return origin_x, origin_y

    def next_window_origin_toward_player(
        self, origin_x: int, origin_y: int, token: int | None = None
    ) -> tuple[int, int]:
        target_x, target_y = self.window_origin(token)
        if origin_x < target_x:
            return origin_x + 1, origin_y
        if origin_x > target_x:
            return origin_x - 1, origin_y
        if origin_y < target_y:
            return origin_x, origin_y + 1
        if origin_y > target_y:
            return origin_x, origin_y - 1
        return origin_x, origin_y

    def window_origin_matches_player(self, origin_x: int, origin_y: int, token: int | None = None) -> bool:
        return (origin_x, origin_y) == self.window_origin(token)

    def edge_window(
        self,
        old_origin_x: int,
        old_origin_y: int,
        new_origin_x: int,
        new_origin_y: int,
        token: int | None = None,
    ) -> Window:
        player = self.player_for(token)
        world = self.world_for(player.map_id)
        if new_origin_x > old_origin_x:
            x = old_origin_x + WINDOW_W
            tiles = world.window_tiles(x, old_origin_y, 1, WINDOW_H)
            return Window(
                self.tick,
                x,
                old_origin_y,
                1,
                WINDOW_H,
                self._tiles_with_static_npcs(player, x, old_origin_y, 1, WINDOW_H, tiles),
            )
        if new_origin_x < old_origin_x:
            x = new_origin_x
            tiles = world.window_tiles(x, old_origin_y, 1, WINDOW_H)
            return Window(
                self.tick,
                x,
                old_origin_y,
                1,
                WINDOW_H,
                self._tiles_with_static_npcs(player, x, old_origin_y, 1, WINDOW_H, tiles),
            )
        if new_origin_y > old_origin_y:
            y = old_origin_y + WINDOW_H
            tiles = world.window_tiles(old_origin_x, y, WINDOW_W, 1)
            return Window(
                self.tick,
                old_origin_x,
                y,
                WINDOW_W,
                1,
                self._tiles_with_static_npcs(player, old_origin_x, y, WINDOW_W, 1, tiles),
            )
        if new_origin_y < old_origin_y:
            y = new_origin_y
            tiles = world.window_tiles(old_origin_x, y, WINDOW_W, 1)
            return Window(
                self.tick,
                old_origin_x,
                y,
                WINDOW_W,
                1,
                self._tiles_with_static_npcs(player, old_origin_x, y, WINDOW_W, 1, tiles),
            )
        return self.window_at(old_origin_x, old_origin_y, token)

    def _tiles_with_static_npcs(
        self,
        player: PlayerState,
        origin_x: int,
        origin_y: int,
        width: int,
        height: int,
        tiles: bytes,
    ) -> bytes:
        map_id = player.map_id
        patched: bytearray | None = None
        for subtype, entity_id in self.named_npc_ids.items():
            npc = self.entities.get(entity_id)
            if (
                npc is None
                or npc.map_id != map_id
                or not npc.is_live
                or not self.entity_visible_to_player(npc, player)
                or not (origin_x <= npc.x < origin_x + width)
                or not (origin_y <= npc.y < origin_y + height)
            ):
                continue
            if patched is None:
                patched = bytearray(tiles)
            tile = NPC_STATIC_TILES.get(subtype, FARMER_TILE)
            patched[(npc.y - origin_y) * width + (npc.x - origin_x)] = tile
        for marker, tile in (
            (GORVAK_MARKER, DEEP_PUMP_TILE),
            (DEEP_PUMP_CONTROLS_MARKER, PUMP_CONTROLS_TILE),
        ):
            if marker is None:
                continue
            prop_map_id, px, py = marker
            if (
                prop_map_id != map_id
                or not (origin_x <= px < origin_x + width)
                or not (origin_y <= py < origin_y + height)
            ):
                continue
            if patched is None:
                patched = bytearray(tiles)
            patched[(py - origin_y) * width + (px - origin_x)] = tile
        result = bytes(patched) if patched is not None else tiles
        return self._patch_story_terrain(player, origin_x, origin_y, width, height, result)

    def _patch_story_terrain(
        self,
        player: PlayerState,
        origin_x: int,
        origin_y: int,
        width: int,
        height: int,
        tiles: bytes,
    ) -> bytes:
        """Apply per-player story terrain overrides to a window (Phase 58).

        Until a player repairs the bridge, every OVERWORLD_BRIDGE_TILES cell in
        the requested rectangle is masked as blocking WATER. After repair the
        generated ROAD terrain shows through unchanged. This is the single choke
        point every terrain-emitting path funnels through, so the mask can never
        be bypassed, and the shared World.tiles array is never mutated -- the
        override is purely per-player and per-window.
        """
        if player.map_id != MAP_OVERWORLD or player.bridge_repaired:
            return tiles
        patched: bytearray | None = None
        for bx, by in OVERWORLD_BRIDGE_TILES:
            if not (origin_x <= bx < origin_x + width and origin_y <= by < origin_y + height):
                continue
            if patched is None:
                patched = bytearray(tiles)
            patched[(by - origin_y) * width + (bx - origin_x)] = WATER
        return bytes(patched) if patched is not None else tiles

    def _in_window(self, x: int, y: int, origin_x: int, origin_y: int) -> bool:
        return (
            origin_x <= x < origin_x + WINDOW_W
            and origin_y <= y < origin_y + WINDOW_H
        )

    # ------------------------------------------------------------------
    # Scripted encounters

    def create_scripted_encounter(
        self,
        owner: PlayerState,
        encounter_id: str,
        *,
        map_id: int | None = None,
        region: EncounterRegion | None = None,
        countdown_ticks: int = 0,
        pause_when_owner_absent: bool = True,
        fail_after_absent_ticks: int = 0,
        cleanup_on_success: bool = True,
        on_active: EncounterCallback | None = None,
        on_progress: EncounterCallback | None = None,
        on_success: EncounterCallback | None = None,
        on_failure: EncounterCallback | None = None,
    ) -> ScriptedEncounter:
        """Create one transient encounter instance for one player token."""
        key = (owner.token, encounter_id)
        if key in self.scripted_encounters:
            raise ValueError(f"encounter already exists for owner: {encounter_id}")
        encounter = ScriptedEncounter(
            encounter_id=encounter_id,
            owner_id=owner.token,
            map_id=owner.map_id if map_id is None else map_id,
            region=region,
            countdown_ticks=countdown_ticks,
            initial_countdown_ticks=countdown_ticks,
            pause_when_owner_absent=pause_when_owner_absent,
            fail_after_absent_ticks=fail_after_absent_ticks,
            cleanup_on_success=cleanup_on_success,
            on_active=on_active,
            on_progress=on_progress,
            on_success=on_success,
            on_failure=on_failure,
        )
        self.scripted_encounters[key] = encounter
        return encounter

    def bridge_repair_layout_ready(self) -> bool:
        return bool(WILHELM_ESCORT_PATH)

    def _encounter_region_from_layout(
        self, bounds: tuple[int, int, int, int, int] | None
    ) -> EncounterRegion | None:
        if bounds is None:
            return None
        map_id, left, top, right, bottom = bounds
        if map_id != MAP_OVERWORLD:
            raise ValueError("bridge defense region must be on the overworld")
        return EncounterRegion(left, top, right, bottom)

    def bridge_repair_waypoints(self) -> tuple[tuple[int, int], ...]:
        if WILHELM_POS is None:
            raise ValueError("Wilhelm start marker is missing")
        if WILHELM_BRIDGE_DESTINATION is None:
            raise ValueError("Wilhelm bridge destination marker is missing")
        start_map_id, dest_x, dest_y = WILHELM_BRIDGE_DESTINATION
        if start_map_id != MAP_OVERWORLD:
            raise ValueError("Wilhelm bridge destination must be on the overworld")
        if not WILHELM_ESCORT_PATH:
            raise ValueError("Wilhelm escort path is empty")
        path = tuple(WILHELM_ESCORT_PATH)
        if path[0] != WILHELM_POS:
            raise ValueError(f"Wilhelm escort path must start at {WILHELM_POS}, found {path[0]}")
        if path[-1] != (dest_x, dest_y):
            raise ValueError(
                f"Wilhelm escort path must end at {(dest_x, dest_y)}, found {path[-1]}"
            )
        for prev, cur in zip(path, path[1:]):
            if abs(prev[0] - cur[0]) + abs(prev[1] - cur[1]) != 1:
                raise ValueError("Wilhelm escort path must move one tile at a time")
        return path[1:]

    def bridge_return_waypoints(self) -> tuple[tuple[int, int], ...]:
        """The same validated path in reverse, from the bridge back to town."""
        full_path = (WILHELM_POS, *self.bridge_repair_waypoints())
        return tuple(reversed(full_path))[1:]

    def spawn_owned_named_npc(
        self,
        owner: PlayerState,
        subtype: int,
        map_id: int,
        x: int,
        y: int,
        *,
        personal: bool = True,
    ) -> Entity:
        flags = ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING | ENTITY_FLAG_NAMED
        if personal:
            flags |= ENTITY_FLAG_PERSONAL
        return self.spawn_entity(
            kind=ENTITY_NPC,
            subtype=subtype,
            map_id=map_id,
            x=x,
            y=y,
            hp=1,
            max_hp=1,
            state=1,
            flags=flags,
            owner_id=owner.token,
        )

    def create_bridge_repair_encounter(
        self,
        owner: PlayerState,
        *,
        encounter_id: str = "bridge_repair",
        countdown_ticks: int = 0,
        fail_after_absent_ticks: int = 0,
        move_interval_ticks: int = 1,
        escort_follow_distance: int = 0,
        cleanup_on_success: bool = False,
        on_active: EncounterCallback | None = None,
        on_progress: EncounterCallback | None = None,
        on_success: EncounterCallback | None = None,
        on_failure: EncounterCallback | None = None,
    ) -> ScriptedEncounter:
        # Success does not clean up Wilhelm's escort entity: the bridge-repair
        # on_success callback starts his reverse walk to town, and that entity
        # is only removed once he actually arrives (_bridge_return_complete).
        if owner.map_id != MAP_OVERWORLD:
            raise ValueError("bridge repair encounter must start on the overworld")
        if WILHELM_POS is None:
            raise ValueError("Wilhelm start marker is missing")
        path = self.bridge_repair_waypoints()
        region = self._encounter_region_from_layout(BRIDGE_DEFENSE_REGION)
        encounter = self.create_scripted_encounter(
            owner,
            encounter_id,
            map_id=MAP_OVERWORLD,
            region=region,
            countdown_ticks=countdown_ticks,
            fail_after_absent_ticks=fail_after_absent_ticks,
            cleanup_on_success=cleanup_on_success,
            on_active=on_active,
            on_progress=on_progress,
            on_success=on_success,
            on_failure=on_failure,
        )
        wilhelm = self.spawn_owned_named_npc(
            owner,
            NPC_WILHELM,
            MAP_OVERWORLD,
            WILHELM_POS[0],
            WILHELM_POS[1],
        )
        self.start_scripted_escort(
            encounter,
            wilhelm,
            path,
            move_interval_ticks=move_interval_ticks,
            escort_follow_distance=escort_follow_distance,
        )
        return encounter

    def get_scripted_encounter(
        self, owner_id: int, encounter_id: str
    ) -> ScriptedEncounter | None:
        return self.scripted_encounters.get((owner_id, encounter_id))

    def activate_scripted_encounter(self, encounter: ScriptedEncounter) -> None:
        encounter.phase = ENCOUNTER_ACTIVE
        encounter.owner_absent_ticks = 0
        encounter.failure_reason = ""
        owner = self.players.get(encounter.owner_id)
        if owner is not None and encounter.on_active is not None:
            encounter.on_active(self, owner, encounter)

    def start_scripted_escort(
        self,
        encounter: ScriptedEncounter,
        npc: Entity,
        waypoints: tuple[tuple[int, int], ...],
        *,
        move_interval_ticks: int = 1,
        escort_follow_distance: int = 0,
    ) -> None:
        if npc.owner_id != encounter.owner_id or npc.map_id != encounter.map_id:
            raise ValueError("escort NPC must belong to the encounter owner and map")
        encounter.spawned_entity_ids.add(npc.entity_id)
        encounter.escort_entity_id = npc.entity_id
        encounter.waypoints = tuple(waypoints)
        encounter.waypoint_index = 0
        encounter.move_interval_ticks = max(1, move_interval_ticks)
        encounter.move_cooldown_ticks = 0
        encounter.escort_follow_distance = max(0, escort_follow_distance)
        encounter.owner_absent_ticks = 0
        encounter.failure_reason = ""
        encounter.phase = ENCOUNTER_ESCORTING

    def reset_scripted_encounter(self, encounter: ScriptedEncounter) -> None:
        self._remove_encounter_entities(encounter)
        encounter.reset_for_retry()

    def fail_scripted_encounter(
        self, encounter: ScriptedEncounter, reason: str = "failed"
    ) -> None:
        if encounter.phase in (ENCOUNTER_FAILED, ENCOUNTER_CLEANUP):
            return
        encounter.phase = ENCOUNTER_FAILED
        encounter.failure_reason = reason
        owner = self.players.get(encounter.owner_id)
        if owner is not None and encounter.on_failure is not None:
            encounter.on_failure(self, owner, encounter)
            self._mark_player_state_dirty(owner)
        self._remove_encounter_entities(encounter)

    def succeed_scripted_encounter(self, encounter: ScriptedEncounter) -> None:
        if encounter.phase in (ENCOUNTER_SUCCEEDED, ENCOUNTER_CLEANUP):
            return
        encounter.phase = ENCOUNTER_SUCCEEDED
        encounter.failure_reason = ""
        owner = self.players.get(encounter.owner_id)
        if owner is not None:
            if encounter.on_success is not None:
                encounter.on_success(self, owner, encounter)
            self._mark_player_state_dirty(owner)
        if encounter.cleanup_on_success:
            self._remove_encounter_entities(encounter)

    def cleanup_scripted_encounter(self, encounter: ScriptedEncounter) -> None:
        self._remove_encounter_entities(encounter)
        encounter.phase = ENCOUNTER_CLEANUP
        self.scripted_encounters.pop(encounter.key, None)

    def cleanup_scripted_encounters_for_owner(self, owner_id: int) -> None:
        for encounter in tuple(self.scripted_encounters.values()):
            if encounter.owner_id == owner_id:
                self.cleanup_scripted_encounter(encounter)
        # Also cover personal triggers/items created just before an encounter
        # record, or entities left after an interrupted setup path.
        for entity in tuple(self.entities.values()):
            if entity.owner_id == owner_id and entity.kind != ENTITY_PLAYER:
                self.remove_entity(entity.entity_id)

    def spawn_encounter_enemy(
        self,
        encounter: ScriptedEncounter,
        enemy_kind: int,
        x: int,
        y: int,
        *,
        hp: int | None = None,
        level: int = 1,
    ) -> Entity:
        enemy = self.spawn_enemy(
            enemy_kind,
            x,
            y,
            map_id=encounter.map_id,
            home_x=0,
            home_y=0,
            owner_id=encounter.owner_id,
            level=level,
        )
        if hp is not None:
            enemy.hp = max(1, hp)
            enemy.max_hp = enemy.hp
        encounter.spawned_entity_ids.add(enemy.entity_id)
        return enemy

    def spawn_personal_item(
        self,
        owner: PlayerState,
        *,
        x: int,
        y: int,
        item_id: int,
        quantity: int = 1,
        map_id: int | None = None,
    ) -> Entity:
        return self.spawn_item(
            x,
            y,
            item_id,
            quantity,
            map_id=owner.map_id if map_id is None else map_id,
            owner_id=owner.token,
            personal=True,
        )

    def spawn_warden_key(
        self,
        owner: PlayerState,
        x: int,
        y: int,
        map_id: int | None = None,
    ) -> Entity:
        return self.spawn_personal_item(
            owner,
            x=x,
            y=y,
            item_id=ITEM_WARDEN_KEY,
            map_id=map_id,
        )

    def grant_personal_sample(
        self, player: PlayerState, item_id: int, required_count: int
    ) -> int:
        """Grant at most the remaining personal oil/rust objective amount."""
        if item_id not in (ITEM_OIL_SAMPLE, ITEM_RUST_SAMPLE):
            raise ValueError("not a story sample item")
        remaining = max(0, required_count - player.inventory.count_item(item_id))
        if remaining == 0 or not player.inventory.add_item(item_id, 1):
            return 0
        self._mark_player_state_dirty(player)
        return 1

    def _remove_encounter_entities(self, encounter: ScriptedEncounter) -> None:
        for entity_id in tuple(encounter.spawned_entity_ids):
            self.remove_entity(entity_id)
        encounter.spawned_entity_ids.clear()
        encounter.escort_entity_id = 0

    def _record_encounter_entity_death(
        self, entity: Entity, attacker: PlayerState
    ) -> None:
        encounter = self._encounter_for_entity(entity.entity_id)
        progress_owner = self.entity_progress_owner(entity, attacker)
        if (
            encounter is not None
            and progress_owner is not None
            and progress_owner.token == encounter.owner_id
        ):
            encounter.kill_count += 1
            encounter.last_attacker_token = attacker.token

    def _encounter_for_entity(self, entity_id: int) -> ScriptedEncounter | None:
        for encounter in self.scripted_encounters.values():
            if entity_id in encounter.spawned_entity_ids:
                return encounter
        return None

    def _update_scripted_encounters(self) -> None:
        for encounter in tuple(self.scripted_encounters.values()):
            if encounter.phase in (ENCOUNTER_FAILED, ENCOUNTER_SUCCEEDED):
                encounter.phase = ENCOUNTER_CLEANUP
                continue
            if encounter.phase == ENCOUNTER_CLEANUP:
                self.cleanup_scripted_encounter(encounter)
                continue
            if encounter.phase == ENCOUNTER_INACTIVE:
                continue

            owner = self.players.get(encounter.owner_id)
            present = encounter.owner_is_present(owner)
            if not present:
                encounter.owner_absent_ticks += 1
                if (
                    encounter.fail_after_absent_ticks > 0
                    and encounter.owner_absent_ticks
                    >= encounter.fail_after_absent_ticks
                ):
                    self.fail_scripted_encounter(encounter, "owner_absent")
                    continue
                if encounter.pause_when_owner_absent:
                    continue
            else:
                encounter.owner_absent_ticks = 0

            if encounter.phase in (ENCOUNTER_ESCORTING, ENCOUNTER_RETURNING):
                self._advance_scripted_escort(encounter)
                continue
            if encounter.phase != ENCOUNTER_ACTIVE:
                continue
            if encounter.boss_entity_id:
                self._advance_gorvak_encounter(encounter)
                continue
            if encounter.countdown_ticks > 0:
                encounter.countdown_ticks -= 1
                encounter.progress_ticks += 1
                if owner is not None and encounter.on_progress is not None:
                    encounter.on_progress(self, owner, encounter)
                if encounter.countdown_ticks == 0:
                    self.succeed_scripted_encounter(encounter)

    def _advance_scripted_escort(self, encounter: ScriptedEncounter) -> None:
        npc = self.entities.get(encounter.escort_entity_id)
        if npc is None or not npc.is_live:
            self.fail_scripted_encounter(encounter, "escort_missing")
            return
        owner = self.players.get(encounter.owner_id)
        if (
            owner is not None
            and encounter.escort_follow_distance > 0
            and abs(owner.x - npc.x) + abs(owner.y - npc.y)
            > encounter.escort_follow_distance
        ):
            return
        if encounter.waypoint_index >= len(encounter.waypoints):
            self._scripted_escort_arrived(encounter)
            return
        if encounter.move_cooldown_ticks > 0:
            encounter.move_cooldown_ticks -= 1
            return

        target_x, target_y = encounter.waypoints[encounter.waypoint_index]
        if (npc.x, npc.y) == (target_x, target_y):
            encounter.waypoint_index += 1
            if encounter.waypoint_index >= len(encounter.waypoints):
                self._scripted_escort_arrived(encounter)
            return

        step_x = (target_x > npc.x) - (target_x < npc.x)
        step_y = 0 if step_x else (target_y > npc.y) - (target_y < npc.y)
        next_x, next_y = npc.x + step_x, npc.y + step_y
        world = self.world_for(encounter.map_id)
        blocked = not world.player_can_enter(next_x, next_y)
        if owner is not None:
            own_player_entity_id = self.player_entities.get(owner.token)
            for entity in self.entities.values():
                if entity.entity_id in (npc.entity_id, own_player_entity_id):
                    continue
                if (
                    entity.map_id == encounter.map_id
                    and entity.x == next_x
                    and entity.y == next_y
                    and self.entity_blocks_player(entity, owner)
                ):
                    blocked = True
                    break
        if blocked:
            return
        npc.x, npc.y = next_x, next_y
        npc.zone_id = zone_for_tile(npc.map_id, npc.x, npc.y)
        encounter.move_cooldown_ticks = encounter.move_interval_ticks - 1
        if (npc.x, npc.y) == (target_x, target_y):
            encounter.waypoint_index += 1
            if encounter.waypoint_index >= len(encounter.waypoints):
                self._scripted_escort_arrived(encounter)

    def _scripted_escort_arrived(self, encounter: ScriptedEncounter) -> None:
        if encounter.is_return_leg:
            self._complete_scripted_return(encounter)
        elif encounter.countdown_ticks > 0:
            self.activate_scripted_encounter(encounter)
        else:
            self.succeed_scripted_encounter(encounter)

    def _complete_scripted_return(self, encounter: ScriptedEncounter) -> None:
        owner = self.players.get(encounter.owner_id)
        if owner is not None and encounter.on_return_complete is not None:
            encounter.on_return_complete(self, owner, encounter)
            self._mark_player_state_dirty(owner)
        self._remove_encounter_entities(encounter)
        encounter.phase = ENCOUNTER_CLEANUP
        self.scripted_encounters.pop(encounter.key, None)

    # ------------------------------------------------------------------
    # Entities

    def next_entity_id(self) -> int:
        for _ in range(1, 256):
            entity_id = self.next_entity_counter & 0xFF
            self.next_entity_counter = 1 if entity_id >= 255 else entity_id + 1
            if entity_id != 0 and entity_id not in self.entities:
                return entity_id
        raise RuntimeError("no free entity ids")

    def spawn_entity(
        self,
        *,
        kind: int,
        subtype: int,
        map_id: int,
        x: int,
        y: int,
        hp: int = 1,
        max_hp: int = 1,
        level: int = 1,
        state: int = 0,
        flags: int = ENTITY_FLAG_VISIBLE,
        owner_id: int = 0,
        zone_id: ZoneId | None = None,
    ) -> Entity:
        entity_id = self.next_entity_id()
        entity = Entity(
            entity_id=entity_id,
            kind=kind,
            subtype=subtype,
            map_id=map_id,
            x=x,
            y=y,
            hp=hp,
            max_hp=max_hp,
            level=level,
            state=state,
            flags=flags,
            owner_id=owner_id,
            zone_id=zone_id,
        )
        self.entities[entity_id] = entity
        if zone_id in self.active_zone_states:
            self.active_zone_states[zone_id].spawned_entity_ids.add(entity_id)
        return entity

    def spawn_enemy(
        self,
        enemy_kind: int,
        x: int,
        y: int,
        zone_id: ZoneId | None = None,
        map_id: int | None = None,
        home_x: int | None = None,
        home_y: int | None = None,
        owner_id: int = 0,
        level: int = 1,
    ) -> Entity:
        if map_id is None:
            map_id = zone_id.map_id if zone_id is not None else self.player.map_id
        if zone_id is None:
            zone_id = zone_for_tile(map_id, x, y)
        enemy_type = ENEMY_TYPES[enemy_kind]
        level = max(1, level)
        hp = enemy_type.hp_for_level(level)
        enemy = self.spawn_entity(
            kind=ENTITY_ENEMY,
            subtype=enemy_kind,
            map_id=map_id,
            x=x,
            y=y,
            hp=hp,
            max_hp=hp,
            level=level,
            state=1,
            flags=ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING | ENTITY_FLAG_HOSTILE | ENTITY_FLAG_TEMPORARY,
            owner_id=owner_id,
            zone_id=zone_id,
        )
        enemy.home_x = x if home_x is None else home_x
        enemy.home_y = y if home_y is None else home_y
        if enemy not in self.beavers:
            self.beavers.append(enemy)
        return enemy

    def spawn_beaver(self, x: int, y: int, zone_id: ZoneId | None = None, map_id: int | None = None) -> Entity:
        return self.spawn_enemy(ENEMY_BEAVER, x, y, zone_id=zone_id, map_id=map_id)

    def spawn_enemy_test_arena(
        self,
        *,
        map_id: int,
        origin_x: int,
        origin_y: int,
        levels: tuple[int, ...] = (1, 4),
    ) -> tuple[Entity, ...]:
        """Source-test fixture: every species at each requested level."""
        spawned: list[Entity] = []
        for row, enemy_kind in enumerate(sorted(ENEMY_TYPES)):
            for column, level in enumerate(levels):
                spawned.append(
                    self.spawn_enemy(
                        enemy_kind,
                        origin_x + column * 2,
                        origin_y + row * 2,
                        map_id=map_id,
                        level=level,
                    )
                )
        return tuple(spawned)

    def spawn_item(
        self,
        x: int,
        y: int,
        item_id: int,
        quantity: int = 1,
        map_id: int | None = None,
        *,
        owner_id: int = 0,
        personal: bool = False,
    ) -> Entity:
        if map_id is None:
            map_id = self.player.map_id
        flags = ENTITY_FLAG_VISIBLE | ENTITY_FLAG_TEMPORARY
        if personal:
            flags |= ENTITY_FLAG_PERSONAL
        item = self.spawn_entity(
            kind=ENTITY_ITEM,
            subtype=item_id,
            map_id=map_id,
            x=x,
            y=y,
            hp=max(1, quantity),
            max_hp=max(1, quantity),
            state=1,
            flags=flags,
            owner_id=owner_id,
            zone_id=zone_for_tile(map_id, x, y),
        )
        item.decay_ticks = ITEM_DESPAWN_TICKS
        return item

    def spawn_named_npc(self, subtype: int, map_id: int, x: int, y: int) -> int:
        """Spawn a static, blocking, named NPC and register it by subtype.

        One generic helper for the whole cast (plan 17.3); the per-subtype
        spawn position comes from the caller so the map redraw can relocate any
        NPC without touching this code.
        """
        npc = self.spawn_entity(
            kind=ENTITY_NPC,
            subtype=subtype,
            map_id=map_id,
            x=x,
            y=y,
            hp=1,
            max_hp=1,
            state=1,
            flags=ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING | ENTITY_FLAG_NAMED,
        )
        self.named_npc_ids[subtype] = npc.entity_id
        return npc.entity_id

    def spawn_farmer(self) -> int:
        return self.spawn_named_npc(NPC_FARMER, MAP_OVERWORLD, FARMER_X, FARMER_Y)

    def spawn_goblin_npc(self) -> int:
        return self.spawn_named_npc(NPC_GOBLIN, MAP_OVERWORLD, GOBLIN_NPC_X, GOBLIN_NPC_Y)

    def spawn_lost_charm_item(self) -> int:
        item = self.spawn_entity(
            kind=ENTITY_ITEM,
            subtype=ITEM_LOST_CHARM,
            map_id=MAP_STARTER_CAVE,
            x=LOST_CHARM_X,
            y=LOST_CHARM_Y,
            hp=1,
            max_hp=1,
            state=1,
            flags=ENTITY_FLAG_VISIBLE,
        )
        # Not a transient loot drop -- it must never expire on its own,
        # only hide-and-respawn on pickup (see _respawn_lost_charm).
        item.decay_ticks = 1 << 30
        return item.entity_id

    def fill_zone_spawns(self, zone_id: ZoneId) -> None:
        zone = self.zone_definition(zone_id)
        for rule in zone.spawn_table:
            if rule.max_count <= 0:
                continue
            count = sum(
                1
                for entity in self.entities_in_zone(zone_id)
                if entity.kind == rule.kind and entity.subtype == rule.subtype and entity.is_live
            )
            while count < rule.max_count:
                tile = self._find_spawn_tile(zone_id, rule)
                if tile is None:
                    break
                self._spawn_from_rule(zone_id, rule, tile[0], tile[1])
                count += 1

    def _spawn_from_rule(self, zone_id: ZoneId, rule: SpawnRule, x: int, y: int) -> Entity:
        level = max(rule.min_level, min(rule.max_level, self.zone_definition(zone_id).danger_level))
        if rule.kind == ENTITY_ENEMY and rule.subtype in ENEMY_TYPES:
            return self.spawn_enemy(
                rule.subtype,
                x,
                y,
                zone_id=zone_id,
                map_id=zone_id.map_id,
                level=level,
            )
        hp = 1
        entity = self.spawn_entity(
            kind=rule.kind,
            subtype=rule.subtype,
            map_id=zone_id.map_id,
            x=x,
            y=y,
            hp=hp,
            max_hp=hp,
            level=level,
            state=1,
            flags=ENTITY_FLAG_VISIBLE | ENTITY_FLAG_BLOCKING | ENTITY_FLAG_HOSTILE | ENTITY_FLAG_TEMPORARY,
            zone_id=zone_id,
        )
        return entity

    def _find_spawn_tile(self, zone_id: ZoneId, rule: SpawnRule) -> tuple[int, int] | None:
        world = self.world_for(zone_id.map_id)
        start_x = zone_id.zx * ZONE_SIZE
        start_y = zone_id.zy * ZONE_SIZE
        end_x = min(start_x + ZONE_SIZE, world.width)
        end_y = min(start_y + ZONE_SIZE, world.height)
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                if world.tile(x, y) in rule.allowed_terrain and self.entity_at(zone_id.map_id, x, y) is None:
                    return (x, y)
        return None

    def remove_entity(self, entity_id: int) -> None:
        entity = self.entities.pop(entity_id, None)
        if entity is None:
            return
        for encounter in self.scripted_encounters.values():
            encounter.spawned_entity_ids.discard(entity_id)
            if encounter.escort_entity_id == entity_id:
                encounter.escort_entity_id = 0
        self.beavers = [beaver for beaver in self.beavers if beaver.entity_id != entity_id]
        if entity.zone_id in self.active_zone_states:
            self.active_zone_states[entity.zone_id].spawned_entity_ids.discard(entity_id)
        for token, player_entity_id in tuple(self.player_entities.items()):
            if player_entity_id == entity_id:
                self.player_entities.pop(token, None)
                self.players.pop(token, None)

    def entities_in_window(
        self,
        map_id: int,
        origin_x: int,
        origin_y: int,
        width: int = WINDOW_W,
        height: int = WINDOW_H,
        token: int | None = None,
    ) -> list[Entity]:
        player = self.players.get(token) if token is not None else None
        return [
            entity
            for entity in self.entities.values()
            if entity.map_id == map_id
            and entity.is_live
            and (player is None or self.entity_visible_to_player(entity, player))
            and origin_x <= entity.x < origin_x + width
            and origin_y <= entity.y < origin_y + height
        ]

    def entities_in_zone(self, zone_id: ZoneId) -> list[Entity]:
        return [
            entity
            for entity in self.entities.values()
            if entity.map_id == zone_id.map_id and entity.zone_id == zone_id
        ]

    def entity_at(
        self,
        map_id: int,
        x: int,
        y: int,
        blocking_only: bool = True,
        player: PlayerState | None = None,
    ) -> Entity | None:
        for entity in self.entities.values():
            if entity.map_id != map_id or entity.x != x or entity.y != y or not entity.is_live:
                continue
            if player is not None and not self.entity_visible_to_player(entity, player):
                continue
            if blocking_only and (
                not entity.is_blocking
                if player is None
                else not self.entity_blocks_player(entity, player)
            ):
                continue
            return entity
        return None

    def hostile_entity_at(
        self, map_id: int, x: int, y: int, player: PlayerState | None = None
    ) -> Entity | None:
        for entity in self.entities.values():
            if entity.map_id == map_id and entity.x == x and entity.y == y and entity.is_live:
                if player is not None and not self.entity_visible_to_player(entity, player):
                    continue
                if (entity.flags & ENTITY_FLAG_HOSTILE) != 0:
                    return entity
        return None

    def item_at(
        self, map_id: int, x: int, y: int, player: PlayerState | None = None
    ) -> Entity | None:
        for entity in self.entities.values():
            if entity.map_id == map_id and entity.x == x and entity.y == y and entity.is_live:
                if entity.kind == ENTITY_ITEM and (
                    player is None or self.entity_collectible_by_player(entity, player)
                ):
                    return entity
        return None

    def player_at(self, map_id: int, x: int, y: int, exclude_token: int | None = None) -> PlayerState | None:
        for token, player in self.players.items():
            if token == exclude_token:
                continue
            if player.map_id == map_id and player.x == x and player.y == y:
                return player
        return None

    def _blocked_by_entity(self, player: PlayerState, x: int, y: int) -> bool:
        own_entity_id = self.player_entities.get(player.token)
        for entity in self.entities.values():
            if entity.entity_id == own_entity_id:
                continue
            if (
                entity.map_id == player.map_id
                and entity.x == x
                and entity.y == y
                and self.entity_blocks_player(entity, player)
            ):
                return True
        return False

    def legacy_beaver_snapshots_for_window(
        self, origin_x: int | None = None, origin_y: int | None = None, token: int | None = None
    ) -> tuple[BeaverSnapshot, ...]:
        player = self.player_for(token)
        snapshots = []
        dynamic_entities = list(self.beavers)
        dynamic_entities.extend(
            entity
            for entity in self.entities.values()
            if entity.kind == ENTITY_NPC
            and entity.subtype == NPC_WILHELM
            and entity.owner_id == player.token
        )
        for entity in dynamic_entities:
            if entity.map_id != player.map_id:
                continue
            if entity.hp <= 0:
                continue
            if not self.entity_visible_to_player(entity, player):
                continue
            if origin_x is not None and origin_y is not None and not self._in_window(entity.x, entity.y, origin_x, origin_y):
                continue
            snapshots.append(entity)
        snapshots.sort(
            key=lambda entity: (
                0 if entity.kind == ENTITY_NPC else 1,
                abs(entity.x - player.x) + abs(entity.y - player.y),
                entity.entity_id,
            )
        )
        return tuple(
            BeaverSnapshot(
                entity.x,
                entity.y,
                entity.hp,
                dynamic_snapshot_kind(entity, include_hit_pulse=True),
            )
            for entity in snapshots[:MAX_BEAVERS]
        )

    # ------------------------------------------------------------------
    # Beaver AI

    def _nearest_live_player(
        self,
        map_id: int,
        x: int,
        y: int,
        entity: Entity | None = None,
    ) -> PlayerState | None:
        if entity is not None and entity.owner_id != 0:
            owner = self.players.get(entity.owner_id)
            encounter = self._encounter_for_entity(entity.entity_id)
            if (
                owner is not None
                and owner.map_id == map_id
                and owner.health > 0
                and not self._transition_protected(owner)
                and (
                    encounter is None
                    or encounter.region is None
                    or encounter.region.contains(owner.x, owner.y)
                )
            ):
                return owner
            return None
        nearest: PlayerState | None = None
        nearest_distance = 0
        for player in self.players.values():
            if player.map_id != map_id or player.health <= 0 or self._transition_protected(player):
                continue
            distance = abs(player.x - x) + abs(player.y - y)
            if nearest is None or distance < nearest_distance or (
                distance == nearest_distance and player.token < nearest.token
            ):
                nearest = player
                nearest_distance = distance
        return nearest

    def _decay_dead_beavers(self) -> None:
        for beaver in tuple(self.beavers):
            if beaver.hp > 0:
                continue
            if beaver.respawn_ticks > 0:
                continue
            if beaver.decay_ticks > 0:
                beaver.decay_ticks -= 1
                continue
            self.remove_entity(beaver.entity_id)

    def _respawn_dead_enemies(self) -> None:
        for enemy in self.beavers:
            if enemy.hp > 0 or enemy.respawn_ticks <= 0:
                continue
            enemy.respawn_ticks -= 1
            if enemy.respawn_ticks > 0:
                continue
            if self.player_at(enemy.map_id, enemy.home_x, enemy.home_y) is not None:
                enemy.respawn_ticks = 1
                continue
            if self.entity_at(enemy.map_id, enemy.home_x, enemy.home_y) is not None:
                enemy.respawn_ticks = 1
                continue
            enemy.x = enemy.home_x
            enemy.y = enemy.home_y
            enemy.hp = enemy.max_hp
            enemy.state = 1
            enemy.decay_ticks = 0
            enemy.aggro_ticks = 0
            enemy.move_cooldown = 0
            enemy.attack_cooldown = 0
            enemy.chop_cooldown = 0
            enemy.zone_id = zone_for_tile(enemy.map_id, enemy.x, enemy.y)

    def _decay_expired_items(self) -> None:
        for entity in tuple(self.entities.values()):
            if entity.kind != ENTITY_ITEM:
                continue
            if entity.decay_ticks > 0:
                entity.decay_ticks -= 1
                continue
            self.remove_entity(entity.entity_id)

    def _respawn_lost_charm(self) -> None:
        item = self.entities.get(self.lost_charm_entity_id)
        if item is None or item.hp > 0 or item.respawn_ticks <= 0:
            return
        item.respawn_ticks -= 1
        if item.respawn_ticks > 0:
            return
        item.hp = 1
        item.max_hp = 1

    def _respawn_herbs(self) -> None:
        for world in self.worlds.values():
            world.tick_herb_cooldowns()
        if self.tile_update is not None:
            return
        for map_id in sorted(self.worlds):
            world = self.worlds[map_id]
            for index in world.ready_herb_respawn_indices():
                x, y = world.coords_for_index(index)
                if world.tile(x, y) != GRASS:
                    world.defer_herb_respawn(index)
                    continue
                if self.player_at(map_id, x, y) is not None:
                    world.defer_herb_respawn(index)
                    continue
                if self.entity_at(map_id, x, y, blocking_only=False) is not None:
                    world.defer_herb_respawn(index)
                    continue
                rx, ry = world.activate_herb_respawn(index)
                self.tile_update = (map_id, rx, ry, HERB)
                return

    def _respawn_trees(self) -> None:
        for world in self.worlds.values():
            world.tick_tree_cooldowns()
        if self.tile_update is not None:
            return
        for map_id in sorted(self.worlds):
            world = self.worlds[map_id]
            for index in world.ready_tree_respawn_indices():
                x, y = world.coords_for_index(index)
                if world.tile(x, y) != TREE_STUMP:
                    world.defer_tree_respawn(index)
                    continue
                if self.player_at(map_id, x, y) is not None:
                    world.defer_tree_respawn(index)
                    continue
                if self.entity_at(map_id, x, y, blocking_only=False) is not None:
                    world.defer_tree_respawn(index)
                    continue
                rx, ry = world.activate_tree_respawn(index)
                self.tile_update = (map_id, rx, ry, TREE_FULL)
                return

    def _move_enemies(self) -> None:
        for enemy in self.beavers:
            if enemy.hp == 0:
                continue
            enemy_type = ENEMY_TYPES.get(enemy.subtype)
            if enemy_type is None or not enemy_type.uses_generic_ai:
                continue
            if enemy.aggro_ticks > 0:
                enemy.aggro_ticks -= 1
            if not self.is_tile_in_active_zone(enemy.map_id, enemy.x, enemy.y):
                continue
            target = self._nearest_live_player(
                enemy.map_id, enemy.x, enemy.y, enemy
            )
            if target is None:
                continue
            if abs(enemy.x - target.x) + abs(enemy.y - target.y) <= 1:
                continue
            if self._try_chop(enemy):
                continue
            if enemy.move_cooldown > 0:
                enemy.move_cooldown -= 1
                continue
            enemy.move_cooldown = enemy_type.move_cooldown
            direction = self._enemy_direction(enemy, target)
            dx, dy = direction_delta(direction)
            nx = enemy.x + dx
            ny = enemy.y + dy
            if self.player_at(enemy.map_id, nx, ny) is not None:
                continue
            if enemy.owner_id == 0:
                if zone_for_tile(enemy.map_id, nx, ny) != zone_for_tile(
                    enemy.map_id, enemy.home_x, enemy.home_y
                ):
                    continue
            else:
                encounter = self._encounter_for_entity(enemy.entity_id)
                if (
                    encounter is not None
                    and encounter.region is not None
                    and not encounter.region.contains(nx, ny)
                ):
                    continue
            world = self.world_for(enemy.map_id)
            if world.enemy_can_enter(nx, ny) and not self._enemy_at(
                nx, ny, enemy.map_id, moving_entity=enemy
            ):
                enemy.x = nx
                enemy.y = ny

    def _move_beavers(self) -> None:
        """Compatibility alias retained for existing server tests/tools."""
        self._move_enemies()

    def _apply_enemy_contact_damage(self) -> None:
        for enemy in self.beavers:
            if enemy.hp <= 0:
                continue
            enemy_type = ENEMY_TYPES.get(enemy.subtype)
            if enemy_type is None or not enemy_type.uses_generic_ai:
                continue
            if enemy.attack_cooldown > 0:
                enemy.attack_cooldown -= 1
                continue
            target = self._nearest_live_player(
                enemy.map_id, enemy.x, enemy.y, enemy
            )
            if target is None:
                continue
            distance = abs(enemy.x - target.x) + abs(enemy.y - target.y)
            if distance <= 1:
                if self._transition_protected(target):
                    continue
                if target.health > 0:
                    target.health = max(
                        0, target.health - enemy_type.damage_for_level(enemy.level)
                    )
                enemy.attack_cooldown = enemy_type.attack_cooldown
                if enemy.subtype == ENEMY_GOBLIN:
                    self.queue_activity_message(target, "The goblin bites you.", MSG_GOBLIN_BITES)
                elif enemy.subtype == ENEMY_BEAVER:
                    self.queue_activity_message(target, "The beaver bites you.", MSG_BEAVER_BITES)
                else:
                    self.queue_activity_message(
                        target, f"The {enemy_type.name} attacks you."
                    )
                if target.health <= 0:
                    self.handle_player_death(target)

    def _apply_beaver_contact_damage(self) -> None:
        """Compatibility alias retained for existing server tests/tools."""
        self._apply_enemy_contact_damage()

    def _try_chop(self, beaver: Entity) -> bool:
        enemy_type = ENEMY_TYPES.get(beaver.subtype)
        if enemy_type is None or not enemy_type.can_chop:
            return False
        if self.tile_update is not None:
            return False
        if beaver.chop_cooldown > 0:
            beaver.chop_cooldown -= 1
            return False
        world = self.world_for(beaver.map_id)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx = beaver.x + dx
            ny = beaver.y + dy
            new_tile = world.chop_tree_if_present(nx, ny, TREE_RESPAWN_TICKS)
            if new_tile is not None:
                beaver.chop_cooldown = BEAVER_CHOP_COOLDOWN
                self.tile_update = (beaver.map_id, nx, ny, new_tile)
                return True
        return False

    def _enemy_direction(self, enemy: Entity, target: PlayerState) -> int:
        enemy_type = ENEMY_TYPES.get(enemy.subtype)
        if enemy_type is None:
            return 1 + (self.rng.next_byte() % 4)
        distance = abs(enemy.x - target.x) + abs(enemy.y - target.y)
        if (
            enemy.aggro_ticks > 0
            or distance <= effective_aggro_range(enemy, target, enemy_type)
        ):
            if abs(enemy.x - target.x) >= abs(enemy.y - target.y):
                return DIR_LEFT if target.x < enemy.x else DIR_RIGHT
            return DIR_UP if target.y < enemy.y else DIR_DOWN
        return 1 + (self.rng.next_byte() % 4)

    def _beaver_direction(self, beaver: Entity, target: PlayerState) -> int:
        """Compatibility alias retained for existing server tests/tools."""
        return self._enemy_direction(beaver, target)

    def _enemy_at(
        self,
        x: int,
        y: int,
        map_id: int | None = None,
        moving_entity: Entity | None = None,
    ) -> bool:
        if map_id is None:
            map_id = self.player.map_id
        for entity in self.entities.values():
            if (
                entity.kind != ENTITY_ENEMY
                or not entity.is_live
                or entity.map_id != map_id
                or entity.x != x
                or entity.y != y
                or entity is moving_entity
            ):
                continue
            if (
                moving_entity is not None
                and moving_entity.owner_id != 0
                and entity.owner_id not in (0, moving_entity.owner_id)
            ):
                continue
            return True
        return False


def visuals_for_map(map_id: int) -> tuple[int, int]:
    """(tileset_id, palette_id) a client needs to render the given map."""
    if map_id == MAP_STARTER_CAVE:
        return TILESET_CAVE, PALETTE_CAVE
    if map_id == MAP_PVP_REALM:
        return TILESET_PVP_REALM, PALETTE_PVP_REALM
    return TILESET_OVERWORLD, PALETTE_OVERWORLD


def map_forces_pvp(map_id: int) -> bool:
    return map_id == MAP_PVP_REALM


def direction_delta(direction: int) -> tuple[int, int]:
    if direction == DIR_UP:
        return (0, -1)
    if direction == DIR_DOWN:
        return (0, 1)
    if direction == DIR_LEFT:
        return (-1, 0)
    if direction == DIR_RIGHT:
        return (1, 0)
    return (0, 0)


def max_hp_for_level(level: int, class_id: int) -> int:
    if class_id == CLASS_HUNTER:
        return 10 + max(1, level) * 2
    return 8 + max(1, level) * 2


def xp_needed_for_next_level(level: int) -> int:
    # Cumulative XP threshold. The slightly widening 25-XP steps keep the
    # mandatory story route near level 6 at Gorvak without requiring grinding.
    return 20 + (max(1, level) - 1) * 25


def ranged_damage_for_level(level: int, class_id: int) -> int:
    if class_id == CLASS_HUNTER:
        return 2 + max(1, level)
    return 1 + max(1, level) // 2


def melee_damage_for_level(level: int, class_id: int) -> int:
    if class_id == CLASS_HUNTER:
        return 1 + max(1, level) // 2
    return 1 + max(1, level)


def hunter_range_for_level(level: int, class_id: int) -> int:
    if class_id == CLASS_HUNTER:
        return HUNTER_RANGE
    return 1


def aim_delta(aim: int) -> tuple[int, int]:
    if aim == 0:
        return (0, -1)
    if aim == 1:
        return (0, 1)
    if aim == 2:
        return (-1, 0)
    if aim == 3:
        return (1, 0)
    return (0, 0)


def client_aim_delta(aim: int) -> tuple[int, int]:
    if aim == CLIENT_AIM_UP:
        return (0, -1)
    if aim == CLIENT_AIM_DOWN:
        return (0, 1)
    if aim == CLIENT_AIM_LEFT:
        return (-1, 0)
    if aim == CLIENT_AIM_RIGHT:
        return (1, 0)
    if aim == CLIENT_AIM_UP_LEFT:
        return (-1, -1)
    if aim == CLIENT_AIM_UP_RIGHT:
        return (1, -1)
    if aim == CLIENT_AIM_DOWN_LEFT:
        return (-1, 1)
    if aim == CLIENT_AIM_DOWN_RIGHT:
        return (1, 1)
    return (0, 0)


def stick_delta(raw_stick: int) -> tuple[int, int]:
    raw = raw_stick & 0x0F
    if raw == 0x0A:
        return (-1, -1)
    if raw == 0x06:
        return (1, -1)
    if raw == 0x09:
        return (-1, 1)
    if raw == 0x05:
        return (1, 1)
    if raw == 0x0E:
        return direction_delta(DIR_UP)
    if raw == 0x0D:
        return direction_delta(DIR_DOWN)
    if raw == 0x0B:
        return direction_delta(DIR_LEFT)
    if raw == 0x07:
        return direction_delta(DIR_RIGHT)
    return (0, 0)
