"""Generic server-side zone grid helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


ZONE_SIZE = 16
ACTIVE_ZONE_RADIUS = 1

ZONE_TOWN = 1
ZONE_ROAD = 2
ZONE_FOREST = 3
ZONE_CAVE = 4
ZONE_WATER = 5


@dataclass(frozen=True, order=True)
class ZoneId:
    map_id: int
    zx: int
    zy: int


@dataclass(frozen=True)
class SpawnRule:
    kind: int
    subtype: int
    min_level: int
    max_level: int
    weight: int
    max_count: int
    respawn_delay: int
    allowed_terrain: tuple[int, ...]


@dataclass(frozen=True)
class ZoneDefinition:
    zone_id: ZoneId
    zone_type: int
    danger_level: int
    flags: int = 0
    spawn_table: tuple[SpawnRule, ...] = ()
    ambient_message_ids: tuple[int, ...] = ()


@dataclass
class ActiveZoneState:
    zone_id: ZoneId
    tick_activated: int
    spawned_entity_ids: set[int] = field(default_factory=set)


def zone_for_tile(map_id: int, x: int, y: int) -> ZoneId:
    return ZoneId(map_id, max(0, x) // ZONE_SIZE, max(0, y) // ZONE_SIZE)


def zones_near_tile(
    map_id: int,
    x: int,
    y: int,
    radius: int = ACTIVE_ZONE_RADIUS,
) -> set[ZoneId]:
    center = zone_for_tile(map_id, x, y)
    zones: set[ZoneId] = set()
    for zy in range(max(0, center.zy - radius), center.zy + radius + 1):
        for zx in range(max(0, center.zx - radius), center.zx + radius + 1):
            zones.add(ZoneId(map_id, zx, zy))
    return zones
