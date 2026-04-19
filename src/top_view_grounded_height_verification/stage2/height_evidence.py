from __future__ import annotations

from typing import Any

from top_view_grounded_height_verification.core.geometry import (
    VALID_ORIENTATIONS,
    adjacency_relation,
    are_adjacent,
    ordered_slots,
)


def _empty_result(evidence: dict[str, Any], failure_reasons: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "tvghv-height-evidence-result-v1.0",
        "height_evidence_status": "insufficient",
        "top_view_slot": evidence.get("top_view_slot"),
        "z_orientation_by_slot": {},
        "supporting_dimensions": [],
        "ruled_out_dimensions": [],
        "unresolved_dimensions": [],
        "verification_readiness": {
            "status": "not_ready",
            "reasons": failure_reasons or ["height_evidence_insufficient"],
        },
        "global_evidence_chain": [],
        "failure_reasons": failure_reasons,
    }


def _direct_orientation_detail(top_view_slot: str, slot: str, relation: str) -> dict[str, Any]:
    return {
        "slot": slot,
        "z_orientation": relation,
        "grounding_type": "direct_top_view_neighbor",
        "propagated_from_slot": None,
        "rule": f"top_view_{relation}_neighbor_defines_z_orientation",
        "evidence_chain": [
            {
                "rule": f"top_view_{relation}_neighbor_defines_z_orientation",
                "from_slot": top_view_slot,
                "to_slot": slot,
                "z_orientation": relation,
            }
        ],
    }


def infer_direct_z_orientation_by_slot(evidence: dict[str, Any]) -> dict[str, str]:
    top_view_slot = evidence.get("top_view_slot")
    direct: dict[str, str] = {}
    if not isinstance(top_view_slot, str):
        return direct
    for slot in evidence.get("occupied_slots", []):
        if slot == top_view_slot:
            continue
        relation = adjacency_relation(top_view_slot, slot)
        if relation in VALID_ORIENTATIONS:
            direct[slot] = relation
    return direct


