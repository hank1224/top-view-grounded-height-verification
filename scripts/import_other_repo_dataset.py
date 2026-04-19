#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from top_view_grounded_height_verification.stage1.dimension_extraction.schema import validate_dimension_output  # noqa: E402
from top_view_grounded_height_verification.stage1.direct_extraction.schema import validate_direct_output  # noqa: E402
from top_view_grounded_height_verification.stage1.top_view_detection.schema import validate_top_view_output  # noqa: E402


SOURCE_ROOT = ROOT / "other_repo" / "test_0402"
SOURCE_DATA = SOURCE_ROOT / "data"
SOURCE_TASKS = SOURCE_DATA / "tasks"
TARGET_DATASET = ROOT / "data" / "package_drawings"
TARGET_TASKS = ROOT / "data" / "tasks"
VALUE_VARIANTS = {"canonical-values", "rotated-values"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_value_images() -> list[dict[str, Any]]:
    manifest_path = SOURCE_DATA / "package_drawings" / "image_manifest.json"
    payload = read_json(manifest_path)
    images = [
        {
            "image_id": image["image_id"],
            "package_name": image["package_name"],
            "package_slug": image["package_slug"],
            "kicad_model_name": image["kicad_model_name"],
            "shape_class": image["shape_class"],
            "variant_name": image["variant_name"],
            "variant_slug": image["variant_slug"],
            "image_path": image["image_path"],
        }
        for image in payload["images"]
        if image.get("variant_slug") in VALUE_VARIANTS
    ]
    images.sort(key=lambda item: item["image_id"])
    if len(images) != 30:
        raise RuntimeError(f"Expected 30 value images, found {len(images)}")
    return images


def image_lookup(images: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {image["image_id"]: image for image in images}


def rebuild_image_dataset(images: list[dict[str, Any]]) -> None:
    if TARGET_DATASET.exists():
        shutil.rmtree(TARGET_DATASET)
    (TARGET_DATASET / "images").mkdir(parents=True)

    for image in images:
        source_path = SOURCE_ROOT / image["image_path"]
        target_path = ROOT / image["image_path"]
        if not source_path.exists():
            raise RuntimeError(f"Missing source image: {source_rel(source_path)}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)

    manifest = {
        "dataset_name": "package_drawings",
        "schema_version": 2,
        "generated_at_utc": now_utc(),
        "source_manifest": source_rel(SOURCE_DATA / "package_drawings" / "image_manifest.json"),
        "image_count": len(images),
        "images": images,
    }
    write_json(TARGET_DATASET / "image_manifest.json", manifest)

    fieldnames = [
        "image_id",
        "package_name",
        "package_slug",
        "kicad_model_name",
        "shape_class",
        "variant_name",
        "variant_slug",
        "image_path",
    ]
    with (TARGET_DATASET / "image_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(images)

    package_count = len({image["package_slug"] for image in images})
    shape_classes = sorted({image["shape_class"] for image in images})
    readme = f"""# Package Drawings Dataset

This directory contains the value-only package drawing dataset imported from:

```text
{source_rel(SOURCE_ROOT)}
```

It contains {package_count} package types with two numeric value variants each:

- `canonical-values`
- `rotated-values`

That gives {len(images)} images total. ID-only variants and raw Notion export files are not copied because the verifier pipeline only consumes numeric value images.

Each image manifest row includes package-level `shape_class` metadata. Current classes:

{chr(10).join(f"- `{shape_class}`" for shape_class in shape_classes)}
"""
    (TARGET_DATASET / "README.md").write_text(readme, encoding="utf-8")


def normalize_case(
    case: dict[str, Any],
    *,
    task_name: str,
    answer_key: str,
    prompt_path: str,
    image: dict[str, Any],
    prompt_name: str | None = None,
) -> dict[str, Any]:
    output = {
        "case_id": f"{case['image_id']}__{task_name}",
        "image_id": case["image_id"],
        "answer_key": answer_key,
        "task_name": task_name,
        "package_name": image["package_name"],
        "package_slug": image["package_slug"],
        "kicad_model_name": image["kicad_model_name"],
        "shape_class": image["shape_class"],
        "variant_name": image["variant_name"],
        "variant_slug": image["variant_slug"],
        "prompt_path": prompt_path,
        "image_path": image["image_path"],
    }
    if prompt_name is not None:
        output["prompt_name"] = prompt_name
    return output


def write_cases(task_name: str, cases: list[dict[str, Any]], source_cases_path: Path) -> None:
    payload = {
        "task_name": task_name,
        "schema_version": 2,
        "generated_at_utc": now_utc(),
        "source_cases": source_rel(source_cases_path),
        "source_image_manifest": "data/package_drawings/image_manifest.json",
        "case_count": len(cases),
        "cases": cases,
    }
    write_json(TARGET_TASKS / task_name / "cases.json", payload)


def convert_direct_cases(images_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    source_path = SOURCE_TASKS / "package_target_extraction" / "cases.json"
    source_cases = read_json(source_path)["cases"]
    cases = [
        normalize_case(
            case,
            task_name="direct_extraction",
            answer_key=case["answer_key"],
            prompt_name="extract_number",
            prompt_path="data/tasks/direct_extraction/prompts/extract_number.md",
            image=images_by_id[case["image_id"]],
        )
        for case in source_cases
        if case.get("prompt_name") == "extract_number" and case.get("image_id") in images_by_id
    ]
    cases.sort(key=lambda item: item["image_id"])
    if len(cases) != 30:
        raise RuntimeError(f"Expected 30 direct cases, found {len(cases)}")
    write_cases("direct_extraction", cases, source_path)
    return cases


def convert_dimension_cases(images_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    source_path = SOURCE_TASKS / "pure_ocr_extraction" / "cases.json"
    source_cases = read_json(source_path)["cases"]
    cases = [
        normalize_case(
            case,
            task_name="dimension_extraction",
            answer_key=f"{case['image_id']}__dimension_extraction",
            prompt_path="data/tasks/dimension_extraction/prompt.md",
            image=images_by_id[case["image_id"]],
        )
        for case in source_cases
        if case.get("image_id") in images_by_id
    ]
    cases.sort(key=lambda item: item["image_id"])
    if len(cases) != 30:
        raise RuntimeError(f"Expected 30 dimension cases, found {len(cases)}")
    write_cases("dimension_extraction", cases, source_path)
    return cases


def convert_top_view_cases(images_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    source_path = SOURCE_TASKS / "top_view_localization" / "cases.json"
    source_cases = read_json(source_path)["cases"]
    cases = [
        normalize_case(
            case,
            task_name="top_view_detection",
            answer_key=f"{case['image_id']}__top_view_detection",
            prompt_path="data/tasks/top_view_detection/prompt.md",
            image=images_by_id[case["image_id"]],
        )
        for case in source_cases
        if case.get("image_id") in images_by_id
    ]
    cases.sort(key=lambda item: item["image_id"])
    if len(cases) != 30:
        raise RuntimeError(f"Expected 30 top-view cases, found {len(cases)}")
    write_cases("top_view_detection", cases, source_path)
    return cases


def write_ground_truth(task_name: str, groups: list[dict[str, Any]], source_path: Path) -> None:
    payload = {
        "task_name": task_name,
        "schema_version": 2,
        "source_ground_truth": source_rel(source_path),
        "generated_at_utc": now_utc(),
        "answer_groups": groups,
    }
    write_json(TARGET_TASKS / task_name / "ground_truth.json", payload)


def convert_direct_ground_truth(
    cases: list[dict[str, Any]],
    images_by_id: dict[str, dict[str, Any]],
) -> None:
    source_path = SOURCE_TASKS / "package_target_extraction" / "ground_truth.json"
    source_groups = read_json(source_path)["answer_groups"]
    cases_by_answer_key: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        cases_by_answer_key.setdefault(case["answer_key"], []).append(case)

    groups: list[dict[str, Any]] = []
    for group in source_groups:
        answer_key = group.get("answer_key")
        if group.get("prompt_name") != "extract_number" or answer_key not in cases_by_answer_key:
            continue
        related_cases = sorted(cases_by_answer_key[answer_key], key=lambda item: item["image_id"])
        package_shape_classes = {
            images_by_id[case["image_id"]]["shape_class"]
            for case in related_cases
        }
        if len(package_shape_classes) != 1:
            raise RuntimeError(f"Expected one shape_class for {answer_key}, found {package_shape_classes}")
        normalized, errors = validate_direct_output(group["ground_truth"], context="ground_truth")
        if normalized is None:
            raise RuntimeError(f"Invalid direct ground truth for {answer_key}: {errors}")
        groups.append(
            {
                "answer_key": answer_key,
                "package_name": group["package_name"],
                "package_slug": group["package_slug"],
                "shape_class": package_shape_classes.pop(),
                "prompt_name": "extract_number",
                "applies_to_case_ids": [case["case_id"] for case in related_cases],
                "applies_to_image_ids": [case["image_id"] for case in related_cases],
                "applies_to_variants": [case["variant_name"] for case in related_cases],
                "annotation_status": group.get("annotation_status", "complete"),
                "ground_truth": group["ground_truth"],
                "evaluation_metadata": group.get("evaluation_metadata", {}),
                "notes": group.get("notes", ""),
            }
        )

    groups.sort(key=lambda item: item["answer_key"])
    if len(groups) != 15:
        raise RuntimeError(f"Expected 15 direct ground truth groups, found {len(groups)}")
    write_ground_truth("direct_extraction", groups, source_path)


def convert_image_ground_truth(
    *,
    source_task_name: str,
    target_task_name: str,
    cases: list[dict[str, Any]],
    validator: Any,
) -> None:
    source_path = SOURCE_TASKS / source_task_name / "ground_truth.json"
    source_groups = read_json(source_path)["answer_groups"]
    groups_by_image_id = {group["image_id"]: group for group in source_groups}

    groups: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda item: item["image_id"]):
        source_group = groups_by_image_id.get(case["image_id"])
        if source_group is None:
            raise RuntimeError(f"Missing {source_task_name} ground truth for {case['image_id']}")
        normalized, errors = validator(
            source_group["ground_truth"],
            context="ground_truth",
            require_bbox=False,
        )
        if normalized is None:
            raise RuntimeError(f"Invalid {target_task_name} ground truth for {case['image_id']}: {errors}")
        groups.append(
            {
                "answer_key": case["answer_key"],
                "case_id": case["case_id"],
                "image_id": case["image_id"],
                "package_name": case["package_name"],
                "package_slug": case["package_slug"],
                "shape_class": case["shape_class"],
                "variant_name": case["variant_name"],
                "variant_slug": case["variant_slug"],
                "prompt_path": case["prompt_path"],
                "image_path": case["image_path"],
                "annotation_status": source_group.get("annotation_status", "complete"),
                "ground_truth": source_group["ground_truth"],
                "notes": source_group.get("notes", ""),
            }
        )

    if len(groups) != 30:
        raise RuntimeError(f"Expected 30 {target_task_name} ground truth groups, found {len(groups)}")
    write_ground_truth(target_task_name, groups, source_path)


def verify_case_alignment(*case_sets: list[dict[str, Any]]) -> None:
    image_id_sets = [{case["image_id"] for case in cases} for cases in case_sets]
    first = image_id_sets[0]
    if any(image_ids != first for image_ids in image_id_sets[1:]):
        raise RuntimeError("Task case image_id sets do not match")


def main() -> int:
    if not SOURCE_ROOT.exists():
        print(f"Missing source repo: {source_rel(SOURCE_ROOT)}", file=sys.stderr)
        return 1

    images = load_value_images()
    images_by_id = image_lookup(images)
    rebuild_image_dataset(images)

    direct_cases = convert_direct_cases(images_by_id)
    dimension_cases = convert_dimension_cases(images_by_id)
    top_view_cases = convert_top_view_cases(images_by_id)
    verify_case_alignment(direct_cases, dimension_cases, top_view_cases)

    convert_direct_ground_truth(direct_cases, images_by_id)
    convert_image_ground_truth(
        source_task_name="pure_ocr_extraction",
        target_task_name="dimension_extraction",
        cases=dimension_cases,
        validator=validate_dimension_output,
    )
    convert_image_ground_truth(
        source_task_name="top_view_localization",
        target_task_name="top_view_detection",
        cases=top_view_cases,
        validator=validate_top_view_output,
    )

    print("Imported value-only dataset: 30 images, 30 cases per Stage 1 task.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
