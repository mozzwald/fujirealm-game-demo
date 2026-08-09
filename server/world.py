"""Minimal FujiRealm world and collision model."""

from __future__ import annotations

from dataclasses import dataclass

from .world_layout_data import (
    CAVE_TILES,
    OVERWORLD_CAVE_ENTRANCE,
    OVERWORLD_CAVE_RETURN,
    OVERWORLD_PVP_REALM_ENTRANCE,
    OVERWORLD_PVP_REALM_RETURN,
    OVERWORLD_RESPAWN,
    OVERWORLD_START,
    OVERWORLD_TILES,
    PVP_REALM_ENTRY,
    PVP_REALM_RESPAWN,
    PVP_REALM_EXIT,
    PVP_REALM_TILES,
    STARTER_CAVE_EXIT,
)


WORLD_W = 128
WORLD_H = 96
TREE_COUNT = 240
HERB_COUNT = 40
MAP_OVERWORLD = 0
MAP_STARTER_CAVE = 1
MAP_PVP_REALM = 2
TILESET_OVERWORLD = 0
TILESET_CAVE = 1
TILESET_PVP_REALM = TILESET_OVERWORLD
PALETTE_OVERWORLD = 0
PALETTE_CAVE = 1
PALETTE_PVP_REALM = 2
STARTER_CAVE_ENTRY = (8, 10)
STARTER_CAVE_RESPAWN = STARTER_CAVE_ENTRY
# Tucked into a side room off the entry corridor, not tied to the CSV map
# data (same rationale as STARTER_CAVE_ENTRY above).
LOST_CHARM_X = 114
LOST_CHARM_Y = 28

GRASS = 0
PLAYER = 1
TREE_FULL = 2
HERB = 3
TREE_DAMAGED = 4
TREE_STUMP = 5
BULLET = 6
BORDER = 7
BEAVER = 8
BEAVER_HURT = 9
ROAD = 10
WATER = 11
BUILDING = 12
CAVE_ENTRANCE = 13
GRAVE = 14
CAVE_FLOOR = 15
CAVE_WALL = 16
CAVE_EXIT = 17


PLAYER_BLOCKING = {
    TREE_FULL,
    TREE_DAMAGED,
    BULLET,
    BORDER,
    BEAVER,
    BEAVER_HURT,
    WATER,
    BUILDING,
    CAVE_WALL,
}
ENEMY_OPEN = {GRASS, HERB, TREE_STUMP, ROAD, CAVE_FLOOR}


