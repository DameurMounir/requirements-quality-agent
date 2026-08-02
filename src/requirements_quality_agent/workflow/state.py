"""Typed LangGraph-compatible state surface."""

from __future__ import annotations

from typing import TypedDict

from requirements_quality_agent.domain.models import (
    ApprovalRecord,
    ApprovalRequest,
    CandidateAnalysis,
    ControlFailure,
    EvidenceDocument,
    ExportManifest,
    Requirement,
    ReviewArtifact,
    SourceManifest,
)


class ReviewState(TypedDict, total=False):
    run_id: str
    status: str
    review_round: int
    expected_source_pack_sha256: str
    manifest_sha256: str
    source_pack_sha256: str
    manifest: SourceManifest
    documents: tuple[EvidenceDocument, ...]
    requirements: tuple[Requirement, ...]
    candidate_analysis: CandidateAnalysis
    artifact: ReviewArtifact
    approval_request: ApprovalRequest
    approval_record: ApprovalRecord
    export_manifest: ExportManifest
    failures: tuple[ControlFailure, ...]
