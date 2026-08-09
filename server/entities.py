"""Generic dynamic entity model for server-owned overlays."""

from __future__ import annotations

from dataclasses import dataclass

from .items import (
    ITEM_GOLD,
    ITEM_HERB,
    ITEM_LOST_CHARM,
    ITEM_OIL_SAMPLE,
    ITEM_POTION,
    ITEM_RUST_SAMPLE,
    ITEM_STICKS,
    ITEM_WARDEN_KEY,
)
from .zones import ZoneId


ENTITY_PLAYER = 1
ENTITY_NPC = 2
ENTITY_ENEMY = 3
ENTITY_ITEM = 4
ENTITY_PROJECTILE = 5

ENEMY_BEAVER = 1
ENEMY_SNAKE = 2
ENEMY_BAT = 3
ENEMY_SLIME = 4
ENEMY_GOBLIN = 5
ENEMY_GORVAK = 6

NPC_FARMER = 1
NPC_GOBLIN = 2
# The Dam Below named cast (Phase 57). Daniel supersedes the generic farmer and
# Grix the generic goblin NPC; the legacy two are kept until the generic story
# dispatch and the map redraw fully migrate them.
NPC_NERISSA = 3
NPC_DANIEL = 4
NPC_WILHELM = 5
NPC_LUCIAN = 6
NPC_GRIX = 7
NAMED_NPC_SUBTYPES = frozenset(
    {NPC_NERISSA, NPC_DANIEL, NPC_WILHELM, NPC_LUCIAN, NPC_GRIX, NPC_FARMER, NPC_GOBLIN}
)
PROJECTILE_ARROW = 1

ENTITY_FLAG_VISIBLE = 0x01
ENTITY_FLAG_BLOCKING = 0x02
ENTITY_FLAG_HOSTILE = 0x04
ENTITY_FLAG_NAMED = 0x08
ENTITY_FLAG_TEMPORARY = 0x10
# Owner-only story items/triggers are not transmitted to unrelated players.
ENTITY_FLAG_PERSONAL = 0x20
# Owned entities normally do not block unrelated players. Set this only when
# an encounter explicitly requires one owned instance to block everybody.
ENTITY_FLAG_BLOCKS_OTHERS = 0x40
# Transient server-side visual state for Wilhelm's active repair animation.
ENTITY_FLAG_WORKING = 0x80


@dataclass
class Entity:
    entity_id: int
    kind: int
    subtype: int
    map_id: int
    x: int
    y: int
    hp: int = 1
    max_hp: int = 1
    level: int = 1
    state: int = 0
    flags: int = ENTITY_FLAG_VISIBLE
    owner_id: int = 0
    zone_id: ZoneId | None = None
    move_cooldown: int = 0
    chop_cooldown: int = 0
    attack_cooldown: int = 0
    aggro_ticks: int = 0
    decay_ticks: int = 0
    home_x: int = 0
    home_y: int = 0
    respawn_ticks: int = 0
    hit_pulse_ticks: int = 0

    @property
    def is_live(self) -> bool:
        return self.hp > 0

    @property
    def is_blocking(self) -> bool:
        return self.is_live and (self.flags & ENTITY_FLAG_BLOCKING) != 0

    @property
    def is_temporary(self) -> bool:
        return (self.flags & ENTITY_FLAG_TEMPORARY) != 0

    @property
    def is_player(self) -> bool:
        return self.kind == ENTITY_PLAYER
