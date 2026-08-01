"""Strict Pydantic contracts shared by every adapter and workflow node."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from requirements_quality_agent.domain.enums import (
    AnalysisOrigin,
    ApprovalAction,
    EvidenceVerdict,
    FindingStatus,
    IssueType,
    RequirementKind,
    Severity,
    WorkflowStatus,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
StableId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9-]{2,79}$")]


class StrictModel(BaseModel):
    """Forbid silent schema drift at application boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SourceManifestEntry(StrictModel):
    source_id: StableId
    version: str = Field(min_length=1, max_length=32)
    path: str = Field(min_length=1, max_length=240)
    sha256: Sha256
    allowed_for_model: bool


class SourceManifest(StrictModel):
    case_id: StableId
    version: str
    created_on: str
    classification: str
    licence: str
    model_input_root: str
    expected_root: str
    sources: tuple[SourceManifestEntry, ...]

    @model_validator(mode="after")
    def unique_sources(self) -> SourceManifest:
        ids = [source.source_id for source in self.sources]
        paths = [source.path for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source IDs must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("source paths must be unique")
        return self


class EvidenceDocument(StrictModel):
    source_id: StableId
    version: str
    relative_path: str
    text: str
    sha256: Sha256


class SourceSpan(StrictModel):
    source_id: StableId
    source_sha256: Sha256
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    exact_text: str = Field(min_length=1)
    exact_text_sha256: Sha256

    @model_validator(mode="after")
    def ordered_bounds(self) -> SourceSpan:
        if self.line_end < self.line_start:
            raise ValueError("line_end must not precede line_start")
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class Requirement(StrictModel):
    requirement_id: StableId
    kind: RequirementKind
    text: str = Field(min_length=1, max_length=5000)
    source_span: SourceSpan


class CandidateCitation(StrictModel):
    source_id: StableId
    exact_quote: str = Field(min_length=1, max_length=5000)
    occurrence: int | None = Field(default=None, ge=1)


class ResolvedCitation(StrictModel):
    verdict: EvidenceVerdict
    source_id: StableId
    source_sha256: Sha256 | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)
    exact_quote: str
    quote_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def resolved_fields_are_complete(self) -> ResolvedCitation:
        resolved_fields = (
            self.source_sha256,
            self.char_start,
            self.char_end,
            self.quote_sha256,
        )
        if self.verdict is EvidenceVerdict.RESOLVED and any(
            value is None for value in resolved_fields
        ):
            raise ValueError("resolved citations require all digest and offset fields")
        return self


class CandidateFinding(StrictModel):
    issue_type: IssueType
    severity: Severity
    requirement_ids: tuple[StableId, ...] = Field(min_length=1)
    explanation: str = Field(min_length=1, max_length=4000)
    citations: tuple[CandidateCitation, ...] = Field(min_length=1)
    proposed_revision: str | None = Field(default=None, max_length=5000)
    clarification_question: str | None = Field(default=None, max_length=2000)
    origin: AnalysisOrigin

    @model_validator(mode="after")
    def pair_issues_have_two_targets(self) -> CandidateFinding:
        if self.issue_type in {IssueType.DUPLICATE, IssueType.CONTRADICTION} and (
            len(set(self.requirement_ids)) < 2 or len(self.citations) < 2
        ):
            raise ValueError("pair findings require two targets and two citations")
        if len(self.requirement_ids) != len(set(self.requirement_ids)):
            raise ValueError("requirement IDs must be unique within a finding")
        return self


class CandidateAnalysis(StrictModel):
    findings: tuple[CandidateFinding, ...]


class VerifiedFinding(StrictModel):
    finding_id: StableId
    issue_type: IssueType
    severity: Severity
    requirement_ids: tuple[StableId, ...]
    explanation: str
    citations: tuple[ResolvedCitation, ...]
    evidence_verdict: EvidenceVerdict
    status: FindingStatus
    proposed_revision: str | None = None
    clarification_question: str | None = None
    origin: AnalysisOrigin


