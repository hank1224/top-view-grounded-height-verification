from __future__ import annotations

import copy
from typing import Any


def canonical_payload() -> dict[str, Any]:
    return {
        "schema_version": "tvghv-evidence-bundle-v0.2",
        "image_id": "pkg__canonical-values",
        "image_path": "data/package_drawings/images/pkg/canonical-values.png",
        "package_name": "Package",
        "package_slug": "pkg",
        "shape_class": "unit_shape",
        "variant_name": "Canonical + Values",
        "variant_slug": "canonical-values",
        "evidence_sources": {
            "direct_extraction": {"provider": "unit"},
            "dimension_extraction": {"provider": "unit"},
            "top_view_detection": {"provider": "unit"},
        },
        "direct_extraction": {
            "prompt_name": "extract_number",
            "schema_valid": True,
            "targets": {
                "body_long_side": {"value": 4.86, "raw_value": 4.86},
                "body_short_side": {"value": 3.55, "raw_value": 3.55},
                "maximum_terminal_to_terminal_span": {"value": 5.3, "raw_value": 5.3},
                "overall_package_height": {"value": 2.15, "raw_value": 2.15},
            },
            "parse_error": None,
            "validation_errors": [],
        },
        "dimension_extraction": {
            "schema_valid": True,
            "ocr_schema_valid": True,
            "bbox_output_valid": True,
            "layout": {
                "upper_left": 1,
                "upper_right": 0,
                "lower_left": 1,
                "lower_right": 1,
            },
            "views": [
                {
                    "slot": "upper_left",
                    "bounding_box_2d": [0, 0, 400, 400],
                    "dimensions": [
                        {"value": "4.86", "numeric_value": 4.86, "orientation": "horizontal", "belongs_to_slot": "upper_left"},
                        {"value": "3.55", "numeric_value": 3.55, "orientation": "vertical", "belongs_to_slot": "upper_left"},
                    ],
                },
                {
                    "slot": "lower_left",
                    "bounding_box_2d": [500, 0, 900, 400],
                    "dimensions": [
                        {"value": "5.3", "numeric_value": 5.3, "orientation": "horizontal", "belongs_to_slot": "lower_left"},
                        {"value": ".22", "numeric_value": 0.22, "orientation": "vertical", "belongs_to_slot": "lower_left"},
                    ],
                },
                {
                    "slot": "lower_right",
                    "bounding_box_2d": [500, 500, 900, 900],
                    "dimensions": [
                        {"value": "2.15", "numeric_value": 2.15, "orientation": "vertical", "belongs_to_slot": "lower_right"},
                        {"value": "2", "numeric_value": 2.0, "orientation": "horizontal", "belongs_to_slot": "lower_right"},
                    ],
                },
            ],
            "parse_error": None,
            "validation_errors": [],
            "bbox_validation_errors": [],
        },
        "top_view_detection": {
            "schema_valid": True,
            "layout": {
                "upper_left": 1,
                "upper_right": 0,
                "lower_left": 1,
                "lower_right": 1,
            },
            "views": [
                {"slot": "upper_left", "bounding_box_2d": [0, 0, 400, 400]},
                {"slot": "lower_left", "bounding_box_2d": [500, 0, 900, 400]},
                {"slot": "lower_right", "bounding_box_2d": [500, 500, 900, 900]},
            ],
            "top_view_slot": "upper_left",
            "parse_error": None,
            "validation_errors": [],
        },
        "ground_truth": {
            "dimension_ground_truth": {
                "layout": {
                    "upper_left": 1,
                    "upper_right": 0,
                    "lower_left": 1,
                    "lower_right": 1,
                },
                "views": [
                    {
                        "slot": "upper_left",
                        "dimensions": [
                            {"value": "4.86", "orientation": "horizontal", "belongs_to_slot": "upper_left"},
                            {"value": "3.55", "orientation": "vertical", "belongs_to_slot": "upper_left"},
                        ],
                    },
                    {
                        "slot": "lower_left",
                        "dimensions": [
                            {"value": "5.3", "orientation": "horizontal", "belongs_to_slot": "lower_left"},
                            {"value": ".22", "orientation": "vertical", "belongs_to_slot": "lower_left"},
                        ],
                    },
                    {
                        "slot": "lower_right",
                        "dimensions": [
                            {"value": "2.15", "orientation": "vertical", "belongs_to_slot": "lower_right"},
                            {"value": "2", "orientation": "horizontal", "belongs_to_slot": "lower_right"},
                        ],
                    },
                ],
            },
            "top_view_ground_truth": {
                "layout": {
                    "upper_left": 1,
                    "upper_right": 0,
                    "lower_left": 1,
                    "lower_right": 1,
                },
                "views": [
                    {"slot": "upper_left"},
                    {"slot": "lower_left"},
                    {"slot": "lower_right"},
                ],
                "top_view_slot": "upper_left",
            },
            "direct_ground_truth": {
                "body_long_side": 4.86,
                "body_short_side": 3.55,
                "maximum_terminal_to_terminal_span": 5.3,
                "overall_package_height": 2.15,
            },
            "evaluation_metadata": {"nuisance_dimensions": 2},
        },
    }


