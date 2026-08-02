from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.storage.local_store import RunStateError
from requirements_quality_agent.application.services import ReviewResult, ReviewService
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import ApprovalSubmission


def _state_path(repository: Path, run_id: str) -> Path:
    return repository / "run-state" / run_id / "state.json"


def _round_two(
    service: ReviewService,
    submission_factory: Callable[..., ApprovalSubmission],
    run_id: str,
) -> ReviewResult:
    first = service.analyze(run_id)
    service.decide(
        submission=submission_factory(first.request, ApprovalAction.REQUEST_REVISION),
        output_root="output",
    )
    return service.resume(run_id)


def _tamper(repository: Path, run_id: str, mutation: str) -> None:
    path = _state_path(repository, run_id)
    state = json.loads(path.read_text())
    if mutation == "historical_artifact":
        state["rounds"][0]["artifact"]["scorecard"]["candidate_findings"] += 1
    elif mutation == "historical_decision_digest":
        state["decisions"][0]["artifact_sha256"] = "f" * 64
    elif mutation == "schema_version":
        state["schema_version"] = "9.9.9"
    elif mutation == "persisted_status":
        state["status"] = "VALIDATED"
    elif mutation == "historical_artifact_status":
        state["rounds"][0]["artifact"]["status"] = "APPROVED"
    elif mutation == "decision_nonce_set":
        state["used_nonce_sha256"] = ["f" * 64]
    elif mutation == "non_monotonic_rounds":
        state["rounds"].reverse()
    elif mutation == "missing_historical_round":
        state["rounds"].pop(0)
    else:
        raise AssertionError(f"unknown mutation: {mutation}")
    path.write_text(json.dumps(state))


def _assert_both_loaders_reject(service: ReviewService, run_id: str) -> None:
    with pytest.raises(RunStateError):
        service.store.load_status(run_id)
    with pytest.raises(RunStateError):
        service.store.load_review(run_id)


@pytest.mark.parametrize(
    "mutation",
    [
        "historical_artifact",
        "historical_decision_digest",
        "schema_version",
        "persisted_status",
        "historical_artifact_status",
        "decision_nonce_set",
        "non_monotonic_rounds",
        "missing_historical_round",
    ],
)
def test_round_two_ledger_tampering_fails_closed_for_every_loader(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
    mutation: str,
) -> None:
    run_id = f"RUN-HISTORY-{mutation.replace('_', '-').upper()}"
    service = service_factory()
    second = _round_two(service, submission_factory, run_id)
    assert second.request.review_round == 2

    _tamper(repository, run_id, mutation)

    _assert_both_loaders_reject(service, run_id)


def test_forged_export_manifest_after_round_two_fails_for_every_loader(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    run_id = "RUN-HISTORY-EXPORT-MANIFEST"
    service = service_factory()
    second = _round_two(service, submission_factory, run_id)
    service.decide(
        submission=submission_factory(second.request, ApprovalAction.APPROVE),
        output_root="output",
    )
    path = _state_path(repository, run_id)
    state = json.loads(path.read_text())
    assert state["status"] == "EXPORTED"
    state["export_manifest"]["artifact_sha256"] = "f" * 64
    path.write_text(json.dumps(state))

    _assert_both_loaders_reject(service, run_id)
