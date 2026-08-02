"""Small local visual demonstration of review and human decision points."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from requirements_quality_agent.adapters.storage.local_store import LocalRunStore
from requirements_quality_agent.config import Settings
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import ApprovalSubmission, RevisionEdit
from requirements_quality_agent.presentation.factory import build_service

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STATE_ROOT = Path("run-state/ui")
OUTPUT_ROOT = Path("output/ui")


def settings() -> Settings:
    base = Settings.from_environment(REPOSITORY_ROOT)
    return Settings(
        repository_root=REPOSITORY_ROOT,
        provider="rule",
        reviewer_id=base.reviewer_id,
        model=base.model,
        reasoning_effort=base.reasoning_effort,
        state_root=STATE_ROOT,
        output_root=OUTPUT_ROOT,
    )


def decide(action: ApprovalAction, edits: tuple[RevisionEdit, ...] = ()) -> None:
    configured = settings()
    store = LocalRunStore(
        repository_root=configured.repository_root,
        state_root=configured.state_root,
    )
    _, request = store.load_review(st.session_state.run_id)
    submission = ApprovalSubmission(
        run_id=request.run_id,
        artifact_sha256=request.artifact_sha256,
        reviewer_id=request.reviewer_id,
        review_round=request.review_round,
        nonce=request.nonce,
        action=action,
        comment="Decision recorded in the local Streamlit demonstration.",
        edits=edits,
    )
    result = build_service(configured, include_model=False).decide(
        submission=submission,
        output_root=str(configured.output_root),
    )
    st.session_state.decision = result.status.value
    if result.next_request is not None:
        st.session_state.review_round = result.next_request.review_round


st.set_page_config(page_title="Requirements Quality Agent", page_icon="✓", layout="wide")
st.title("Requirements Quality Agent")
st.caption("Find what is unclear before it becomes expensive.")
st.info(
    "This local demo uses the transparent rule baseline and synthetic evidence. "
    "Nothing is approved until you choose a review action."
)

if st.button("Run the evidence-linked review", type="primary"):
    result = build_service(settings()).analyze()
    st.session_state.run_id = result.artifact.run_id
    st.session_state.decision = "NEEDS_REVIEW"

if "run_id" in st.session_state:
    configured = settings()
    store = LocalRunStore(
        repository_root=configured.repository_root,
        state_root=configured.state_root,
    )
    artifact, request = store.load_review(st.session_state.run_id)
    st.subheader("Review packet")
    st.code(f"Run: {artifact.run_id}\nArtifact SHA-256: {request.artifact_sha256}")

    columns = st.columns(4)
    columns[0].metric("Source items", artifact.scorecard.total_items)
    columns[1].metric("Verified findings", artifact.scorecard.verified_findings)
    columns[2].metric("Blocked findings", artifact.scorecard.blocked_findings)
    columns[3].metric("Revision proposals", len(artifact.revisions))

    st.subheader("Evidence-linked findings")
    st.dataframe(
        [
            {
                "ID": finding.finding_id,
                "Type": finding.issue_type.value,
                "Severity": finding.severity.value,
                "Requirements": ", ".join(finding.requirement_ids),
                "Evidence": ", ".join(
                    f"{citation.source_id}:{citation.char_start}-{citation.char_end}"
                    for citation in finding.citations
                ),
            }
            for finding in artifact.findings
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Human-reviewed proposals")
    edited: list[RevisionEdit] = []
    for proposal in artifact.revisions:
        replacement = st.text_area(
            f"{proposal.proposal_id} · {proposal.requirement_id}",
            value=proposal.proposed_text,
            key=f"edit-{request.review_round}-{proposal.proposal_id}",
        )
        if replacement != proposal.proposed_text:
            edited.append(
                RevisionEdit(proposal_id=proposal.proposal_id, replacement_text=replacement)
            )

    if st.session_state.decision == "NEEDS_REVIEW":
        st.warning(
            "The reviewer identity is demonstrative, not enterprise authentication. "
            "Every decision is bound to this run, digest, round, and one-use nonce."
        )
        approve, edit, revise, reject = st.columns(4)
        if approve.button("Approve exact artifact", type="primary"):
            decide(ApprovalAction.APPROVE)
            st.success("Approved and exported locally.")
            st.rerun()
        if edit.button("Submit edited proposals", disabled=not edited):
            decide(ApprovalAction.EDIT, tuple(edited))
            st.success("Edits created a new digest and review round.")
            st.rerun()
        if revise.button("Request revision"):
            decide(ApprovalAction.REQUEST_REVISION)
            st.warning("Revision requested; no approved export was created.")
            st.rerun()
        if reject.button("Reject"):
            decide(ApprovalAction.REJECT)
            st.error("Rejected; no approved export was created.")
            st.rerun()
    elif st.session_state.decision == "REVISION_REQUESTED":
        if st.button("Resume requested analysis", type="primary"):
            result = build_service(settings()).resume(st.session_state.run_id)
            st.session_state.decision = result.artifact.status.value
            st.rerun()
    else:
        st.info("This review round is closed. Start a new run to make another decision.")

    st.caption(f"Current local decision state: {st.session_state.decision}")
