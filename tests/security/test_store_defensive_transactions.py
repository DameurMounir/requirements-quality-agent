from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from requirements_quality_agent.adapters.output.local_files import LocalReportExporter
from requirements_quality_agent.adapters.storage.local_store import LocalRunStore, RunStateError
from requirements_quality_agent.application.services import ReviewService
from requirements_quality_agent.controls.approval import (
    approval_record,
    new_approval_request,
)
from requirements_quality_agent.controls.canonical import sha256_text
from requirements_quality_agent.domain.enums import ApprovalAction, WorkflowStatus
from requirements_quality_agent.domain.models import (
    ApprovalSubmission,
    ControlFailure,
    RevisionEdit,
)


def _path(repository: Path, run_id: str) -> Path:
    return repository / "run-state" / run_id / "state.json"


def _read(repository: Path, run_id: str) -> dict[str, object]:
    return json.loads(_path(repository, run_id).read_text())


def _write(repository: Path, run_id: str, state: dict[str, object]) -> None:
    _path(repository, run_id).write_text(json.dumps(state))


def _failure() -> ControlFailure:
    return ControlFailure(
        code="TEST-FAILURE",
        safe_message="controlled test failure",
        stage=WorkflowStatus.ANALYZING,
        retryable=False,
    )


def test_state_root_must_be_inside_repository(repository: Path, tmp_path: Path) -> None:
    with pytest.raises(RunStateError, match="inside the repository"):
        LocalRunStore(repository_root=repository, state_root=tmp_path / "outside-state")


@pytest.mark.parametrize("run_id", ["../escape", "lowercase", "A", "RUN_UNDERSCORE"])
def test_run_ids_are_allowlisted(repository: Path, run_id: str) -> None:
    store = LocalRunStore(repository_root=repository, state_root=Path("run-state"))
    with pytest.raises(RunStateError, match="unsafe run ID"):
        store.load_status(run_id)


def test_missing_run_directory_is_rejected(repository: Path) -> None:
    store = LocalRunStore(repository_root=repository, state_root=Path("run-state"))
    with pytest.raises(RunStateError, match="missing or invalid"):
        store.load_status("RUN-MISSING")


@pytest.mark.parametrize("lock_kind", ["symlink", "directory"])
def test_run_lock_must_be_a_regular_openable_file(
    repository: Path,
    tmp_path: Path,
    service_factory: Callable[..., ReviewService],
    lock_kind: str,
) -> None:
    run_id = f"RUN-LOCK-{lock_kind.upper()}"
    service = service_factory()
    service.analyze(run_id)
    lock = repository / "run-state" / run_id / ".lock"
    lock.unlink()
    if lock_kind == "symlink":
        outside = tmp_path / "outside-lock"
        outside.write_text("lock")
        lock.symlink_to(outside)
        message = "lock may not be a symlink"
    else:
        lock.mkdir()
        message = "cannot be opened safely"
    with pytest.raises(RunStateError, match=message):
        service.store.load_status(run_id)


@pytest.mark.parametrize(
    "mutation",
    [
        "status_not_string",
        "status_unknown",
        "rounds_not_list",
        "round_not_object",
        "duplicate_nonces",
        "none_round_with_rounds",
        "boolean_round",
        "artifact_run",
        "request_run",
        "request_round",
    ],
)
def test_malformed_ledger_bindings_are_rejected(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    mutation: str,
) -> None:
    run_id = f"RUN-LEDGER-{mutation.replace('_', '-').upper()}"
    service = service_factory()
    service.analyze(run_id)
    state = _read(repository, run_id)
    if mutation == "status_not_string":
        state["status"] = 7
    elif mutation == "status_unknown":
        state["status"] = "UNKNOWN"
    elif mutation == "rounds_not_list":
        state["rounds"] = {}
    elif mutation == "round_not_object":
        state["rounds"] = ["not-an-object"]
    elif mutation == "duplicate_nonces":
        state["used_nonce_sha256"] = ["a" * 64, "a" * 64]
    elif mutation == "none_round_with_rounds":
        state["current_round"] = None
    elif mutation == "boolean_round":
        state["current_round"] = True
    elif mutation == "artifact_run":
        state["rounds"][0]["artifact"]["run_id"] = "RUN-DIFFERENT"
    elif mutation == "request_run":
        state["rounds"][0]["request"]["run_id"] = "RUN-DIFFERENT"
    else:
        state["rounds"][0]["request"]["review_round"] = 2
    _write(repository, run_id, state)

    with pytest.raises(RunStateError):
        service.store.load_status(run_id)


