from itertools import pairwise

import pytest

from requirements_quality_agent.domain.enums import WorkflowStatus
from requirements_quality_agent.workflow.topology import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    require_transition,
)


def test_happy_path_is_explicit() -> None:
    path = [
        WorkflowStatus.RECEIVED,
        WorkflowStatus.VALIDATED,
        WorkflowStatus.ANALYZING,
        WorkflowStatus.VERIFYING,
        WorkflowStatus.NEEDS_REVIEW,
        WorkflowStatus.APPROVED,
        WorkflowStatus.EXPORTED,
    ]
    for current, target in pairwise(path):
        require_transition(current, target)


def test_export_cannot_be_reached_without_approval() -> None:
    with pytest.raises(InvalidTransition):
        require_transition(WorkflowStatus.NEEDS_REVIEW, WorkflowStatus.EXPORTED)


def test_terminal_states_have_no_outgoing_edges() -> None:
    for status in (
        WorkflowStatus.REJECTED,
        WorkflowStatus.BLOCKED,
        WorkflowStatus.ERROR,
        WorkflowStatus.EXPORTED,
    ):
        assert not ALLOWED_TRANSITIONS[status]
