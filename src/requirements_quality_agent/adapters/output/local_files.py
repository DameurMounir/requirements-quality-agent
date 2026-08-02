"""Write deterministic, non-overwriting reports for an approved artifact."""

from __future__ import annotations

import hashlib
import html
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from requirements_quality_agent.controls.approval import review_artifact_digest
from requirements_quality_agent.controls.canonical import domain_digest
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import (
    ApprovalRecord,
    ExportedFile,
    ExportManifest,
    ReviewArtifact,
)


class ExportRejected(RuntimeError):
    """Raised when export authorization or path controls fail."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_cell(value: object) -> str:
    normalized = str(value).replace("\r\n", "\n").replace("\r", "\n")
    safe = html.escape(normalized, quote=False).replace("\n", " ")
    safe = safe.replace("\\", "\\\\")
    for marker in ("`", "|", "[", "]", "(", ")", "!", "*", "_", "#", "+", "-", ">"):
        safe = safe.replace(marker, f"\\{marker}")
    return safe


def _render_markdown(artifact: ReviewArtifact, approval: ApprovalRecord) -> str:
    lines = [
        "# Requirements quality review",
        "",
        f"- Run: `{artifact.run_id}`",
        f"- Artifact SHA-256: `{approval.artifact_sha256}`",
        f"- Reviewer: `{_safe_cell(approval.reviewer_id)}`",
        f"- Decision: `{approval.action.value}`",
        f"- Source items: {artifact.scorecard.total_items}",
        f"- Verified findings: {artifact.scorecard.verified_findings}",
        f"- Blocked findings: {artifact.scorecard.blocked_findings}",
        "",
        "## Findings",
        "",
        (
            "| ID | Type | Severity | Status | Evidence verdict | Requirements | "
            "Evidence | Explanation |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for finding in artifact.findings:
        evidence = ", ".join(
            f"{citation.source_id}:{citation.char_start}-{citation.char_end}"
            for citation in finding.citations
            if citation.char_start is not None and citation.char_end is not None
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _safe_cell(finding.finding_id),
                    _safe_cell(finding.issue_type.value),
                    _safe_cell(finding.severity.value),
                    _safe_cell(finding.status.value),
                    _safe_cell(finding.evidence_verdict.value),
                    _safe_cell(", ".join(finding.requirement_ids)),
                    _safe_cell(evidence),
                    _safe_cell(finding.explanation),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Human-reviewed revision proposals",
            "",
            "| Proposal | Requirement | Proposed wording |",
            "|---|---|---|",
        ]
    )
    for proposal in artifact.revisions:
        lines.append(
            "| "
            + " | ".join(
                [
                    _safe_cell(proposal.proposal_id),
                    _safe_cell(proposal.requirement_id),
                    _safe_cell(proposal.proposed_text),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Open clarification questions", ""])
    lines.extend(f"- {_safe_cell(question)}" for question in artifact.clarification_questions)
    lines.extend(
        [
            "",
            "## Limitation",
            "",
            (
                "This is a synthetic local demonstration. An evidence link proves location, not "
                "semantic correctness. The recorded reviewer identity is not enterprise "
                "authentication."
            ),
            "",
        ]
    )
    return "\n".join(lines)


class LocalReportExporter:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve(strict=True)

    def validate_output_root(self, output_root: Path) -> Path:
        if output_root.is_absolute() or ".." in output_root.parts:
            raise ExportRejected("output root must be a repository-relative safe path")
        candidate = self._repository_root / output_root
        current = self._repository_root
        for part in output_root.parts:
            current /= part
            if current.is_symlink():
                raise ExportRejected("output path may not contain a symlink")
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self._repository_root)
        except ValueError as exc:
            raise ExportRejected("output root must remain inside the repository") from exc
        return resolved

    def _existing_manifest(
        self,
        *,
        run_dir: Path,
        artifact: ReviewArtifact,
        approval: ApprovalRecord,
    ) -> ExportManifest:
        if run_dir.is_symlink() or not run_dir.is_dir():
            raise ExportRejected("existing run output is unsafe")
        manifest_path = run_dir / "export-manifest.json"
        if manifest_path.is_symlink():
            raise ExportRejected("existing export manifest is unsafe")
        try:
            manifest = ExportManifest.model_validate_json(manifest_path.read_bytes())
        except (OSError, ValueError) as exc:
            raise ExportRejected("existing run output is incomplete") from exc
        if (
            manifest.run_id != artifact.run_id
            or manifest.artifact_sha256 != review_artifact_digest(artifact)
            or manifest.approval_sha256 != domain_digest("approval-record", approval)
        ):
            raise ExportRejected("existing run output has different bindings")
        if {item.relative_path for item in manifest.files} != {"report.json", "report.md"}:
            raise ExportRejected("existing export file set is invalid")
        for item in manifest.files:
            path = run_dir / item.relative_path
            if path.is_symlink() or not path.is_file():
                raise ExportRejected("existing exported file is unsafe or missing")
            if _sha256(path) != item.sha256 or path.stat().st_size != item.size_bytes:
                raise ExportRejected("existing exported file digest changed")
        return manifest

    def export(
        self,
        *,
        artifact: ReviewArtifact,
        approval: ApprovalRecord,
        output_root: Path,
    ) -> ExportManifest:
        if approval.action is not ApprovalAction.APPROVE:
            raise ExportRejected("only APPROVE permits report export")
        current_digest = review_artifact_digest(artifact)
        if current_digest != approval.artifact_sha256:
            raise ExportRejected("approval does not bind the current artifact")

        resolved_root = self.validate_output_root(output_root)
        resolved_root.mkdir(parents=True, exist_ok=True)
        if resolved_root.is_symlink() or resolved_root.resolve(strict=True) != resolved_root:
            raise ExportRejected("output root changed during validation")

        run_dir = resolved_root / artifact.run_id
        if run_dir.exists() or run_dir.is_symlink():
            return self._existing_manifest(
                run_dir=run_dir,
                artifact=artifact,
                approval=approval,
            )
        staging = resolved_root / f".{artifact.run_id}.{secrets.token_hex(8)}.tmp"
        staging.mkdir()

        report_payload = {
            "artifact": artifact.model_dump(mode="json"),
            "decision": approval.model_dump(mode="json"),
        }
        json_path = staging / "report.json"
        markdown_path = staging / "report.md"
        json_path.write_text(
            json.dumps(report_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        markdown_path.write_text(
            _render_markdown(artifact, approval), encoding="utf-8", newline="\n"
        )
        files = tuple(
            ExportedFile(
                relative_path=str(path.relative_to(staging)),
                sha256=_sha256(path),
                size_bytes=path.stat().st_size,
            )
            for path in (json_path, markdown_path)
        )
        manifest = ExportManifest(
            schema_version="1.0.0",
            run_id=artifact.run_id,
            artifact_sha256=current_digest,
            approval_sha256=domain_digest("approval-record", approval),
            exported_at=datetime.now(UTC),
            files=files,
        )
        (staging / "export-manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        try:
            staging.rename(run_dir)
        except FileExistsError:
            return self._existing_manifest(
                run_dir=run_dir,
                artifact=artifact,
                approval=approval,
            )
        return manifest
