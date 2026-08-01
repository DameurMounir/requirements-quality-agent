from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.output.local_files import (
    ExportRejected,
    LocalReportExporter,
)
from requirements_quality_agent.application.services import ReviewService
from requirements_quality_agent.controls.approval import approval_record
from requirements_quality_agent.domain.enums import ApprovalAction
from requirements_quality_agent.domain.models import (
    ApprovalRecord,
    ApprovalSubmission,
    ReviewArtifact,
)


def _approved_pair(
    service: ReviewService,
    run_id: str,
    submission_factory: Callable[..., ApprovalSubmission],
) -> tuple[ReviewArtifact, ApprovalRecord]:
    review = service.analyze(run_id)
    submission = submission_factory(review.request, ApprovalAction.APPROVE)
    return review.artifact, approval_record(request=review.request, submission=submission)


def test_exporter_rejects_non_approval_and_stale_artifact_digest(
    repository: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    review = service.analyze("RUN-EXPORT-AUTH")
    rejected = approval_record(
        request=review.request,
        submission=submission_factory(review.request, ApprovalAction.REJECT),
    )
    exporter = LocalReportExporter(repository)
    with pytest.raises(ExportRejected, match="only APPROVE"):
        exporter.export(artifact=review.artifact, approval=rejected, output_root=Path("output"))

    approved = approval_record(
        request=review.request,
        submission=submission_factory(review.request, ApprovalAction.APPROVE),
    )
    stale = approved.model_copy(update={"artifact_sha256": "f" * 64})
    with pytest.raises(ExportRejected, match="does not bind"):
        exporter.export(artifact=review.artifact, approval=stale, output_root=Path("output"))
    assert not (repository / "output").exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_manifest", "incomplete"),
        ("invalid_manifest", "incomplete"),
        ("different_binding", "different bindings"),
        ("wrong_file_set", "file set"),
        ("missing_file", "unsafe or missing"),
        ("changed_file", "digest changed"),
        ("report_symlink", "unsafe or missing"),
        ("manifest_symlink", "manifest is unsafe"),
    ],
)
def test_existing_export_tampering_fails_closed(
    repository: Path,
    tmp_path: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
    mutation: str,
    message: str,
) -> None:
    service = service_factory()
    artifact, approval = _approved_pair(service, "RUN-EXPORT-TAMPER", submission_factory)
    exporter = LocalReportExporter(repository)
    exporter.export(artifact=artifact, approval=approval, output_root=Path("output"))
    run_dir = repository / "output" / artifact.run_id
    manifest_path = run_dir / "export-manifest.json"
    manifest = json.loads(manifest_path.read_text())

    if mutation == "missing_manifest":
        manifest_path.unlink()
    elif mutation == "invalid_manifest":
        manifest_path.write_text("not json")
    elif mutation == "different_binding":
        manifest["artifact_sha256"] = "f" * 64
        manifest_path.write_text(json.dumps(manifest))
    elif mutation == "wrong_file_set":
        manifest["files"] = manifest["files"][:1]
        manifest_path.write_text(json.dumps(manifest))
    elif mutation == "missing_file":
        (run_dir / "report.json").unlink()
    elif mutation == "changed_file":
        (run_dir / "report.md").write_text("changed")
    elif mutation == "report_symlink":
        report_path = run_dir / "report.md"
        outside = tmp_path / "outside-report.md"
        outside.write_bytes(report_path.read_bytes())
        report_path.unlink()
        report_path.symlink_to(outside)
    else:
        outside = tmp_path / "outside-manifest.json"
        outside.write_bytes(manifest_path.read_bytes())
        manifest_path.unlink()
        manifest_path.symlink_to(outside)

    with pytest.raises(ExportRejected, match=message):
        exporter.export(artifact=artifact, approval=approval, output_root=Path("output"))


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_preexisting_unsafe_run_output_is_rejected(
    repository: Path,
    tmp_path: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
    kind: str,
) -> None:
    service = service_factory()
    artifact, approval = _approved_pair(service, "RUN-UNSAFE-OUTPUT", submission_factory)
    output = repository / "output"
    output.mkdir()
    run_path = output / artifact.run_id
    if kind == "file":
        run_path.write_text("not a directory")
    else:
        outside = tmp_path / "external-run-output"
        outside.mkdir()
        run_path.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ExportRejected, match="existing run output is unsafe"):
        LocalReportExporter(repository).export(
            artifact=artifact,
            approval=approval,
            output_root=Path("output"),
        )


def test_nested_output_component_symlink_is_rejected_before_external_write(
    repository: Path,
    tmp_path: Path,
    service_factory: Callable[..., ReviewService],
    submission_factory: Callable[..., ApprovalSubmission],
) -> None:
    service = service_factory()
    artifact, approval = _approved_pair(service, "RUN-NESTED-OUTPUT-LINK", submission_factory)
    outside = tmp_path / "external-output"
    outside.mkdir()
    reports = repository / "reports"
    reports.mkdir()
    (reports / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ExportRejected, match="output path may not contain a symlink"):
        LocalReportExporter(repository).export(
            artifact=artifact,
            approval=approval,
            output_root=Path("reports/linked/nested"),
        )

    assert list(outside.iterdir()) == []
