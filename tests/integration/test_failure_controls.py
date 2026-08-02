from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.application.services import (
    AnalysisBlocked,
    ReviewService,
    RunFailed,
    build_artifact,
)
from requirements_quality_agent.controls.canonical import sha256_text
from requirements_quality_agent.domain.enums import (
    AnalysisOrigin,
    IssueType,
    Severity,
    WorkflowStatus,
)
from requirements_quality_agent.domain.models import (
    CandidateAnalysis,
    CandidateCitation,
    CandidateFinding,
    EvidenceDocument,
    Requirement,
)


class StaticModel:
    def __init__(self, candidate: CandidateAnalysis) -> None:
        self._candidate = candidate

    @property
    def name(self) -> str:
        return "static-test-model"

    @property
    def model_id(self) -> str:
        return "static-v1"

    @property
    def prompt_sha256(self) -> str:
        return sha256_text("static-test-prompt")

    @property
    def reasoning_effort(self) -> str:
        return "none"

    @property
    def configuration(self) -> dict[str, str | int | float | bool | None]:
        return {"mode": "static-test"}

    def analyze(
        self,
        *,
        documents: tuple[EvidenceDocument, ...],
        requirements: tuple[Requirement, ...],
    ) -> CandidateAnalysis:
        del documents, requirements
        return self._candidate


class FailingModel(StaticModel):
    def __init__(self) -> None:
        super().__init__(CandidateAnalysis(findings=()))

    def analyze(
        self,
        *,
        documents: tuple[EvidenceDocument, ...],
        requirements: tuple[Requirement, ...],
    ) -> CandidateAnalysis:
        del documents, requirements
        raise RuntimeError("untrusted provider details")


def _contradiction(
    repository: Path,
    *,
    second_quote: str,
    severity: Severity = Severity.LOW,
) -> CandidateAnalysis:
    pack = load_case_pack(repository)
    by_id = {item.requirement_id: item for item in pack.requirements}
    left = by_id["FR-008"]
    right = by_id["BR-001"]
    return CandidateAnalysis(
        findings=(
            CandidateFinding(
                issue_type=IssueType.CONTRADICTION,
                severity=severity,
                requirement_ids=(left.requirement_id, right.requirement_id),
                explanation="The two statements prescribe mutually exclusive outcomes.",
                citations=(
                    CandidateCitation(
                        source_id=left.source_span.source_id,
                        exact_quote=left.text,
                    ),
                    CandidateCitation(
                        source_id=right.source_span.source_id,
                        exact_quote=second_quote,
                    ),
                ),
                origin=AnalysisOrigin.FIXTURE,
            ),
        )
    )


def _mismatched_contradiction(repository: Path, mismatch: str) -> CandidateAnalysis:
    pack = load_case_pack(repository)
    by_id = {item.requirement_id: item for item in pack.requirements}
    left = by_id["FR-008"]
    right = by_id["BR-001"]
    if mismatch == "cross_source":
        left_citation = CandidateCitation(
            source_id=right.source_span.source_id,
            exact_quote=left.text,
        )
    else:
        wrong_target = by_id["FR-009"]
        left_citation = CandidateCitation(
            source_id=wrong_target.source_span.source_id,
            exact_quote=wrong_target.text,
        )
    return CandidateAnalysis(
        findings=(
            CandidateFinding(
                issue_type=IssueType.CONTRADICTION,
                severity=Severity.LOW,
                requirement_ids=(left.requirement_id, right.requirement_id),
                explanation="The injected adapter attached evidence to the wrong target.",
                citations=(
                    left_citation,
                    CandidateCitation(
                        source_id=right.source_span.source_id,
                        exact_quote=right.text,
                    ),
                ),
                origin=AnalysisOrigin.FIXTURE,
            ),
        )
    )


def _state(repository: Path, run_id: str) -> dict[str, object]:
    path = repository / "run-state" / run_id / "state.json"
    return json.loads(path.read_text())


def test_graph_persists_safe_error_when_analysis_adapter_raises(
    repository: Path,
    service_factory: Callable[..., ReviewService],
) -> None:
    service = service_factory(model=FailingModel())

    with pytest.raises(RunFailed, match="analysis adapter failed closed"):
        service.analyze("RUN-GRAPH-ERROR")

    assert service.store.load_status("RUN-GRAPH-ERROR") is WorkflowStatus.ERROR
    state = _state(repository, "RUN-GRAPH-ERROR")
    assert state["failure"] == {
        "code": "ANALYSIS-ERROR",
        "retryable": True,
        "safe_message": "the analysis adapter failed closed",
        "stage": WorkflowStatus.ANALYZING.value,
    }
    assert state["rounds"] == []
    assert "untrusted provider details" not in json.dumps(state)


def test_low_model_severity_cannot_bypass_unsupported_contradiction_block(
    repository: Path,
    service_factory: Callable[..., ReviewService],
) -> None:
    candidate = _contradiction(repository, second_quote="quote absent from all sources")
    service = service_factory(model=StaticModel(candidate))

    with pytest.raises(RunFailed, match="evidence verification blocked"):
        service.analyze("RUN-GRAPH-BLOCKED")

    assert service.store.load_status("RUN-GRAPH-BLOCKED") is WorkflowStatus.BLOCKED
    state = _state(repository, "RUN-GRAPH-BLOCKED")
    assert state["failure"]["code"] == "EVIDENCE-BLOCKED"
    assert state["failure"]["stage"] == WorkflowStatus.VERIFYING.value
    assert state["rounds"] == []


def test_resolved_contradiction_uses_control_owned_critical_severity(
    repository: Path,
) -> None:
    pack = load_case_pack(repository)
    right = next(item for item in pack.requirements if item.requirement_id == "BR-001")
    candidate = _contradiction(repository, second_quote=right.text, severity=Severity.LOW)
    model = StaticModel(candidate)

    artifact = build_artifact(
        run_id="RUN-CONTROL-SEVERITY",
        pack=pack,
        candidate=candidate,
        model=model,
    )

    assert candidate.findings[0].severity is Severity.LOW
    assert artifact.findings[0].severity is Severity.CRITICAL


def test_direct_build_blocks_unsupported_contradiction_even_when_model_says_low(
    repository: Path,
) -> None:
    pack = load_case_pack(repository)
    candidate = _contradiction(repository, second_quote="fabricated quote", severity=Severity.LOW)

    with pytest.raises(AnalysisBlocked, match="blocking issue lacks exact evidence"):
        build_artifact(
            run_id="RUN-DIRECT-BLOCK",
            pack=pack,
            candidate=candidate,
            model=StaticModel(candidate),
        )


@pytest.mark.parametrize(
    ("mismatch", "run_id"),
    [
        ("cross_source", "RUN-CROSS-SOURCE-CITATION"),
        ("wrong_target", "RUN-WRONG-TARGET-CITATION"),
    ],
)
def test_cross_source_or_wrong_target_citation_blocks_the_integration_run(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    mismatch: str,
    run_id: str,
) -> None:
    candidate = _mismatched_contradiction(repository, mismatch)
    service = service_factory(model=StaticModel(candidate))

    with pytest.raises(RunFailed, match="evidence verification blocked"):
        service.analyze(run_id)

    assert service.store.load_status(run_id) is WorkflowStatus.BLOCKED
    state = _state(repository, run_id)
    assert state["failure"]["code"] == "EVIDENCE-BLOCKED"
    assert state["rounds"] == []
    assert not (repository / "output").exists()
