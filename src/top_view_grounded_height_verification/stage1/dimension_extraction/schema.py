from __future__ import annotations

import json
from collections import Counter
from typing import Any


TASK_NAME = "dimension_extraction"
SLOT_ORDER = ("upper_left", "upper_right", "lower_left", "lower_right")
SLOT_INDEX = {slot: index for index, slot in enumerate(SLOT_ORDER)}
VALID_ORIENTATIONS = {"horizontal", "vertical"}


class DimensionExtractionSchemaError(Exception):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


def expect_keys(obj: dict[str, Any], expected: set[str], context: str, errors: list[str]) -> None:
    actual = set(obj)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{context} missing keys: {missing}")
    if extra:
        errors.append(f"{context} unexpected keys: {extra}")


def validate_layout(value: Any, context: str, errors: list[str]) -> dict[str, int] | None:
    if not isinstance(value, dict):
        errors.append(f"{context} must be an object")
        return None
    expect_keys(value, set(SLOT_ORDER), context, errors)
    if set(value) != set(SLOT_ORDER):
        return None
    normalized: dict[str, int] = {}
    for slot in SLOT_ORDER:
        cell = value.get(slot)
        if isinstance(cell, bool) or cell not in {0, 1}:
            errors.append(f"{context}.{slot} must be 0 or 1")
        else:
            normalized[slot] = cell
    if sum(normalized.values()) != 3:
        errors.append(f"{context} must contain exactly three occupied slots")
    return normalized


def occupied_slots_from_layout(layout: dict[str, int]) -> set[str]:
    return {slot for slot, cell in layout.items() if cell == 1}


def strip_bboxes(output: dict[str, Any]) -> dict[str, Any]:
    stripped_views = []
    for view in output.get("views", []):
        if isinstance(view, dict):
            stripped_views.append({key: value for key, value in view.items() if key != "bounding_box_2d"})
    return {
        "layout": output.get("layout"),
        "views": stripped_views,
    }


def validate_bbox(value: Any, context: str, errors: list[str]) -> list[int | float] | None:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
    ):
        errors.append(f"{context} must be [ymin, xmin, ymax, xmax] with numeric values")
        return None
    ymin, xmin, ymax, xmax = value
    if any(item < 0 or item > 1000 for item in value):
        errors.append(f"{context} values must be normalized coordinates from 0 to 1000")
    if ymin >= ymax:
        errors.append(f"{context} must have ymin < ymax")
    if xmin >= xmax:
        errors.append(f"{context} must have xmin < xmax")
    return value


def validate_bbox_outputs(data: Any) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return False, ["prediction must be a JSON object"]
    views = data.get("views")
    if not isinstance(views, list):
        return False, ["prediction.views must be an array"]
    for view_index, view in enumerate(views):
        context = f"prediction.views[{view_index}].bounding_box_2d"
        if not isinstance(view, dict) or "bounding_box_2d" not in view:
            errors.append(f"{context} is required")
            continue
        validate_bbox(view.get("bounding_box_2d"), context, errors)
    return not errors, errors


