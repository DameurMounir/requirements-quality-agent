from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from types import ModuleType

import pytest

import requirements_quality_agent.adapters.storage.local_store as storage_module
import requirements_quality_agent.presentation.factory as factory_module
from requirements_quality_agent.application.services import (
    DecisionResult,
    ReviewResult,
    ReviewService,
)
from requirements_quality_agent.controls.approval import approval_record, new_approval_request
from requirements_quality_agent.domain.enums import ApprovalAction, WorkflowStatus
from requirements_quality_agent.domain.models import ApprovalSubmission

APP_MODULE = "requirements_quality_agent.presentation.streamlit_app"


class SessionState(dict[str, object]):
    def __getattr__(self, name: str) -> object:
        return self[name]

    def __setattr__(self, name: str, value: object) -> None:
        self[name] = value


class FakeColumn:
    def __init__(self, streamlit: FakeStreamlit) -> None:
        self.streamlit = streamlit

    def metric(self, label: str, value: object) -> None:
        self.streamlit.events.append(("metric", label, value))

    def button(self, label: str, **kwargs: object) -> bool:
        return self.streamlit.button(label, **kwargs)


class FakeStreamlit(ModuleType):
    def __init__(
        self,
        *,
        initial_state: dict[str, object],
        clicks: set[str],
        edit_proposals: bool,
    ) -> None:
        super().__init__("streamlit")
        self.session_state = SessionState(initial_state)
        self.clicks = clicks
        self.edit_proposals = edit_proposals
        self.events: list[tuple[object, ...]] = []
        self.reruns = 0

    def set_page_config(self, **kwargs: object) -> None:
        self.events.append(("page", kwargs))

    def title(self, value: str) -> None:
        self.events.append(("title", value))

    def caption(self, value: str) -> None:
        self.events.append(("caption", value))

    def info(self, value: str) -> None:
        self.events.append(("info", value))

    def warning(self, value: str) -> None:
        self.events.append(("warning", value))

    def success(self, value: str) -> None:
        self.events.append(("success", value))

    def error(self, value: str) -> None:
        self.events.append(("error", value))

    def subheader(self, value: str) -> None:
        self.events.append(("subheader", value))

    def code(self, value: str) -> None:
        self.events.append(("code", value))

    def dataframe(self, value: object, **kwargs: object) -> None:
        self.events.append(("dataframe", value, kwargs))

    def columns(self, count: int) -> list[FakeColumn]:
        return [FakeColumn(self) for _ in range(count)]

    def text_area(self, label: str, *, value: str, **kwargs: object) -> str:
        self.events.append(("text_area", label, kwargs))
        if self.edit_proposals:
            return value + " Human-edited wording."
        return value

    def button(self, label: str, **kwargs: object) -> bool:
        self.events.append(("button", label, kwargs))
        return label in self.clicks

    def rerun(self) -> None:
        self.reruns += 1


class FakeStore:
    review: ReviewResult

    def __init__(self, **_: object) -> None:
        pass

    def load_review(self, run_id: str) -> tuple[object, object]:
        assert run_id == self.review.artifact.run_id
        return self.review.artifact, self.review.request


class FakeService:
    def __init__(self, review: ReviewResult) -> None:
        self.review = review
        self.analyze_calls = 0
        self.resume_calls = 0
        self.actions: list[ApprovalAction] = []

    def analyze(self) -> ReviewResult:
        self.analyze_calls += 1
        return self.review

    def resume(self, run_id: str) -> ReviewResult:
        assert run_id == self.review.artifact.run_id
        self.resume_calls += 1
        return self.review

    def decide(self, *, submission: ApprovalSubmission, output_root: str) -> DecisionResult:
        assert output_root == "output/ui"
        self.actions.append(submission.action)
        record = approval_record(request=self.review.request, submission=submission)
        target = {
            ApprovalAction.APPROVE: WorkflowStatus.EXPORTED,
            ApprovalAction.EDIT: WorkflowStatus.NEEDS_REVIEW,
            ApprovalAction.REQUEST_REVISION: WorkflowStatus.REVISION_REQUESTED,
            ApprovalAction.REJECT: WorkflowStatus.REJECTED,
        }[submission.action]
        next_request = None
        if submission.action is ApprovalAction.EDIT:
            next_request = new_approval_request(
                artifact=self.review.artifact,
                reviewer_id=self.review.request.reviewer_id,
                review_round=2,
            )
        return DecisionResult(
            run_id=self.review.artifact.run_id,
            status=target,
            artifact_sha256=self.review.request.artifact_sha256,
            decision=record,
            next_request=next_request,
        )


