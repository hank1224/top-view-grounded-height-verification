from __future__ import annotations

from typing import Any

from top_view_grounded_height_verification.core.numeric import DEFAULT_TOLERANCE, parse_dimension_value, values_equal


VERIFIED_TARGET = "overall_package_height"


def _numeric_dimensions(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dimension
        for dimension in dimensions
        if isinstance(dimension, dict) and dimension.get("numeric_value") is not None
    ]


def _all_dimension_buckets(height_evidence_result: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        list(height_evidence_result.get("supporting_dimensions", []))
        + list(height_evidence_result.get("ruled_out_dimensions", []))
        + list(height_evidence_result.get("unresolved_dimensions", []))
    )


def _matching_dimensions(
    dimensions: list[dict[str, Any]],
    value: float,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[dict[str, Any]]:
    return [
        dimension
        for dimension in _numeric_dimensions(dimensions)
        if values_equal(dimension.get("numeric_value"), value, tolerance=tolerance)
    ]


def _empty_result(
    *,
    decision: str,
    model_value: float | None,
    derived_height_value: float | None,
    failure_reasons: list[str],
    matched_supporting: list[dict[str, Any]] | None = None,
    contradicting: list[dict[str, Any]] | None = None,
    rejecting_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    matched_supporting = matched_supporting or []
    contradicting = contradicting or []
    rejecting_evidence = rejecting_evidence or []
    return {
        "schema_version": "tvghv-screening-result-v1.0",
        "screening_status": "reported",
        "decision": decision,
        "verified_target": VERIFIED_TARGET,
        "model_value": model_value,
        "derived_height_value": derived_height_value,
        "derivation_rule": "max_supporting_dimension_numeric_value" if derived_height_value is not None else None,
        "matched_supporting_dimension_uids": [
            dimension.get("dimension_uid") for dimension in matched_supporting
        ],
        "matched_supporting_dimension_values": [
            dimension.get("value") for dimension in matched_supporting
        ],
        "contradicting_dimension_uids": [
            dimension.get("dimension_uid") for dimension in contradicting
        ],
        "rejecting_evidence": rejecting_evidence,
        "evidence_chain": _combined_evidence_chain(matched_supporting),
        "failure_reasons": failure_reasons,
    }


def _combined_evidence_chain(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for dimension in dimensions:
        for step in dimension.get("evidence_chain", []):
            if not isinstance(step, dict):
                continue
            key = tuple(sorted(step.items()))
            if key in seen:
                continue
            seen.add(key)
            chain.append(step)
    return chain


def _extract_model_height(direct_extraction: dict[str, Any]) -> tuple[float | None, list[str]]:
    target = direct_extraction.get("targets", {}).get(VERIFIED_TARGET)
    if not isinstance(target, dict):
        return None, [f"direct_extraction.targets.{VERIFIED_TARGET} is missing"]
    model_value = parse_dimension_value(target.get("value"))
    if model_value is None:
        return None, [f"direct_extraction.targets.{VERIFIED_TARGET}.value is not numeric"]
    return model_value, []


def derive_height_from_supporting_dimensions(supporting_dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_supporting = _numeric_dimensions(supporting_dimensions)
    if not numeric_supporting:
        return {
            "derived_height_value": None,
            "supporting_dimensions": [],
            "failure_reasons": ["no_numeric_supporting_dimensions"],
        }
    max_value = max(float(dimension["numeric_value"]) for dimension in numeric_supporting)
    matched = [
        dimension
        for dimension in numeric_supporting
        if values_equal(dimension.get("numeric_value"), max_value)
    ]
    return {
        "derived_height_value": max_value,
        "supporting_dimensions": matched,
        "failure_reasons": [],
    }


def compare_model_height_with_derived_height(model_value: float, derived_value: float) -> str:
    return "equal" if values_equal(model_value, derived_value) else "different"


def screen_height_answer(
    direct_extraction: dict[str, Any],
    height_evidence_result: dict[str, Any],
) -> dict[str, Any]:
    model_value, model_errors = _extract_model_height(direct_extraction if isinstance(direct_extraction, dict) else {})
    readiness = height_evidence_result.get("verification_readiness", {})
    prereq_errors: list[str] = []
    if height_evidence_result.get("height_evidence_status") != "constructed":
        prereq_errors.append("height_evidence_not_constructed")
    if not isinstance(readiness, dict) or readiness.get("status") != "ready":
        prereq_errors.append("verification_not_ready")
        prereq_errors.extend(readiness.get("reasons", []) if isinstance(readiness, dict) else [])
    if model_errors:
        return _empty_result(
            decision="insufficient_evidence",
            model_value=model_value,
            derived_height_value=None,
            failure_reasons=[*prereq_errors, *model_errors],
        )
    if prereq_errors:
        return _empty_result(
            decision="insufficient_evidence",
            model_value=model_value,
            derived_height_value=None,
            failure_reasons=prereq_errors,
        )

    supporting_dimensions = list(height_evidence_result.get("supporting_dimensions", []))
    ruled_out_dimensions = list(height_evidence_result.get("ruled_out_dimensions", []))
    derived = derive_height_from_supporting_dimensions(supporting_dimensions)
    derived_height_value = derived["derived_height_value"]
    if derived_height_value is None:
        return _empty_result(
            decision="insufficient_evidence",
            model_value=model_value,
            derived_height_value=None,
            failure_reasons=derived["failure_reasons"],
        )

    all_numeric_dimensions = _numeric_dimensions(_all_dimension_buckets(height_evidence_result))
    if not _matching_dimensions(all_numeric_dimensions, model_value):
        return _empty_result(
            decision="insufficient_evidence",
            model_value=model_value,
            derived_height_value=derived_height_value,
            failure_reasons=["model_value_not_found_in_ocr_dimension_values"],
        )

    max_support_matches = _matching_dimensions(supporting_dimensions, derived_height_value)
    model_support_matches = _matching_dimensions(supporting_dimensions, model_value)
    if values_equal(model_value, derived_height_value):
        if not any(match.get("evidence_chain") for match in max_support_matches):
            return _empty_result(
                decision="insufficient_evidence",
                model_value=model_value,
                derived_height_value=derived_height_value,
                matched_supporting=max_support_matches,
                failure_reasons=["matched_supporting_dimension_missing_evidence_chain"],
            )
        return _empty_result(
            decision="supported",
            model_value=model_value,
            derived_height_value=derived_height_value,
            matched_supporting=max_support_matches,
            failure_reasons=[],
        )

    ruled_out_matches = _matching_dimensions(ruled_out_dimensions, model_value)
    if ruled_out_matches:
        return _empty_result(
            decision="contradicted",
            model_value=model_value,
            derived_height_value=derived_height_value,
            contradicting=ruled_out_matches,
            rejecting_evidence=[
                {
                    "rule": "model_value_matches_ruled_out_dimension",
                    "dimension_uid": dimension.get("dimension_uid"),
                    "value": dimension.get("value"),
                    "numeric_value": dimension.get("numeric_value"),
                }
                for dimension in ruled_out_matches
            ],
            failure_reasons=[],
        )

    if model_support_matches:
        return _empty_result(
            decision="contradicted",
            model_value=model_value,
            derived_height_value=derived_height_value,
            matched_supporting=model_support_matches,
            contradicting=model_support_matches,
            rejecting_evidence=[
                {
                    "rule": "model_value_is_supporting_dimension_but_not_maximum",
                    "dimension_uid": dimension.get("dimension_uid"),
                    "value": dimension.get("value"),
                    "numeric_value": dimension.get("numeric_value"),
                    "derived_height_value": derived_height_value,
                }
                for dimension in model_support_matches
            ],
            failure_reasons=[],
        )

    return _empty_result(
        decision="insufficient_evidence",
        model_value=model_value,
        derived_height_value=derived_height_value,
        failure_reasons=["model_value_not_classified_against_height_evidence"],
    )
