"""Transient state for player-owned scripted encounters.

Encounter records and their entity IDs are deliberately server-memory only.
Stable story results are applied by callbacks to ``PlayerState`` and persisted
through the normal game-state saver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


ENCOUNTER_INACTIVE = "inactive"
ENCOUNTER_ESCORTING = "escorting"
ENCOUNTER_ACTIVE = "active"
ENCOUNTER_RETURNING = "returning"
ENCOUNTER_SUCCEEDED = "succeeded"
ENCOUNTER_FAILED = "failed"
ENCOUNTER_CLEANUP = "cleanup"

VALID_ENCOUNTER_PHASES = frozenset(
    {
        ENCOUNTER_INACTIVE,
        ENCOUNTER_ESCORTING,
        ENCOUNTER_ACTIVE,
        ENCOUNTER_RETURNING,
        ENCOUNTER_SUCCEEDED,
        ENCOUNTER_FAILED,
        ENCOUNTER_CLEANUP,
    }
)

EncounterCallback = Callable[[Any, Any, "ScriptedEncounter"], None]


@dataclass(frozen=True)
class EncounterRegion:
    """Inclusive owner-presence rectangle on an encounter's map."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.right < self.left or self.bottom < self.top:
            raise ValueError("encounter region bounds are reversed")

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass
class ScriptedEncounter:
    encounter_id: str
    owner_id: int
    map_id: int
    phase: str = ENCOUNTER_INACTIVE
    region: EncounterRegion | None = None
    spawned_entity_ids: set[int] = field(default_factory=set)
    countdown_ticks: int = 0
    initial_countdown_ticks: int = 0
    progress_ticks: int = 0
    pause_when_owner_absent: bool = True
    fail_after_absent_ticks: int = 0
    owner_absent_ticks: int = 0
    escort_entity_id: int = 0
    waypoints: tuple[tuple[int, int], ...] = ()
    waypoint_index: int = 0
    move_interval_ticks: int = 1
    move_cooldown_ticks: int = 0
    escort_follow_distance: int = 0
    kill_count: int = 0
    last_attacker_token: int = 0
    failure_reason: str = ""
    cleanup_on_success: bool = True
    is_return_leg: bool = False
    # Boss-fight fields (Gorvak): dispatched by encounter_id in
    # _update_scripted_encounters rather than the generic countdown/escort
    # machinery, since the fight ends on the boss's death, not a timer.
    boss_entity_id: int = 0
    summon_entity_id: int = 0
    next_summon_kind: int = 0
    summon_cooldown_ticks: int = 0
    on_active: EncounterCallback | None = None
    on_progress: EncounterCallback | None = None
    on_success: EncounterCallback | None = None
    on_failure: EncounterCallback | None = None
    on_return_complete: EncounterCallback | None = None

    def __post_init__(self) -> None:
        if not self.encounter_id:
            raise ValueError("encounter_id must not be empty")
        if self.owner_id == 0:
            raise ValueError("scripted encounters require a nonzero owner")
        if self.phase not in VALID_ENCOUNTER_PHASES:
            raise ValueError(f"invalid encounter phase: {self.phase}")
        self.countdown_ticks = max(0, int(self.countdown_ticks))
        self.initial_countdown_ticks = max(
            self.countdown_ticks, int(self.initial_countdown_ticks)
        )
        self.fail_after_absent_ticks = max(0, int(self.fail_after_absent_ticks))
        self.move_interval_ticks = max(1, int(self.move_interval_ticks))
        self.escort_follow_distance = max(0, int(self.escort_follow_distance))

    @property
    def key(self) -> tuple[int, str]:
        return self.owner_id, self.encounter_id

    def owner_is_present(self, player: Any) -> bool:
        if player is None or player.map_id != self.map_id or player.health <= 0:
            return False
        if getattr(player, "transition_loading", False):
            return False
        return self.region is None or self.region.contains(player.x, player.y)

    def reset_for_retry(self) -> None:
        self.phase = ENCOUNTER_INACTIVE
        self.spawned_entity_ids.clear()
        self.countdown_ticks = self.initial_countdown_ticks
        self.progress_ticks = 0
        self.owner_absent_ticks = 0
        self.escort_entity_id = 0
        self.waypoint_index = 0
        self.move_cooldown_ticks = 0
        self.kill_count = 0
        self.last_attacker_token = 0
        self.failure_reason = ""
        self.is_return_leg = False
        self.boss_entity_id = 0
        self.summon_entity_id = 0
        self.next_summon_kind = 0
        self.summon_cooldown_ticks = 0