def validate_dimension(
    value: Any,
    *,
    view_slot: str,
    context: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{context} must be an object")
        return None
    expect_keys(value, {"value", "orientation", "belongs_to_slot"}, context, errors)

    dimension_value = value.get("value")
    if not isinstance(dimension_value, str) or not dimension_value:
        errors.append(f"{context}.value must be a non-empty string")
        numeric_value = None
    else:
        numeric_value = parse_dimension_value(dimension_value)
        if numeric_value is None:
            errors.append(f"{context}.value must be parseable as a number")

    orientation = value.get("orientation")
    if orientation not in VALID_ORIENTATIONS:
        errors.append(f"{context}.orientation must be one of {sorted(VALID_ORIENTATIONS)}")

    belongs_to_slot = value.get("belongs_to_slot")
    if belongs_to_slot not in SLOT_INDEX:
        errors.append(f"{context}.belongs_to_slot must be one of {list(SLOT_ORDER)}")
    elif belongs_to_slot != view_slot:
        errors.append(f"{context}.belongs_to_slot must match the parent view slot")

    if errors:
        return None
    return {
        "value": dimension_value,
        "numeric_value": numeric_value,
        "orientation": orientation,
        "belongs_to_slot": view_slot,
    }


def validate_dimension_output(
    data: Any,
    *,
    context: str = "output",
    require_bbox: bool = True,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, [f"{context} must be a JSON object"]
    expect_keys(data, {"layout", "views"}, context, errors)

    layout = validate_layout(data.get("layout"), f"{context}.layout", errors)
    views = data.get("views")
    if not isinstance(views, list):
        errors.append(f"{context}.views must be an array")
        return None, errors
    if layout is None:
        return None, errors

    occupied_slots = occupied_slots_from_layout(layout)
    seen_slots: set[str] = set()
    normalized_views: list[dict[str, Any]] = []
    view_keys = {"slot", "bounding_box_2d", "dimensions"} if require_bbox else {"slot", "dimensions"}

    for view_index, view in enumerate(views):
        view_context = f"{context}.views[{view_index}]"
        if not isinstance(view, dict):
            errors.append(f"{view_context} must be an object")
            continue
        if require_bbox:
            expect_keys(view, view_keys, view_context, errors)
        else:
            missing = sorted(view_keys - set(view))
            if missing:
                errors.append(f"{view_context} missing keys: {missing}")
        slot = view.get("slot")
        if slot not in SLOT_INDEX:
            errors.append(f"{view_context}.slot must be one of {list(SLOT_ORDER)}")
            continue
        if slot not in occupied_slots:
            errors.append(f"{view_context}.slot is not marked occupied in layout")
        if slot in seen_slots:
            errors.append(f"{view_context}.slot appears more than once")
        seen_slots.add(slot)

        bbox = None
        if require_bbox:
            bbox = validate_bbox(view.get("bounding_box_2d"), f"{view_context}.bounding_box_2d", errors)

        dimensions = view.get("dimensions")
        if not isinstance(dimensions, list):
            errors.append(f"{view_context}.dimensions must be an array")
            continue
        normalized_dimensions = []
        for dimension_index, dimension in enumerate(dimensions):
            before = len(errors)
            normalized_dimension = validate_dimension(
                dimension,
                view_slot=slot,
                context=f"{view_context}.dimensions[{dimension_index}]",
                errors=errors,
            )
            if normalized_dimension is not None and len(errors) == before:
                normalized_dimensions.append(normalized_dimension)
        normalized_dimensions.sort(
            key=lambda item: (
                item["value"],
                item["orientation"],
                item["belongs_to_slot"],
            )
        )
        normalized_view: dict[str, Any] = {
            "slot": slot,
            "dimensions": normalized_dimensions,
        }
        if require_bbox:
            normalized_view["bounding_box_2d"] = bbox
        normalized_views.append(normalized_view)

    missing_views = occupied_slots - seen_slots
    if missing_views:
        errors.append(f"{context}.views missing occupied slots: {sorted(missing_views, key=SLOT_INDEX.get)}")
    if len(views) != len(occupied_slots):
        errors.append(f"{context}.views must contain exactly one object per occupied slot")
    if errors:
        return None, errors

    normalized_views.sort(key=lambda item: SLOT_INDEX[item["slot"]])
    return {"layout": layout, "views": normalized_views}, []


def normalize_prediction(data: Any) -> tuple[dict[str, Any] | None, list[str]]:
    normalized, errors = validate_dimension_output(data, require_bbox=True)
    answer_normalized, answer_errors = validate_dimension_output(data, require_bbox=False)
    bbox_output_valid, bbox_errors = validate_bbox_outputs(data)
    if answer_normalized is None:
        return None, answer_errors or errors
    if normalized is None:
        return {
            "schema_valid": False,
            "ocr_schema_valid": True,
            "bbox_output_valid": bbox_output_valid,
            **answer_normalized,
            "parse_error": None,
            "validation_errors": errors,
            "bbox_validation_errors": bbox_errors,
        }, []
    return {
        "schema_valid": True,
        "ocr_schema_valid": True,
        "bbox_output_valid": bbox_output_valid,
        **normalized,
        "parse_error": None,
        "validation_errors": [],
        "bbox_validation_errors": bbox_errors,
    }, []


def flatten_dimensions(output: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(output, dict):
        return []
    dimensions: list[dict[str, Any]] = []
    for view in output.get("views", []):
        if isinstance(view, dict):
            dimensions.extend([dim for dim in view.get("dimensions", []) if isinstance(dim, dict)])
    return dimensions


def counter_f1(expected_items: list[Any], predicted_items: list[Any]) -> dict[str, Any]:
    expected_counter = Counter(expected_items)
    predicted_counter = Counter(predicted_items)
    matched = sum((expected_counter & predicted_counter).values())
    precision = matched / sum(predicted_counter.values()) if predicted_counter else 0.0
    recall = matched / sum(expected_counter.values()) if expected_counter else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "matched_count": matched,
        "predicted_count": sum(predicted_counter.values()),
        "expected_count": sum(expected_counter.values()),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def compare_outputs(predicted: Any, expected: Any) -> dict[str, Any]:
    expected_norm, expected_errors = validate_dimension_output(expected, context="ground_truth", require_bbox=False)
    if expected_errors:
        raise DimensionExtractionSchemaError(f"Ground truth failed validation: {expected_errors}")

    bbox_output_valid, bbox_errors = validate_bbox_outputs(predicted)
    full_output_norm, full_output_errors = validate_dimension_output(predicted, require_bbox=True)
    predicted_for_ocr = strip_bboxes(predicted) if isinstance(predicted, dict) else predicted
    predicted_norm, predicted_errors = validate_dimension_output(predicted_for_ocr, require_bbox=False)
    schema_valid = full_output_norm is not None
    validation_errors = full_output_errors if full_output_errors else predicted_errors

    if predicted_norm is None:
        expected_dims = flatten_dimensions(expected_norm)
        expected_slots = occupied_slots_from_layout(expected_norm["layout"])
        return {
            "schema_valid": schema_valid,
            "ocr_schema_valid": False,
            "validation_errors": validation_errors,
            "normalized_output": None,
            "layout_exact_match": False,
            "layout_slot_correct_count": 0,
            "layout_slot_total_count": len(SLOT_ORDER),
            "layout_slot_accuracy": 0.0,
            "occupied_slot_precision": 0.0,
            "occupied_slot_recall": 0.0,
            "occupied_slot_f1": 0.0,
            "occupied_slot_matched_count": 0,
            "expected_occupied_slot_count": len(expected_slots),
            "predicted_occupied_slot_count": 0,
            "bbox_output_valid": bbox_output_valid,
            "bbox_validation_errors": bbox_errors,
            "dimension_value_precision": 0.0,
            "dimension_value_recall": 0.0,
            "dimension_value_f1": 0.0,
            "dimension_value_matched_count": 0,
            "dimension_value_slot_matched_count": 0,
            "dimension_assignment_accuracy": 0.0,
            "orientation_accuracy": 0.0,
            "exact_match": False,
            "expected_dimension_count": len(expected_dims),
            "predicted_dimension_count": 0,
            "matched_dimension_count": 0,
            "dimension_full_matched_count": 0,
        }

    expected_slots = occupied_slots_from_layout(expected_norm["layout"])
    predicted_slots = occupied_slots_from_layout(predicted_norm["layout"])
    slot_scores = counter_f1(list(expected_slots), list(predicted_slots))

    expected_dims = flatten_dimensions(expected_norm)
    predicted_dims = flatten_dimensions(predicted_norm)
    expected_value_items = [item["value"] for item in expected_dims]
    predicted_value_items = [item["value"] for item in predicted_dims]
    value_scores = counter_f1(expected_value_items, predicted_value_items)

    expected_value_slot_items = [
        (item["value"], item["belongs_to_slot"]) for item in expected_dims
    ]
    predicted_value_slot_items = [
        (item["value"], item["belongs_to_slot"]) for item in predicted_dims
    ]
    value_slot_scores = counter_f1(expected_value_slot_items, predicted_value_slot_items)

    expected_full_items = [
        (item["value"], item["belongs_to_slot"], item["orientation"]) for item in expected_dims
    ]
    predicted_full_items = [
        (item["value"], item["belongs_to_slot"], item["orientation"]) for item in predicted_dims
    ]
    full_scores = counter_f1(expected_full_items, predicted_full_items)

    layout_exact_match = predicted_norm["layout"] == expected_norm["layout"]
    layout_slot_correct_count = sum(
        1
        for slot in SLOT_ORDER
        if predicted_norm["layout"].get(slot) == expected_norm["layout"].get(slot)
    )
    layout_slot_accuracy = layout_slot_correct_count / len(SLOT_ORDER)
    exact_match = canonical_json(predicted_norm) == canonical_json(expected_norm)
    assignment_accuracy = (
        value_slot_scores["matched_count"] / value_scores["matched_count"]
        if value_scores["matched_count"]
        else (1.0 if not expected_dims and not predicted_dims else 0.0)
    )
    orientation_accuracy = (
        full_scores["matched_count"] / value_slot_scores["matched_count"]
        if value_slot_scores["matched_count"]
        else (1.0 if not expected_dims and not predicted_dims else 0.0)
    )

    return {
        "schema_valid": schema_valid,
        "ocr_schema_valid": True,
        "validation_errors": validation_errors,
        "normalized_output": full_output_norm or predicted_norm,
        "layout_exact_match": layout_exact_match,
        "layout_slot_correct_count": layout_slot_correct_count,
        "layout_slot_total_count": len(SLOT_ORDER),
        "layout_slot_accuracy": round(layout_slot_accuracy, 4),
        "occupied_slot_precision": slot_scores["precision"],
        "occupied_slot_recall": slot_scores["recall"],
        "occupied_slot_f1": slot_scores["f1"],
        "occupied_slot_matched_count": slot_scores["matched_count"],
        "expected_occupied_slot_count": slot_scores["expected_count"],
        "predicted_occupied_slot_count": slot_scores["predicted_count"],
        "bbox_output_valid": bbox_output_valid,
        "bbox_validation_errors": bbox_errors,
        "dimension_value_precision": value_scores["precision"],
        "dimension_value_recall": value_scores["recall"],
        "dimension_value_f1": value_scores["f1"],
        "dimension_value_matched_count": value_scores["matched_count"],
        "dimension_value_slot_matched_count": value_slot_scores["matched_count"],
        "dimension_assignment_accuracy": round(assignment_accuracy, 4),
        "orientation_accuracy": round(orientation_accuracy, 4),
        "exact_match": exact_match,
        "expected_dimension_count": len(expected_dims),
        "predicted_dimension_count": len(predicted_dims),
        "matched_dimension_count": full_scores["matched_count"],
        "dimension_full_matched_count": full_scores["matched_count"],
        "dimension_value_metrics": {
            "matched_count": value_scores["matched_count"],
            "predicted_count": value_scores["predicted_count"],
            "expected_count": value_scores["expected_count"],
            "precision": value_scores["precision"],
            "recall": value_scores["recall"],
            "f1": value_scores["f1"],
        },
    }


def load_answer_map(ground_truth_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = ground_truth_payload.get("answer_groups")
    if not isinstance(groups, list):
        raise DimensionExtractionSchemaError("Ground truth file must contain an `answer_groups` array")
    return {group["answer_key"]: group for group in groups if isinstance(group, dict)}
