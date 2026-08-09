#!/usr/bin/env python3
"""Wipe saves written by an older server schema back to a clean level-1 game.

When the server diverges far enough from what players' stored progress was
built against (quest ids, story stages, map coordinates, PvP flags), migrating
that progress is rarely worth it. This tool resets every stale record while keeping the two
things that matter for identity -- the **token** (so a client's stored token
still logs in) and the **username** (so the name is not released back into the
taken-name pool) -- plus **gold** and **pvp_kills** as a carry-over.

Staleness is decided by ``server/schema.py``'s ``PLAYER_SCHEMA_VERSION``, which
``serialize_player_state`` stamps onto every save. Records already stamped with
the current version were written by the new server and are left untouched, so:

* the run is idempotent -- a second run does nothing;
* it is safe to run *after* the new server is live, and anyone who played in the
  meantime keeps what they earned;
* bumping ``PLAYER_SCHEMA_VERSION`` later makes this tool wipe again.

Every reset goes through the live ``_normalize_restored_player`` ->
``serialize_player_state`` -> ``deserialize_player_state`` path, the same as
``manage_test_player.py``, so anything that would break at real login breaks
here instead.

Dry run by default. Usage from the repository root:

    python3 tools/reset_old_sessions.py --store /path/to/sessions.json
    python3 tools/reset_old_sessions.py --store /path/to/sessions.json --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# Allow ``import server.*`` regardless of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.game import (  # noqa: E402
    MAP_OVERWORLD,
    OVERWORLD_START,
    GameState,
    PlayerState,
    _record_int,
    deserialize_player_state,
    player_state_is_current,
    serialize_player_state,
)
from server.login_server import DEFAULT_STORE, SessionStore  # noqa: E402
from server.schema import PLAYER_SCHEMA_VERSION  # noqa: E402


# Fields that survive a reset, with the same ceilings deserialize_player_state
# applies, so a garbage value degrades to 0 instead of crashing the run.
CARRIED_FIELDS = ("gold", "pvp_kills")
CARRY_MAX = 9999

SKIP_NO_STATE = "skip: no player_state"
SKIP_CURRENT = "skip: already current"


def make_fresh_state(token: str, username: str, old: dict[str, object], game: GameState) -> dict[str, object]:
    """Build a clean level-1 player_state carrying gold/pvp_kills from ``old``."""
    fresh = PlayerState(int(token), username)
    # A brand-new player starts at the map-generated overworld start marker.
    # PlayerState's own default is OVERWORLD_RESPAWN, an arbitrary placeholder;
    # GameState.add_player overrides it the same way for a real new login.
    fresh.map_id = MAP_OVERWORLD
    fresh.x, fresh.y = OVERWORLD_START
    for name in CARRIED_FIELDS:
        setattr(fresh, name, max(0, min(CARRY_MAX, _record_int(old, name, 0))))
    game._normalize_restored_player(fresh)
    payload = serialize_player_state(fresh)
    # Validation: a real login re-deserializes; confirm it loads with no error.
    deserialize_player_state(int(token), username, payload)
    # Consumed by hybrid_server._process_bootstrap to greet this player as new
    # rather than "Welcome back." Dropped again by the first save after login,
    # since serialize_player_state never emits it.
    payload["fresh_start"] = True
    return payload


def run(store: SessionStore, apply: bool, backup: bool) -> int:
    store.load()
    if not store.sessions:
        print("(no records)")
        return 0

    game = GameState()
    plan: list[tuple[str, str, str]] = []  # token, username, action
    reset_payloads: dict[str, tuple[str, dict[str, object]]] = {}

    for token, record in sorted(store.sessions.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        username = str(record.get("username", ""))
        old = record.get("player_state")
        if not isinstance(old, dict):
            plan.append((token, username, SKIP_NO_STATE))
            continue
        if player_state_is_current(old):
            plan.append((token, username, SKIP_CURRENT))
            continue
        payload = make_fresh_state(token, username, old, game)
        reset_payloads[token] = (username, payload)
        plan.append(
            (
                token,
                username,
                f"reset: lvl {_record_int(old, 'level', 1)}->1  "
                f"gold {payload['gold']}  kills {payload['pvp_kills']}",
            )
        )

    for token, username, action in plan:
        print(f"{token:>12}  {username:<16}  {action}")

    resets = len(reset_payloads)
    skipped_current = sum(1 for _, _, a in plan if a == SKIP_CURRENT)
    skipped_empty = sum(1 for _, _, a in plan if a == SKIP_NO_STATE)
    print(
        f"\n{len(plan)} records: {resets} to reset, "
        f"{skipped_current} already at schema v{PLAYER_SCHEMA_VERSION}, "
        f"{skipped_empty} without a player_state"
    )

    if not apply:
        print("dry run -- nothing written (pass --apply to write)")
        return 0
    if not resets:
        print("nothing to do")
        return 0

    if backup and store.path.exists():
        backup_path = store.path.with_name(f"{store.path.name}.bak-{int(time.time())}")
        shutil.copy2(store.path, backup_path)
        print(f"backup written: {backup_path}")

    for token, (username, payload) in reset_payloads.items():
        store.save_player_state(token, username, payload)
    print(f"reset {resets} records in {store.path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="path to sessions.json")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        help="skip the sessions.json.bak-<ts> copy taken before writing",
    )
    parser.set_defaults(backup=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.store)
    if not path.exists():
        print(f"no such store: {path}", file=sys.stderr)
        return 2
    try:
        store = SessionStore(path)
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
        print(f"unreadable store {path}: {exc}", file=sys.stderr)
        return 2
    return run(store, apply=args.apply, backup=args.backup)


if __name__ == "__main__":
    raise SystemExit(main())
