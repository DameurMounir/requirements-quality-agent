import pytest
from pydantic import ValidationError

from requirements_quality_agent.domain.enums import AnalysisOrigin, IssueType, Severity
from requirements_quality_agent.domain.models import CandidateCitation, CandidateFinding


def test_pair_finding_requires_two_targets_and_citations() -> None:
    with pytest.raises(ValidationError, match="pair findings require"):
        CandidateFinding(
            issue_type=IssueType.CONTRADICTION,
            severity=Severity.CRITICAL,
            requirement_ids=("FR-001",),
            explanation="Candidate conflict",
            citations=(CandidateCitation(source_id="SRC-001", exact_quote="text"),),
            origin=AnalysisOrigin.FIXTURE,
        )


def test_model_output_cannot_add_approval_field() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CandidateFinding.model_validate(
            {
                "issue_type": IssueType.AMBIGUOUS_TERM,
                "severity": Severity.HIGH,
                "requirement_ids": ["FR-001"],
                "explanation": "Candidate ambiguity",
                "citations": [{"source_id": "SRC-001", "exact_quote": "quickly"}],
                "origin": AnalysisOrigin.FIXTURE,
                "approved": True,
            }
        )
