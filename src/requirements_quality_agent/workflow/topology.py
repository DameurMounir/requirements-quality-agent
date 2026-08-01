"""Fail-closed public workflow transition contract."""

from __future__ import annotations

from requirements_quality_agent.domain.enums import WorkflowStatus

ALLOWED_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.RECEIVED: frozenset({WorkflowStatus.VALIDATED, WorkflowStatus.REJECTED}),
    WorkflowStatus.VALIDATED: frozenset({WorkflowStatus.ANALYZING, WorkflowStatus.ERROR}),
    WorkflowStatus.ANALYZING: frozenset({WorkflowStatus.VERIFYING, WorkflowStatus.ERROR}),
    WorkflowStatus.VERIFYING: frozenset(
        {WorkflowStatus.NEEDS_REVIEW, WorkflowStatus.BLOCKED, WorkflowStatus.ERROR}
    ),
    WorkflowStatus.NEEDS_REVIEW: frozenset(
        {
            WorkflowStatus.APPROVED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.REVISION_REQUESTED,
        }
    ),
    WorkflowStatus.REVISION_REQUESTED: frozenset(
        {WorkflowStatus.ANALYZING, WorkflowStatus.BLOCKED}
    ),
    WorkflowStatus.APPROVED: frozenset({WorkflowStatus.EXPORTED, WorkflowStatus.ERROR}),
    WorkflowStatus.REJECTED: frozenset(),
    WorkflowStatus.BLOCKED: frozenset(),
    WorkflowStatus.ERROR: frozenset(),
    WorkflowStatus.EXPORTED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when code attempts a path outside the frozen state machine."""


def require_transition(current: WorkflowStatus, target: WorkflowStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"transition {current.value} -> {target.value} is forbidden")