@dataclass
class World:
    width: int = WORLD_W
    height: int = WORLD_H

    def __post_init__(self) -> None:
        self.tiles = [GRASS] * (self.width * self.height)
        for x in range(self.width):
            self.set_tile(x, 0, BORDER)
            self.set_tile(x, self.height - 1, BORDER)
        for y in range(self.height):
            self.set_tile(0, y, BORDER)
            self.set_tile(self.width - 1, y, BORDER)
        self.rebuild_registries()

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def index(self, x: int, y: int) -> int:
        if not self.in_bounds(x, y):
            raise IndexError(f"world coordinate out of bounds: {x},{y}")
        return y * self.width + x

    def tile(self, x: int, y: int) -> int:
        if not self.in_bounds(x, y):
            return BORDER
        return self.tiles[self.index(x, y)]

    def set_tile(self, x: int, y: int, tile: int) -> None:
        self.tiles[self.index(x, y)] = tile

    def player_can_enter(self, x: int, y: int) -> bool:
        return self.tile(x, y) not in PLAYER_BLOCKING

    def enemy_can_enter(self, x: int, y: int) -> bool:
        return self.tile(x, y) in ENEMY_OPEN

    def rebuild_registries(self) -> None:
        self.herb_spawn_indices = {i for i, tile in enumerate(self.tiles) if tile == HERB}
        self.herb_respawn_ticks: dict[int, int] = {}
        self.tree_spawn_indices = {i for i, tile in enumerate(self.tiles) if tile == TREE_FULL}
        self.tree_respawn_ticks: dict[int, int] = {}

    def consume_herb_if_present(self, x: int, y: int, respawn_ticks: int | None = None) -> bool:
        if self.tile(x, y) != HERB:
            return False
        index = self.index(x, y)
        self.set_tile(x, y, GRASS)
        if respawn_ticks is not None and index in self.herb_spawn_indices:
            self.herb_respawn_ticks[index] = respawn_ticks
        return True

    def tick_herb_cooldowns(self) -> None:
        for index, ticks in tuple(self.herb_respawn_ticks.items()):
            if ticks > 0:
                self.herb_respawn_ticks[index] = ticks - 1

    def ready_herb_respawn_indices(self) -> list[int]:
        return sorted(index for index, ticks in self.herb_respawn_ticks.items() if ticks <= 0)

    def coords_for_index(self, index: int) -> tuple[int, int]:
        return index % self.width, index // self.width

    def activate_herb_respawn(self, index: int) -> tuple[int, int]:
        x, y = self.coords_for_index(index)
        self.set_tile(x, y, HERB)
        self.herb_respawn_ticks.pop(index, None)
        return x, y

    def defer_herb_respawn(self, index: int) -> None:
        if index in self.herb_respawn_ticks:
            self.herb_respawn_ticks[index] = 1

    def chop_tree_if_present(self, x: int, y: int, respawn_ticks: int | None = None) -> int | None:
        tile = self.tile(x, y)
        if tile == TREE_FULL:
            self.set_tile(x, y, TREE_DAMAGED)
            return TREE_DAMAGED
        if tile == TREE_DAMAGED:
            index = self.index(x, y)
            self.set_tile(x, y, TREE_STUMP)
            if respawn_ticks is not None and index in self.tree_spawn_indices:
                self.tree_respawn_ticks[index] = respawn_ticks
            return TREE_STUMP
        return None

    def tick_tree_cooldowns(self) -> None:
        for index, ticks in tuple(self.tree_respawn_ticks.items()):
            if ticks > 0:
                self.tree_respawn_ticks[index] = ticks - 1

    def ready_tree_respawn_indices(self) -> list[int]:
        return sorted(index for index, ticks in self.tree_respawn_ticks.items() if ticks <= 0)

    def activate_tree_respawn(self, index: int) -> tuple[int, int]:
        x, y = self.coords_for_index(index)
        self.set_tile(x, y, TREE_FULL)
        self.tree_respawn_ticks.pop(index, None)
        return x, y

    def defer_tree_respawn(self, index: int) -> None:
        if index in self.tree_respawn_ticks:
            self.tree_respawn_ticks[index] = 1

    def window_tiles(self, origin_x: int, origin_y: int, width: int, height: int) -> bytes:
        tiles = bytearray()
        for row in range(height):
            y = origin_y + row
            for col in range(width):
                x = origin_x + col
                tiles.append(self.tile(x, y))
        return bytes(tiles)


def build_seeded_world(seed: int) -> World:
    return build_overworld(seed)


def build_world_map(map_id: int, seed: int) -> World:
    if map_id == MAP_OVERWORLD:
        return build_overworld(seed)
    if map_id == MAP_STARTER_CAVE:
        return build_starter_cave(seed)
    if map_id == MAP_PVP_REALM:
        return build_pvp_realm(seed)
    raise ValueError(f"unknown map_id: {map_id}")


def _build_from_layout(tiles: list[int]) -> World:
    world = World()
    world.tiles = list(tiles)
    world.rebuild_registries()
    return world


def build_overworld(seed: int) -> World:
    """Loads the hand-authored layout (maps/overworld.csv via
    tools/import_map_csv.py). `seed` is accepted for interface
    compatibility but unused now that the layout is fixed rather than
    procedurally generated -- see build_overworld_procedural for the
    original seeded generator, kept for reference."""
    return _build_from_layout(OVERWORLD_TILES)


def build_starter_cave(seed: int) -> World:
    """Loads the hand-authored layout (maps/cave.csv via
    tools/import_map_csv.py). `seed` is accepted for interface
    compatibility but unused -- see build_starter_cave_procedural for the
    original hand-authored-in-code generator, kept for reference."""
    return _build_from_layout(CAVE_TILES)


def build_pvp_realm(seed: int) -> World:
    """Loads the hand-authored layout (maps/pvp_realm.csv via
    tools/import_map_csv.py). `seed` is accepted for interface
    compatibility but unused now that the layout is fixed rather than
    procedurally generated."""
    return _build_from_layout(PVP_REALM_TILES)


