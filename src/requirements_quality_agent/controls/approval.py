"""Digest-bound approval construction and validation."""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime

from requirements_quality_agent.controls.canonical import domain_digest, sha256_text
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalSubmission,
    ReviewArtifact,
)


class ApprovalRejected(ValueError):
    """Raised when a review decision is stale, mismatched, or replayed."""


def review_artifact_digest(artifact: ReviewArtifact) -> str:
    return domain_digest("review-artifact", artifact)


def new_approval_request(
    *,
    artifact: ReviewArtifact,
    reviewer_id: str,
    review_round: int,
) -> ApprovalRequest:
    return ApprovalRequest(
        run_id=artifact.run_id,
        artifact_sha256=review_artifact_digest(artifact),
        reviewer_id=reviewer_id,
        review_round=review_round,
        nonce=secrets.token_urlsafe(32),
        allowed_actions=tuple(ApprovalAction),
    )


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def validate_submission(
    *,
    request: ApprovalRequest,
    submission: ApprovalSubmission,
) -> None:
    comparisons = {
        "run_id": (request.run_id, submission.run_id),
        "artifact_sha256": (request.artifact_sha256, submission.artifact_sha256),
        "reviewer_id": (request.reviewer_id, submission.reviewer_id),
        "nonce": (request.nonce, submission.nonce),
    }
    mismatches = [name for name, values in comparisons.items() if not _same(*values)]
    if request.review_round != submission.review_round:
        mismatches.append("review_round")
    if submission.action not in request.allowed_actions:
        mismatches.append("action")
    if mismatches:
        raise ApprovalRejected(f"approval binding mismatch: {', '.join(sorted(mismatches))}")


def approval_record(
    *,
    request: ApprovalRequest,
    submission: ApprovalSubmission,
    now: datetime | None = None,
) -> ApprovalRecord:
    validate_submission(request=request, submission=submission)
    decided_at = now or datetime.now(UTC)
    submission_digest = domain_digest("approval-submission", submission)
    return ApprovalRecord(
        approval_id=f"APR-{submission_digest[:16].upper()}",
        run_id=submission.run_id,
        artifact_sha256=submission.artifact_sha256,
        reviewer_id=submission.reviewer_id,
        review_round=submission.review_round,
        nonce_sha256=sha256_text(submission.nonce),
        action=submission.action,
        comment=submission.comment,
        decided_at=decided_at,
        submission_sha256=submission_digest,
    )