def rotated_payload() -> dict[str, Any]:
    payload = canonical_payload()
    payload = copy.deepcopy(payload)
    payload["image_id"] = "pkg__rotated-values"
    payload["variant_name"] = "Rotated + Values"
    payload["variant_slug"] = "rotated-values"
    layout = {
        "upper_left": 1,
        "upper_right": 1,
        "lower_left": 1,
        "lower_right": 0,
    }
    payload["dimension_extraction"]["layout"] = layout
    payload["top_view_detection"]["layout"] = layout
    payload["dimension_extraction"]["views"] = [
        {
            "slot": "upper_left",
            "bounding_box_2d": [0, 0, 400, 400],
            "dimensions": [
                {"value": "4.86", "numeric_value": 4.86, "orientation": "horizontal", "belongs_to_slot": "upper_left"},
                {"value": "3.55", "numeric_value": 3.55, "orientation": "vertical", "belongs_to_slot": "upper_left"},
            ],
        },
        {
            "slot": "upper_right",
            "bounding_box_2d": [0, 500, 400, 900],
            "dimensions": [
                {"value": "2.15", "numeric_value": 2.15, "orientation": "horizontal", "belongs_to_slot": "upper_right"},
                {"value": "2", "numeric_value": 2.0, "orientation": "vertical", "belongs_to_slot": "upper_right"},
            ],
        },
        {
            "slot": "lower_left",
            "bounding_box_2d": [500, 0, 900, 400],
            "dimensions": [
                {"value": "5.3", "numeric_value": 5.3, "orientation": "horizontal", "belongs_to_slot": "lower_left"},
                {"value": ".22", "numeric_value": 0.22, "orientation": "vertical", "belongs_to_slot": "lower_left"},
            ],
        },
    ]
    payload["top_view_detection"]["views"] = [
        {"slot": "upper_left", "bounding_box_2d": [0, 0, 400, 400]},
        {"slot": "upper_right", "bounding_box_2d": [0, 500, 400, 900]},
        {"slot": "lower_left", "bounding_box_2d": [500, 0, 900, 400]},
    ]
    payload["ground_truth"]["dimension_ground_truth"]["layout"] = layout
    payload["ground_truth"]["top_view_ground_truth"]["layout"] = layout
    payload["ground_truth"]["dimension_ground_truth"]["views"] = [
        {"slot": "upper_left", "dimensions": payload["dimension_extraction"]["views"][0]["dimensions"]},
        {"slot": "upper_right", "dimensions": payload["dimension_extraction"]["views"][1]["dimensions"]},
        {"slot": "lower_left", "dimensions": payload["dimension_extraction"]["views"][2]["dimensions"]},
    ]
    payload["ground_truth"]["top_view_ground_truth"]["views"] = [
        {"slot": "upper_left"},
        {"slot": "upper_right"},
        {"slot": "lower_left"},
    ]
    return payload


def set_height_answer(payload: dict[str, Any], value: Any) -> dict[str, Any]:
    updated = copy.deepcopy(payload)
    updated["direct_extraction"]["targets"]["overall_package_height"]["value"] = value
    updated["direct_extraction"]["targets"]["overall_package_height"]["raw_value"] = value
    return updated
