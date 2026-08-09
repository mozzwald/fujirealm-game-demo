"""Server-only PvP arena bots for real-hardware remote-player load testing."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

try:
    from .game import (
        CLIENT_AIM_DOWN,
        CLIENT_AIM_LEFT,
        CLIENT_AIM_RIGHT,
        CLIENT_AIM_UP,
        CLASS_HUNTER,
        HUNTER_RANGE,
        MAP_PVP_REALM,
        PLAYER_FIRE_BUTTON,
        GameState,
        max_hp_for_level,
        xp_needed_for_next_level,
    )
    from .protocol import PlayerStatePacket
    from .world_layout_data import PVP_REALM_RESPAWN
except ImportError:  # pragma: no cover - direct script execution
    from game import (
        CLIENT_AIM_DOWN,
        CLIENT_AIM_LEFT,
        CLIENT_AIM_RIGHT,
        CLIENT_AIM_UP,
        CLASS_HUNTER,
        HUNTER_RANGE,
        MAP_PVP_REALM,
        PLAYER_FIRE_BUTTON,
        GameState,
        max_hp_for_level,
        xp_needed_for_next_level,
    )
    from protocol import PlayerStatePacket
    from world_layout_data import PVP_REALM_RESPAWN


PVP_BOT_MAX_COUNT = 24
PVP_BOT_LEVEL = 5
DEFAULT_PVP_BOT_TOKEN_BASE = 0xF0000000
PVP_BOT_PATHS = (
    ((31, 42), (36, 42), (41, 42), (41, 47), (41, 52), (36, 52), (31, 52), (31, 47)),
    ((33, 44), (36, 44), (39, 44), (39, 47), (39, 50), (36, 50), (33, 50), (33, 47)),
    ((35, 46), (37, 46), (37, 48), (35, 48)),
    ((31, 44), (34, 42), (38, 42), (41, 44), (41, 50), (38, 52), (34, 52), (31, 50)),
    ((36, 42), (41, 47), (36, 52), (31, 47)),
    ((32, 47), (36, 43), (40, 47), (36, 51)),
)
PVP_BOT_PATH = PVP_BOT_PATHS[0]


@dataclass(frozen=True)
class PvpBotConfig:
    enabled: bool = False
    count: int = 0
    max_count: int = PVP_BOT_MAX_COUNT
    token_base: int = DEFAULT_PVP_BOT_TOKEN_BASE
    move_every_ticks: int = 4
    fire_cooldown_ticks: int = 20
    can_fire: bool = True
    anchor_radius: int = 8
    mode: str = "arena"
    orbit_every_ticks: int = 8


@dataclass
class PvpBotRuntime:
    token: int
    seq: int = 0
    fire_counter: int = 0
    last_fire_tick: int = -999999
    next_move_tick: int = 0
    formation_index: int = 0
    path_id: int = 0
    path_index: int = 0
    fire_release_pending: bool = False


class PvpBotController:
    def __init__(self, game: GameState, config: PvpBotConfig):
        if not 0 <= config.count <= config.max_count:
            raise ValueError(f"pvp bot count must be 0..{config.max_count}")
        if config.token_base < 0 or config.token_base + config.count > 0x100000000:
            raise ValueError("pvp bot token range must fit in 32 bits")
        if config.move_every_ticks < 1:
            raise ValueError("pvp bot move cadence must be at least 1 tick")
        if config.fire_cooldown_ticks < 1:
            raise ValueError("pvp bot fire cooldown must be at least 1 tick")
        if config.orbit_every_ticks < 1:
            raise ValueError("pvp bot orbit cadence must be at least 1 tick")
        if config.mode not in {"arena", "orbit", "path"}:
            raise ValueError("pvp bot mode must be arena, orbit, or path")
        self.game = game
        self.config = config
        self.runtimes: dict[int, PvpBotRuntime] = {}
        self.bot_tokens: set[int] = set()
        if config.enabled and config.count:
            self.ensure_bots()

    def ensure_bots(self) -> None:
        for index in range(self.config.count):
            token = self.config.token_base + index
            self.bot_tokens.add(token)
            self.runtimes.setdefault(
                token,
                PvpBotRuntime(
                    token=token,
                    formation_index=index,
                    path_id=index % len(PVP_BOT_PATHS),
                    path_index=(index // len(PVP_BOT_PATHS)) % len(PVP_BOT_PATHS[index % len(PVP_BOT_PATHS)]),
                ),
            )
            player = self.game.players.get(token)
            is_new = player is None
            if is_new:
                x, y = self._spawn_position(index)
                player = self.game.add_player(token, x=x, y=y, map_id=MAP_PVP_REALM)
            player.username = f"BOT{index + 1:02d}"
            self._apply_level_five_stats(player, heal=is_new)
            player.map_id = MAP_PVP_REALM
            player.respawn_map_id = MAP_PVP_REALM
            player.respawn_x, player.respawn_y = PVP_REALM_RESPAWN
            player.pvp_enabled = True
            player.respawn_correction_ticks = 0
            self.game._sync_player_entity(player)

    def remove_bots(self) -> None:
        for token in tuple(self.bot_tokens):
            self.game.remove_player(token)
        self.bot_tokens.clear()
        self.runtimes.clear()

    def step(self, tick: int, realtime_tokens: Iterable[int]) -> None:
        if not self.config.enabled or not self.config.count:
            return
        self.ensure_bots()
        real_tokens = [token for token in realtime_tokens if token not in self.bot_tokens]
        anchor = self._anchor_player(real_tokens)
        if anchor is None:
            self._park_bots()
            return
        for runtime in self.runtimes.values():
            player = self.game.players.get(runtime.token)
            if player is None:
                continue
            self._enforce_arena(player, runtime)
            if self.config.mode == "path":
                path = self._path_for(runtime)
                target_x, target_y = path[runtime.path_index]
            else:
                target_x, target_y = self._formation_target(anchor.x, anchor.y, runtime.formation_index, tick)
            next_x, next_y, facing = player.x, player.y, player.facing
            should_move = tick >= runtime.next_move_tick
            if should_move:
                if self.config.mode == "path" and (player.x, player.y) == (target_x, target_y):
                    runtime.path_index = (runtime.path_index + 1) % len(path)
                    target_x, target_y = path[runtime.path_index]
                if self.config.mode == "path":
                    next_x, next_y, facing = self._next_path_step(
                        player.x,
                        player.y,
                        target_x,
                        target_y,
                        runtime,
                    )
                else:
                    next_x, next_y, facing = self._next_step(player.x, player.y, target_x, target_y)
                if self.config.mode == "path" and (next_x, next_y) == (target_x, target_y):
                    runtime.path_index = (runtime.path_index + 1) % len(path)
                runtime.next_move_tick = tick + self.config.move_every_ticks
            fire = self._can_fire(player.x, player.y, anchor.x, anchor.y, tick, runtime)
            if fire is not None:
                facing = fire
                runtime.fire_counter = (runtime.fire_counter + 1) & 0xFF
                runtime.last_fire_tick = tick
                runtime.fire_release_pending = True
                buttons = PLAYER_FIRE_BUTTON
            else:
                buttons = 0
                if runtime.fire_release_pending:
                    runtime.fire_release_pending = False
            self._apply_packet(runtime, next_x, next_y, facing, buttons)
            moved = self.game.players.get(runtime.token)
            if moved is not None:
                self._enforce_arena(moved, runtime)

    def _anchor_player(self, real_tokens: list[int]):
        arena_players = [
            self.game.players[token]
            for token in real_tokens
            if token not in self.bot_tokens
            and token in self.game.players
            and self.game.players[token].map_id == MAP_PVP_REALM
        ]
        arena_players.sort(key=lambda player: player.token)
        return arena_players[0] if arena_players else None

    def _park_bots(self) -> None:
        for runtime in self.runtimes.values():
            player = self.game.players.get(runtime.token)
            if player is not None:
                self._enforce_arena(player, runtime)

    def _enforce_arena(self, player, runtime: PvpBotRuntime) -> None:
        if player.map_id == MAP_PVP_REALM and player.health > 0:
            player.pvp_enabled = True
            return
        player.map_id = MAP_PVP_REALM
        player.x, player.y = self._spawn_position(runtime.formation_index)
        self._apply_level_five_stats(player, heal=True)
        player.respawn_map_id = MAP_PVP_REALM
        player.respawn_x, player.respawn_y = PVP_REALM_RESPAWN
        player.pvp_enabled = True
        player.respawn_correction_ticks = 0
        self.game._sync_player_entity(player)

    def _apply_level_five_stats(self, player, heal: bool) -> None:
        player.class_id = CLASS_HUNTER
        player.level = PVP_BOT_LEVEL
        player.xp = 0
        player.xp_next = xp_needed_for_next_level(PVP_BOT_LEVEL)
        player.max_health = max_hp_for_level(PVP_BOT_LEVEL, CLASS_HUNTER)
        if heal:
            player.health = player.max_health
        else:
            player.health = min(player.health, player.max_health)

    def _spawn_position(self, index: int) -> tuple[int, int]:
        sx, sy = PVP_REALM_RESPAWN
        offsets = (
            (0, 0),
            (1, 0),
            (-1, 0),
            (0, 1),
            (0, -1),
            (2, 0),
            (-2, 0),
            (0, 2),
            (0, -2),
            (1, 1),
            (-1, 1),
            (1, -1),
            (-1, -1),
            (2, 1),
            (-2, 1),
            (2, -1),
            (-2, -1),
            (1, 2),
            (-1, 2),
            (1, -2),
            (-1, -2),
            (3, 0),
            (-3, 0),
            (0, 3),
        )
        world = self.game.world_for(MAP_PVP_REALM)
        for attempt in range(len(offsets)):
            dx, dy = offsets[(index + attempt) % len(offsets)]
            x, y = sx + dx, sy + dy
            if world.player_can_enter(x, y) and self.game.entity_at(MAP_PVP_REALM, x, y, blocking_only=True) is None:
                return x, y
        return sx, sy

    def _formation_target(self, anchor_x: int, anchor_y: int, index: int, tick: int = 0) -> tuple[int, int]:
        radius = max(2, min(self.config.anchor_radius, 10))
        ring = (
            (-radius, 0),
            (radius, 0),
            (0, -radius),
            (0, radius),
            (-radius, -radius // 2),
            (radius, -radius // 2),
            (-radius, radius // 2),
            (radius, radius // 2),
            (-radius // 2, -radius),
            (radius // 2, -radius),
            (-radius // 2, radius),
            (radius // 2, radius),
            (-radius - 2, 0),
            (radius + 2, 0),
            (0, -radius - 2),
            (0, radius + 2),
            (-radius - 2, -radius // 2),
            (radius + 2, -radius // 2),
            (-radius - 2, radius // 2),
            (radius + 2, radius // 2),
            (-radius // 2, -radius - 2),
            (radius // 2, -radius - 2),
            (-radius // 2, radius + 2),
            (radius // 2, radius + 2),
        )
        phase = tick // self.config.orbit_every_ticks if self.config.mode == "orbit" else 0
        dx, dy = ring[(index + phase) % len(ring)]
        return anchor_x + dx, anchor_y + dy

    def _path_for(self, runtime: PvpBotRuntime) -> tuple[tuple[int, int], ...]:
        return PVP_BOT_PATHS[runtime.path_id % len(PVP_BOT_PATHS)]

    def _next_step(self, x: int, y: int, target_x: int, target_y: int) -> tuple[int, int, int]:
        choices: list[tuple[int, int, int]] = []
        if target_x > x:
            choices.append((x + 1, y, CLIENT_AIM_RIGHT))
        elif target_x < x:
            choices.append((x - 1, y, CLIENT_AIM_LEFT))
        if target_y > y:
            choices.append((x, y + 1, CLIENT_AIM_DOWN))
        elif target_y < y:
            choices.append((x, y - 1, CLIENT_AIM_UP))
        world = self.game.world_for(MAP_PVP_REALM)
        for nx, ny, facing in choices:
            if world.player_can_enter(nx, ny) and self.game.entity_at(MAP_PVP_REALM, nx, ny, blocking_only=True) is None:
                return nx, ny, facing
        return x, y, CLIENT_AIM_RIGHT if target_x >= x else CLIENT_AIM_LEFT

    def _next_path_step(
        self,
        x: int,
        y: int,
        target_x: int,
        target_y: int,
        runtime: PvpBotRuntime,
    ) -> tuple[int, int, int]:
        choices: list[tuple[int, int, int]] = []
        dx = 1 if target_x > x else -1 if target_x < x else 0
        dy = 1 if target_y > y else -1 if target_y < y else 0
        if dx:
            choices.append((x + dx, y, CLIENT_AIM_RIGHT if dx > 0 else CLIENT_AIM_LEFT))
        if dy:
            choices.append((x, y + dy, CLIENT_AIM_DOWN if dy > 0 else CLIENT_AIM_UP))
        if dx:
            choices.extend(
                (
                    (x, y + 1, CLIENT_AIM_DOWN),
                    (x, y - 1, CLIENT_AIM_UP),
                )
            )
        if dy:
            choices.extend(
                (
                    (x + 1, y, CLIENT_AIM_RIGHT),
                    (x - 1, y, CLIENT_AIM_LEFT),
                )
            )
        world = self.game.world_for(MAP_PVP_REALM)
        for nx, ny, facing in choices:
            if world.player_can_enter(nx, ny) and self.game.entity_at(MAP_PVP_REALM, nx, ny, blocking_only=True) is None:
                return nx, ny, facing
        path = self._path_for(runtime)
        for offset in range(1, len(path)):
            runtime.path_index = (runtime.path_index + 1) % len(path)
            nx, ny = path[runtime.path_index]
            if abs(nx - x) + abs(ny - y) <= 1 and self.game.entity_at(MAP_PVP_REALM, nx, ny, blocking_only=True) is None:
                facing = CLIENT_AIM_RIGHT if nx > x else CLIENT_AIM_LEFT if nx < x else CLIENT_AIM_DOWN if ny > y else CLIENT_AIM_UP
                return nx, ny, facing
        return x, y, CLIENT_AIM_RIGHT if target_x >= x else CLIENT_AIM_LEFT

    def _can_fire(self, x: int, y: int, target_x: int, target_y: int, tick: int, runtime: PvpBotRuntime) -> int | None:
        if not self.config.can_fire:
            return None
        if tick - runtime.last_fire_tick < self.config.fire_cooldown_ticks:
            return None
        distance = abs(target_x - x) + abs(target_y - y)
        if distance > HUNTER_RANGE:
            return None
        if target_x == x:
            return CLIENT_AIM_DOWN if target_y > y else CLIENT_AIM_UP
        if target_y == y:
            return CLIENT_AIM_RIGHT if target_x > x else CLIENT_AIM_LEFT
        return None

    def _apply_packet(self, runtime: PvpBotRuntime, x: int, y: int, facing: int, buttons: int) -> None:
        runtime.seq = (runtime.seq + 1) & 0xFFFF
        packet = PlayerStatePacket(
            seq=runtime.seq,
            x=x,
            y=y,
            facing=facing,
            buttons=buttons,
            fire_counter=runtime.fire_counter,
            pickup_counter=0,
            last_server_seq=0,
        )
        self.game.apply_player_state(packet, token=runtime.token)
