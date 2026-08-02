from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.adapters.models.rule import RuleAnalysisAdapter
from requirements_quality_agent.domain.enums import AnalysisOrigin
from requirements_quality_agent.domain.models import CandidateAnalysis

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "evaluate_rule_baseline.py"
SPEC = importlib.util.spec_from_file_location("rule_baseline_evaluator_under_test", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the rule baseline evaluator")
evaluator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evaluator
SPEC.loader.exec_module(evaluator)


def _complete_evaluation_root(repository: Path) -> Path:
    script_target = repository / "scripts" / "evaluate_rule_baseline.py"
    rule_target = (
        repository / "src" / "requirements_quality_agent" / "adapters" / "models" / "rule.py"
    )
    script_target.parent.mkdir(parents=True)
    rule_target.parent.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "scripts" / "evaluate_rule_baseline.py", script_target)
    shutil.copy2(
        PROJECT_ROOT / "src" / "requirements_quality_agent" / "adapters" / "models" / "rule.py",
        rule_target,
    )
    return repository


def test_answer_key_pair_labels_are_normalized_and_deduplicated() -> None:
    rows = evaluator._load_answer_key(  # noqa: SLF001
        PROJECT_ROOT / "case" / "expected" / "requirements-labels.jsonl"
    )

    keys, raw_count = evaluator.normalize_answer_key(rows)

    assert raw_count == 48
    assert len(keys) == 43
    assert raw_count - len(keys) == 5
    assert evaluator.FindingKey.create("DUPLICATE", ("FR-006", "FR-016")) in keys
    assert evaluator.FindingKey.create("DUPLICATE", ("FR-016", "FR-006")) in keys
    assert sum(key.issue_type == "DUPLICATE" for key in keys) == 2
    assert sum(key.issue_type == "CONTRADICTION" for key in keys) == 3


def test_prediction_normalization_sorts_targets_and_removes_duplicates(repository: Path) -> None:
    pack = load_case_pack(repository)
    candidate = RuleAnalysisAdapter().analyze(
        documents=pack.documents,
        requirements=pack.requirements,
    )
    pair = next(finding for finding in candidate.findings if len(finding.requirement_ids) == 2)
    reversed_pair = pair.model_copy(
        update={"requirement_ids": tuple(reversed(pair.requirement_ids))}
    )
    duplicate_candidate = CandidateAnalysis(findings=(*candidate.findings, pair, reversed_pair))

    keys = evaluator.normalize_predictions(duplicate_candidate)

    assert len(keys) == len(candidate.findings)
    assert evaluator.FindingKey.create(pair.issue_type.value, pair.requirement_ids) in keys


def test_fixture_origin_is_rejected_from_rule_baseline_measurement(repository: Path) -> None:
    pack = load_case_pack(repository)
    rule_candidate = RuleAnalysisAdapter().analyze(
        documents=pack.documents,
        requirements=pack.requirements,
    )
    fixture_finding = rule_candidate.findings[0].model_copy(
        update={"origin": AnalysisOrigin.FIXTURE}
    )

    with pytest.raises(evaluator.EvaluationError, match="only RULE-origin"):
        evaluator.normalize_predictions(CandidateAnalysis(findings=(fixture_finding,)))


def test_exact_set_scoring_reports_tp_fp_fn_and_category_metrics() -> None:
    expected = {
        evaluator.FindingKey.create("AMBIGUOUS_TERM", ("FR-001",)),
        evaluator.FindingKey.create("DUPLICATE", ("FR-006", "FR-016")),
    }
    predicted = {
        *expected,
        evaluator.FindingKey.create("UNTESTABLE", ("FR-005",)),
    }

    scored = evaluator.score_keys(expected, predicted)

    assert scored["overall"] == {
        "expected": 2,
        "predicted": 3,
        "tp": 2,
        "fp": 1,
        "fn": 0,
        "precision": 0.666667,
        "recall": 1.0,
        "f1": 0.8,
    }
    assert scored["per_category"]["UNTESTABLE"] == {
        "expected": 0,
        "predicted": 1,
        "tp": 0,
        "fp": 1,
        "fn": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    assert scored["false_positive_keys"] == [{"issue_type": "UNTESTABLE", "target_ids": ["FR-005"]}]
    assert scored["false_negative_keys"] == []


def test_clean_flawed_item_counts_use_all_targets() -> None:
    rows: tuple[dict[str, object], ...] = (
        {"requirement_id": "FR-001", "clean": False, "issues": (), "related_ids": ()},
        {"requirement_id": "FR-002", "clean": True, "issues": (), "related_ids": ()},
        {"requirement_id": "FR-003", "clean": False, "issues": (), "related_ids": ()},
    )
    predicted = {
        evaluator.FindingKey.create("DUPLICATE", ("FR-001", "FR-002")),
    }

    counts = evaluator.classify_items(rows, predicted)

    assert counts == {
        "total_items": 3,
        "gold_flawed": 2,
        "gold_clean": 1,
        "predicted_flawed": 2,
        "predicted_clean": 1,
        "flawed_as_flawed": 1,
        "clean_as_flawed": 1,
        "flawed_as_clean": 1,
        "clean_as_clean": 0,
        "correct": 1,
        "accuracy": 0.333333,
    }


def test_evaluation_does_not_read_or_require_the_fixture(repository: Path) -> None:
    root = _complete_evaluation_root(repository)
    fixture = root / "case" / "fixtures" / "candidate-analysis.json"
    fixture.unlink()

    result = evaluator.build_evaluation(root)

    assert result["fixture_used"] is False
    assert result["is_ai_accuracy"] is False
    assert result["baseline_kind"] == "CASE_TUNED_DETERMINISTIC_RULE_BASELINE"
    assert result["finding_metrics"]["overall"]["tp"] == 43


def test_committed_results_match_the_locked_evaluator_and_digests() -> None:
    expected = evaluator.build_evaluation(PROJECT_ROOT)
    json_path = PROJECT_ROOT / "evaluation" / "results" / "rule-baseline.json"
    markdown_path = PROJECT_ROOT / "evaluation" / "results" / "rule-baseline.md"

    committed = json.loads(json_path.read_text())

    assert committed == expected
    assert markdown_path.read_text() == evaluator.render_markdown(expected)
    assert committed["finding_metrics"]["overall"] == {
        "expected": 43,
        "predicted": 43,
        "tp": 43,
        "fp": 0,
        "fn": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }
    assert committed["item_classification"] == {
        "total_items": 50,
        "gold_flawed": 40,
        "gold_clean": 10,
        "predicted_flawed": 40,
        "predicted_clean": 10,
        "flawed_as_flawed": 40,
        "clean_as_flawed": 0,
        "flawed_as_clean": 0,
        "clean_as_clean": 10,
        "correct": 50,
        "accuracy": 1.0,
    }
    assert (
        committed["digests"]["answer_key_sha256"]
        == hashlib.sha256(
            (PROJECT_ROOT / "case" / "expected" / "requirements-labels.jsonl").read_bytes()
        ).hexdigest()
    )
    assert (
        committed["digests"]["evaluator_sha256"]
        == hashlib.sha256(
            (PROJECT_ROOT / "scripts" / "evaluate_rule_baseline.py").read_bytes()
        ).hexdigest()
    )
    assert "not AI/model accuracy" in markdown_path.read_text()
