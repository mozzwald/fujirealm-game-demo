"""Hardcoded first quest definitions for the RPG demo."""

QUEST_NONE = 0
QUEST_ROAD_TROUBLE = 1
QUEST_LOST_CHARM = 2
QUEST_REPAIR_BRIDGE = 3
QUEST_BLACKWATER_BITE = 4
QUEST_LIVING_MUD = 5

QUEST_STATE_NOT_STARTED = 0
QUEST_STATE_ACTIVE = 1
QUEST_STATE_READY_TO_TURN_IN = 2
QUEST_STATE_COMPLETE = 3

# --- The Dam Below: persistent main-story progression -----------------------
#
# ``story_stage`` is the durable milestone anchor for the whole campaign; it
# advances one step per main quest and never regresses in normal play. It is
# deliberately independent of ``active_quest_id`` so a permanent milestone is
# never inferred from the current scalar quest (see plan section 17.1).
# ``story_step`` is the per-stage objective sub-index (e.g. Gorvak's stage walks
# through "find him" -> "defeat him" -> "use the key"). Only stable checkpoints
# are persisted; transient encounter state (summon HP, escort path index, defense
# timer) is never saved and resets on reload.
STORY_STAGE_NONE = 0             # brand-new player, story not begun
STORY_STAGE_WELCOME = 1          # Q1 Welcome to Willowcross: speak to Daniel
STORY_STAGE_ROAD_TROUBLE = 2     # Q2 Road Trouble: beavers + sticks -> Wilhelm
STORY_STAGE_BRIDGE = 3           # Q2.5 Repair the Bridge: escort/defend Wilhelm
STORY_STAGE_BEYOND_ROAD = 4      # Q3 Beyond the Washed Road: reach Lucian
STORY_STAGE_BLACKWATER = 5       # Q4 Blackwater Bite: clear marsh snakes
STORY_STAGE_LIVING_MUD = 6       # Q5 Living Mud: oil/rust samples -> Nerissa
STORY_STAGE_GOBLIN_WARNED = 7    # Q6 The Goblin Who Warned Us: find Grix
STORY_STAGE_WARDEN_KEY = 8       # Q7 The Warden Key: recover key -> Grix
STORY_STAGE_GORVAK = 9           # Q8 Pumpmaster Gorvak: floodworks / boss / pump
STORY_STAGE_RETURN_NERISSA = 10  # Q9 Willowcross Saved: report the shutdown
STORY_STAGE_COMPLETE = 11        # demo complete, PvP arena unlocked

STORY_STAGE_FIRST = STORY_STAGE_WELCOME
STORY_STAGE_LAST = STORY_STAGE_COMPLETE
VALID_STORY_STAGES = set(range(STORY_STAGE_NONE, STORY_STAGE_COMPLETE + 1))

# Human-readable stage labels for tooling / debug output (never sent to the
# client -- the HUD objective line stays server-owned prose elsewhere).
STORY_STAGE_NAMES = {
    STORY_STAGE_NONE: "none",
    STORY_STAGE_WELCOME: "welcome",
    STORY_STAGE_ROAD_TROUBLE: "road_trouble",
    STORY_STAGE_BRIDGE: "bridge",
    STORY_STAGE_BEYOND_ROAD: "beyond_road",
    STORY_STAGE_BLACKWATER: "blackwater",
    STORY_STAGE_LIVING_MUD: "living_mud",
    STORY_STAGE_GOBLIN_WARNED: "goblin_warned",
    STORY_STAGE_WARDEN_KEY: "warden_key",
    STORY_STAGE_GORVAK: "gorvak",
    STORY_STAGE_RETURN_NERISSA: "return_nerissa",
    STORY_STAGE_COMPLETE: "complete",
}
STORY_STAGE_BY_NAME = {name: stage for stage, name in STORY_STAGE_NAMES.items()}

ROAD_TROUBLE_TARGET = 6
ROAD_TROUBLE_REWARD_XP = 20
ROAD_TROUBLE_REWARD_GOLD = 7

LOST_CHARM_TARGET = 1
LOST_CHARM_REWARD_GOLD = 25

