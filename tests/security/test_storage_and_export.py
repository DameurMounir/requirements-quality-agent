from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.adapters.storage.local_store import LocalRunStore, RunStateError
from requirements_quality_agent.application.services import ReviewService
from requirements_quality_agent.controls.canonical import sha256_text
from requirements_quality_agent.domain.enums import (
    AnalysisOrigin,
    ApprovalAction,
    IssueType,
    Severity,
    WorkflowStatus,
)
from requirements_quality_agent.domain.models import (
    ApprovalSubmission,
    CandidateAnalysis,
    CandidateCitation,
    CandidateFinding,
    EvidenceDocument,
    Requirement,
)


class MarkdownModel:
    @property
    def name(self) -> str:
        return "markdown-safety-test"

    @property
    def model_id(self) -> None:
        return None

    @property
    def prompt_sha256(self) -> str:
        return sha256_text("markdown-safety-test")

    @property
    def reasoning_effort(self) -> None:
        return None

    @property
    def configuration(self) -> dict[str, str | int | float | bool | None]:
        return {"mode": "markdown-safety-test"}

    def analyze(
        self,
        *,
        documents: tuple[EvidenceDocument, ...],
        requirements: tuple[Requirement, ...],
    ) -> CandidateAnalysis:
        del documents
        target = next(item for item in requirements if item.requirement_id == "FR-001")
        return CandidateAnalysis(
            findings=(
                CandidateFinding(
                    issue_type=IssueType.AMBIGUOUS_TERM,
                    severity=Severity.LOW,
                    requirement_ids=(target.requirement_id,),
                    explanation=(
                        "Unsafe | [link](https://invalid) *bold* _under_ <script>."
                        "\r\n# injected heading\r`code`"
                    ),
                    citations=(
                        CandidateCitation(
                            source_id=target.source_span.source_id,
                            exact_quote=target.text,
                        ),
                    ),
                    proposed_revision=(
                        "Measure | [this](https://invalid) and do not render <script>."
                        "\r# proposal heading\r\n`proposal code`"
                    ),
                    clarification_question=(
                        "Who owns | [this](https://invalid)?\r\n# question heading\r`question code`"
                    ),
                    origin=AnalysisOrigin.FIXTURE,
                ),
            )
        )


def _state_path(repository: Path, run_id: str) -> Path:
    return repository / "run-state" / run_id / "state.json"


@pytest.mark.parametrize("tamper", ["run_id", "artifact_digest", "current_round"])
def test_tampered_run_digest_or_round_is_rejected(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    tamper: str,
) -> None:
    run_id = f"RUN-TAMPER-{tamper.replace('_', '-').upper()}"
    service = service_factory()
    service.analyze(run_id)
    path = _state_path(repository, run_id)
    state = json.loads(path.read_text())
    if tamper == "run_id":
        state["run_id"] = "RUN-DIFFERENT"
    elif tamper == "artifact_digest":
        state["rounds"][0]["request"]["artifact_sha256"] = "f" * 64
    else:
        state["current_round"] = 9
    path.write_text(json.dumps(state))

    with pytest.raises(RunStateError):
        service.store.load_review(run_id)


def test_tampered_artifact_content_is_rejected_by_digest_binding(
    repository: Path,
    service_factory: Callable[..., ReviewService],
) -> None:
    run_id = "RUN-TAMPER-CONTENT"
    service = service_factory()
    service.analyze(run_id)
    path = _state_path(repository, run_id)
    state = json.loads(path.read_text())
    state["rounds"][0]["artifact"]["scorecard"]["candidate_findings"] += 1
    path.write_text(json.dumps(state))

    with pytest.raises(RunStateError, match="digest binding"):
        service.store.load_review(run_id)


def test_state_root_symlink_is_rejected(repository: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-state"
    outside.mkdir()
    (repository / "linked-state").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RunStateError, match="state root may not be a symlink"):
        LocalRunStore(repository_root=repository, state_root=Path("linked-state"))


def test_run_directory_symlink_is_rejected(repository: Path, tmp_path: Path) -> None:
    store = LocalRunStore(repository_root=repository, state_root=Path("run-state"))
    outside = tmp_path / "outside-run"
    outside.mkdir()
    (repository / "run-state" / "RUN-LINKED").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RunStateError, match="run directory may not be a symlink"):
        store.load_status("RUN-LINKED")


def test_run_ledger_symlink_is_rejected(
    repository: Path,
    tmp_path: Path,
    service_factory: Callable[..., ReviewService],
) -> None:
    run_id = "RUN-LINKED-LEDGER"
    service = service_factory()
    service.analyze(run_id)
    state_path = _state_path(repository, run_id)
    outside = tmp_path / "outside-state.json"
    outside.write_bytes(state_path.read_bytes())
    state_path.unlink()
    state_path.symlink_to(outside)

    with pytest.raises(RunStateError, match="ledger may not be a symlink"):
        service.store.load_status(run_id)


def test_output_symlink_is_rejected_without_writing_external_files(
    repository: Path,
    tmp_path: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    run_id = "RUN-LINKED-OUTPUT"
    service = service_factory()
    review = service.analyze(run_id)
    outside = tmp_path / "outside-output"
    outside.mkdir()
    (repository / "linked-output").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink"):
        service.decide(
            submission=submission_factory(review.request, ApprovalAction.APPROVE),
            output_root="linked-output",
        )

    assert list(outside.iterdir()) == []
    assert service.store.load_status(run_id) is WorkflowStatus.NEEDS_REVIEW


def test_markdown_escapes_model_text_and_exposes_control_status_columns(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    run_id = "RUN-MARKDOWN-SAFE"
    service = service_factory(
        model=MarkdownModel(),
        reviewer_id="reviewer | [unsafe](x)\r\n# reviewer heading\r`reviewer code`",
    )
    review = service.analyze(run_id)
    decision = service.decide(
        submission=submission_factory(review.request, ApprovalAction.APPROVE),
        output_root="output",
    )
    assert decision.status is WorkflowStatus.EXPORTED
    markdown = (repository / "output" / run_id / "report.md").read_text()

    assert "| ID | Type | Severity | Status | Evidence verdict |" in markdown
    assert "| VERIFIED | RESOLVED |" in markdown
    assert "Unsafe \\| \\[link\\]\\(https://invalid\\) \\*bold\\* \\_under\\_" in markdown
    assert "&lt;script&gt;" in markdown
    assert "reviewer \\| \\[unsafe\\]\\(x\\)" in markdown
    assert "\\# injected heading" in markdown
    assert "\\# proposal heading" in markdown
    assert "\\# question heading" in markdown
    assert "\\# reviewer heading" in markdown
    assert "\\`code\\`" in markdown
    assert "\r" not in markdown
    assert "\n# injected heading" not in markdown
    assert "Unsafe | [link](https://invalid)" not in markdown
    assert "<script>" not in markdown


def test_fixture_and_gold_files_never_enter_model_documents(repository: Path) -> None:
    pack = load_case_pack(repository)
    paths = {document.relative_path for document in pack.documents}

    assert all(path.startswith("case/evidence/") for path in paths)
    assert not any("expected" in path or "fixtures" in path for path in paths)
    assert all("requirements-labels.jsonl" not in document.text for document in pack.documents)