def _run_app(
    *,
    monkeypatch: pytest.MonkeyPatch,
    review: ReviewResult,
    initial_state: dict[str, object],
    clicks: set[str],
    edit_proposals: bool = False,
) -> tuple[FakeStreamlit, FakeService]:
    streamlit = FakeStreamlit(
        initial_state=initial_state,
        clicks=clicks,
        edit_proposals=edit_proposals,
    )
    service = FakeService(review)
    FakeStore.review = review
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setattr(storage_module, "LocalRunStore", FakeStore)
    monkeypatch.setattr(factory_module, "build_service", lambda *_args, **_kwargs: service)
    monkeypatch.delitem(sys.modules, APP_MODULE, raising=False)
    importlib.import_module(APP_MODULE)
    return streamlit, service


@pytest.mark.parametrize(
    ("click", "action", "edit_proposals", "message_kind"),
    [
        ("Approve exact artifact", ApprovalAction.APPROVE, False, "success"),
        ("Submit edited proposals", ApprovalAction.EDIT, True, "success"),
        ("Request revision", ApprovalAction.REQUEST_REVISION, False, "warning"),
        ("Reject", ApprovalAction.REJECT, False, "error"),
    ],
)
def test_streamlit_open_review_actions_are_digest_bound_without_real_io(
    service_factory: Callable[..., ReviewService],
    monkeypatch: pytest.MonkeyPatch,
    click: str,
    action: ApprovalAction,
    edit_proposals: bool,
    message_kind: str,
) -> None:
    review = service_factory().analyze(f"RUN-UI-{action.value.replace('_', '-')}")

    streamlit, service = _run_app(
        monkeypatch=monkeypatch,
        review=review,
        initial_state={"run_id": review.artifact.run_id, "decision": "NEEDS_REVIEW"},
        clicks={click},
        edit_proposals=edit_proposals,
    )

    assert service.actions == [action]
    assert streamlit.reruns == 1
    assert any(event[0] == "dataframe" for event in streamlit.events)
    assert any(event[0] == message_kind for event in streamlit.events)
    if action is ApprovalAction.EDIT:
        assert streamlit.session_state["review_round"] == 2


def test_streamlit_can_start_a_review_without_real_io(
    service_factory: Callable[..., ReviewService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = service_factory().analyze("RUN-UI-START")

    streamlit, service = _run_app(
        monkeypatch=monkeypatch,
        review=review,
        initial_state={},
        clicks={"Run the evidence-linked review"},
    )

    assert service.analyze_calls == 1
    assert streamlit.session_state["run_id"] == review.artifact.run_id
    assert streamlit.session_state["decision"] == "NEEDS_REVIEW"


def test_streamlit_resumes_requested_revision_without_real_io(
    service_factory: Callable[..., ReviewService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = service_factory().analyze("RUN-UI-RESUME")

    streamlit, service = _run_app(
        monkeypatch=monkeypatch,
        review=review,
        initial_state={"run_id": review.artifact.run_id, "decision": "REVISION_REQUESTED"},
        clicks={"Resume requested analysis"},
    )

    assert service.resume_calls == 1
    assert streamlit.session_state["decision"] == "NEEDS_REVIEW"
    assert streamlit.reruns == 1


def test_streamlit_closed_round_shows_read_only_state(
    service_factory: Callable[..., ReviewService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = service_factory().analyze("RUN-UI-CLOSED")

    streamlit, service = _run_app(
        monkeypatch=monkeypatch,
        review=review,
        initial_state={"run_id": review.artifact.run_id, "decision": "EXPORTED"},
        clicks=set(),
    )

    assert service.actions == []
    assert any(
        event[0] == "info" and "review round is closed" in str(event[1])
        for event in streamlit.events
    )