def _infer_direct_orientation_details(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    top_view_slot = evidence.get("top_view_slot")
    details: dict[str, dict[str, Any]] = {}
    if not isinstance(top_view_slot, str):
        return details
    for slot in evidence.get("occupied_slots", []):
        if slot == top_view_slot:
            continue
        relation = adjacency_relation(top_view_slot, slot)
        if relation in VALID_ORIENTATIONS:
            details[slot] = _direct_orientation_detail(top_view_slot, slot, relation)
    return details


def propagate_z_orientation_between_non_top_views(
    evidence: dict[str, Any],
    direct_orientations: dict[str, str],
) -> dict[str, str]:
    details = {
        slot: {
            "z_orientation": orientation,
            "evidence_chain": [],
        }
        for slot, orientation in direct_orientations.items()
    }
    propagated = _propagate_orientation_details(evidence, details)
    return {
        slot: detail["z_orientation"]
        for slot, detail in propagated.items()
    }


def _propagate_orientation_details(
    evidence: dict[str, Any],
    orientation_details: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    top_view_slot = evidence.get("top_view_slot")
    occupied_slots = [slot for slot in evidence.get("occupied_slots", []) if slot != top_view_slot]
    changed = True
    while changed:
        changed = False
        for slot in occupied_slots:
            if slot in orientation_details:
                continue
            candidate_sources = [
                source
                for source in ordered_slots(set(orientation_details))
                if source != top_view_slot and are_adjacent(source, slot)
            ]
            if not candidate_sources:
                continue
            source = candidate_sources[0]
            source_detail = orientation_details[source]
            z_orientation = source_detail["z_orientation"]
            chain_step = {
                "rule": "non_top_view_inherits_z_axis_orientation_from_grounded_neighbor",
                "from_slot": source,
                "to_slot": slot,
                "z_orientation": z_orientation,
            }
            orientation_details[slot] = {
                "slot": slot,
                "z_orientation": z_orientation,
                "grounding_type": "propagated_from_non_top_view",
                "propagated_from_slot": source,
                "rule": "non_top_view_inherits_z_axis_orientation_from_grounded_neighbor",
                "evidence_chain": list(source_detail.get("evidence_chain", [])) + [chain_step],
            }
            changed = True
    return orientation_details


def _bucket_record(
    dimension: dict[str, Any],
    *,
    orientation_detail: dict[str, Any] | None,
    rule: str,
    grounding_type: str | None = None,
) -> dict[str, Any]:
    return {
        "dimension_uid": dimension.get("dimension_uid"),
        "value": dimension.get("value"),
        "numeric_value": dimension.get("numeric_value"),
        "belongs_to_slot": dimension.get("belongs_to_slot"),
        "dimension_line_orientation": dimension.get("orientation"),
        "z_axis_orientation_for_slot": (
            orientation_detail.get("z_orientation") if isinstance(orientation_detail, dict) else None
        ),
        "grounding_type": grounding_type or (
            orientation_detail.get("grounding_type") if isinstance(orientation_detail, dict) else None
        ),
        "propagated_from_slot": (
            orientation_detail.get("propagated_from_slot") if isinstance(orientation_detail, dict) else None
        ),
        "rule": rule,
        "evidence_chain": list(orientation_detail.get("evidence_chain", [])) if isinstance(orientation_detail, dict) else [],
        "valid": dimension.get("valid", True),
        "invalid_reasons": list(dimension.get("invalid_reasons", [])),
    }


def classify_dimensions_for_height(
    evidence: dict[str, Any],
    z_orientation_by_slot: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    orientation_details = _orientation_details_from_map(evidence, z_orientation_by_slot)
    return _classify_dimensions_with_details(evidence, orientation_details)


def _orientation_details_from_map(evidence: dict[str, Any], z_orientation_by_slot: dict[str, str]) -> dict[str, dict[str, Any]]:
    top_view_slot = evidence.get("top_view_slot")
    details: dict[str, dict[str, Any]] = {}
    for slot, orientation in z_orientation_by_slot.items():
        relation = adjacency_relation(top_view_slot, slot) if isinstance(top_view_slot, str) else "invalid"
        if relation in VALID_ORIENTATIONS and relation == orientation:
            details[slot] = _direct_orientation_detail(top_view_slot, slot, orientation)
        else:
            details[slot] = {
                "slot": slot,
                "z_orientation": orientation,
                "grounding_type": "propagated_from_non_top_view",
                "propagated_from_slot": None,
                "rule": "non_top_view_inherits_z_axis_orientation_from_grounded_neighbor",
                "evidence_chain": [],
            }
    return details


def _classify_dimensions_with_details(
    evidence: dict[str, Any],
    orientation_details: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    top_view_slot = evidence.get("top_view_slot")
    supporting: list[dict[str, Any]] = []
    ruled_out: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for dimension in evidence.get("dimensions", []):
        if not isinstance(dimension, dict):
            continue
        slot = dimension.get("belongs_to_slot")
        if slot == top_view_slot:
            ruled_out.append(
                _bucket_record(
                    dimension,
                    orientation_detail=None,
                    rule="top_view_dimensions_are_excluded_from_z_axis_grounding",
                    grounding_type="top_view_dimension_excluded",
                )
            )
            continue
        if not dimension.get("valid", True):
            unresolved.append(
                _bucket_record(
                    dimension,
                    orientation_detail=orientation_details.get(slot),
                    rule="dimension_local_evidence_invalid",
                )
            )
            continue
        orientation_detail = orientation_details.get(slot)
        if not orientation_detail:
            unresolved.append(
                _bucket_record(
                    dimension,
                    orientation_detail=None,
                    rule="slot_z_orientation_unresolved",
                )
            )
            continue
        if dimension.get("orientation") == orientation_detail.get("z_orientation"):
            supporting.append(
                _bucket_record(
                    dimension,
                    orientation_detail=orientation_detail,
                    rule=orientation_detail.get("rule", "dimension_orientation_matches_slot_z_axis"),
                )
            )
        else:
            ruled_out.append(
                _bucket_record(
                    dimension,
                    orientation_detail=orientation_detail,
                    rule="dimension_orientation_inconsistent_with_slot_z_axis",
                )
            )

    return {
        "supporting_dimensions": supporting,
        "ruled_out_dimensions": ruled_out,
        "unresolved_dimensions": unresolved,
    }


def evaluate_verification_readiness(height_evidence_result: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if height_evidence_result.get("height_evidence_status") != "constructed":
        reasons.append("height_evidence_not_constructed")
    if not height_evidence_result.get("supporting_dimensions"):
        reasons.append("no_supporting_dimensions")
    numeric_supporting = [
        dimension
        for dimension in height_evidence_result.get("supporting_dimensions", [])
        if dimension.get("numeric_value") is not None
    ]
    if not numeric_supporting:
        reasons.append("no_numeric_supporting_dimensions")

    expected_non_top_slots = set(height_evidence_result.get("expected_non_top_slots", []))
    oriented_slots = set(height_evidence_result.get("z_orientation_by_slot", {}))
    unresolved_slots = expected_non_top_slots - oriented_slots
    if unresolved_slots:
        reasons.append("unresolved_non_top_view_orientation")

    unresolved_dimensions = height_evidence_result.get("unresolved_dimensions", [])
    if unresolved_dimensions:
        reasons.append("unresolved_dimensions_present")
    if height_evidence_result.get("unit_comparability") == "unknown":
        reasons.append("unit_comparability_unknown")

    if reasons:
        return {
            "status": "not_ready",
            "reasons": reasons,
        }
    return {
        "status": "ready",
        "reasons": [],
    }


def build_height_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    if evidence.get("status") != "valid":
        return _empty_result(evidence, ["evidence_fusion_invalid", *evidence.get("failure_reasons", [])])

    top_view_slot = evidence.get("top_view_slot")
    occupied_slots = evidence.get("occupied_slots", [])
    if not isinstance(top_view_slot, str) or top_view_slot not in occupied_slots:
        return _empty_result(evidence, ["top_view_slot_invalid"])

    orientation_details = _infer_direct_orientation_details(evidence)
    orientation_details = _propagate_orientation_details(evidence, orientation_details)
    z_orientation_by_slot = {
        slot: detail["z_orientation"]
        for slot, detail in ((slot, orientation_details[slot]) for slot in ordered_slots(set(orientation_details)))
    }
    expected_non_top_slots = [slot for slot in occupied_slots if slot != top_view_slot]
    if not z_orientation_by_slot:
        return _empty_result(evidence, ["no_reliable_z_orientation"])

    buckets = _classify_dimensions_with_details(evidence, orientation_details)
    supporting = buckets["supporting_dimensions"]
    numeric_supporting = [dimension for dimension in supporting if dimension.get("numeric_value") is not None]
    if not supporting:
        result = {
            "schema_version": "tvghv-height-evidence-result-v1.0",
            "height_evidence_status": "insufficient",
            "top_view_slot": top_view_slot,
            "z_orientation_by_slot": z_orientation_by_slot,
            **buckets,
            "verification_readiness": {"status": "not_ready", "reasons": ["no_supporting_dimensions"]},
            "global_evidence_chain": _global_evidence_chain(orientation_details),
            "failure_reasons": ["no_supporting_dimensions"],
            "expected_non_top_slots": expected_non_top_slots,
            "unit_comparability": "dataset_default_consistent",
        }
        return result
    if not numeric_supporting:
        result = {
            "schema_version": "tvghv-height-evidence-result-v1.0",
            "height_evidence_status": "insufficient",
            "top_view_slot": top_view_slot,
            "z_orientation_by_slot": z_orientation_by_slot,
            **buckets,
            "verification_readiness": {"status": "not_ready", "reasons": ["no_numeric_supporting_dimensions"]},
            "global_evidence_chain": _global_evidence_chain(orientation_details),
            "failure_reasons": ["no_numeric_supporting_dimensions"],
            "expected_non_top_slots": expected_non_top_slots,
            "unit_comparability": "dataset_default_consistent",
        }
        return result

    result = {
        "schema_version": "tvghv-height-evidence-result-v1.0",
        "height_evidence_status": "constructed",
        "top_view_slot": top_view_slot,
        "z_orientation_by_slot": z_orientation_by_slot,
        **buckets,
        "verification_readiness": {"status": "not_ready", "reasons": []},
        "global_evidence_chain": _global_evidence_chain(orientation_details),
        "failure_reasons": [],
        "expected_non_top_slots": expected_non_top_slots,
        "unit_comparability": "dataset_default_consistent",
    }
    result["verification_readiness"] = evaluate_verification_readiness(result)
    return result


def _global_evidence_chain(orientation_details: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for slot in ordered_slots(set(orientation_details)):
        for step in orientation_details[slot].get("evidence_chain", []):
            key = tuple(sorted(step.items()))
            if key in seen:
                continue
            seen.add(key)
            chain.append(step)
    return chain
