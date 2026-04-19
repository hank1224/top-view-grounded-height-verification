from __future__ import annotations

from collections import Counter
from typing import Any

from top_view_grounded_height_verification.core.geometry import occupied_slots_from_layout
from top_view_grounded_height_verification.core.numeric import parse_dimension_value


def _flatten_gt_dimensions(ground_truth: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(ground_truth, dict):
        return []
    dimensions: list[dict[str, Any]] = []
    for view in ground_truth.get("views", []):
        if not isinstance(view, dict):
            continue
        slot = view.get("slot")
        for dimension in view.get("dimensions", []):
            if not isinstance(dimension, dict):
                continue
            item = dict(dimension)
            item.setdefault("belongs_to_slot", slot)
            dimensions.append(item)
    return dimensions


def _value_key(value: Any) -> float | str | None:
    numeric = parse_dimension_value(value)
    if numeric is not None:
        return numeric
    if value is None:
        return None
    return str(value)


def _dimension_value_counter(dimensions: list[dict[str, Any]]) -> Counter:
    return Counter(
        key
        for key in (_value_key(dimension.get("value")) for dimension in dimensions)
        if key is not None
    )


def _counter_metric(expected: Counter, predicted: Counter) -> dict[str, Any]:
    matched = sum((expected & predicted).values())
    predicted_count = sum(predicted.values())
    expected_count = sum(expected.values())
    precision = matched / predicted_count if predicted_count else 0.0
    recall = matched / expected_count if expected_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact_match_count": matched,
    }


def _counter_diff_values(left: Counter, right: Counter) -> list[Any]:
    diff = left - right
    values: list[Any] = []
    for value, count in diff.items():
        values.extend([value] * count)
    return values


def _prediction_dimensions(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dimension
        for dimension in evidence.get("dimensions", [])
        if isinstance(dimension, dict)
    ]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def build_evidence_audit_report(evidence: dict[str, Any], ground_truth: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ground_truth, dict):
        return {
            "audit_status": "not_available",
            "notes": ["ground_truth is not provided"],
        }

    dimension_gt = ground_truth.get("dimension_ground_truth")
    top_view_gt = ground_truth.get("top_view_ground_truth")
    if not isinstance(dimension_gt, dict) and not isinstance(top_view_gt, dict):
        return {
            "audit_status": "not_available",
            "notes": ["ground_truth does not contain dimension or top-view data"],
        }

    notes: list[str] = []
    predicted_dimensions = _prediction_dimensions(evidence)
    gt_dimensions = _flatten_gt_dimensions(dimension_gt if isinstance(dimension_gt, dict) else None)

    predicted_values = _dimension_value_counter(predicted_dimensions)
    expected_values = _dimension_value_counter(gt_dimensions)
    value_metrics = _counter_metric(expected_values, predicted_values)
    value_metrics["false_positive_values"] = _counter_diff_values(predicted_values, expected_values)
    value_metrics["missing_gt_values"] = _counter_diff_values(expected_values, predicted_values)

    expected_value_items = Counter(
        _value_key(dimension.get("value"))
        for dimension in gt_dimensions
        if _value_key(dimension.get("value")) is not None
    )
    predicted_value_items = Counter(
        _value_key(dimension.get("value"))
        for dimension in predicted_dimensions
        if _value_key(dimension.get("value")) is not None
    )
    expected_value_slot_items = Counter(
        (_value_key(dimension.get("value")), dimension.get("belongs_to_slot"))
        for dimension in gt_dimensions
        if _value_key(dimension.get("value")) is not None
    )
    predicted_value_slot_items = Counter(
        (_value_key(dimension.get("value")), dimension.get("belongs_to_slot"))
        for dimension in predicted_dimensions
        if _value_key(dimension.get("value")) is not None
    )
    expected_full_items = Counter(
        (
            _value_key(dimension.get("value")),
            dimension.get("belongs_to_slot"),
            dimension.get("orientation"),
        )
        for dimension in gt_dimensions
        if _value_key(dimension.get("value")) is not None
    )
    predicted_full_items = Counter(
        (
            _value_key(dimension.get("value")),
            dimension.get("belongs_to_slot"),
            dimension.get("orientation"),
        )
        for dimension in predicted_dimensions
        if _value_key(dimension.get("value")) is not None
    )

    value_matched = sum((expected_value_items & predicted_value_items).values())
    value_slot_matched = sum((expected_value_slot_items & predicted_value_slot_items).values())
    full_matched = sum((expected_full_items & predicted_full_items).values())
    slot_assignment_accuracy = _ratio(value_slot_matched, value_matched)
    orientation_accuracy = _ratio(full_matched, value_slot_matched)

    layout_consistent = evidence.get("status") == "valid"
    layout_correct = None
    if isinstance(dimension_gt, dict) and isinstance(dimension_gt.get("layout"), dict):
        layout_correct = evidence.get("layout") == dimension_gt.get("layout")
    else:
        notes.append("dimension_ground_truth.layout is not available")

    top_view_correct = None
    if isinstance(top_view_gt, dict) and top_view_gt.get("top_view_slot") is not None:
        top_view_correct = evidence.get("top_view_slot") == top_view_gt.get("top_view_slot")
    else:
        notes.append("top_view_ground_truth.top_view_slot is not available")

    expected_slots = []
    if isinstance(dimension_gt, dict) and isinstance(dimension_gt.get("layout"), dict):
        expected_slots = occupied_slots_from_layout(dimension_gt["layout"])

    return {
        "audit_status": "reported",
        "layout_consistent": layout_consistent,
        "layout_correct": layout_correct,
        "top_view_correct": top_view_correct,
        "ocr_value_metrics": value_metrics,
        "orientation_accuracy": orientation_accuracy,
        "slot_assignment_accuracy": slot_assignment_accuracy,
        "evidence_completeness": {
            "expected_dimension_count": len(gt_dimensions),
            "predicted_dimension_count": len(predicted_dimensions),
            "expected_occupied_slot_count": len(expected_slots),
            "predicted_occupied_slot_count": len(evidence.get("occupied_slots", [])),
        },
        "notes": notes,
    }