@pytest.mark.parametrize("ledger_kind", ["invalid_json", "directory"])
def test_invalid_ledger_storage_is_rejected(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    ledger_kind: str,
) -> None:
    run_id = f"RUN-INVALID-{ledger_kind.replace('_', '-').upper()}"
    service = service_factory()
    service.analyze(run_id)
    path = _path(repository, run_id)
    path.unlink()
    if ledger_kind == "invalid_json":
        path.write_text("not-json")
        message = "missing or invalid"
    else:
        path.mkdir()
        message = "ledger is invalid"
    with pytest.raises(RunStateError, match=message):
        service.store.load_status(run_id)


@pytest.mark.parametrize("mutation", ["decision_run", "missing_nonce"])
def test_decision_ledger_bindings_are_validated(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
    mutation: str,
) -> None:
    run_id = f"RUN-DECISION-{mutation.replace('_', '-').upper()}"
    service = service_factory()
    review = service.analyze(run_id)
    service.decide(
        submission=submission_factory(review.request, ApprovalAction.REQUEST_REVISION),
        output_root="output",
    )
    state = _read(repository, run_id)
    if mutation == "decision_run":
        state["decisions"][0]["run_id"] = "RUN-DIFFERENT"
    else:
        state["used_nonce_sha256"] = []
    _write(repository, run_id, state)
    with pytest.raises(RunStateError, match="bindings are invalid"):
        service.store.load_status(run_id)


def test_save_review_rejects_mismatch_noninitial_and_duplicate(
    service_factory: Callable[..., ReviewService],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-SAVE-REVIEW")
    mismatched = review.request.model_copy(update={"run_id": "RUN-DIFFERENT"})
    with pytest.raises(RunStateError, match="run IDs differ"):
        service.store.save_review(review.artifact, mismatched)
    later = review.request.model_copy(update={"review_round": 2})
    with pytest.raises(RunStateError, match="round one"):
        service.store.save_review(review.artifact, later)
    with pytest.raises(RunStateError, match="already exists"):
        service.store.save_review(review.artifact, review.request)


def test_save_failure_validates_status_updates_open_and_preserves_terminal(
    service_factory: Callable[..., ReviewService],
) -> None:
    service = service_factory()
    run_id = "RUN-SAVE-FAILURE"
    service.analyze(run_id)
    with pytest.raises(RunStateError, match="invalid failure status"):
        service.store.save_failure(run_id, WorkflowStatus.APPROVED, _failure())
    service.store.save_failure(run_id, WorkflowStatus.BLOCKED, _failure())
    assert service.store.load_status(run_id) is WorkflowStatus.BLOCKED
    with pytest.raises(RunStateError, match="terminal run status"):
        service.store.save_failure(run_id, WorkflowStatus.ERROR, _failure())


def test_transaction_methods_validate_action_and_current_status(
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-TRANSACTION-GUARDS")
    approve = approval_record(
        request=review.request,
        submission=submission_factory(review.request, ApprovalAction.APPROVE),
    )
    with pytest.raises(RunStateError, match="action and status"):
        service.store.commit_decision(approve, WorkflowStatus.REJECTED)
    with pytest.raises(RunStateError, match="requires an EDIT"):
        service.store.commit_edit(approve, review.artifact, review.request)
    with pytest.raises(RunStateError, match="not waiting"):
        service.store.commit_revision(review.artifact, review.request)
    with pytest.raises(RunStateError, match="not approved"):
        service.store.load_approved(review.artifact.run_id)


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        ("round", "not monotonic"),
        ("reviewer", "reviewer binding"),
        ("same_digest", "digest did not change"),
        ("nonce", "ledger bindings are invalid"),
        ("source", "source-pack binding"),
    ],
)
def test_edit_transaction_rejects_stale_or_changed_bindings(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
    variant: str,
    message: str,
) -> None:
    service = service_factory()
    review = service.analyze(f"RUN-EDIT-GUARD-{variant.replace('_', '-').upper()}")
    proposal = review.artifact.revisions[0]
    edit_submission = submission_factory(
        review.request,
        ApprovalAction.EDIT,
        edits=(
            RevisionEdit(
                proposal_id=proposal.proposal_id,
                replacement_text=proposal.proposed_text + " Edited.",
            ),
        ),
    )
    edit_record = approval_record(request=review.request, submission=edit_submission)
    changed_artifact = review.artifact.model_copy(
        update={"clarification_questions": (*review.artifact.clarification_questions, "Edited?")}
    )
    next_request = new_approval_request(
        artifact=changed_artifact,
        reviewer_id=review.request.reviewer_id,
        review_round=2,
    )
    if variant == "round":
        next_request = next_request.model_copy(update={"review_round": 1})
    elif variant == "reviewer":
        next_request = next_request.model_copy(update={"reviewer_id": "other-reviewer"})
    elif variant == "same_digest":
        changed_artifact = review.artifact
        next_request = new_approval_request(
            artifact=review.artifact,
            reviewer_id=review.request.reviewer_id,
            review_round=2,
        )
    elif variant == "nonce":
        state = _read(repository, review.artifact.run_id)
        state["used_nonce_sha256"] = [sha256_text(next_request.nonce)]
        _write(repository, review.artifact.run_id, state)
    else:
        changed_artifact = changed_artifact.model_copy(update={"source_pack_sha256": "f" * 64})
        next_request = new_approval_request(
            artifact=changed_artifact,
            reviewer_id=review.request.reviewer_id,
            review_round=2,
        )

    with pytest.raises(RunStateError, match=message):
        service.store.commit_edit(edit_record, changed_artifact, next_request)


