from __future__ import annotations

import json
from typing import Any


TASK_NAME = "direct_extraction"
TARGET_KEYS = (
    "body_long_side",
    "body_short_side",
    "maximum_terminal_to_terminal_span",
    "overall_package_height",
)


class DirectExtractionSchemaError(Exception):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_direct_output(data: Any, *, context: str = "output") -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, [f"{context} must be a JSON object"]

    expected = set(TARGET_KEYS)
    actual = set(data)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{context} missing keys: {missing}")
    if extra:
        errors.append(f"{context} unexpected keys: {extra}")

    normalized: dict[str, float | int | None] = {}
    for key in TARGET_KEYS:
        value = data.get(key)
        if value is None:
            normalized[key] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{context}.{key} must be a number or null")
        else:
            normalized[key] = value

    if errors:
        return None, errors
    return normalized, []


def normalize_prediction(data: Any) -> tuple[dict[str, Any] | None, list[str]]:
    normalized, errors = validate_direct_output(data)
    if normalized is None:
        return None, errors
    return {
        "prompt_name": "extract_number",
        "schema_valid": True,
        "targets": {
            key: {
                "value": normalized[key],
                "raw_value": normalized[key],
            }
            for key in TARGET_KEYS
        },
        "parse_error": None,
        "validation_errors": [],
    }, []


def normalize_expected(data: Any) -> tuple[dict[str, Any] | None, list[str]]:
    return validate_direct_output(data, context="ground_truth")


def compare_outputs(predicted: Any, expected: Any) -> dict[str, Any]:
    predicted_norm, predicted_errors = validate_direct_output(predicted)
    expected_norm, expected_errors = validate_direct_output(expected, context="ground_truth")
    if expected_errors:
        raise DirectExtractionSchemaError(f"Ground truth failed validation: {expected_errors}")

    field_matches = {key: False for key in TARGET_KEYS}
    if predicted_norm is None:
        return {
            "schema_valid": False,
            "validation_errors": predicted_errors,
            "field_matches": field_matches,
            "matched_field_count": 0,
            "field_count": len(TARGET_KEYS),
            "field_match_rate": 0.0,
            "exact_match": False,
            "normalized_output": None,
        }

    field_matches = {
        key: predicted_norm[key] == expected_norm[key]
        for key in TARGET_KEYS
    }
    matched_field_count = sum(1 for matched in field_matches.values() if matched)
    field_count = len(TARGET_KEYS)
    return {
        "schema_valid": True,
        "validation_errors": [],
        "field_matches": field_matches,
        "matched_field_count": matched_field_count,
        "field_count": field_count,
        "field_match_rate": matched_field_count / field_count,
        "exact_match": matched_field_count == field_count,
        "normalized_output": predicted_norm,
    }


def load_answer_map(ground_truth_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = ground_truth_payload.get("answer_groups")
    if not isinstance(groups, list):
        raise DirectExtractionSchemaError("Ground truth file must contain an `answer_groups` array")
    mapping: dict[str, dict[str, Any]] = {}
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise DirectExtractionSchemaError(f"answer_groups[{index}] must be an object")
        answer_key = group.get("answer_key")
        if not isinstance(answer_key, str) or not answer_key:
            raise DirectExtractionSchemaError(f"answer_groups[{index}].answer_key must be a non-empty string")
        mapping[answer_key] = group
    return mapping
