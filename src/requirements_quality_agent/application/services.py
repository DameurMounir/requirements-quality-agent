"""Application orchestration for analysis, persisted review, and approved export."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from requirements_quality_agent.adapters.input.local_pack import LoadedPack, load_case_pack
from requirements_quality_agent.application.ports import AnalysisModel, ReportExporter, RunStore
from requirements_quality_agent.controls.approval import (
    approval_record,
    new_approval_request,
    validate_submission,
)
from requirements_quality_agent.controls.canonical import domain_digest
from requirements_quality_agent.controls.citations import resolve_citation
from requirements_quality_agent.controls.quality_policy import (
    blocks_without_evidence,
    controlled_severity,
)
from requirements_quality_agent.domain.enums import (
    ApprovalAction,
    EvidenceVerdict,
    FindingStatus,
    WorkflowStatus,
)
from requirements_quality_agent.domain.models import (
    AnalysisProvenance,
    ApprovalRecord,
    ApprovalRequest,
    ApprovalSubmission,
    CandidateAnalysis,
    ControlFailure,
    ExportManifest,
    QualityScorecard,
    Requirement,
    ReviewArtifact,
    RevisionProposal,
    VerifiedFinding,
)
from requirements_quality_agent.workflow.state import ReviewState
from requirements_quality_agent.workflow.topology import require_transition


class AnalysisBlocked(RuntimeError):
    """Raised when a mandatory evidence control blocks human review."""


class RunFailed(RuntimeError):
    """Raised after a safe terminal failure has been persisted."""


class ReviewDecisionRejected(ValueError):
    """Raised for an invalid edit or unsupported review action."""


@dataclass(frozen=True, slots=True)
class ReviewResult:
    artifact: ReviewArtifact
    request: ApprovalRequest


@dataclass(frozen=True, slots=True)
class DecisionResult:
    run_id: str
    status: WorkflowStatus
    artifact_sha256: str
    decision: ApprovalRecord
    next_request: ApprovalRequest | None = None
    export_manifest: ExportManifest | None = None


def new_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d")
    return f"RUN-{timestamp}-{secrets.token_hex(4).upper()}"


def _citation_covers(requirement: Requirement, citation_start: int, citation_end: int) -> bool:
    span = requirement.source_span
    return span.char_start <= citation_start and citation_end <= span.char_end


def _evidence_verdict(
    candidate: CandidateAnalysis,
    pack: LoadedPack,
) -> tuple[tuple[VerifiedFinding, ...], bool]:
    requirements = {item.requirement_id: item for item in pack.requirements}
    verified: list[VerifiedFinding] = []
    critical_block = False

    for item in candidate.findings:
        unknown = [item_id for item_id in item.requirement_ids if item_id not in requirements]
        if unknown:
            raise AnalysisBlocked(f"candidate targets unknown requirements: {', '.join(unknown)}")
        citations = tuple(resolve_citation(citation, pack.documents) for citation in item.citations)
        all_resolved = all(citation.verdict is EvidenceVerdict.RESOLVED for citation in citations)
        target_coverage = True
        for requirement_id in item.requirement_ids:
            requirement = requirements[requirement_id]
            covered = any(
                citation.verdict is EvidenceVerdict.RESOLVED
                and citation.source_id == requirement.source_span.source_id
                and citation.char_start is not None
                and citation.char_end is not None
                and _citation_covers(requirement, citation.char_start, citation.char_end)
                for citation in citations
            )
            target_coverage = target_coverage and covered

        severity = controlled_severity(item.issue_type)
        if all_resolved and target_coverage:
            verdict = EvidenceVerdict.RESOLVED
            status = FindingStatus.VERIFIED
        else:
            verdict = next(
                (
                    citation.verdict
                    for citation in citations
                    if citation.verdict is not EvidenceVerdict.RESOLVED
                ),
                EvidenceVerdict.QUOTE_NOT_FOUND,
            )
            status = FindingStatus.BLOCKED
            if blocks_without_evidence(item.issue_type):
                critical_block = True

        identity = {
            "issue_type": item.issue_type.value,
            "requirement_ids": sorted(item.requirement_ids),
            "citations": [
                {
                    "source_id": citation.source_id,
                    "quote_sha256": citation.quote_sha256,
                    "verdict": citation.verdict.value,
                }
                for citation in citations
            ],
        }
        finding_id = f"FND-{domain_digest('finding', identity)[:16].upper()}"
        verified.append(
            VerifiedFinding(
                finding_id=finding_id,
                issue_type=item.issue_type,
                severity=severity,
                requirement_ids=item.requirement_ids,
                explanation=item.explanation,
                citations=citations,
                evidence_verdict=verdict,
                status=status,
                proposed_revision=(
                    item.proposed_revision if status is FindingStatus.VERIFIED else None
                ),
                clarification_question=item.clarification_question,
                origin=item.origin,
            )
        )
    return tuple(verified), critical_block


def _revisions(
    findings: tuple[VerifiedFinding, ...],
    requirements: tuple[Requirement, ...],
) -> tuple[RevisionProposal, ...]:
    by_id = {item.requirement_id: item for item in requirements}
    grouped: dict[tuple[str, str], list[str]] = {}
    for finding in findings:
        if finding.status is not FindingStatus.VERIFIED or finding.proposed_revision is None:
            continue
        if len(finding.requirement_ids) != 1:
            continue
        key = (finding.requirement_ids[0], finding.proposed_revision)
        grouped.setdefault(key, []).append(finding.finding_id)

    proposals: list[RevisionProposal] = []
    for (requirement_id, proposed_text), finding_ids in sorted(grouped.items()):
        requirement = by_id[requirement_id]
        identity = {
            "requirement_id": requirement_id,
            "proposed_text": proposed_text,
            "finding_ids": sorted(finding_ids),
        }
        proposals.append(
            RevisionProposal(
                proposal_id=f"PRP-{domain_digest('proposal', identity)[:16].upper()}",
                requirement_id=requirement_id,
                original_text_sha256=requirement.source_span.exact_text_sha256,
                proposed_text=proposed_text,
                finding_ids=tuple(sorted(finding_ids)),
            )
        )
    return tuple(proposals)


def _apply_revision_edits(
    artifact: ReviewArtifact,
    submission: ApprovalSubmission,
) -> ReviewArtifact:
    edits = {edit.proposal_id: edit.replacement_text for edit in submission.edits}
    if len(edits) != len(submission.edits):
        raise ReviewDecisionRejected("each proposal may be edited once per decision")
    known = {proposal.proposal_id for proposal in artifact.revisions}
    unknown = set(edits) - known
    if unknown:
        raise ReviewDecisionRejected(f"unknown proposal IDs: {', '.join(sorted(unknown))}")

    changed = False
    updated_revisions: list[RevisionProposal] = []
    for proposal in artifact.revisions:
        proposed_text = edits.get(proposal.proposal_id, proposal.proposed_text)
        if proposed_text == proposal.proposed_text:
            updated_revisions.append(proposal)
            continue
        changed = True
        identity = {
            "requirement_id": proposal.requirement_id,
            "proposed_text": proposed_text,
            "finding_ids": sorted(proposal.finding_ids),
        }
        updated_revisions.append(
            RevisionProposal(
                proposal_id=f"PRP-{domain_digest('proposal', identity)[:16].upper()}",
                requirement_id=proposal.requirement_id,
                original_text_sha256=proposal.original_text_sha256,
                proposed_text=proposed_text,
                finding_ids=proposal.finding_ids,
            )
        )
    if not changed:
        raise ReviewDecisionRejected("EDIT must change at least one proposal")
    return ReviewArtifact.model_validate(
        {
            **artifact.model_dump(mode="python"),
            "status": WorkflowStatus.NEEDS_REVIEW,
            "revisions": tuple(updated_revisions),
        }
    )


def build_artifact(
    *,
    run_id: str,
    pack: LoadedPack,
    candidate: CandidateAnalysis,
    model: AnalysisModel,
) -> ReviewArtifact:
    findings, critical_block = _evidence_verdict(candidate, pack)
    if critical_block:
        raise AnalysisBlocked("a blocking issue lacks exact evidence")
    revisions = _revisions(findings, pack.requirements)
    questions = tuple(
        dict.fromkeys(
            finding.clarification_question
            for finding in findings
            if finding.clarification_question is not None
        )
    )
    verified_count = sum(item.status is FindingStatus.VERIFIED for item in findings)
    blocked_count = sum(item.status is FindingStatus.BLOCKED for item in findings)
    question_targets = {
        requirement_id
        for finding in findings
        if finding.clarification_question is not None
        for requirement_id in finding.requirement_ids
    }
    configuration = {
        "adapter": model.name,
        "model": model.model_id,
        "reasoning_effort": model.reasoning_effort,
        "adapter_configuration": model.configuration,
        "workflow": "requirements-review/v1",
    }
    return ReviewArtifact(
        schema_version="1.0.0",
        run_id=run_id,
        status=WorkflowStatus.NEEDS_REVIEW,
        manifest_sha256=pack.manifest_sha256,
        source_pack_sha256=pack.source_pack_sha256,
        requirements=pack.requirements,
        findings=findings,
        revisions=revisions,
        clarification_questions=questions,
        scorecard=QualityScorecard(
            method_version="1.0.0",
            total_items=len(pack.requirements),
            candidate_findings=len(candidate.findings),
            verified_findings=verified_count,
            blocked_findings=blocked_count,
            items_with_open_questions=len(question_targets),
        ),
        provenance=AnalysisProvenance(
            adapter=model.name,
            model=model.model_id,
            reasoning_effort=model.reasoning_effort,
            prompt_sha256=model.prompt_sha256,
            configuration_sha256=domain_digest("analysis-configuration", configuration),
        ),
    )


class ReviewService:
    def __init__(
        self,
        *,
        repository_root: str,
        model: AnalysisModel | None,
        store: RunStore,
        exporter: ReportExporter,
        reviewer_id: str,
    ) -> None:
        self.repository_root = Path(repository_root).resolve(strict=True)
        self.model = model
        self.store = store
        self.exporter = exporter
        self.reviewer_id = reviewer_id

    def _require_model(self) -> AnalysisModel:
        if self.model is None:
            raise RunFailed("an analysis model is required for this operation")
        return self.model

    @staticmethod
    def _failure(
        *,
        code: str,
        message: str,
        stage: WorkflowStatus,
        retryable: bool,
    ) -> tuple[ControlFailure, ...]:
        return (
            ControlFailure(
                code=code,
                safe_message=message,
                stage=stage,
                retryable=retryable,
            ),
        )

    def _graph(self) -> Any:
        model = self._require_model()
        builder = StateGraph(ReviewState)

        def validate_pack(state: ReviewState) -> dict[str, object]:
            current = WorkflowStatus(state["status"])
            try:
                pack = load_case_pack(self.repository_root)
            except (OSError, ValueError):
                target = (
                    WorkflowStatus.REJECTED
                    if current is WorkflowStatus.RECEIVED
                    else WorkflowStatus.BLOCKED
                )
                require_transition(current, target)
                return {
                    "status": target.value,
                    "failures": self._failure(
                        code="INPUT-REJECTED",
                        message="the source pack failed deterministic validation",
                        stage=current,
                        retryable=False,
                    ),
                }

            expected_digest = state.get("expected_source_pack_sha256")
            if expected_digest is not None and pack.source_pack_sha256 != expected_digest:
                require_transition(current, WorkflowStatus.BLOCKED)
                return {
                    "status": WorkflowStatus.BLOCKED.value,
                    "failures": self._failure(
                        code="SOURCE-PACK-CHANGED",
                        message="the source pack changed after the prior review round",
                        stage=current,
                        retryable=False,
                    ),
                }
            if current is WorkflowStatus.RECEIVED:
                require_transition(current, WorkflowStatus.VALIDATED)
                next_status = WorkflowStatus.VALIDATED
            else:
                next_status = current
            return {
                "status": next_status.value,
                "manifest": pack.manifest,
                "manifest_sha256": pack.manifest_sha256,
                "source_pack_sha256": pack.source_pack_sha256,
                "documents": pack.documents,
                "requirements": pack.requirements,
            }

        def analyze(state: ReviewState) -> dict[str, object]:
            current = WorkflowStatus(state["status"])
            require_transition(current, WorkflowStatus.ANALYZING)
            try:
                candidate = CandidateAnalysis.model_validate(
                    model.analyze(
                        documents=state["documents"],
                        requirements=state["requirements"],
                    )
                )
            except Exception:
                require_transition(WorkflowStatus.ANALYZING, WorkflowStatus.ERROR)
                return {
                    "status": WorkflowStatus.ERROR.value,
                    "failures": self._failure(
                        code="ANALYSIS-ERROR",
                        message="the analysis adapter failed closed",
                        stage=WorkflowStatus.ANALYZING,
                        retryable=True,
                    ),
                }
            return {
                "status": WorkflowStatus.ANALYZING.value,
                "candidate_analysis": candidate,
            }

        def verify(state: ReviewState) -> dict[str, object]:
            require_transition(WorkflowStatus(state["status"]), WorkflowStatus.VERIFYING)
            pack = LoadedPack(
                manifest=state["manifest"],
                manifest_sha256=state["manifest_sha256"],
                source_pack_sha256=state["source_pack_sha256"],
                documents=state["documents"],
                requirements=state["requirements"],
            )
            try:
                artifact = build_artifact(
                    run_id=state["run_id"],
                    pack=pack,
                    candidate=state["candidate_analysis"],
                    model=model,
                )
            except AnalysisBlocked:
                require_transition(WorkflowStatus.VERIFYING, WorkflowStatus.BLOCKED)
                return {
                    "status": WorkflowStatus.BLOCKED.value,
                    "failures": self._failure(
                        code="EVIDENCE-BLOCKED",
                        message="mandatory evidence verification blocked the run",
                        stage=WorkflowStatus.VERIFYING,
                        retryable=False,
                    ),
                }
            except (RuntimeError, ValueError):
                require_transition(WorkflowStatus.VERIFYING, WorkflowStatus.ERROR)
                return {
                    "status": WorkflowStatus.ERROR.value,
                    "failures": self._failure(
                        code="VERIFICATION-ERROR",
                        message="artifact verification failed closed",
                        stage=WorkflowStatus.VERIFYING,
                        retryable=False,
                    ),
                }
            return {"status": WorkflowStatus.VERIFYING.value, "artifact": artifact}

        def prepare_review(state: ReviewState) -> dict[str, object]:
            require_transition(WorkflowStatus(state["status"]), WorkflowStatus.NEEDS_REVIEW)
            artifact = state["artifact"]
            request = new_approval_request(
                artifact=artifact,
                reviewer_id=self.reviewer_id,
                review_round=state["review_round"],
            )
            return {
                "status": WorkflowStatus.NEEDS_REVIEW.value,
                "approval_request": request,
            }

        def after_validation(state: ReviewState) -> str:
            return (
                "analyze"
                if WorkflowStatus(state["status"])
                in {WorkflowStatus.VALIDATED, WorkflowStatus.REVISION_REQUESTED}
                else "end"
            )

        def after_analysis(state: ReviewState) -> str:
            return (
                "verify" if WorkflowStatus(state["status"]) is WorkflowStatus.ANALYZING else "end"
            )

        def after_verification(state: ReviewState) -> str:
            return (
                "prepare_review"
                if WorkflowStatus(state["status"]) is WorkflowStatus.VERIFYING
                else "end"
            )

        builder.add_node("validate_pack", validate_pack)
        builder.add_node("analyze", analyze)
        builder.add_node("verify", verify)
        builder.add_node("prepare_review", prepare_review)
        builder.add_edge(START, "validate_pack")
        builder.add_conditional_edges(
            "validate_pack",
            after_validation,
            {"analyze": "analyze", "end": END},
        )
        builder.add_conditional_edges(
            "analyze",
            after_analysis,
            {"verify": "verify", "end": END},
        )
        builder.add_conditional_edges(
            "verify",
            after_verification,
            {"prepare_review": "prepare_review", "end": END},
        )
        builder.add_edge("prepare_review", END)
        return builder.compile()

    def _run_analysis_graph(
        self,
        *,
        run_id: str,
        status: WorkflowStatus,
        review_round: int,
        expected_source_pack_sha256: str | None = None,
    ) -> ReviewResult:
        graph = self._graph()
        state: ReviewState = {
            "run_id": run_id,
            "status": status.value,
            "review_round": review_round,
        }
        if expected_source_pack_sha256 is not None:
            state["expected_source_pack_sha256"] = expected_source_pack_sha256
        result = graph.invoke(state)
        result_status = WorkflowStatus(result["status"])
        if result_status is not WorkflowStatus.NEEDS_REVIEW:
            failures = result.get("failures", ())
            failure = (
                failures[-1]
                if failures
                else ControlFailure(
                    code="WORKFLOW-ERROR",
                    safe_message="the analysis workflow failed closed",
                    stage=result_status,
                    retryable=False,
                )
            )
            self.store.save_failure(run_id, result_status, failure)
            raise RunFailed(failure.safe_message)
        return ReviewResult(
            artifact=result["artifact"],
            request=result["approval_request"],
        )

    def analyze(self, run_id: str | None = None) -> ReviewResult:
        resolved_run_id = run_id or new_run_id()
        result = self._run_analysis_graph(
            run_id=resolved_run_id,
            status=WorkflowStatus.RECEIVED,
            review_round=1,
        )
        self.store.save_review(result.artifact, result.request)
        return result

    def resume(self, run_id: str) -> ReviewResult:
        previous_artifact, previous_request = self.store.load_review(run_id)
        if self.store.load_status(run_id) is not WorkflowStatus.REVISION_REQUESTED:
            raise ReviewDecisionRejected("run is not waiting for revised analysis")
        result = self._run_analysis_graph(
            run_id=run_id,
            status=WorkflowStatus.REVISION_REQUESTED,
            review_round=previous_request.review_round + 1,
            expected_source_pack_sha256=previous_artifact.source_pack_sha256,
        )
        self.store.commit_revision(result.artifact, result.request)
        return result

    def decide(
        self,
        *,
        submission: ApprovalSubmission,
        output_root: str,
    ) -> DecisionResult:
        artifact, request = self.store.load_review(submission.run_id)
        if self.store.load_status(submission.run_id) is not WorkflowStatus.NEEDS_REVIEW:
            raise ReviewDecisionRejected("run is not open for review")
        validate_submission(request=request, submission=submission)

        if submission.action is ApprovalAction.EDIT:
            updated_artifact = _apply_revision_edits(artifact, submission)
            next_request = new_approval_request(
                artifact=updated_artifact,
                reviewer_id=request.reviewer_id,
                review_round=request.review_round + 1,
            )
            require_transition(
                WorkflowStatus.NEEDS_REVIEW,
                WorkflowStatus.REVISION_REQUESTED,
            )
            require_transition(
                WorkflowStatus.REVISION_REQUESTED,
                WorkflowStatus.ANALYZING,
            )
            require_transition(WorkflowStatus.ANALYZING, WorkflowStatus.VERIFYING)
            require_transition(WorkflowStatus.VERIFYING, WorkflowStatus.NEEDS_REVIEW)
            decision = approval_record(request=request, submission=submission)
            self.store.commit_edit(decision, updated_artifact, next_request)
            return DecisionResult(
                run_id=artifact.run_id,
                status=WorkflowStatus.NEEDS_REVIEW,
                artifact_sha256=next_request.artifact_sha256,
                decision=decision,
                next_request=next_request,
            )

        target = {
            ApprovalAction.APPROVE: WorkflowStatus.APPROVED,
            ApprovalAction.REJECT: WorkflowStatus.REJECTED,
            ApprovalAction.REQUEST_REVISION: WorkflowStatus.REVISION_REQUESTED,
        }[submission.action]
        require_transition(WorkflowStatus.NEEDS_REVIEW, target)
        if target is WorkflowStatus.APPROVED:
            self.exporter.validate_output_root(Path(output_root))
        decision = approval_record(request=request, submission=submission)
        self.store.commit_decision(decision, target)

        if target is not WorkflowStatus.APPROVED:
            return DecisionResult(
                run_id=artifact.run_id,
                status=target,
                artifact_sha256=request.artifact_sha256,
                decision=decision,
            )

        manifest = self.export_approved(artifact.run_id, output_root)
        return DecisionResult(
            run_id=artifact.run_id,
            status=WorkflowStatus.EXPORTED,
            artifact_sha256=request.artifact_sha256,
            decision=decision,
            export_manifest=manifest,
        )

    def export_approved(self, run_id: str, output_root: str) -> ExportManifest:
        status = self.store.load_status(run_id)
        if status not in {WorkflowStatus.APPROVED, WorkflowStatus.EXPORTED}:
            raise ReviewDecisionRejected("run is not approved for export")
        artifact, approval = self.store.load_approved(run_id)
        manifest = self.exporter.export(
            artifact=artifact,
            approval=approval,
            output_root=Path(output_root),
        )
        if status is WorkflowStatus.APPROVED:
            require_transition(WorkflowStatus.APPROVED, WorkflowStatus.EXPORTED)
            self.store.mark_exported(run_id, approval.approval_id, manifest)
        return manifest