def build_overworld_procedural(seed: int) -> World:
    world = World()
    rng = DeterministicRng(seed)
    protected = {
        OVERWORLD_START,
        (11, 10),
        (10, 11),
        OVERWORLD_CAVE_ENTRANCE,
        OVERWORLD_CAVE_RETURN,
        OVERWORLD_RESPAWN,
    }
    for x in range(4, 22):
        world.set_tile(x, 10, ROAD)
    for y in range(8, 13):
        world.set_tile(8, y, ROAD)
    for x in range(6, 12):
        for y in range(7, 10):
            world.set_tile(x, y, BUILDING)
    world.set_tile(*OVERWORLD_RESPAWN, GRAVE)
    world.set_tile(*OVERWORLD_CAVE_ENTRANCE, CAVE_ENTRANCE)
    for gy in range(4, WORLD_H - 4, 8):
        for gx in range(4, WORLD_W - 4, 8):
            x = gx + (rng.next_byte() % 5) - 2
            y = gy + (rng.next_byte() % 5) - 2
            if world.tile(x, y) == GRASS and (x, y) not in protected:
                world.set_tile(x, y, TREE_FULL)
    placed = 0
    while placed < TREE_COUNT:
        x, y = random_cell(rng)
        if world.tile(x, y) == GRASS and (x, y) not in protected:
            world.set_tile(x, y, TREE_FULL)
            placed += 1
    placed = 0
    while placed < HERB_COUNT:
        x, y = random_cell(rng)
        if world.tile(x, y) == GRASS:
            world.set_tile(x, y, HERB)
            placed += 1
    world.rebuild_registries()
    return world


def build_starter_cave_procedural(seed: int) -> World:
    world = World()
    world.tiles = [CAVE_WALL] * (world.width * world.height)
    for x in range(world.width):
        world.set_tile(x, 0, BORDER)
        world.set_tile(x, world.height - 1, BORDER)
    for y in range(world.height):
        world.set_tile(0, y, BORDER)
        world.set_tile(world.width - 1, y, BORDER)

    def carve_rect(left: int, top: int, right: int, bottom: int) -> None:
        for cy in range(top, bottom + 1):
            for cx in range(left, right + 1):
                world.set_tile(cx, cy, CAVE_FLOOR)

    def carve_hline(y: int, left: int, right: int) -> None:
        for cx in range(left, right + 1):
            world.set_tile(cx, y, CAVE_FLOOR)

    def carve_vline(x: int, top: int, bottom: int) -> None:
        for cy in range(top, bottom + 1):
            world.set_tile(x, cy, CAVE_FLOOR)

    cave_left = 4
    cave_right = 116
    cave_top = 6
    cave_bottom = 62
    main_rows = (10, 16, 22, 28, 34, 40, 46, 52, 58)
    for row_index, y in enumerate(main_rows):
        left = cave_left + (0 if row_index % 2 == 0 else 8)
        right = cave_right - (8 if row_index % 2 == 0 else 0)
        carve_hline(y, left, right)
        carve_hline(y + 1, left, right)
    for x in (8, 20, 32, 44, 56, 68, 80, 92, 104, 112):
        for top, bottom in ((10, 16), (22, 28), (34, 40), (46, 52)):
            carve_vline(x, top, bottom)
            if x % 24 == 8:
                carve_vline(x + 1, top, bottom)
    for x in (18, 42, 66, 90):
        carve_vline(x, cave_top, cave_bottom)
    for room in (
        (6, 8, 14, 13),
        (26, 18, 36, 24),
        (50, 30, 62, 36),
        (74, 12, 86, 18),
        (96, 42, 110, 50),
        (30, 50, 44, 60),
        (62, 48, 76, 58),
    ):
        carve_rect(*room)
    world.set_tile(*STARTER_CAVE_ENTRY, CAVE_FLOOR)
    world.set_tile(*STARTER_CAVE_EXIT, CAVE_EXIT)
    world.rebuild_registries()
    return world


class DeterministicRng:
    """16-bit LFSR with stable cross-language behavior."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFF

    def next_u16(self) -> int:
        carry = self.state & 1
        self.state >>= 1
        if carry:
            self.state ^= 0xB400
        self.state &= 0xFFFF
        return self.state

    def next_byte(self) -> int:
        return self.next_u16() >> 8


def random_cell(rng: DeterministicRng) -> tuple[int, int]:
    while True:
        x = rng.next_byte() & 0x7F
        if x < WORLD_W - 2:
            x += 1
            break
    while True:
        y = rng.next_byte() & 0x7F
        if y < WORLD_H - 2:
            y += 1
            break
    return x, y
