from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.storage.local_store import RunStateError
from requirements_quality_agent.application.services import (
    ReviewDecisionRejected,
    ReviewService,
)
from requirements_quality_agent.controls.approval import ApprovalRejected, review_artifact_digest
from requirements_quality_agent.controls.canonical import domain_digest
from requirements_quality_agent.domain.enums import ApprovalAction, WorkflowStatus
from requirements_quality_agent.domain.models import ApprovalSubmission, RevisionEdit


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ledger(repository: Path, run_id: str) -> dict[str, object]:
    return json.loads((repository / "run-state" / run_id / "state.json").read_text())


def test_rule_analysis_pauses_with_exactly_bound_review(
    repository: Path,
    service_factory: Callable[..., ReviewService],
) -> None:
    service = service_factory()

    result = service.analyze("RUN-RULE-PAUSE")

    assert result.artifact.status is WorkflowStatus.NEEDS_REVIEW
    assert result.request.review_round == 1
    assert result.request.artifact_sha256 == review_artifact_digest(result.artifact)
    assert result.request.reviewer_id == "test-reviewer"
    assert len(result.artifact.requirements) == 50
    assert result.artifact.scorecard.verified_findings == len(result.artifact.findings)
    assert result.artifact.scorecard.blocked_findings == 0
    assert result.artifact.revisions
    assert service.store.load_status(result.artifact.run_id) is WorkflowStatus.NEEDS_REVIEW
    loaded_artifact, loaded_request = service.store.load_review(result.artifact.run_id)
    assert loaded_artifact == result.artifact
    assert loaded_request == result.request
    assert not (repository / "output").exists()


def test_approve_exports_the_exact_artifact_and_approval(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-EXACT-EXPORT")

    decision = service.decide(
        submission=submission_factory(
            review.request,
            ApprovalAction.APPROVE,
            comment="Evidence reviewed against every cited source.",
        ),
        output_root="output",
    )

    assert decision.status is WorkflowStatus.EXPORTED
    assert decision.export_manifest is not None
    assert decision.artifact_sha256 == review.request.artifact_sha256
    assert service.store.load_status(review.artifact.run_id) is WorkflowStatus.EXPORTED
    run_output = repository / "output" / review.artifact.run_id
    report = json.loads((run_output / "report.json").read_text())
    assert report["artifact"] == review.artifact.model_dump(mode="json")
    assert report["decision"] == decision.decision.model_dump(mode="json")
    manifest = decision.export_manifest
    assert manifest.artifact_sha256 == review_artifact_digest(review.artifact)
    assert manifest.approval_sha256 == domain_digest("approval-record", decision.decision)
    assert {item.relative_path for item in manifest.files} == {"report.json", "report.md"}
    for item in manifest.files:
        exported = run_output / item.relative_path
        assert _sha256(exported) == item.sha256
        assert exported.stat().st_size == item.size_bytes


def test_export_retry_is_idempotent_and_does_not_rewrite_files(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-IDEMPOTENT")
    decision = service.decide(
        submission=submission_factory(review.request, ApprovalAction.APPROVE),
        output_root="output",
    )
    assert decision.export_manifest is not None
    run_output = repository / "output" / review.artifact.run_id
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in run_output.iterdir()
    }

    retried = service.export_approved(review.artifact.run_id, "output")

    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in run_output.iterdir()
    }
    assert retried == decision.export_manifest
    assert after == before
    assert service.store.load_status(review.artifact.run_id) is WorkflowStatus.EXPORTED


