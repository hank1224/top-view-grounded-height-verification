from __future__ import annotations

from typing import Any


SLOT_ORDER = ("upper_left", "upper_right", "lower_left", "lower_right")
SLOT_INDEX = {slot: index for index, slot in enumerate(SLOT_ORDER)}
SLOT_COORDS = {
    "upper_left": (0, 0),
    "upper_right": (0, 1),
    "lower_left": (1, 0),
    "lower_right": (1, 1),
}
VALID_ORIENTATIONS = {"horizontal", "vertical"}


def is_valid_slot(slot: Any) -> bool:
    return isinstance(slot, str) and slot in SLOT_INDEX


def ordered_slots(slots: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    return sorted(slots, key=SLOT_INDEX.get)


def occupied_slots_from_layout(layout: dict[str, int]) -> list[str]:
    return [slot for slot in SLOT_ORDER if layout.get(slot) == 1]


def validate_l_shaped_layout(layout: Any, *, context: str = "layout") -> tuple[dict[str, int] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(layout, dict):
        return None, [f"{context} must be an object"]

    expected = set(SLOT_ORDER)
    actual = set(layout)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{context} missing keys: {missing}")
    if extra:
        errors.append(f"{context} unexpected keys: {extra}")
    if missing or extra:
        return None, errors

    normalized: dict[str, int] = {}
    for slot in SLOT_ORDER:
        value = layout.get(slot)
        if isinstance(value, bool) or value not in {0, 1}:
            errors.append(f"{context}.{slot} must be 0 or 1")
        else:
            normalized[slot] = value

    if errors:
        return None, errors
    if sum(normalized.values()) != 3:
        errors.append(f"{context} must contain exactly three occupied slots")
    if errors:
        return None, errors
    return normalized, []


def adjacency_relation(slot_a: str, slot_b: str) -> str:
    if not is_valid_slot(slot_a) or not is_valid_slot(slot_b):
        return "invalid"
    if slot_a == slot_b:
        return "same"
    row_a, col_a = SLOT_COORDS[slot_a]
    row_b, col_b = SLOT_COORDS[slot_b]
    if row_a == row_b and col_a != col_b:
        return "horizontal"
    if col_a == col_b and row_a != row_b:
        return "vertical"
    return "diagonal"


def are_adjacent(slot_a: str, slot_b: str) -> bool:
    return adjacency_relation(slot_a, slot_b) in {"horizontal", "vertical"}

