from __future__ import annotations

from typing import Any


DEFAULT_TOLERANCE = 1e-6


def parse_dimension_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def values_equal(a: float | int | None, b: float | int | None, tolerance: float = DEFAULT_TOLERANCE) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tolerance


def value_in(value: float, candidates: list[float], tolerance: float = DEFAULT_TOLERANCE) -> bool:
    return any(values_equal(value, candidate, tolerance=tolerance) for candidate in candidates)

