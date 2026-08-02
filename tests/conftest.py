from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.models.rule import RuleAnalysisAdapter
from requirements_quality_agent.adapters.output.local_files import LocalReportExporter
from requirements_quality_agent.adapters.storage.local_store import LocalRunStore
from requirements_quality_agent.application.ports import AnalysisModel
from requirements_quality_agent.application.services import ReviewService
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import (
    ApprovalRequest,
    ApprovalSubmission,
    RevisionEdit,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Create an isolated repository boundary containing the frozen case pack."""

    root = tmp_path / "repository"
    root.mkdir()
    shutil.copytree(PROJECT_ROOT / "case", root / "case")
    return root


@pytest.fixture
def service_factory(
    repository: Path,
) -> Callable[..., ReviewService]:
    def build(
        *,
        model: AnalysisModel | None = None,
        state_root: Path = Path("run-state"),
        reviewer_id: str = "test-reviewer",
    ) -> ReviewService:
        return ReviewService(
            repository_root=str(repository),
            model=model if model is not None else RuleAnalysisAdapter(),
            store=LocalRunStore(repository_root=repository, state_root=state_root),
            exporter=LocalReportExporter(repository),
            reviewer_id=reviewer_id,
        )

    return build


def _submission_for(
    request: ApprovalRequest,
    action: ApprovalAction,
    *,
    comment: str | None = None,
    edits: tuple[RevisionEdit, ...] = (),
) -> ApprovalSubmission:
    return ApprovalSubmission(
        run_id=request.run_id,
        artifact_sha256=request.artifact_sha256,
        reviewer_id=request.reviewer_id,
        review_round=request.review_round,
        nonce=request.nonce,
        action=action,
        comment=comment,
        edits=edits,
    )


@pytest.fixture
def submission_factory() -> Callable[..., ApprovalSubmission]:
    return _submission_for
