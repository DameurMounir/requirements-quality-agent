"""Command-line interface for validate, analyze, review, and inspect."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.adapters.storage.local_store import LocalRunStore, RunStateError
from requirements_quality_agent.application.services import DecisionResult, ReviewResult
from requirements_quality_agent.config import Settings
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import ApprovalSubmission, RevisionEdit
from requirements_quality_agent.presentation.factory import build_service


def _settings(args: argparse.Namespace) -> Settings:
    environment = Settings.from_environment(Path(args.repo))
    state_root = getattr(args, "state_root", None)
    output_root = getattr(args, "output_root", None)
    return Settings(
        repository_root=environment.repository_root,
        provider=getattr(args, "provider", None) or environment.provider,
        reviewer_id=getattr(args, "reviewer_id", None) or environment.reviewer_id,
        model=getattr(args, "model", None) or environment.model,
        reasoning_effort=getattr(args, "reasoning_effort", None) or environment.reasoning_effort,
        state_root=Path(state_root) if state_root else environment.state_root,
        output_root=Path(output_root) if output_root else environment.output_root,
    )


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _review_summary(result: ReviewResult) -> dict[str, object]:
    return {
        "run_id": result.artifact.run_id,
        "status": "NEEDS_REVIEW",
        "artifact_sha256": result.request.artifact_sha256,
        "review_round": result.request.review_round,
        "reviewer_id": result.request.reviewer_id,
        "requirements": result.artifact.scorecard.total_items,
        "verified_findings": result.artifact.scorecard.verified_findings,
        "blocked_findings": result.artifact.scorecard.blocked_findings,
        "revision_proposals": len(result.artifact.revisions),
        "next": (
            f"requirements-quality-agent review --run-id {result.artifact.run_id} --action APPROVE"
        ),
    }


def _decision_summary(result: DecisionResult) -> dict[str, object]:
    value: dict[str, object] = {
        "run_id": result.run_id,
        "status": result.status.value,
        "artifact_sha256": result.artifact_sha256,
        "decision_id": result.decision.approval_id,
        "decision": result.decision.action.value,
    }
    if result.next_request is not None:
        value["next_review_round"] = result.next_request.review_round
        value["next_artifact_sha256"] = result.next_request.artifact_sha256
    if result.export_manifest is not None:
        value["exported_files"] = [file.relative_path for file in result.export_manifest.files]
    return value


def _parse_edit(raw: str) -> RevisionEdit:
    proposal_id, separator, replacement = raw.partition("=")
    if not separator or not proposal_id or not replacement:
        raise ValueError("edits use PROPOSAL_ID=REPLACEMENT_TEXT")
    return RevisionEdit(proposal_id=proposal_id, replacement_text=replacement)


def cmd_validate(args: argparse.Namespace) -> int:
    settings = _settings(args)
    pack = load_case_pack(settings.repository_root)
    _print(
        {
            "case_id": pack.manifest.case_id,
            "manifest_sha256": pack.manifest_sha256,
            "source_pack_sha256": pack.source_pack_sha256,
            "documents": len(pack.documents),
            "requirements": len(pack.requirements),
            "status": "VALIDATED",
        }
    )
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    settings = _settings(args)
    result = build_service(settings).analyze(run_id=args.run_id)
    _print(_review_summary(result))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    settings = _settings(args)
    result = build_service(settings).resume(args.run_id)
    _print(_review_summary(result))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    settings = _settings(args)
    store = LocalRunStore(
        repository_root=settings.repository_root,
        state_root=settings.state_root,
    )
    _, request = store.load_review(args.run_id)
    edits = tuple(_parse_edit(raw) for raw in args.edit)
    submission = ApprovalSubmission(
        run_id=request.run_id,
        artifact_sha256=request.artifact_sha256,
        reviewer_id=args.reviewer_id or request.reviewer_id,
        review_round=request.review_round,
        nonce=request.nonce,
        action=ApprovalAction(args.action),
        comment=args.comment,
        edits=edits,
    )
    result = build_service(settings, include_model=False).decide(
        submission=submission,
        output_root=str(settings.output_root),
    )
    _print(_decision_summary(result))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    settings = _settings(args)
    manifest = build_service(settings, include_model=False).export_approved(
        args.run_id,
        str(settings.output_root),
    )
    _print(
        {
            "run_id": manifest.run_id,
            "status": "EXPORTED",
            "artifact_sha256": manifest.artifact_sha256,
            "exported_files": [item.relative_path for item in manifest.files],
        }
    )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    settings = _settings(args)
    store = LocalRunStore(
        repository_root=settings.repository_root,
        state_root=settings.state_root,
    )
    status = store.load_status(args.run_id)
    summary: dict[str, object] = {"run_id": args.run_id, "status": status.value}
    try:
        artifact, request = store.load_review(args.run_id)
    except RunStateError:
        pass
    else:
        summary.update(
            {
                "artifact_sha256": request.artifact_sha256,
                "review_round": request.review_round,
                "reviewer_id": request.reviewer_id,
                "requirements": len(artifact.requirements),
                "findings": len(artifact.findings),
                "revisions": len(artifact.revisions),
                "questions": len(artifact.clarification_questions),
            }
        )
    _print(summary)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="requirements-quality-agent",
        description="Evidence-linked review of the frozen synthetic requirements pack.",
    )
    root.add_argument("--repo", default=".", help="repository root (default: current directory)")
    subparsers = root.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="verify and summarize the source pack")
    validate.set_defaults(handler=cmd_validate)

    analyze = subparsers.add_parser("analyze", help="run analysis and pause for review")
    analyze.add_argument("--provider", choices=("rule", "fixture", "openai"))
    analyze.add_argument("--model")
    analyze.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high"))
    analyze.add_argument("--reviewer-id")
    analyze.add_argument("--run-id")
    analyze.add_argument("--state-root")
    analyze.add_argument("--output-root")
    analyze.set_defaults(handler=cmd_analyze)

    resume = subparsers.add_parser("resume", help="resume a requested revision")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--provider", choices=("rule", "fixture", "openai"))
    resume.add_argument("--model")
    resume.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high"))
    resume.add_argument("--reviewer-id")
    resume.add_argument("--state-root")
    resume.add_argument("--output-root")
    resume.set_defaults(handler=cmd_resume)

    review = subparsers.add_parser("review", help="record a human review decision")
    review.add_argument("--run-id", required=True)
    review.add_argument("--action", required=True, choices=tuple(ApprovalAction))
    review.add_argument("--reviewer-id")
    review.add_argument("--comment")
    review.add_argument("--edit", action="append", default=[], metavar="PROPOSAL_ID=TEXT")
    review.add_argument("--state-root")
    review.add_argument("--output-root")
    review.set_defaults(handler=cmd_review)

    export = subparsers.add_parser("export", help="retry export for an approved run")
    export.add_argument("--run-id", required=True)
    export.add_argument("--state-root")
    export.add_argument("--output-root")
    export.set_defaults(handler=cmd_export)

    show = subparsers.add_parser("show", help="show the current review round")
    show.add_argument("--run-id", required=True)
    show.add_argument("--state-root")
    show.add_argument("--output-root")
    show.set_defaults(handler=cmd_show)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
