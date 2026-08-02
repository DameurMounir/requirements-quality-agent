"""Small ports that prevent provider and storage code from entering the domain."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from requirements_quality_agent.domain.models import (
    ApprovalRecord,
    ApprovalRequest,
    CandidateAnalysis,
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

    def consume_nonce(self, run_id: str, nonce_sha256: str) -> None: ...


class ReportExporter(Protocol):
    def export(
        self,
        *,
        artifact: ReviewArtifact,
        approval: ApprovalRecord,
        output_root: Path,
    ) -> ExportManifest: ...