# Repair the Bridge is not kill-count based: the escort/defense encounter
# itself is the objective, so progress is just "not done" (0) vs "done" (1),
# same pattern as Lost Charm's single-item turn-in.
REPAIR_BRIDGE_TARGET = 4
REPAIR_BRIDGE_REWARD_XP = 15
REPAIR_BRIDGE_REWARD_GOLD = 10

BLACKWATER_TARGET = 5
BLACKWATER_REWARD_XP = 10
BLACKWATER_REWARD_GOLD = 8

# Living Mud tracks two independent sample counts, but the single-quest
# progress/target scalar can only show a combined count (e.g. "Living Mud
# 3/4"); the HUD reminder while active spells out the oil/rust split
# separately (see _grant_living_mud_sample in game.py).
LIVING_MUD_OIL_TARGET = 2
LIVING_MUD_RUST_TARGET = 2
LIVING_MUD_TARGET = LIVING_MUD_OIL_TARGET + LIVING_MUD_RUST_TARGET
LIVING_MUD_REWARD_XP = 15
LIVING_MUD_REWARD_GOLD = 15

# Willowcross Saved (Quest 9): a pure story milestone like Beyond the Washed
# Road, not tracked as its own active_quest_id -- gated on story_stage and
# the durable pvp_unlocked flag instead.
WILLOWCROSS_SAVED_REWARD_XP = 20
WILLOWCROSS_SAVED_REWARD_GOLD = 25

# Phase 60 initial no-grind balance. Values are cumulative route contributions,
# not final tuning; Phase 69 revisits them after the complete maps/encounters
# exist. Expected levels use xp_needed_for_next_level(): 20,45,70,95,120...
INITIAL_PROGRESSION_ROUTE = (
    ("Welcome", 5, 1),
    ("Road Trouble enemies", 15, 2),
    ("Road Trouble reward", 10, 2),
    ("Bridge defense", 15, 3),
    ("Beyond the Washed Road", 5, 3),
    ("Blackwater Bite", 30, 4),
    ("Living Mud", 37, 5),
    ("Warden Key", 10, 6),
)

MSG_NONE = 0
MSG_QUEST_STARTED = 1
MSG_QUEST_PROGRESS = 2
MSG_QUEST_READY = 3
MSG_QUEST_COMPLETE = 4
MSG_BEAVER_KILLED = 5
MSG_GOT_STICKS = 6
MSG_BEAVER_BITES = 7
MSG_QUEST_REMINDER = 8
MSG_FARMER_THANKS = 9
MSG_LEVEL_UP = 10
MSG_PLAYER_DIED = 11
MSG_RESPAWN_GRAVE = 12
MSG_RESPAWN_CAVE = 13
MSG_GOT_GOLD = 14
MSG_GOBLIN_KILLED = 15
MSG_GOBLIN_BITES = 16
MSG_QUEST_OFFER = 17
MSG_WELCOME_NEW = 18
MSG_WELCOME_BACK = 19
MSG_GOBLIN_THANKS = 20
MSG_PVP_HIT = 21
MSG_PLAYER_ENTERED = 22
MSG_PLAYER_LEFT = 23
MSG_PVP_KILL = 24
MSG_PVP_ARENA_LOCKED = 25

QUEST_NAMES = {
    QUEST_ROAD_TROUBLE: "Save My Orchard",
    QUEST_LOST_CHARM: "Lost Charm",
    QUEST_REPAIR_BRIDGE: "Repair the Bridge",
    QUEST_BLACKWATER_BITE: "Blackwater Bite",
    QUEST_LIVING_MUD: "Living Mud",
}


def quest_status_text(quest_id: int, state: int, progress: int, target: int) -> str:
    """Build the HUD quest-status line the Atari client displays verbatim.

    Adding a new quest only needs an entry in QUEST_NAMES here -- the client
    has no quest-specific text of its own to keep in sync.
    """
    if quest_id == QUEST_NONE or state == QUEST_STATE_NOT_STARTED:
        return ""
    name = QUEST_NAMES.get(quest_id, "")
    if state == QUEST_STATE_COMPLETE:
        return f"{name} done"
    return f"{name} {progress}/{target}"
