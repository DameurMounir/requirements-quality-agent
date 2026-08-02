"""Small ports that prevent provider and storage code from entering the domain."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from requirements_quality_agent.domain.enums import WorkflowStatus
from requirements_quality_agent.domain.models import (
    ApprovalRecord,
    ApprovalRequest,
    CandidateAnalysis,
    ControlFailure,
    EvidenceDocument,
    ExportManifest,
    Requirement,
    ReviewArtifact,
)


class AnalysisModel(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model_id(self) -> str | None: ...

    @property
    def prompt_sha256(self) -> str: ...

    @property
    def reasoning_effort(self) -> str | None: ...

    @property
    def configuration(self) -> dict[str, str | int | float | bool | None]: ...

    def analyze(
        self,
        *,
        documents: tuple[EvidenceDocument, ...],
        requirements: tuple[Requirement, ...],
    ) -> CandidateAnalysis: ...


class RunStore(Protocol):
    def save_review(
        self,
        artifact: ReviewArtifact,
        request: ApprovalRequest,
    ) -> None: ...

    def load_review(self, run_id: str) -> tuple[ReviewArtifact, ApprovalRequest]: ...

    def save_failure(
        self,
        run_id: str,
        status: WorkflowStatus,
        failure: ControlFailure,
    ) -> None: ...

    def commit_decision(
        self,
        approval: ApprovalRecord,
        status: WorkflowStatus,
    ) -> None: ...

    def commit_edit(
        self,
        approval: ApprovalRecord,
        artifact: ReviewArtifact,
        request: ApprovalRequest,
    ) -> None: ...

    def commit_revision(
        self,
        artifact: ReviewArtifact,
        request: ApprovalRequest,
    ) -> None: ...

    def load_status(self, run_id: str) -> WorkflowStatus: ...

    def load_approved(self, run_id: str) -> tuple[ReviewArtifact, ApprovalRecord]: ...

    def mark_exported(
        self,
        run_id: str,
        approval_id: str,
        manifest: ExportManifest,
    ) -> None: ...


class ReportExporter(Protocol):
    def validate_output_root(self, output_root: Path) -> Path: ...

    def export(
        self,
        *,
        artifact: ReviewArtifact,
        approval: ApprovalRecord,
        output_root: Path,
    ) -> ExportManifest: ...
