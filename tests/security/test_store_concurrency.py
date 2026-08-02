from __future__ import annotations

import json
import multiprocessing
from collections.abc import Callable
from pathlib import Path
from queue import Empty
from typing import Any

from requirements_quality_agent.adapters.storage.local_store import LocalRunStore
from requirements_quality_agent.application.services import ReviewService
from requirements_quality_agent.config import Settings
from requirements_quality_agent.controls.approval import review_artifact_digest
from requirements_quality_agent.controls.canonical import sha256_text
from requirements_quality_agent.domain.enums import ApprovalAction, WorkflowStatus
from requirements_quality_agent.domain.models import ApprovalSubmission
from requirements_quality_agent.presentation.factory import build_service


def _attempt_same_rejection(
    repository: str,
    run_id: str,
    start_event: Any,
    ready_queue: Any,
    result_queue: Any,
) -> None:
    """Load one shared review, then attempt its exact rejection in this process."""

    nonce_sha256: str | None = None
    try:
        root = Path(repository)
        settings = Settings(
            repository_root=root,
            provider="rule",
            reviewer_id="test-reviewer",
            state_root=Path("run-state"),
            output_root=Path("output"),
        )
        service = build_service(settings, include_model=False)
        _, request = service.store.load_review(run_id)
        submission = ApprovalSubmission(
            run_id=request.run_id,
            artifact_sha256=request.artifact_sha256,
            reviewer_id=request.reviewer_id,
            review_round=request.review_round,
            nonce=request.nonce,
            action=ApprovalAction.REJECT,
            comment="Concurrent one-use nonce regression.",
        )
        nonce_sha256 = sha256_text(request.nonce)
        ready_queue.put({"ready": True, "nonce_sha256": nonce_sha256})
        if not start_event.wait(timeout=20):
            raise TimeoutError("coordinated decision start was not released")
        result = service.decide(submission=submission, output_root="output")
        result_queue.put(
            {
                "outcome": "success",
                "status": result.status.value,
                "nonce_sha256": nonce_sha256,
            }
        )
    except Exception as exc:
        if nonce_sha256 is None:
            ready_queue.put(
                {
                    "ready": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
        result_queue.put(
            {
                "outcome": "failure",
                "error_type": type(exc).__name__,
                "message": str(exc),
                "nonce_sha256": nonce_sha256,
            }
        )


def _get(queue: Any) -> dict[str, object]:
    try:
        value = queue.get(timeout=20)
    except Empty as exc:
        raise AssertionError("worker did not report before the bounded timeout") from exc
    assert isinstance(value, dict)
    return value


def test_two_processes_cannot_consume_the_same_review_nonce(
    repository: Path,
    service_factory: Callable[..., ReviewService],
) -> None:
    prepared = service_factory().analyze("RUN-CONCURRENT-NONCE")
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    ready_queue = context.Queue()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_attempt_same_rejection,
            args=(
                str(repository),
                prepared.artifact.run_id,
                start_event,
                ready_queue,
                result_queue,
            ),
        )
        for _ in range(2)
    ]

    try:
        for process in processes:
            process.start()
        ready = [_get(ready_queue) for _ in processes]
        assert all(message["ready"] is True for message in ready), ready
        assert {message["nonce_sha256"] for message in ready} == {
            sha256_text(prepared.request.nonce)
        }

        start_event.set()
        outcomes = [_get(result_queue) for _ in processes]
        for process in processes:
            process.join(timeout=20)
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        start_event.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        ready_queue.close()
        result_queue.close()
        ready_queue.join_thread()
        result_queue.join_thread()

    successes = [item for item in outcomes if item["outcome"] == "success"]
    failures = [item for item in outcomes if item["outcome"] == "failure"]
    assert len(successes) == 1, outcomes
    assert successes[0]["status"] == WorkflowStatus.REJECTED.value
    assert len(failures) == 1, outcomes
    assert failures[0]["error_type"] in {"ReviewDecisionRejected", "RunStateError"}
    assert {item["nonce_sha256"] for item in outcomes} == {sha256_text(prepared.request.nonce)}

    store = LocalRunStore(repository_root=repository, state_root=Path("run-state"))
    assert store.load_status(prepared.artifact.run_id) is WorkflowStatus.REJECTED
    artifact, request = store.load_review(prepared.artifact.run_id)
    assert artifact == prepared.artifact
    assert request == prepared.request
    assert request.artifact_sha256 == review_artifact_digest(artifact)

    state_path = repository / "run-state" / prepared.artifact.run_id / "state.json"
    state = json.loads(state_path.read_text())
    assert state["status"] == WorkflowStatus.REJECTED.value
    assert state["current_round"] == 1
    assert len(state["rounds"]) == 1
    assert len(state["decisions"]) == 1
    assert state["decisions"][0]["action"] == ApprovalAction.REJECT.value
    assert state["used_nonce_sha256"] == [sha256_text(prepared.request.nonce)]
    assert state["failure"] is None
    assert state["export_manifest"] is None
