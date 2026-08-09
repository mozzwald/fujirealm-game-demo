#!/usr/bin/env python3
"""Development-only test-player creation/modification tool for The Dam Below.

This is a repo-side CLI, NOT a server endpoint -- it is never reachable by a
live client and is intended purely for iteration during the story build. It
reads and writes the *same* ``sessions.json`` the login server uses, through the
same ``SessionStore``, and every edit is pushed through the live
``deserialize_player_state`` -> ``_normalize_restored_player`` ->
``serialize_player_state`` path so a test player exercises exactly the
persistence and normalization rules a real player does (plan section 17.18).

The whole point is to reach any story stage without replaying the 30-60 minute
chain: create a player, jump their ``story_stage``, grant items / set milestone
flags, teleport to an anchor, and log in normally.

Run from the repository root, e.g.:

    python3 tools/manage_test_player.py create --username GORVAKTEST \
        --level 5 --stage gorvak --warden-key --anchor cave
    python3 tools/manage_test_player.py show --token 123456
    python3 tools/manage_test_player.py set --token 123456 --pump-shutdown
    python3 tools/manage_test_player.py reset --token 123456
    python3 tools/manage_test_player.py stages      # list stage names
    python3 tools/manage_test_player.py anchors      # list teleport anchors
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow ``import server.*`` regardless of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.game import (  # noqa: E402
    DEEP_PUMP_CONTROLS_MARKER,
    FARMER_X,
    FARMER_Y,
    GOBLIN_NPC_X,
    GOBLIN_NPC_Y,
    GORVAK_MARKER,
    MAP_OVERWORLD,
    MAP_PVP_REALM,
    MAP_STARTER_CAVE,
    OVERWORLD_RESPAWN,
    PVP_REALM_RESPAWN,
    WARDEN_KEY_MARKER,
    GameState,
    PlayerState,
    deserialize_player_state,
    serialize_player_state,
)
from server.items import (  # noqa: E402
    ITEM_GOLD,
    ITEM_HERB,
    ITEM_LOST_CHARM,
    ITEM_OIL_SAMPLE,
    ITEM_POTION,
    ITEM_RUST_SAMPLE,
    ITEM_STICKS,
    ITEM_WARDEN_KEY,
)
from server.login_server import DEFAULT_STORE, SessionStore  # noqa: E402
from server.quests import (  # noqa: E402
    STORY_STAGE_BY_NAME,
    STORY_STAGE_NAMES,
    VALID_STORY_STAGES,
)
from server.world import STARTER_CAVE_ENTRY  # noqa: E402


# Named teleport anchors available today. Story-specific anchors (Grix, bridge,
# Gorvak home, Deep Pump controls, Lucian's lookout) resolve from generated map
# metadata in Phase 58; extend this table from world_layout_data there rather
# than hard-coding coordinates. (map_id, x, y)
ANCHORS: dict[str, tuple[int, int, int]] = {
    "town": (MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1]),
    "spawn": (MAP_OVERWORLD, OVERWORLD_RESPAWN[0], OVERWORLD_RESPAWN[1]),
    "daniel": (MAP_OVERWORLD, FARMER_X, FARMER_Y),
    "goblin": (MAP_OVERWORLD, GOBLIN_NPC_X, GOBLIN_NPC_Y),
    "grix": (MAP_OVERWORLD, GOBLIN_NPC_X, GOBLIN_NPC_Y),
    "key": (WARDEN_KEY_MARKER[0], WARDEN_KEY_MARKER[1], WARDEN_KEY_MARKER[2]),
    "cave": (MAP_STARTER_CAVE, STARTER_CAVE_ENTRY[0], STARTER_CAVE_ENTRY[1]),
    "pvp": (MAP_PVP_REALM, PVP_REALM_RESPAWN[0], PVP_REALM_RESPAWN[1]),
}
# Gorvak/pump anchors only exist once the cave CSV defines GOR/DPC markers.
if GORVAK_MARKER is not None:
    ANCHORS["gorvak"] = GORVAK_MARKER
if DEEP_PUMP_CONTROLS_MARKER is not None:
    ANCHORS["pump"] = DEEP_PUMP_CONTROLS_MARKER

# Item names accepted by --grant-item / --remove-item / --set-item in addition
# to raw numeric IDs.
ITEM_NAME_TO_ID: dict[str, int] = {
    "gold": ITEM_GOLD,
    "sticks": ITEM_STICKS,
    "herb": ITEM_HERB,
    "potion": ITEM_POTION,
    "charm": ITEM_LOST_CHARM,
    "warden_key": ITEM_WARDEN_KEY,
    "oil": ITEM_OIL_SAMPLE,
    "oil_sample": ITEM_OIL_SAMPLE,
    "rust": ITEM_RUST_SAMPLE,
    "rust_sample": ITEM_RUST_SAMPLE,
}

# Milestone flags: CLI name -> PlayerState attribute.
MILESTONE_FLAGS: dict[str, str] = {
    "bridge-staged": "bridge_materials_staged",
    "bridge-repaired": "bridge_repaired",
    "grix-callout": "grix_callout_seen",
    "warden-key": "warden_key_collected",
    "gorvak-defeated": "gorvak_defeated",
    "pump-shutdown": "deep_pump_shutdown",
    "pvp-unlocked": "pvp_unlocked",
}


def _resolve_stage(value: str) -> int:
    """Accept a stage name (``gorvak``) or an integer stage number."""
    text = value.strip().lower()
    if text in STORY_STAGE_BY_NAME:
        return STORY_STAGE_BY_NAME[text]
    try:
        stage = int(text)
    except ValueError:
        raise SystemExit(f"unknown story stage: {value!r} (see `stages`)")
    if stage not in VALID_STORY_STAGES:
        raise SystemExit(f"story stage out of range: {stage} (see `stages`)")
    return stage


def _resolve_item(token: str) -> int:
    text = token.strip().lower()
    if text in ITEM_NAME_TO_ID:
        return ITEM_NAME_TO_ID[text]
    try:
        return int(text)
    except ValueError:
        raise SystemExit(f"unknown item: {token!r}")


def _parse_item_spec(spec: str) -> tuple[int, int]:
    """Parse ``ID[:QTY]`` / ``NAME[:QTY]`` -> (item_id, quantity)."""
    if ":" in spec:
        name, _, qty_text = spec.partition(":")
        qty = int(qty_text)
    else:
        name, qty = spec, 1
    return _resolve_item(name), qty


def _add_field_arguments(parser: argparse.ArgumentParser) -> None:
    """Shared mutation options for both ``create`` and ``set``."""
    parser.add_argument("--username", help="set display username")
    parser.add_argument("--level", type=int, help="set player level")
    parser.add_argument("--xp", type=int, help="set current xp (xp_next re-normalized)")
    parser.add_argument("--gold", type=int, help="set gold")
    parser.add_argument("--stage", help="story stage name or number (see `stages`)")
    parser.add_argument("--step", type=int, help="per-stage objective sub-step")
    parser.add_argument("--active-quest", type=int, help="active_quest_id (advanced)")
    parser.add_argument("--quest-state", type=int, help="quest_state (advanced)")
    parser.add_argument("--quest-progress", type=int, help="quest_progress (advanced)")
    parser.add_argument("--quest-target", type=int, help="quest_target (advanced)")

    # Milestone flags: paired --flag / --no-flag.
    for name in MILESTONE_FLAGS:
        parser.add_argument(f"--{name}", dest=f"flag_{name}", action="store_true", default=None)
        parser.add_argument(f"--no-{name}", dest=f"flag_{name}", action="store_false", default=None)

    # Items.
    parser.add_argument(
        "--grant-item", action="append", default=[], metavar="ID[:QTY]",
        help="grant item (name or id), repeatable",
    )
    parser.add_argument(
        "--remove-item", action="append", default=[], metavar="ID[:QTY]",
        help="remove item (name or id), repeatable",
    )
    parser.add_argument(
        "--set-item", action="append", default=[], metavar="ID:QTY",
        help="set item stack to an exact quantity (0 clears), repeatable",
    )

    # Teleport.
    parser.add_argument("--anchor", help=f"teleport to a named anchor: {', '.join(ANCHORS)}")
    parser.add_argument("--map", type=int, dest="map_id", help="explicit map id")
    parser.add_argument("--x", type=int, help="explicit x")
    parser.add_argument("--y", type=int, help="explicit y")


def _apply_mutations(player: PlayerState, args: argparse.Namespace) -> None:
    if args.username is not None:
        player.username = args.username
    if args.level is not None:
        player.level = args.level
    if args.xp is not None:
        player.xp = args.xp
    if args.gold is not None:
        player.gold = args.gold
    if args.stage is not None:
        player.story_stage = _resolve_stage(args.stage)
    if args.step is not None:
        player.story_step = args.step
    if args.active_quest is not None:
        player.active_quest_id = args.active_quest
    if args.quest_state is not None:
        player.quest_state = args.quest_state
    if args.quest_progress is not None:
        player.quest_progress = args.quest_progress
    if args.quest_target is not None:
        player.quest_target = args.quest_target

    for name, attr in MILESTONE_FLAGS.items():
        value = getattr(args, f"flag_{name}")
        if value is not None:
            setattr(player, attr, value)
    # --warden-key is both a milestone and the tangible key item.
    warden = getattr(args, "flag_warden-key")
    if warden is True:
        player.inventory.add_item(ITEM_LOST_CHARM, 1)
    elif warden is False:
        player.inventory.remove_item(ITEM_LOST_CHARM, player.inventory.count_item(ITEM_LOST_CHARM) or 1)

    for spec in args.grant_item:
        item_id, qty = _parse_item_spec(spec)
        player.inventory.add_item(item_id, qty)
    for spec in args.remove_item:
        item_id, qty = _parse_item_spec(spec)
        player.inventory.remove_item(item_id, qty)
    for spec in args.set_item:
        item_id, qty = _parse_item_spec(spec)
        have = player.inventory.count_item(item_id)
        if have:
            player.inventory.remove_item(item_id, have)
        if qty > 0:
            player.inventory.add_item(item_id, qty)

    if args.anchor is not None:
        key = args.anchor.strip().lower()
        if key not in ANCHORS:
            raise SystemExit(f"unknown anchor: {args.anchor!r} (see `anchors`)")
        player.map_id, player.x, player.y = ANCHORS[key]
        player.respawn_map_id, player.respawn_x, player.respawn_y = ANCHORS[key]
    if args.map_id is not None:
        player.map_id = args.map_id
    if args.x is not None:
        player.x = args.x
    if args.y is not None:
        player.y = args.y


def _normalize_and_persist(store: SessionStore, token: str, player: PlayerState) -> dict:
    """Run the edited player through the live restore path, then save it.

    This mirrors ``GameState._restore_player_from_record`` exactly, so anything
    that would break at real login breaks here instead.
    """
    game = GameState()
    game._normalize_restored_player(player)
    payload = serialize_player_state(player)
    # Validation: a real login re-deserializes; confirm it loads with no error.
    deserialize_player_state(int(token), player.username, payload)
    store.save_player_state(token, player.username, payload)
    return payload


def _load_player(store: SessionStore, token: str) -> PlayerState:
    record = store.get_record(token)
    if record is None:
        raise SystemExit(f"no such player token: {token}")
    payload = store.load_player_state(token) or {}
    username = str(record.get("username", "")) or f"Player{token[-4:]}"
    return deserialize_player_state(int(token), username, payload)


def _describe(token: str, player: PlayerState) -> str:
    inv = ", ".join(f"{i}x{q}" for i, q in player.inventory.as_tuple()) or "(empty)"
    stage_name = STORY_STAGE_NAMES.get(player.story_stage, str(player.story_stage))
    flags = [n for n in MILESTONE_FLAGS.values() if getattr(player, n)]
    return (
        f"token={token} user={player.username!r} class={player.class_id} "
        f"lvl={player.level} xp={player.xp}/{player.xp_next} gold={player.gold}\n"
        f"  map={player.map_id} pos=({player.x},{player.y}) "
        f"respawn=({player.respawn_map_id}:{player.respawn_x},{player.respawn_y})\n"
        f"  story_stage={player.story_stage}({stage_name}) story_step={player.story_step}\n"
        f"  milestones: {', '.join(flags) if flags else '(none)'}\n"
        f"  active_quest={player.active_quest_id} state={player.quest_state} "
        f"progress={player.quest_progress}/{player.quest_target} "
        f"pvp_enabled={player.pvp_enabled} pvp_kills={player.pvp_kills}\n"
        f"  inventory: {inv}"
    )


# --- subcommands ------------------------------------------------------------

def cmd_create(store: SessionStore, args: argparse.Namespace) -> int:
    username = args.username
    if not username:
        raise SystemExit("create requires --username")
    if args.token:
        token = str(args.token)
        if store.get_record(token) is not None:
            raise SystemExit(f"token already exists: {token}")
        store.save_player_state(token, username, serialize_player_state(PlayerState(int(token), username)))
    else:
        token = store.register(username)
        if token is None:
            raise SystemExit(f"username already taken: {username!r}")
    player = _load_player(store, token)
    _apply_mutations(player, args)
    _normalize_and_persist(store, token, player)
    print(f"created player token={token}")
    print(_describe(token, _load_player(store, token)))
    return 0


def cmd_set(store: SessionStore, args: argparse.Namespace) -> int:
    token = str(args.token)
    player = _load_player(store, token)
    _apply_mutations(player, args)
    _normalize_and_persist(store, token, player)
    print(_describe(token, _load_player(store, token)))
    return 0


def cmd_reset(store: SessionStore, args: argparse.Namespace) -> int:
    token = str(args.token)
    record = store.get_record(token)
    if record is None:
        raise SystemExit(f"no such player token: {token}")
    # Reset is keyed by token, so username/token always survive; --keep-identity
    # documents that intent (an explicit rename uses `set --username`).
    username = str(record.get("username", ""))
    fresh = PlayerState(int(token), username)
    _normalize_and_persist(store, token, fresh)
    print(f"reset player token={token} to a clean new-game state")
    print(_describe(token, _load_player(store, token)))
    return 0


def cmd_delete(store: SessionStore, args: argparse.Namespace) -> int:
    token = str(args.token)
    if store.get_record(token) is None:
        raise SystemExit(f"no such player token: {token}")
    store.load()
    store.sessions.pop(token, None)
    store.save()
    print(f"deleted player token={token}")
    return 0


def cmd_show(store: SessionStore, args: argparse.Namespace) -> int:
    if args.token:
        token = str(args.token)
        print(_describe(token, _load_player(store, token)))
        return 0
    store.load()
    if not store.sessions:
        print("(no players)")
        return 0
    for token, record in sorted(store.sessions.items()):
        ps = record.get("player_state")
        if isinstance(ps, dict):
            player = deserialize_player_state(int(token), str(record.get("username", "")), ps)
            stage = STORY_STAGE_NAMES.get(player.story_stage, player.story_stage)
            print(f"{token:>10}  {player.username:<16} lvl={player.level:<3} stage={stage}")
        else:
            print(f"{token:>10}  {record.get('username',''):<16} (no player_state)")
    return 0


def cmd_stages(store: SessionStore, args: argparse.Namespace) -> int:
    for stage in sorted(VALID_STORY_STAGES):
        print(f"{stage:>3}  {STORY_STAGE_NAMES[stage]}")
    return 0


def cmd_anchors(store: SessionStore, args: argparse.Namespace) -> int:
    for name, (map_id, x, y) in ANCHORS.items():
        print(f"{name:<8} map={map_id} ({x},{y})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="path to sessions.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="create a test player")
    p_create.add_argument("--token", help="explicit token (else auto-generated)")
    _add_field_arguments(p_create)
    p_create.set_defaults(func=cmd_create)

    p_set = sub.add_parser("set", help="modify an existing test player")
    p_set.add_argument("--token", required=True)
    _add_field_arguments(p_set)
    p_set.set_defaults(func=cmd_set)

    p_reset = sub.add_parser("reset", help="reset a player to clean new-game state")
    p_reset.add_argument("--token", required=True)
    p_reset.add_argument("--keep-identity", action="store_true", help="(default) keep username/token")
    p_reset.set_defaults(func=cmd_reset)

    p_delete = sub.add_parser("delete", help="delete a test player record")
    p_delete.add_argument("--token", required=True)
    p_delete.set_defaults(func=cmd_delete)

    p_show = sub.add_parser("show", help="show one player or list all")
    p_show.add_argument("--token", help="token to detail (omit to list all)")
    p_show.set_defaults(func=cmd_show)

    p_stages = sub.add_parser("stages", help="list story stage names/numbers")
    p_stages.set_defaults(func=cmd_stages)

    p_anchors = sub.add_parser("anchors", help="list teleport anchors")
    p_anchors.set_defaults(func=cmd_anchors)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = SessionStore(args.store)
    return args.func(store, args)


if __name__ == "__main__":
    raise SystemExit(main())