class RevisionProposal(StrictModel):
    proposal_id: StableId
    requirement_id: StableId
    original_text_sha256: Sha256
    proposed_text: str = Field(min_length=1, max_length=5000)
    finding_ids: tuple[StableId, ...] = Field(min_length=1)


class QualityScorecard(StrictModel):
    method_version: str
    total_items: int = Field(ge=0)
    candidate_findings: int = Field(ge=0)
    verified_findings: int = Field(ge=0)
    blocked_findings: int = Field(ge=0)
    items_with_open_questions: int = Field(ge=0)


class AnalysisProvenance(StrictModel):
    adapter: str
    model: str | None
    reasoning_effort: str | None
    prompt_sha256: Sha256
    configuration_sha256: Sha256


class ReviewArtifact(StrictModel):
    schema_version: str
    run_id: StableId
    status: WorkflowStatus
    manifest_sha256: Sha256
    source_pack_sha256: Sha256
    requirements: tuple[Requirement, ...]
    findings: tuple[VerifiedFinding, ...]
    revisions: tuple[RevisionProposal, ...]
    clarification_questions: tuple[str, ...]
    scorecard: QualityScorecard
    provenance: AnalysisProvenance

    @model_validator(mode="after")
    def references_are_consistent(self) -> ReviewArtifact:
        requirement_ids = [item.requirement_id for item in self.requirements]
        finding_ids = [item.finding_id for item in self.findings]
        proposal_ids = [item.proposal_id for item in self.revisions]
        for label, values in (
            ("requirement", requirement_ids),
            ("finding", finding_ids),
            ("proposal", proposal_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} IDs must be unique")

        requirement_set = set(requirement_ids)
        finding_set = set(finding_ids)
        for finding in self.findings:
            if not set(finding.requirement_ids) <= requirement_set:
                raise ValueError("finding references an unknown requirement")
        for proposal in self.revisions:
            if proposal.requirement_id not in requirement_set:
                raise ValueError("proposal references an unknown requirement")
            if not set(proposal.finding_ids) <= finding_set:
                raise ValueError("proposal references an unknown finding")
        return self


class ApprovalRequest(StrictModel):
    run_id: StableId
    artifact_sha256: Sha256
    reviewer_id: str = Field(min_length=1, max_length=120)
    review_round: int = Field(ge=1, le=10)
    nonce: str = Field(min_length=32, max_length=128)
    allowed_actions: tuple[ApprovalAction, ...]


class RevisionEdit(StrictModel):
    proposal_id: StableId
    replacement_text: str = Field(min_length=1, max_length=5000)


class ApprovalSubmission(StrictModel):
    run_id: StableId
    artifact_sha256: Sha256
    reviewer_id: str = Field(min_length=1, max_length=120)
    review_round: int = Field(ge=1, le=10)
    nonce: str = Field(min_length=32, max_length=128)
    action: ApprovalAction
    comment: str | None = Field(default=None, max_length=2000)
    edits: tuple[RevisionEdit, ...] = ()

    @model_validator(mode="after")
    def edits_match_action(self) -> ApprovalSubmission:
        if self.action is ApprovalAction.EDIT and not self.edits:
            raise ValueError("EDIT requires at least one typed edit")
        if self.action is not ApprovalAction.EDIT and self.edits:
            raise ValueError("edits are allowed only with EDIT")
        return self


class ApprovalRecord(StrictModel):
    approval_id: StableId
    run_id: StableId
    artifact_sha256: Sha256
    reviewer_id: str
    review_round: int
    nonce_sha256: Sha256
    action: ApprovalAction
    comment: str | None
    decided_at: datetime
    submission_sha256: Sha256


class ControlFailure(StrictModel):
    code: StableId
    safe_message: str = Field(min_length=1, max_length=500)
    stage: WorkflowStatus
    retryable: bool


class ExportedFile(StrictModel):
    relative_path: str
    sha256: Sha256
    size_bytes: int = Field(ge=0)


class ExportManifest(StrictModel):
    schema_version: str
    run_id: StableId
    artifact_sha256: Sha256
    approval_sha256: Sha256
    exported_at: datetime
    files: tuple[ExportedFile, ...]
