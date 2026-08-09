"""The Dam Below: generic NPC interaction dispatch and story dialogue scenes.

Phase 57 replaces the two hard-coded farmer/goblin interaction branches with a
generic route: ``interact(game, player, npc)`` selects a handler by NPC subtype
(and, for the story cast, the player's ``story_stage``/``story_step``). The
detailed story prose lives here on the server, delivered through the paged
``DIALOGUE_PAGE`` modal rather than the 39-char HUD line.

Every named NPC (Nerissa, Daniel, Wilhelm, Lucian, Grix) now has a dedicated,
stage-aware handler on ``GameState``. The legacy two-quest demo NPCs
(``NPC_FARMER``/``NPC_GOBLIN``) are kept only for backward-compatible tests
that spawn them directly; nothing on the live map uses those subtypes anymore.
Speaker IDs are the NPC subtype values -- the client maps them to fixed local
names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .entities import (
    Entity,
    NPC_DANIEL,
    NPC_FARMER,
    NPC_GOBLIN,
    NPC_GRIX,
    NPC_LUCIAN,
    NPC_NERISSA,
    NPC_WILHELM,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .game import GameState, PlayerState


# Dialogue/scene IDs. Stable identifiers so saved analytics or later
# stage-branching can reference a scene without depending on its text.
DLG_NERISSA_INTRO = 1
DLG_WILHELM_INTRO = 3
DLG_WILHELM_BRIDGE_START = 6
DLG_NERISSA_POST_BRIDGE = 7
DLG_DANIEL_OFFER = 8
DLG_DANIEL_COMPLETE = 9
DLG_WILHELM_COMPLETE = 10
DLG_LUCIAN_BLACKWATER_OFFER = 11
DLG_LUCIAN_LIVING_MUD_OFFER = 12
DLG_LUCIAN_SAMPLES_REDIRECT = 13
DLG_NERISSA_SAMPLES = 14
DLG_GRIX_EXPLAIN = 15
DLG_GRIX_COMPLETE = 16
DLG_PUMP_SHUTDOWN = 17
DLG_NERISSA_ENDING = 18


def interact(game: "GameState", player: "PlayerState", npc: Entity) -> bool:
    """Generic NPC interaction dispatch, keyed by NPC subtype."""
    # Legacy demo NPCs keep their exact existing quest behaviour.
    if npc.subtype == NPC_FARMER:
        return game._interact_farmer(player)
    if npc.subtype == NPC_GOBLIN:
        return game._interact_goblin(player)

    if npc.subtype == NPC_DANIEL:
        return game._interact_daniel(player)
    if npc.subtype == NPC_WILHELM:
        return game._interact_wilhelm(player)
    if npc.subtype == NPC_GRIX:
        return game._interact_grix(player)
    if npc.subtype == NPC_NERISSA:
        return game._interact_nerissa(player)
    if npc.subtype == NPC_LUCIAN:
        return game._interact_lucian(player)
    return False
