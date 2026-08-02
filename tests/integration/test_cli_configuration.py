from __future__ import annotations

import json
from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from requirements_quality_agent.adapters.storage.local_store import LocalRunStore
from requirements_quality_agent.domain.enums import WorkflowStatus
from requirements_quality_agent.domain.models import ControlFailure
from requirements_quality_agent.presentation.cli import main


def test_cli_honors_environment_state_and_output_roots(
    repository: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("REQUIREMENTS_AGENT_PROVIDER", "rule")
    monkeypatch.setenv("REQUIREMENTS_AGENT_REVIEWER_ID", "environment-reviewer")
    monkeypatch.setenv("REQUIREMENTS_AGENT_STATE_ROOT", "environment-state")
    monkeypatch.setenv("REQUIREMENTS_AGENT_OUTPUT_ROOT", "environment-output")
    run_id = "RUN-CLI-ENV"

    analyze_code = main(
        [
            "--repo",
            str(repository),
            "analyze",
            "--run-id",
            run_id,
        ]
    )
    analyze_payload = json.loads(capsys.readouterr().out)

    assert analyze_code == 0
    assert analyze_payload["status"] == "NEEDS_REVIEW"
    assert analyze_payload["reviewer_id"] == "environment-reviewer"
    assert (repository / "environment-state" / run_id / "state.json").is_file()
    assert not (repository / "run-state").exists()

    review_code = main(
        [
            "--repo",
            str(repository),
            "review",
            "--run-id",
            run_id,
            "--action",
            "APPROVE",
        ]
    )
    review_payload = json.loads(capsys.readouterr().out)

    assert review_code == 0
    assert review_payload["status"] == "EXPORTED"
    assert (repository / "environment-output" / run_id / "report.json").is_file()
    assert (repository / "environment-output" / run_id / "report.md").is_file()
    assert not (repository / "output").exists()


def test_cli_flags_override_environment_roots(
    repository: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("REQUIREMENTS_AGENT_STATE_ROOT", "environment-state")
    monkeypatch.setenv("REQUIREMENTS_AGENT_OUTPUT_ROOT", "environment-output")
    run_id = "RUN-CLI-FLAGS"

    assert (
        main(
            [
                "--repo",
                str(repository),
                "analyze",
                "--run-id",
                run_id,
                "--state-root",
                "flag-state",
                "--output-root",
                "flag-output",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "--repo",
                str(repository),
                "review",
                "--run-id",
                run_id,
                "--action",
                "APPROVE",
                "--state-root",
                "flag-state",
                "--output-root",
                "flag-output",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (repository / "flag-state" / run_id / "state.json").is_file()
    assert (repository / "flag-output" / run_id / "report.json").is_file()
    assert not (repository / "environment-state").exists()
    assert not (repository / "environment-output").exists()


def test_cli_validate_show_and_idempotent_export(
    repository: Path,
    capsys: CaptureFixture[str],
) -> None:
    assert main(["--repo", str(repository), "validate"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == "VALIDATED"
    assert validated["requirements"] == 50

    run_id = "RUN-CLI-SHOW"
    assert main(["--repo", str(repository), "analyze", "--run-id", run_id]) == 0
    capsys.readouterr()
    assert main(["--repo", str(repository), "show", "--run-id", run_id]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["status"] == "NEEDS_REVIEW"
    assert shown["requirements"] == 50
    assert shown["review_round"] == 1

    assert (
        main(
            [
                "--repo",
                str(repository),
                "review",
                "--run-id",
                run_id,
                "--action",
                "APPROVE",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--repo", str(repository), "export", "--run-id", run_id]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["status"] == "EXPORTED"
    assert set(exported["exported_files"]) == {"report.json", "report.md"}


def test_cli_request_revision_and_resume(
    repository: Path,
    capsys: CaptureFixture[str],
) -> None:
    run_id = "RUN-CLI-RESUME"
    assert main(["--repo", str(repository), "analyze", "--run-id", run_id]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--repo",
                str(repository),
                "review",
                "--run-id",
                run_id,
                "--action",
                "REQUEST_REVISION",
                "--comment",
                "Run it again.",
            ]
        )
        == 0
    )
    requested = json.loads(capsys.readouterr().out)
    assert requested["status"] == "REVISION_REQUESTED"

    assert main(["--repo", str(repository), "resume", "--run-id", run_id]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["status"] == "NEEDS_REVIEW"
    assert resumed["review_round"] == 2


def test_cli_edit_parsing_and_invalid_edit_error(
    repository: Path,
    capsys: CaptureFixture[str],
) -> None:
    run_id = "RUN-CLI-EDIT"
    assert main(["--repo", str(repository), "analyze", "--run-id", run_id]) == 0
    capsys.readouterr()
    store = LocalRunStore(repository_root=repository, state_root=Path("run-state"))
    artifact, request = store.load_review(run_id)
    proposal = artifact.revisions[0]
    replacement = proposal.proposed_text + " Confirm the timestamp."

    assert (
        main(
            [
                "--repo",
                str(repository),
                "review",
                "--run-id",
                run_id,
                "--action",
                "EDIT",
                "--edit",
                f"{proposal.proposal_id}={replacement}",
            ]
        )
        == 0
    )
    edited = json.loads(capsys.readouterr().out)
    assert edited["status"] == "NEEDS_REVIEW"
    assert edited["next_review_round"] == 2
    assert edited["next_artifact_sha256"] != request.artifact_sha256

    invalid_run = "RUN-CLI-BAD-EDIT"
    assert main(["--repo", str(repository), "analyze", "--run-id", invalid_run]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--repo",
                str(repository),
                "review",
                "--run-id",
                invalid_run,
                "--action",
                "EDIT",
                "--edit",
                "malformed",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "edits use PROPOSAL_ID=REPLACEMENT_TEXT" in captured.err


def test_cli_show_handles_a_failure_run_without_a_review_round(
    repository: Path,
    capsys: CaptureFixture[str],
) -> None:
    run_id = "RUN-CLI-FAILED"
    store = LocalRunStore(repository_root=repository, state_root=Path("run-state"))
    store.save_failure(
        run_id,
        WorkflowStatus.ERROR,
        ControlFailure(
            code="TEST-ERROR",
            safe_message="synthetic failure",
            stage=WorkflowStatus.ANALYZING,
            retryable=False,
        ),
    )

    assert main(["--repo", str(repository), "show", "--run-id", run_id]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown == {"run_id": run_id, "status": "ERROR"}