def test_reject_is_terminal_and_creates_no_export(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-REJECTED")

    result = service.decide(
        submission=submission_factory(
            review.request,
            ApprovalAction.REJECT,
            comment="The proposed wording changes the intended policy.",
        ),
        output_root="output",
    )

    assert result.status is WorkflowStatus.REJECTED
    assert result.export_manifest is None
    assert service.store.load_status(review.artifact.run_id) is WorkflowStatus.REJECTED
    assert not (repository / "output").exists()
    with pytest.raises(ReviewDecisionRejected, match="not approved"):
        service.export_approved(review.artifact.run_id, "output")


def test_request_revision_resumes_as_the_next_persisted_round(
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    first = service.analyze("RUN-REVISION")
    requested = service.decide(
        submission=submission_factory(
            first.request,
            ApprovalAction.REQUEST_REVISION,
            comment="Re-run the review after reconsidering the evidence.",
        ),
        output_root="output",
    )
    assert requested.status is WorkflowStatus.REVISION_REQUESTED
    assert service.store.load_status(first.artifact.run_id) is WorkflowStatus.REVISION_REQUESTED

    second = service.resume(first.artifact.run_id)

    assert second.request.review_round == 2
    assert second.request.nonce != first.request.nonce
    assert second.artifact.source_pack_sha256 == first.artifact.source_pack_sha256
    assert second.request.artifact_sha256 == review_artifact_digest(second.artifact)
    assert service.store.load_status(first.artifact.run_id) is WorkflowStatus.NEEDS_REVIEW
    _, current_request = service.store.load_review(first.artifact.run_id)
    assert current_request == second.request


def test_edit_creates_new_proposal_artifact_digest_and_review_round(
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    first = service.analyze("RUN-EDIT")
    original = first.artifact.revisions[0]
    replacement = original.proposed_text + " The owner shall confirm the result in the audit log."
    submission = submission_factory(
        first.request,
        ApprovalAction.EDIT,
        comment="Use this clearer controlled wording.",
        edits=(RevisionEdit(proposal_id=original.proposal_id, replacement_text=replacement),),
    )

    edited = service.decide(submission=submission, output_root="output")

    assert edited.status is WorkflowStatus.NEEDS_REVIEW
    assert edited.next_request is not None
    assert edited.next_request.review_round == 2
    assert edited.next_request.artifact_sha256 != first.request.artifact_sha256
    current_artifact, current_request = service.store.load_review(first.artifact.run_id)
    changed = next(
        proposal
        for proposal in current_artifact.revisions
        if proposal.requirement_id == original.requirement_id
    )
    assert changed.proposed_text == replacement
    assert changed.proposal_id != original.proposal_id
    assert current_request == edited.next_request
    assert review_artifact_digest(current_artifact) == edited.next_request.artifact_sha256

    with pytest.raises(ApprovalRejected, match="approval binding mismatch"):
        service.decide(submission=submission, output_root="output")


def test_consumed_nonce_is_rejected_even_if_status_is_tampered_back_open(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-NONCE-REPLAY")
    submission = submission_factory(review.request, ApprovalAction.REQUEST_REVISION)
    result = service.decide(submission=submission, output_root="output")
    state_path = repository / "run-state" / review.artifact.run_id / "state.json"
    state = json.loads(state_path.read_text())
    state["status"] = WorkflowStatus.NEEDS_REVIEW.value
    state_path.write_text(json.dumps(state))

    with pytest.raises(RunStateError, match="ledger bindings are invalid"):
        service.store.commit_decision(result.decision, WorkflowStatus.REVISION_REQUESTED)


def test_wrong_status_rejects_review_resume_and_export(
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-WRONG-STATUS")
    with pytest.raises(ReviewDecisionRejected, match="not waiting"):
        service.resume(review.artifact.run_id)

    rejected = service.decide(
        submission=submission_factory(review.request, ApprovalAction.REJECT),
        output_root="output",
    )
    assert rejected.status is WorkflowStatus.REJECTED
    with pytest.raises(ReviewDecisionRejected, match="not open"):
        service.decide(
            submission=submission_factory(review.request, ApprovalAction.REJECT),
            output_root="output",
        )
    with pytest.raises(ReviewDecisionRejected, match="not approved"):
        service.export_approved(review.artifact.run_id, "output")


def test_round_ten_revision_failure_does_not_mutate_state(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-ROUND-TEN")
    for _ in range(9):
        service.decide(
            submission=submission_factory(review.request, ApprovalAction.REQUEST_REVISION),
            output_root="output",
        )
        review = service.resume(review.artifact.run_id)
    assert review.request.review_round == 10
    state_path = repository / "run-state" / review.artifact.run_id / "state.json"
    before = state_path.read_bytes()

    with pytest.raises(RunStateError, match="maximum review rounds"):
        service.decide(
            submission=submission_factory(
                review.request,
                ApprovalAction.REQUEST_REVISION,
            ),
            output_root="output",
        )

    assert state_path.read_bytes() == before
    assert service.store.load_status(review.artifact.run_id) is WorkflowStatus.NEEDS_REVIEW


def test_approval_with_unsafe_output_path_does_not_consume_review(
    repository: Path,
    tmp_path: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    for run_id, output_root, target in (
        ("RUN-ABSOLUTE-PATH", str(tmp_path / "outside-output"), tmp_path / "outside-output"),
        ("RUN-PARENT-PATH", "../escape-output", repository.parent / "escape-output"),
    ):
        review = service.analyze(run_id)
        with pytest.raises(RuntimeError, match="repository-relative"):
            service.decide(
                submission=submission_factory(review.request, ApprovalAction.APPROVE),
                output_root=output_root,
            )
        assert service.store.load_status(run_id) is WorkflowStatus.NEEDS_REVIEW
        assert not target.exists()


def test_ledger_records_each_revision_round_and_consumed_decision(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    first = service.analyze("RUN-LEDGER")
    service.decide(
        submission=submission_factory(first.request, ApprovalAction.REQUEST_REVISION),
        output_root="output",
    )
    second = service.resume(first.artifact.run_id)

    state = _ledger(repository, first.artifact.run_id)
    assert state["current_round"] == 2
    assert [item["review_round"] for item in state["rounds"]] == [1, 2]
    assert state["decisions"][0]["action"] == ApprovalAction.REQUEST_REVISION.value
    assert len(state["used_nonce_sha256"]) == 1
    assert state["rounds"][1]["request"] == second.request.model_dump(mode="json")
