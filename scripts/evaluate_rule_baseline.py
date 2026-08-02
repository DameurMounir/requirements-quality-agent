#!/usr/bin/env python3
"""Evaluate the case-tuned deterministic rule baseline on the frozen answer key."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.adapters.models.rule import RuleAnalysisAdapter
from requirements_quality_agent.controls.canonical import domain_digest
from requirements_quality_agent.domain.enums import AnalysisOrigin
from requirements_quality_agent.domain.models import CandidateAnalysis

ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY_PATH = ROOT / "case" / "expected" / "requirements-labels.jsonl"
RULE_SOURCE_PATH = ROOT / "src" / "requirements_quality_agent" / "adapters" / "models" / "rule.py"
JSON_OUTPUT_PATH = ROOT / "evaluation" / "results" / "rule-baseline.json"
MARKDOWN_OUTPUT_PATH = ROOT / "evaluation" / "results" / "rule-baseline.md"
PAIR_ISSUE_TYPES = frozenset({"CONTRADICTION", "DUPLICATE"})
EVALUATOR_VERSION = "1.0.0"
NORMALIZATION_VERSION = "issue-type-plus-sorted-target-ids/v1"


class EvaluationError(ValueError):
    """Raised when the frozen evaluation inputs violate the locked contract."""


class AnswerRow(TypedDict):
    requirement_id: str
    clean: bool
    issues: tuple[str, ...]
    related_ids: tuple[str, ...]


@dataclass(frozen=True, order=True, slots=True)
class FindingKey:
    """Exact comparison key independent of pair direction or finding order."""

    issue_type: str
    target_ids: tuple[str, ...]

    @classmethod
    def create(cls, issue_type: str, target_ids: list[str] | tuple[str, ...]) -> FindingKey:
        normalized_targets = tuple(sorted(set(target_ids)))
        if not issue_type or not normalized_targets:
            raise EvaluationError("finding keys require an issue type and target IDs")
        return cls(issue_type=issue_type, target_ids=normalized_targets)

    def as_dict(self) -> dict[str, object]:
        return {"issue_type": self.issue_type, "target_ids": list(self.target_ids)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_answer_key(path: Path) -> tuple[AnswerRow, ...]:
    rows: list[AnswerRow] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise EvaluationError(f"answer-key line {line_number} is not an object")
        requirement_id = raw.get("requirement_id")
        clean = raw.get("clean")
        issues = raw.get("issues")
        related_ids = raw.get("related_ids")
        if (
            not isinstance(requirement_id, str)
            or not isinstance(clean, bool)
            or not isinstance(issues, list)
            or not all(isinstance(item, str) for item in issues)
            or not isinstance(related_ids, list)
            or not all(isinstance(item, str) for item in related_ids)
        ):
            raise EvaluationError(f"answer-key line {line_number} has invalid fields")
        if requirement_id in seen:
            raise EvaluationError(f"duplicate answer-key item: {requirement_id}")
        if clean == bool(issues):
            raise EvaluationError(f"clean/issue mismatch for {requirement_id}")
        seen.add(requirement_id)
        rows.append(
            {
                "requirement_id": requirement_id,
                "clean": clean,
                "issues": tuple(issues),
                "related_ids": tuple(related_ids),
            }
        )
    if not rows:
        raise EvaluationError("answer key is empty")
    return tuple(rows)


def normalize_answer_key(
    rows: tuple[AnswerRow, ...],
) -> tuple[set[FindingKey], int]:
    raw_label_count = 0
    keys: set[FindingKey] = set()
    known_ids = {row["requirement_id"] for row in rows}
    for row in rows:
        requirement_id = row["requirement_id"]
        issues = row["issues"]
        related_ids = row["related_ids"]
        if not set(related_ids) <= known_ids:
            raise EvaluationError(f"unknown related ID for {requirement_id}")
        for issue_type in issues:
            raw_label_count += 1
            targets: tuple[str, ...]
            if issue_type in PAIR_ISSUE_TYPES:
                if len(related_ids) != 1:
                    raise EvaluationError(
                        f"pair issue {issue_type} for {requirement_id} requires one related ID"
                    )
                targets = (requirement_id, related_ids[0])
            else:
                targets = (requirement_id,)
            keys.add(FindingKey.create(issue_type, targets))
    return keys, raw_label_count


def normalize_predictions(candidate: CandidateAnalysis) -> set[FindingKey]:
    keys: set[FindingKey] = set()
    for finding in candidate.findings:
        if finding.origin is not AnalysisOrigin.RULE:
            raise EvaluationError("only RULE-origin findings may enter this baseline evaluation")
        keys.add(FindingKey.create(finding.issue_type.value, finding.requirement_ids))
    return keys


def _metrics(tp: int, fp: int, fn: int) -> dict[str, int | float]:
    precision = 0.0 if tp + fp == 0 else round(tp / (tp + fp), 6)
    recall = 0.0 if tp + fn == 0 else round(tp / (tp + fn), 6)
    f1 = 0.0 if 2 * tp + fp + fn == 0 else round((2 * tp) / (2 * tp + fp + fn), 6)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def score_keys(
    expected: set[FindingKey],
    predicted: set[FindingKey],
) -> dict[str, object]:
    true_positives = expected & predicted
    false_positives = predicted - expected
    false_negatives = expected - predicted
    categories = sorted({key.issue_type for key in expected | predicted})
    per_category: dict[str, dict[str, int | float]] = {}
    for category in categories:
        category_expected = {key for key in expected if key.issue_type == category}
        category_predicted = {key for key in predicted if key.issue_type == category}
        category_tp = len(category_expected & category_predicted)
        category_fp = len(category_predicted - category_expected)
        category_fn = len(category_expected - category_predicted)
        per_category[category] = {
            "expected": len(category_expected),
            "predicted": len(category_predicted),
            **_metrics(category_tp, category_fp, category_fn),
        }
    return {
        "overall": {
            "expected": len(expected),
            "predicted": len(predicted),
            **_metrics(len(true_positives), len(false_positives), len(false_negatives)),
        },
        "per_category": per_category,
        "true_positive_keys": [key.as_dict() for key in sorted(true_positives)],
        "false_positive_keys": [key.as_dict() for key in sorted(false_positives)],
        "false_negative_keys": [key.as_dict() for key in sorted(false_negatives)],
    }


def classify_items(
    rows: tuple[AnswerRow, ...],
    predicted: set[FindingKey],
) -> dict[str, int | float]:
    all_ids = {row["requirement_id"] for row in rows}
    gold_flawed = {row["requirement_id"] for row in rows if not row["clean"]}
    predicted_flawed = {item_id for key in predicted for item_id in key.target_ids}
    unknown = predicted_flawed - all_ids
    if unknown:
        raise EvaluationError(f"predictions reference unknown items: {', '.join(sorted(unknown))}")
    gold_clean = all_ids - gold_flawed
    predicted_clean = all_ids - predicted_flawed
    flawed_as_flawed = len(gold_flawed & predicted_flawed)
    clean_as_flawed = len(gold_clean & predicted_flawed)
    flawed_as_clean = len(gold_flawed & predicted_clean)
    clean_as_clean = len(gold_clean & predicted_clean)
    correct = flawed_as_flawed + clean_as_clean
    return {
        "total_items": len(all_ids),
        "gold_flawed": len(gold_flawed),
        "gold_clean": len(gold_clean),
        "predicted_flawed": len(predicted_flawed),
        "predicted_clean": len(predicted_clean),
        "flawed_as_flawed": flawed_as_flawed,
        "clean_as_flawed": clean_as_flawed,
        "flawed_as_clean": flawed_as_clean,
        "clean_as_clean": clean_as_clean,
        "correct": correct,
        "accuracy": 0.0 if not all_ids else round(correct / len(all_ids), 6),
    }


def build_evaluation(repository_root: Path = ROOT) -> dict[str, Any]:
    root = repository_root.resolve(strict=True)
    answer_key_path = root / "case" / "expected" / "requirements-labels.jsonl"
    evaluator_path = root / "scripts" / "evaluate_rule_baseline.py"
    rule_source_path = (
        root / "src" / "requirements_quality_agent" / "adapters" / "models" / "rule.py"
    )
    pack = load_case_pack(root)
    rows = _load_answer_key(answer_key_path)
    expected, raw_answer_labels = normalize_answer_key(rows)
    adapter = RuleAnalysisAdapter()
    candidate = adapter.analyze(documents=pack.documents, requirements=pack.requirements)
    predicted = normalize_predictions(candidate)
    configuration: dict[str, Any] = {
        "evaluator_version": EVALUATOR_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "comparison": "exact-set-membership",
        "pair_issue_types": sorted(PAIR_ISSUE_TYPES),
        "adapter": adapter.name,
        "adapter_configuration": adapter.configuration,
        "answer_key": "case/expected/requirements-labels.jsonl",
        "fixture_excluded": True,
    }
    scores = score_keys(expected, predicted)
    return {
        "schema_version": "1.0.0",
        "baseline_kind": "CASE_TUNED_DETERMINISTIC_RULE_BASELINE",
        "baseline_name": adapter.name,
        "measurement_scope": (
            "Exact performance of a case-tuned deterministic rule baseline on one frozen "
            "synthetic case. This is not AI or model accuracy and is not a generalization claim."
        ),
        "is_ai_accuracy": False,
        "fixture_used": False,
        "configuration": configuration,
        "digests": {
            "source_pack_sha256": pack.source_pack_sha256,
            "source_manifest_sha256": pack.manifest_sha256,
            "answer_key_sha256": _sha256(answer_key_path),
            "evaluator_sha256": _sha256(evaluator_path),
            "configuration_sha256": domain_digest("rule-baseline-evaluation-config", configuration),
            "rule_source_sha256": _sha256(rule_source_path),
            "adapter_prompt_sha256": adapter.prompt_sha256,
        },
        "normalization": {
            "key": "issue_type + sorted unique target IDs",
            "answer_key_raw_labels": raw_answer_labels,
            "answer_key_normalized_keys": len(expected),
            "answer_key_pair_duplicates_removed": raw_answer_labels - len(expected),
            "prediction_raw_findings": len(candidate.findings),
            "prediction_normalized_keys": len(predicted),
            "prediction_duplicates_removed": len(candidate.findings) - len(predicted),
        },
        "finding_metrics": scores,
        "item_classification": classify_items(rows, predicted),
    }


def render_markdown(result: dict[str, Any]) -> str:
    digests = result["digests"]
    normalization = result["normalization"]
    finding_metrics = result["finding_metrics"]
    overall = finding_metrics["overall"]
    per_category = finding_metrics["per_category"]
    item = result["item_classification"]
    lines = [
        "# Transparent rule baseline evaluation",
        "",
        "> **Scope:** This is a case-tuned deterministic rule baseline evaluated on one frozen",
        "> synthetic case. It is **not AI/model accuracy** and makes no generalization claim. The",
        "> digest-bound fixture is excluded from this evaluation.",
        "",
        "## Exact finding results",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Expected normalized keys | {overall['expected']} |",
        f"| Predicted normalized keys | {overall['predicted']} |",
        f"| True positives | {overall['tp']} |",
        f"| False positives | {overall['fp']} |",
        f"| False negatives | {overall['fn']} |",
        f"| Precision | {overall['precision']:.6f} |",
        f"| Recall | {overall['recall']:.6f} |",
        f"| F1 | {overall['f1']:.6f} |",
        "",
        "The answer key contains "
        f"{normalization['answer_key_raw_labels']} row-level labels and "
        f"{normalization['answer_key_normalized_keys']} exact normalized keys. "
        f"{normalization['answer_key_pair_duplicates_removed']} mirrored pair labels were "
        "deduplicated before scoring.",
        "",
        "## Per-category results",
        "",
        "| Category | Expected | Predicted | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for category, metrics in per_category.items():
        lines.append(
            f"| {category} | {metrics['expected']} | {metrics['predicted']} | "
            f"{metrics['tp']} | {metrics['fp']} | {metrics['fn']} | "
            f"{metrics['precision']:.6f} | {metrics['recall']:.6f} | {metrics['f1']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Clean/flawed item classification",
            "",
            "| Count | Value |",
            "|---|---:|",
            f"| Total items | {item['total_items']} |",
            f"| Gold flawed | {item['gold_flawed']} |",
            f"| Gold clean | {item['gold_clean']} |",
            f"| Predicted flawed | {item['predicted_flawed']} |",
            f"| Predicted clean | {item['predicted_clean']} |",
            f"| Flawed classified as flawed | {item['flawed_as_flawed']} |",
            f"| Clean classified as flawed | {item['clean_as_flawed']} |",
            f"| Flawed classified as clean | {item['flawed_as_clean']} |",
            f"| Clean classified as clean | {item['clean_as_clean']} |",
            f"| Accuracy | {item['accuracy']:.6f} |",
            "",
            "## Locked provenance",
            "",
            "| Digest | SHA-256 |",
            "|---|---|",
        ]
    )
    for label, digest in digests.items():
        lines.append(f"| `{label}` | `{digest}` |")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "These rules were written for this published synthetic case. The scores show agreement "
            "with this answer key only. They do not measure an LLM, the offline fixture, "
            "unseen requirements, semantic generalization, or production fitness.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    result = build_evaluation(ROOT)
    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    MARKDOWN_OUTPUT_PATH.write_text(
        render_markdown(result),
        encoding="utf-8",
        newline="\n",
    )
    overall = result["finding_metrics"]["overall"]
    print(
        "PASS: case-tuned deterministic baseline; "
        f"TP={overall['tp']} FP={overall['fp']} FN={overall['fn']} "
        f"F1={overall['f1']:.6f}; fixture excluded; not AI accuracy"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
