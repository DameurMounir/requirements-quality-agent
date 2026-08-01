from datetime import UTC, datetime

import pytest

from requirements_quality_agent.controls.approval import (
    ApprovalRejected,
    approval_record,
    validate_submission,
)
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import ApprovalRequest, ApprovalSubmission

DIGEST = "a" * 64


def request() -> ApprovalRequest:
    return ApprovalRequest(
        run_id="RUN-001",
        artifact_sha256=DIGEST,
        reviewer_id="demo-owner",
        review_round=1,
        nonce="n" * 32,
        allowed_actions=tuple(ApprovalAction),
    )


def submission(**changes: object) -> ApprovalSubmission:
    values: dict[str, object] = {
        "run_id": "RUN-001",
        "artifact_sha256": DIGEST,
        "reviewer_id": "demo-owner",
        "review_round": 1,
        "nonce": "n" * 32,
        "action": ApprovalAction.APPROVE,
    }
    values.update(changes)
    return ApprovalSubmission.model_validate(values)


def test_matching_submission_is_accepted() -> None:
    validate_submission(request=request(), submission=submission())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", "RUN-999"),
        ("artifact_sha256", "b" * 64),
        ("reviewer_id", "other-reviewer"),
        ("review_round", 2),
        ("nonce", "x" * 32),
    ],
)
def test_binding_mismatch_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ApprovalRejected, match=field):
        validate_submission(request=request(), submission=submission(**{field: value}))


def test_record_preserves_exact_binding() -> None:
    decided_at = datetime(2026, 8, 1, tzinfo=UTC)
    record = approval_record(request=request(), submission=submission(), now=decided_at)
    assert record.artifact_sha256 == DIGEST
    assert record.action is ApprovalAction.APPROVE
    assert record.decided_at == decided_at
    assert len(record.submission_sha256) == 64
