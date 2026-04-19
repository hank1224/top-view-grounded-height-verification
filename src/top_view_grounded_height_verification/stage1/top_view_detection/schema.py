from __future__ import annotations

import json
from typing import Any


TASK_NAME = "top_view_detection"
SLOT_ORDER = ("upper_left", "upper_right", "lower_left", "lower_right")
SLOT_INDEX = {slot: index for index, slot in enumerate(SLOT_ORDER)}


class TopViewDetectionSchemaError(Exception):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
        "top_view_slot": output.get("top_view_slot"),
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


def validate_top_view_output(
    data: Any,
    *,
    context: str = "output",
    require_bbox: bool = True,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, [f"{context} must be a JSON object"]
    expect_keys(data, {"layout", "views", "top_view_slot"}, context, errors)

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
    view_keys = {"slot", "bounding_box_2d"} if require_bbox else {"slot"}

    for view_index, view in enumerate(views):
        view_context = f"{context}.views[{view_index}]"
        if not isinstance(view, dict):
            errors.append(f"{view_context} must be an object")
            continue
        expect_keys(view, view_keys, view_context, errors)
        slot = view.get("slot")
        if slot not in SLOT_INDEX:
            errors.append(f"{view_context}.slot must be one of {list(SLOT_ORDER)}")
            continue
        if slot not in occupied_slots:
            errors.append(f"{view_context}.slot is not marked occupied in layout")
        if slot in seen_slots:
            errors.append(f"{view_context}.slot appears more than once")
        seen_slots.add(slot)
        normalized_view: dict[str, Any] = {"slot": slot}
        if require_bbox:
            normalized_view["bounding_box_2d"] = validate_bbox(
                view.get("bounding_box_2d"),
                f"{view_context}.bounding_box_2d",
                errors,
            )
        normalized_views.append(normalized_view)

    missing_views = occupied_slots - seen_slots
    if missing_views:
        errors.append(f"{context}.views missing occupied slots: {sorted(missing_views, key=SLOT_INDEX.get)}")
    if len(views) != len(occupied_slots):
        errors.append(f"{context}.views must contain exactly one object per occupied slot")

    top_view_slot = data.get("top_view_slot")
    if top_view_slot not in SLOT_INDEX:
        errors.append(f"{context}.top_view_slot must be one of {list(SLOT_ORDER)}")
    elif top_view_slot not in occupied_slots:
        errors.append(f"{context}.top_view_slot must be one of the occupied view slots")

    if errors:
        return None, errors
    normalized_views.sort(key=lambda item: SLOT_INDEX[item["slot"]])
    return {
        "layout": layout,
        "views": normalized_views,
        "top_view_slot": top_view_slot,
    }, []


def normalize_prediction(data: Any) -> tuple[dict[str, Any] | None, list[str]]:
    normalized, errors = validate_top_view_output(data, require_bbox=True)
    topology_data = strip_bboxes(data) if isinstance(data, dict) else data
    topology_normalized, topology_errors = validate_top_view_output(topology_data, require_bbox=False)
    bbox_output_valid, bbox_errors = validate_bbox_outputs(data)
    if topology_normalized is None:
        return None, topology_errors or errors
    if normalized is None:
        return {
            "schema_valid": False,
            "topology_schema_valid": True,
            "bbox_output_valid": bbox_output_valid,
            **topology_normalized,
            "parse_error": None,
            "validation_errors": errors,
            "bbox_validation_errors": bbox_errors,
        }, []
    return {
        "schema_valid": True,
        "topology_schema_valid": True,
        "bbox_output_valid": bbox_output_valid,
        **normalized,
        "parse_error": None,
        "validation_errors": [],
        "bbox_validation_errors": bbox_errors,
    }, []


def compare_outputs(predicted: Any, expected: Any) -> dict[str, Any]:
    expected_norm, expected_errors = validate_top_view_output(
        expected,
        context="ground_truth",
        require_bbox=False,
    )
    if expected_errors:
        raise TopViewDetectionSchemaError(f"Ground truth failed validation: {expected_errors}")

    bbox_output_valid, bbox_errors = validate_bbox_outputs(predicted)
    full_output_norm, full_output_errors = validate_top_view_output(predicted, require_bbox=True)
    predicted_for_topology = strip_bboxes(predicted) if isinstance(predicted, dict) else predicted
    predicted_norm, predicted_errors = validate_top_view_output(predicted_for_topology, require_bbox=False)
    schema_valid = full_output_norm is not None
    validation_errors = full_output_errors if full_output_errors else predicted_errors

    if predicted_norm is None:
        return {
            "schema_valid": schema_valid,
            "topology_schema_valid": False,
            "bbox_output_valid": bbox_output_valid,
            "bbox_validation_errors": bbox_errors,
            "validation_errors": validation_errors,
            "exact_match": False,
            "normalized_output": None,
            "top_view_slot_match": False,
        }

    predicted_answer = {
        "layout": predicted_norm["layout"],
        "views": [{"slot": view["slot"]} for view in predicted_norm["views"]],
        "top_view_slot": predicted_norm["top_view_slot"],
    }
    exact_match = canonical_json(predicted_answer) == canonical_json(expected_norm)
    return {
        "schema_valid": schema_valid,
        "topology_schema_valid": True,
        "bbox_output_valid": bbox_output_valid,
        "bbox_validation_errors": bbox_errors,
        "validation_errors": validation_errors,
        "exact_match": exact_match,
        "normalized_output": full_output_norm or predicted_norm,
        "top_view_slot_match": predicted_norm["top_view_slot"] == expected_norm["top_view_slot"],
    }


def load_answer_map(ground_truth_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = ground_truth_payload.get("answer_groups")
    if not isinstance(groups, list):
        raise TopViewDetectionSchemaError("Ground truth file must contain an `answer_groups` array")
    return {group["answer_key"]: group for group in groups if isinstance(group, dict)}
