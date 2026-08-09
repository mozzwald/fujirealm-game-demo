"""Small stack-only inventory model for Phase 14."""

from __future__ import annotations

from dataclasses import dataclass, field


ITEM_GOLD = 1
ITEM_STICKS = 2
ITEM_HERB = 3
ITEM_POTION = 4
ITEM_WARDEN_KEY = 5
ITEM_OIL_SAMPLE = 6
ITEM_RUST_SAMPLE = 7
# Save/protocol compatibility for the two-quest baseline.
ITEM_LOST_CHARM = ITEM_WARDEN_KEY
VALID_ITEM_IDS = frozenset(
    {
        ITEM_GOLD,
        ITEM_STICKS,
        ITEM_HERB,
        ITEM_POTION,
        ITEM_WARDEN_KEY,
        ITEM_OIL_SAMPLE,
        ITEM_RUST_SAMPLE,
    }
)
MAX_INVENTORY_SLOTS = 8
MAX_STACK_QUANTITY = 99


@dataclass
class InventorySlot:
    item_id: int
    quantity: int


@dataclass
class Inventory:
    slots: list[InventorySlot] = field(default_factory=list)

    def add_item(self, item_id: int, quantity: int) -> bool:
        if item_id <= 0 or quantity <= 0:
            return False
        for slot in self.slots:
            if slot.item_id == item_id:
                slot.quantity = min(MAX_STACK_QUANTITY, slot.quantity + quantity)
                return True
        if len(self.slots) >= MAX_INVENTORY_SLOTS:
            return False
        self.slots.append(InventorySlot(item_id, min(MAX_STACK_QUANTITY, quantity)))
        return True

    def remove_item(self, item_id: int, quantity: int) -> bool:
        if item_id <= 0 or quantity <= 0:
            return False
        for index, slot in enumerate(self.slots):
            if slot.item_id != item_id:
                continue
            if slot.quantity < quantity:
                return False
            slot.quantity -= quantity
            if slot.quantity == 0:
                del self.slots[index]
            return True
        return False

    def count_item(self, item_id: int) -> int:
        return sum(slot.quantity for slot in self.slots if slot.item_id == item_id)

    def as_tuple(self) -> tuple[tuple[int, int], ...]:
        return tuple((slot.item_id, slot.quantity) for slot in self.slots)
