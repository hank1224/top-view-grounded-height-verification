from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from top_view_grounded_height_verification.common.io_utils import ROOT


NormalizeFn = Callable[[Any], tuple[Optional[dict[str, Any]], list[str]]]
CompareFn = Callable[[Any, Any], dict[str, Any]]
LoadAnswerMapFn = Callable[[dict[str, Any]], dict[str, dict[str, Any]]]


@dataclass(frozen=True)
class Stage1TaskSpec:
    task_name: str
    cases_path: Path
    ground_truth_path: Path
    output_root: Path
    schema_module: str

    @property
    def normalize_prediction(self) -> NormalizeFn:
        return getattr(importlib.import_module(self.schema_module), "normalize_prediction")

    @property
    def compare_outputs(self) -> CompareFn:
        return getattr(importlib.import_module(self.schema_module), "compare_outputs")

    @property
    def load_answer_map(self) -> LoadAnswerMapFn:
        return getattr(importlib.import_module(self.schema_module), "load_answer_map")


TASK_SPECS = {
    "direct_extraction": Stage1TaskSpec(
        task_name="direct_extraction",
        cases_path=ROOT / "data" / "tasks" / "direct_extraction" / "cases.json",
        ground_truth_path=ROOT / "data" / "tasks" / "direct_extraction" / "ground_truth.json",
        output_root=ROOT / "runs" / "stage1" / "direct_extraction",
        schema_module="top_view_grounded_height_verification.stage1.direct_extraction.schema",
    ),
    "dimension_extraction": Stage1TaskSpec(
        task_name="dimension_extraction",
        cases_path=ROOT / "data" / "tasks" / "dimension_extraction" / "cases.json",
        ground_truth_path=ROOT / "data" / "tasks" / "dimension_extraction" / "ground_truth.json",
        output_root=ROOT / "runs" / "stage1" / "dimension_extraction",
        schema_module="top_view_grounded_height_verification.stage1.dimension_extraction.schema",
    ),
    "top_view_detection": Stage1TaskSpec(
        task_name="top_view_detection",
        cases_path=ROOT / "data" / "tasks" / "top_view_detection" / "cases.json",
        ground_truth_path=ROOT / "data" / "tasks" / "top_view_detection" / "ground_truth.json",
        output_root=ROOT / "runs" / "stage1" / "top_view_detection",
        schema_module="top_view_grounded_height_verification.stage1.top_view_detection.schema",
    ),
}


def get_task_spec(task_name: str) -> Stage1TaskSpec:
    try:
        return TASK_SPECS[task_name]
    except KeyError as exc:
        supported = ", ".join(sorted(TASK_SPECS))
        raise ValueError(f"Unsupported Stage 1 task `{task_name}`. Supported tasks: {supported}") from exc
