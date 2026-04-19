from __future__ import annotations

from typing import Any

from top_view_grounded_height_verification.core.geometry import (
    SLOT_INDEX,
    SLOT_ORDER,
    VALID_ORIENTATIONS,
    is_valid_slot,
    occupied_slots_from_layout,
    ordered_slots,
    validate_l_shaped_layout,
)
from top_view_grounded_height_verification.core.numeric import parse_dimension_value


def _base_evidence(input_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "invalid",
        "image_id": input_payload.get("image_id"),
        "image_path": input_payload.get("image_path"),
        "layout": None,
        "occupied_slots": [],
        "top_view_slot": None,
        "views": [],
        "dimensions": [],
        "warnings": [],
        "failure_reasons": [],
    }


def validate_layout_consistency(
    dimension_extraction: dict[str, Any],
    top_view_detection: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    dimension_layout, dimension_errors = validate_l_shaped_layout(
        dimension_extraction.get("layout"),
        context="dimension_extraction.layout",
    )
    top_view_layout, top_view_errors = validate_l_shaped_layout(
        top_view_detection.get("layout"),
        context="top_view_detection.layout",
    )
    errors.extend(dimension_errors)
    errors.extend(top_view_errors)
    if dimension_layout is not None and top_view_layout is not None and dimension_layout != top_view_layout:
        errors.append("dimension_extraction.layout does not match top_view_detection.layout")
    return errors


def _validate_views(
    views: Any,
    *,
    occupied_slots: list[str],
    context: str,
    require_dimensions: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(views, list):
        return [], [f"{context}.views must be an array"]

    seen_slots: set[str] = set()
    normalized_views: list[dict[str, Any]] = []
    occupied_set = set(occupied_slots)
    for index, view in enumerate(views):
        view_context = f"{context}.views[{index}]"
        if not isinstance(view, dict):
            errors.append(f"{view_context} must be an object")
            continue
        slot = view.get("slot")
        if not is_valid_slot(slot):
            errors.append(f"{view_context}.slot must be one of {list(SLOT_ORDER)}")
            continue
        if slot not in occupied_set:
            errors.append(f"{view_context}.slot is not marked occupied in layout")
        if slot in seen_slots:
            errors.append(f"{view_context}.slot appears more than once")
        seen_slots.add(slot)
        if require_dimensions and not isinstance(view.get("dimensions"), list):
            errors.append(f"{view_context}.dimensions must be an array")

        normalized_view = {
            "slot": slot,
            "bounding_box_2d": view.get("bounding_box_2d"),
        }
        if require_dimensions:
            normalized_view["dimensions"] = view.get("dimensions", [])
        normalized_views.append(normalized_view)

    missing = set(occupied_slots) - seen_slots
    if missing:
        errors.append(f"{context}.views missing occupied slots: {ordered_slots(missing)}")
    if len(views) != len(occupied_slots):
        errors.append(f"{context}.views must contain exactly one object per occupied slot")

    normalized_views.sort(key=lambda item: SLOT_INDEX[item["slot"]])
    return normalized_views, errors


def _dimension_uid(slot: str, index: int) -> str:
    return f"{slot}_d{index}"


def flatten_dimensions(dimension_extraction: dict[str, Any]) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    per_slot_counts: dict[str, int] = {}
    for view in dimension_extraction.get("views", []):
        if not isinstance(view, dict):
            continue
        slot = view.get("slot")
        if not isinstance(slot, str):
            slot = "unknown"
        if not isinstance(view.get("dimensions"), list):
            continue
        for raw_dimension in view["dimensions"]:
            per_slot_counts[slot] = per_slot_counts.get(slot, 0) + 1
            dimension = _normalize_dimension(
                raw_dimension,
                parent_slot=slot,
                dimension_uid=_dimension_uid(slot, per_slot_counts[slot]),
            )
            dimensions.append(dimension)
    return dimensions


def _normalize_dimension(raw_dimension: Any, *, parent_slot: str, dimension_uid: str) -> dict[str, Any]:
    invalid_reasons: list[str] = []
    if not isinstance(raw_dimension, dict):
        return {
            "dimension_uid": dimension_uid,
            "value": None,
            "numeric_value": None,
            "orientation": None,
            "belongs_to_slot": parent_slot,
            "parent_slot": parent_slot,
            "valid": False,
            "invalid_reasons": ["dimension must be an object"],
            "raw": raw_dimension,
        }

    raw_value = raw_dimension.get("value")
    numeric_value = parse_dimension_value(raw_dimension.get("numeric_value"))
    if numeric_value is None:
        numeric_value = parse_dimension_value(raw_value)
    if numeric_value is None:
        invalid_reasons.append("dimension_value_not_numeric")

    orientation = raw_dimension.get("orientation")
    if orientation not in VALID_ORIENTATIONS:
        invalid_reasons.append("invalid_dimension_orientation")

    belongs_to_slot = raw_dimension.get("belongs_to_slot")
    if not is_valid_slot(belongs_to_slot):
        invalid_reasons.append("invalid_belongs_to_slot")
    elif belongs_to_slot != parent_slot:
        invalid_reasons.append("belongs_to_slot_mismatch")

    return {
        "dimension_uid": dimension_uid,
        "value": raw_value,
        "numeric_value": numeric_value,
        "orientation": orientation,
        "belongs_to_slot": belongs_to_slot,
        "parent_slot": parent_slot,
        "valid": not invalid_reasons,
        "invalid_reasons": invalid_reasons,
        "raw": raw_dimension,
    }


def build_evidence(input_payload: dict[str, Any]) -> dict[str, Any]:
    evidence = _base_evidence(input_payload)
    dimension_extraction = input_payload.get("dimension_extraction")
    top_view_detection = input_payload.get("top_view_detection")
    if not isinstance(dimension_extraction, dict):
        evidence["failure_reasons"].append("dimension_extraction must be an object")
        return evidence
    if not isinstance(top_view_detection, dict):
        evidence["failure_reasons"].append("top_view_detection must be an object")
        return evidence
    if is_valid_slot(top_view_detection.get("top_view_slot")):
        evidence["top_view_slot"] = top_view_detection.get("top_view_slot")

    if dimension_extraction.get("ocr_schema_valid") is False:
        evidence["failure_reasons"].append("dimension_extraction.ocr_schema_valid is false")
        return evidence
    top_view_topology_valid = top_view_detection.get(
        "topology_schema_valid",
        top_view_detection.get("schema_valid"),
    )
    if top_view_detection.get("schema_valid") is False and not top_view_topology_valid:
        evidence["failure_reasons"].append("top_view_detection.schema_valid is false")
        return evidence

    layout_errors = validate_layout_consistency(dimension_extraction, top_view_detection)
    if layout_errors:
        evidence["failure_reasons"].extend(layout_errors)
        return evidence

    layout, _ = validate_l_shaped_layout(dimension_extraction.get("layout"), context="dimension_extraction.layout")
    if layout is None:
        evidence["failure_reasons"].append("dimension_extraction.layout is invalid")
        return evidence
    occupied_slots = occupied_slots_from_layout(layout)

    dimension_views, dimension_view_errors = _validate_views(
        dimension_extraction.get("views"),
        occupied_slots=occupied_slots,
        context="dimension_extraction",
        require_dimensions=True,
    )
    top_view_views, top_view_errors = _validate_views(
        top_view_detection.get("views"),
        occupied_slots=occupied_slots,
        context="top_view_detection",
        require_dimensions=False,
    )
    if dimension_view_errors or top_view_errors:
        evidence["failure_reasons"].extend(dimension_view_errors)
        evidence["failure_reasons"].extend(top_view_errors)
        return evidence

    top_view_slot = top_view_detection.get("top_view_slot")
    if not is_valid_slot(top_view_slot):
        evidence["failure_reasons"].append("top_view_detection.top_view_slot must be a valid slot")
        return evidence
    if top_view_slot not in occupied_slots:
        evidence["failure_reasons"].append("top_view_detection.top_view_slot must be one of the occupied slots")
        return evidence

    if dimension_extraction.get("schema_valid") is False and dimension_extraction.get("ocr_schema_valid") is True:
        evidence["warnings"].append("dimension_extraction_schema_invalid_but_ocr_layout_valid")
    if dimension_extraction.get("bbox_output_valid") is False:
        evidence["warnings"].append("dimension_extraction_bbox_output_invalid")
    if top_view_detection.get("schema_valid") is False and top_view_topology_valid:
        evidence["warnings"].append("top_view_detection_schema_invalid_but_topology_valid")
    if top_view_detection.get("bbox_output_valid") is False:
        evidence["warnings"].append("top_view_detection_bbox_output_invalid")

    evidence.update(
        {
            "status": "valid",
            "layout": layout,
            "occupied_slots": occupied_slots,
            "top_view_slot": top_view_slot,
            "views": dimension_views,
            "top_view_views": top_view_views,
            "dimensions": flatten_dimensions({"views": dimension_views}),
            "failure_reasons": [],
        }
    )
    return evidence