def test_edit_at_round_ten_is_atomic(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-EDIT-ROUND-TEN")
    for _ in range(9):
        service.decide(
            submission=submission_factory(review.request, ApprovalAction.REQUEST_REVISION),
            output_root="output",
        )
        review = service.resume(review.artifact.run_id)
    assert review.request.review_round == 10
    proposal = review.artifact.revisions[0]
    submission = submission_factory(
        review.request,
        ApprovalAction.EDIT,
        edits=(RevisionEdit(proposal_id=proposal.proposal_id, replacement_text="Edited text"),),
    )
    before = _path(repository, review.artifact.run_id).read_bytes()

    with pytest.raises(ValidationError, match="less than or equal to 10"):
        service.decide(submission=submission, output_root="output")
    assert _path(repository, review.artifact.run_id).read_bytes() == before


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        ("round", "not monotonic"),
        ("reviewer", "reviewer binding"),
        ("nonce", "ledger bindings are invalid"),
        ("source", "source-pack binding"),
    ],
)
def test_revision_transaction_rejects_changed_bindings(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
    variant: str,
    message: str,
) -> None:
    service = service_factory()
    review = service.analyze(f"RUN-REV-GUARD-{variant.upper()}")
    service.decide(
        submission=submission_factory(review.request, ApprovalAction.REQUEST_REVISION),
        output_root="output",
    )
    changed_artifact = review.artifact.model_copy(
        update={"clarification_questions": (*review.artifact.clarification_questions, "Revised?")}
    )
    request = new_approval_request(
        artifact=changed_artifact,
        reviewer_id=review.request.reviewer_id,
        review_round=2,
    )
    if variant == "round":
        request = request.model_copy(update={"review_round": 1})
    elif variant == "reviewer":
        request = request.model_copy(update={"reviewer_id": "other-reviewer"})
    elif variant == "nonce":
        state = _read(repository, review.artifact.run_id)
        state["used_nonce_sha256"].append(sha256_text(request.nonce))
        _write(repository, review.artifact.run_id, state)
    else:
        changed_artifact = changed_artifact.model_copy(update={"source_pack_sha256": "f" * 64})
        request = new_approval_request(
            artifact=changed_artifact,
            reviewer_id=review.request.reviewer_id,
            review_round=2,
        )

    with pytest.raises(RunStateError, match=message):
        service.store.commit_revision(changed_artifact, request)


def test_mark_exported_validates_status_approval_and_manifest_bindings(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-MARK-GUARDS")
    submission = submission_factory(review.request, ApprovalAction.APPROVE)
    approval = approval_record(request=review.request, submission=submission)
    manifest = LocalReportExporter(repository).export(
        artifact=review.artifact,
        approval=approval,
        output_root=Path("output-direct"),
    )
    with pytest.raises(RunStateError, match="only an approved"):
        service.store.mark_exported(review.artifact.run_id, approval.approval_id, manifest)

    service.store.commit_decision(approval, WorkflowStatus.APPROVED)
    with pytest.raises(RunStateError, match="approval identity"):
        service.store.mark_exported(review.artifact.run_id, "APR-WRONG", manifest)
    wrong_manifest = manifest.model_copy(update={"approval_sha256": "f" * 64})
    with pytest.raises(RunStateError, match="does not bind"):
        service.store.mark_exported(
            review.artifact.run_id,
            approval.approval_id,
            wrong_manifest,
        )


def test_approved_status_without_one_bound_approval_is_rejected(
    repository: Path,
    service_factory: Callable[..., ReviewService],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-MISSING-APPROVAL")
    state = _read(repository, review.artifact.run_id)
    state["status"] = WorkflowStatus.APPROVED.value
    _write(repository, review.artifact.run_id, state)

    with pytest.raises(RunStateError, match="ledger bindings are invalid"):
        service.store.load_approved(review.artifact.run_id)
