"""Atomic local run ledger for cross-process review and recovery demonstrations."""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from requirements_quality_agent.controls.approval import review_artifact_digest
from requirements_quality_agent.controls.canonical import domain_digest, sha256_text
from requirements_quality_agent.domain.enums import ApprovalAction, WorkflowStatus
from requirements_quality_agent.domain.models import (
    ApprovalRecord,
    ApprovalRequest,
    ControlFailure,
    ExportManifest,
    ReviewArtifact,
)

SAFE_ID = re.compile(r"^[A-Z0-9-]{3,100}$")
FINAL_STATUSES = {
    WorkflowStatus.REJECTED,
    WorkflowStatus.BLOCKED,
    WorkflowStatus.ERROR,
    WorkflowStatus.EXPORTED,
}


class RunStateError(RuntimeError):
    """Raised when local state is missing, unsafe, stale, or replayed."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _write_new(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    _write_new(
        temporary,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    os.replace(temporary, path)


class LocalRunStore:
    """Persist each run as one atomically replaced, lock-protected JSON ledger."""

    def __init__(self, *, repository_root: Path, state_root: Path) -> None:
        self._repository_root = repository_root.resolve(strict=True)
        candidate = state_root if state_root.is_absolute() else self._repository_root / state_root
        if candidate.is_symlink():
            raise RunStateError("state root may not be a symlink")
        resolved_candidate = candidate.resolve(strict=False)
        if not _inside(resolved_candidate, self._repository_root):
            raise RunStateError("state root must remain inside the repository")
        resolved_candidate.mkdir(parents=True, exist_ok=True)
        self._state_root = resolved_candidate.resolve(strict=True)

    def _checked_directory(
        self,
        path: Path,
        *,
        create: bool,
        label: str,
    ) -> Path:
        if path.is_symlink():
            raise RunStateError(f"{label} may not be a symlink")
        if create:
            try:
                path.mkdir(exist_ok=True)
            except OSError as exc:
                raise RunStateError(f"{label} cannot be created") from exc
        if not path.is_dir():
            raise RunStateError(f"{label} is missing or invalid")
        resolved = path.resolve(strict=True)
        if not _inside(resolved, self._state_root):
            raise RunStateError(f"{label} escapes the state root")
        return resolved

    def _run_dir(self, run_id: str, *, create: bool = False) -> Path:
        if SAFE_ID.fullmatch(run_id) is None:
            raise RunStateError("unsafe run ID")
        return self._checked_directory(
            self._state_root / run_id,
            create=create,
            label="run directory",
        )

    @contextmanager
    def _locked(self, run_dir: Path) -> Iterator[None]:
        lock_path = run_dir / ".lock"
        if lock_path.is_symlink():
            raise RunStateError("run lock may not be a symlink")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise RunStateError("run lock cannot be opened safely") from exc
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _state_path(self, run_dir: Path) -> Path:
        path = run_dir / "state.json"
        if path.is_symlink():
            raise RunStateError("run ledger may not be a symlink")
        return path

    @staticmethod
    def _status(state: dict[str, object]) -> WorkflowStatus:
        value = state.get("status")
        if not isinstance(value, str):
            raise RunStateError("run status is invalid")
        try:
            return WorkflowStatus(value)
        except ValueError as exc:
            raise RunStateError("run status is invalid") from exc

    def _read_state_unlocked(self, run_dir: Path, run_id: str) -> dict[str, object]:
        path = self._state_path(run_dir)
        try:
            resolved = path.resolve(strict=True)
            if not _inside(resolved, self._state_root) or not resolved.is_file():
                raise RunStateError("run ledger is invalid")
            raw = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RunStateError("run ledger is missing or invalid") from exc
        if not isinstance(raw, dict) or raw.get("run_id") != run_id:
            raise RunStateError("run ledger identity is invalid")
        self._validate_state(raw, run_id)
        return raw

    def _validate_state(self, state: dict[str, object], run_id: str) -> None:
        try:
            if state.get("schema_version") != "1.0.0":
                raise ValueError
            status = self._status(state)
            rounds = state["rounds"]
            decisions = state["decisions"]
            nonces = state["used_nonce_sha256"]
            if not isinstance(rounds, list) or not isinstance(decisions, list):
                raise TypeError
            if any(not isinstance(item, dict) for item in rounds):
                raise TypeError
            if not isinstance(nonces, list) or len(nonces) != len(set(nonces)):
                raise TypeError
            if any(not isinstance(item, str) for item in nonces):
                raise TypeError

            current_round = state.get("current_round")
            if current_round is None:
                if rounds or decisions or nonces:
                    raise ValueError
                parsed_rounds: dict[int, tuple[ReviewArtifact, ApprovalRequest]] = {}
            else:
                if isinstance(current_round, bool) or not isinstance(current_round, int):
                    raise TypeError
                if current_round != len(rounds) or current_round < 1 or current_round > 10:
                    raise ValueError
                parsed_rounds = {
                    number: self._parse_round(raw, run_id, number)
                    for number, raw in enumerate(rounds, 1)
                }
                source_digests = {
                    artifact.source_pack_sha256 for artifact, _ in parsed_rounds.values()
                }
                manifest_digests = {
                    artifact.manifest_sha256 for artifact, _ in parsed_rounds.values()
                }
                reviewer_ids = {request.reviewer_id for _, request in parsed_rounds.values()}
                request_nonces = {
                    sha256_text(request.nonce) for _, request in parsed_rounds.values()
                }
                if (
                    len(source_digests) != 1
                    or len(manifest_digests) != 1
                    or len(reviewer_ids) != 1
                    or len(request_nonces) != len(parsed_rounds)
                ):
                    raise ValueError

            parsed_decisions = [ApprovalRecord.model_validate(item) for item in decisions]
            if any(item.run_id != run_id for item in parsed_decisions):
                raise ValueError
            decision_rounds = [item.review_round for item in parsed_decisions]
            if decision_rounds != sorted(decision_rounds) or len(decision_rounds) != len(
                set(decision_rounds)
            ):
                raise ValueError
            if nonces != [item.nonce_sha256 for item in parsed_decisions]:
                raise ValueError
            for decision in parsed_decisions:
                if decision.review_round not in parsed_rounds:
                    raise ValueError
                _, request = parsed_rounds[decision.review_round]
                if (
                    decision.artifact_sha256 != request.artifact_sha256
                    or decision.reviewer_id != request.reviewer_id
                    or decision.nonce_sha256 != sha256_text(request.nonce)
                    or decision.action not in request.allowed_actions
                    or decision.approval_id != f"APR-{decision.submission_sha256[:16].upper()}"
                ):
                    raise ValueError

            decisions_by_round = {item.review_round: item for item in parsed_decisions}
            if current_round is not None:
                for number in range(1, current_round):
                    historical_decision = decisions_by_round.get(number)
                    if historical_decision is None or historical_decision.action not in {
                        ApprovalAction.EDIT,
                        ApprovalAction.REQUEST_REVISION,
                    }:
                        raise ValueError
                current_decision = decisions_by_round.get(current_round)
            else:
                current_decision = None

            failure_raw = state.get("failure")
            failure = None if failure_raw is None else ControlFailure.model_validate(failure_raw)
            export_raw = state.get("export_manifest")
            export_manifest = (
                None if export_raw is None else ExportManifest.model_validate(export_raw)
            )

            if status is WorkflowStatus.NEEDS_REVIEW:
                if (
                    current_decision is not None
                    or failure is not None
                    or export_manifest is not None
                ):
                    raise ValueError
            elif status is WorkflowStatus.REVISION_REQUESTED:
                if (
                    current_decision is None
                    or current_decision.action is not ApprovalAction.REQUEST_REVISION
                    or failure is not None
                    or export_manifest is not None
                ):
                    raise ValueError
            elif status in {WorkflowStatus.APPROVED, WorkflowStatus.EXPORTED}:
                if (
                    current_decision is None
                    or current_decision.action is not ApprovalAction.APPROVE
                ):
                    raise ValueError
                if failure is not None:
                    raise ValueError
                if status is WorkflowStatus.APPROVED and export_manifest is not None:
                    raise ValueError
                if status is WorkflowStatus.EXPORTED:
                    if export_manifest is None or current_round is None:
                        raise ValueError
                    artifact, _ = parsed_rounds[current_round]
                    if (
                        export_manifest.run_id != run_id
                        or export_manifest.artifact_sha256 != review_artifact_digest(artifact)
                        or export_manifest.approval_sha256
                        != domain_digest("approval-record", current_decision)
                    ):
                        raise ValueError
            elif status is WorkflowStatus.REJECTED:
                human_rejection = (
                    current_decision is not None
                    and current_decision.action is ApprovalAction.REJECT
                    and failure is None
                )
                input_rejection = current_round is None and failure is not None
                if not (human_rejection or input_rejection) or export_manifest is not None:
                    raise ValueError
            elif status in {WorkflowStatus.BLOCKED, WorkflowStatus.ERROR}:
                if failure is None or export_manifest is not None:
                    raise ValueError
                if (
                    current_round is not None
                    and current_decision is not None
                    and (current_decision.action is not ApprovalAction.REQUEST_REVISION)
                ):
                    raise ValueError
            else:
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise RunStateError("run ledger bindings are invalid") from exc

    def _persist_state(
        self,
        path: Path,
        state: dict[str, object],
        run_id: str,
    ) -> None:
        self._validate_state(state, run_id)
        _atomic_json(path, state)

    def _parse_round(
        self,
        raw: object,
        run_id: str,
        review_round: int,
    ) -> tuple[ReviewArtifact, ApprovalRequest]:
        if not isinstance(raw, dict):
            raise RunStateError("review round is invalid")
        try:
            if raw["review_round"] != review_round:
                raise ValueError
            artifact = ReviewArtifact.model_validate(raw["artifact"])
            request = ApprovalRequest.model_validate(raw["request"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RunStateError("review round is invalid") from exc
        if artifact.run_id != run_id or request.run_id != run_id:
            raise RunStateError("review round run binding is invalid")
        if request.review_round != review_round:
            raise RunStateError("review round number binding is invalid")
        if artifact.status is not WorkflowStatus.NEEDS_REVIEW:
            raise RunStateError("review artifact status is invalid")
        if request.allowed_actions != tuple(ApprovalAction):
            raise RunStateError("review action contract is invalid")
        if request.artifact_sha256 != review_artifact_digest(artifact):
            raise RunStateError("review artifact digest binding is invalid")
        return artifact, request

    @staticmethod
    def _round_payload(
        artifact: ReviewArtifact,
        request: ApprovalRequest,
    ) -> dict[str, object]:
        return {
            "review_round": request.review_round,
            "artifact": artifact.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
        }

    def _current_round(
        self,
        state: dict[str, object],
        run_id: str,
    ) -> tuple[ReviewArtifact, ApprovalRequest]:
        current_round = state.get("current_round")
        rounds = state.get("rounds")
        if isinstance(current_round, bool) or not isinstance(current_round, int):
            raise RunStateError("run has no review round")
        if not isinstance(rounds, list):
            raise RunStateError("run rounds are invalid")
        raw = None
        for item in rounds:
            if not isinstance(item, dict):
                raise RunStateError("run rounds are invalid")
            if item.get("review_round") == current_round:
                raw = item
                break
        return self._parse_round(raw, run_id, current_round)

    def save_review(self, artifact: ReviewArtifact, request: ApprovalRequest) -> None:
        if artifact.run_id != request.run_id:
            raise RunStateError("artifact and request run IDs differ")
        if request.review_round != 1:
            raise RunStateError("an initial review must use round one")
        self._parse_round(self._round_payload(artifact, request), artifact.run_id, 1)
        run_dir = self._run_dir(artifact.run_id, create=True)
        with self._locked(run_dir):
            if self._state_path(run_dir).exists():
                raise RunStateError("run already exists")
            state: dict[str, object] = {
                "schema_version": "1.0.0",
                "run_id": artifact.run_id,
                "status": WorkflowStatus.NEEDS_REVIEW.value,
                "current_round": 1,
                "rounds": [self._round_payload(artifact, request)],
                "decisions": [],
                "used_nonce_sha256": [],
                "failure": None,
                "export_manifest": None,
            }
            self._persist_state(self._state_path(run_dir), state, artifact.run_id)

    def save_failure(
        self,
        run_id: str,
        status: WorkflowStatus,
        failure: ControlFailure,
    ) -> None:
        if status not in {WorkflowStatus.REJECTED, WorkflowStatus.BLOCKED, WorkflowStatus.ERROR}:
            raise RunStateError("invalid failure status")
        run_dir = self._run_dir(run_id, create=True)
        with self._locked(run_dir):
            state_path = self._state_path(run_dir)
            if state_path.exists():
                state = self._read_state_unlocked(run_dir, run_id)
                if self._status(state) in FINAL_STATUSES:
                    raise RunStateError("terminal run status cannot be replaced")
                state["status"] = status.value
                state["failure"] = failure.model_dump(mode="json")
            else:
                state = {
                    "schema_version": "1.0.0",
                    "run_id": run_id,
                    "status": status.value,
                    "current_round": None,
                    "rounds": [],
                    "decisions": [],
                    "used_nonce_sha256": [],
                    "failure": failure.model_dump(mode="json"),
                    "export_manifest": None,
                }
            self._persist_state(state_path, state, run_id)

    def load_review(self, run_id: str) -> tuple[ReviewArtifact, ApprovalRequest]:
        run_dir = self._run_dir(run_id)
        with self._locked(run_dir):
            state = self._read_state_unlocked(run_dir, run_id)
            return self._current_round(state, run_id)

    def load_status(self, run_id: str) -> WorkflowStatus:
        run_dir = self._run_dir(run_id)
        with self._locked(run_dir):
            state = self._read_state_unlocked(run_dir, run_id)
            return self._status(state)

    def _validate_open_decision(
        self,
        state: dict[str, object],
        approval: ApprovalRecord,
    ) -> tuple[ReviewArtifact, ApprovalRequest]:
        if self._status(state) is not WorkflowStatus.NEEDS_REVIEW:
            raise RunStateError("run is not open for review")
        artifact, request = self._current_round(state, approval.run_id)
        used_nonces = state.get("used_nonce_sha256")
        if not isinstance(used_nonces, list):
            raise RunStateError("run nonce ledger is invalid")
        if (
            approval.artifact_sha256 != request.artifact_sha256
            or approval.reviewer_id != request.reviewer_id
            or approval.review_round != request.review_round
            or approval.nonce_sha256 != sha256_text(request.nonce)
            or approval.nonce_sha256 in used_nonces
        ):
            raise RunStateError("decision does not bind the open review")
        return artifact, request

    @staticmethod
    def _append_decision(state: dict[str, object], approval: ApprovalRecord) -> None:
        decisions = state["decisions"]
        nonces = state["used_nonce_sha256"]
        if not isinstance(decisions, list) or not isinstance(nonces, list):
            raise RunStateError("run decision ledger is invalid")
        decisions.append(approval.model_dump(mode="json"))
        nonces.append(approval.nonce_sha256)

    def commit_decision(
        self,
        approval: ApprovalRecord,
        status: WorkflowStatus,
    ) -> None:
        expected = {
            ApprovalAction.APPROVE: WorkflowStatus.APPROVED,
            ApprovalAction.REJECT: WorkflowStatus.REJECTED,
            ApprovalAction.REQUEST_REVISION: WorkflowStatus.REVISION_REQUESTED,
        }
        if approval.action not in expected or expected[approval.action] is not status:
            raise RunStateError("decision action and status do not agree")
        run_dir = self._run_dir(approval.run_id)
        with self._locked(run_dir):
            state = self._read_state_unlocked(run_dir, approval.run_id)
            _, request = self._validate_open_decision(state, approval)
            if status is WorkflowStatus.REVISION_REQUESTED and request.review_round >= 10:
                raise RunStateError("maximum review rounds reached")
            self._append_decision(state, approval)
            state["status"] = status.value
            self._persist_state(self._state_path(run_dir), state, approval.run_id)

    def commit_edit(
        self,
        approval: ApprovalRecord,
        artifact: ReviewArtifact,
        request: ApprovalRequest,
    ) -> None:
        if approval.action is not ApprovalAction.EDIT:
            raise RunStateError("edit transaction requires an EDIT decision")
        run_dir = self._run_dir(approval.run_id)
        with self._locked(run_dir):
            state = self._read_state_unlocked(run_dir, approval.run_id)
            previous_artifact, previous_request = self._validate_open_decision(state, approval)
            if previous_request.review_round >= 10:
                raise RunStateError("maximum review rounds reached")
            if request.review_round != previous_request.review_round + 1:
                raise RunStateError("edited review round is not monotonic")
            if request.reviewer_id != previous_request.reviewer_id:
                raise RunStateError("edit changed the reviewer binding")
            if request.artifact_sha256 == previous_request.artifact_sha256:
                raise RunStateError("edited artifact digest did not change")
            used_nonces = state.get("used_nonce_sha256")
            if not isinstance(used_nonces, list) or sha256_text(request.nonce) in used_nonces:
                raise RunStateError("edit reused a consumed nonce")
            if artifact.source_pack_sha256 != previous_artifact.source_pack_sha256:
                raise RunStateError("edit changed the source-pack binding")
            self._parse_round(
                self._round_payload(artifact, request),
                approval.run_id,
                request.review_round,
            )
            rounds = state["rounds"]
            if not isinstance(rounds, list):
                raise RunStateError("run rounds are invalid")
            self._append_decision(state, approval)
            rounds.append(self._round_payload(artifact, request))
            state["current_round"] = request.review_round
            state["status"] = WorkflowStatus.NEEDS_REVIEW.value
            self._persist_state(self._state_path(run_dir), state, approval.run_id)

    def commit_revision(
        self,
        artifact: ReviewArtifact,
        request: ApprovalRequest,
    ) -> None:
        run_dir = self._run_dir(artifact.run_id)
        with self._locked(run_dir):
            state = self._read_state_unlocked(run_dir, artifact.run_id)
            if self._status(state) is not WorkflowStatus.REVISION_REQUESTED:
                raise RunStateError("run is not waiting for revised analysis")
            previous_artifact, previous_request = self._current_round(state, artifact.run_id)
            if request.review_round != previous_request.review_round + 1:
                raise RunStateError("revision review round is not monotonic")
            if request.review_round > 10:
                raise RunStateError("maximum review rounds reached")
            if request.reviewer_id != previous_request.reviewer_id:
                raise RunStateError("revision changed the reviewer binding")
            used_nonces = state.get("used_nonce_sha256")
            if not isinstance(used_nonces, list) or sha256_text(request.nonce) in used_nonces:
                raise RunStateError("revision reused a consumed nonce")
            if artifact.source_pack_sha256 != previous_artifact.source_pack_sha256:
                raise RunStateError("revision changed the source-pack binding")
            self._parse_round(
                self._round_payload(artifact, request),
                artifact.run_id,
                request.review_round,
            )
            rounds = state["rounds"]
            if not isinstance(rounds, list):
                raise RunStateError("run rounds are invalid")
            rounds.append(self._round_payload(artifact, request))
            state["current_round"] = request.review_round
            state["status"] = WorkflowStatus.NEEDS_REVIEW.value
            self._persist_state(self._state_path(run_dir), state, artifact.run_id)

    def load_approved(self, run_id: str) -> tuple[ReviewArtifact, ApprovalRecord]:
        run_dir = self._run_dir(run_id)
        with self._locked(run_dir):
            state = self._read_state_unlocked(run_dir, run_id)
            if self._status(state) not in {
                WorkflowStatus.APPROVED,
                WorkflowStatus.EXPORTED,
            }:
                raise RunStateError("run is not approved")
            artifact, request = self._current_round(state, run_id)
            decisions = state["decisions"]
            if not isinstance(decisions, list):
                raise RunStateError("run decisions are invalid")
            approvals = [
                ApprovalRecord.model_validate(item)
                for item in decisions
                if item.get("action") == ApprovalAction.APPROVE.value
            ]
            if len(approvals) != 1 or approvals[0].artifact_sha256 != request.artifact_sha256:
                raise RunStateError("approved artifact binding is invalid")
            return artifact, approvals[0]

    def mark_exported(
        self,
        run_id: str,
        approval_id: str,
        manifest: ExportManifest,
    ) -> None:
        run_dir = self._run_dir(run_id)
        with self._locked(run_dir):
            state = self._read_state_unlocked(run_dir, run_id)
            if self._status(state) is not WorkflowStatus.APPROVED:
                raise RunStateError("only an approved run can be marked exported")
            artifact, approval = self.load_approved_without_lock(state, run_id)
            if approval.approval_id != approval_id:
                raise RunStateError("export approval identity is invalid")
            if (
                manifest.run_id != run_id
                or manifest.artifact_sha256 != review_artifact_digest(artifact)
                or manifest.approval_sha256 != domain_digest("approval-record", approval)
            ):
                raise RunStateError("export manifest does not bind the approved artifact")
            state["status"] = WorkflowStatus.EXPORTED.value
            state["export_manifest"] = manifest.model_dump(mode="json")
            self._persist_state(self._state_path(run_dir), state, run_id)

    def load_approved_without_lock(
        self,
        state: dict[str, object],
        run_id: str,
    ) -> tuple[ReviewArtifact, ApprovalRecord]:
        artifact, request = self._current_round(state, run_id)
        decisions = state.get("decisions")
        if not isinstance(decisions, list):
            raise RunStateError("run decisions are invalid")
        approvals = [
            ApprovalRecord.model_validate(item)
            for item in decisions
            if item.get("action") == ApprovalAction.APPROVE.value
        ]
        if len(approvals) != 1 or approvals[0].artifact_sha256 != request.artifact_sha256:
            raise RunStateError("approved artifact binding is invalid")
        return artifact, approvals[0]
