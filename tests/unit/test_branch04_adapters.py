from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.adapters.models.fixture import (
    FixtureAnalysisAdapter,
    FixtureNotFound,
)
from requirements_quality_agent.adapters.models.openai_responses import (
    SYSTEM_INSTRUCTIONS,
    OpenAIAdapterError,
    OpenAIResponsesAdapter,
)
from requirements_quality_agent.domain.enums import AnalysisOrigin, IssueType, Severity
from requirements_quality_agent.domain.models import (
    CandidateAnalysis,
    CandidateCitation,
    CandidateFinding,
)


def _single_candidate(origin: AnalysisOrigin = AnalysisOrigin.FIXTURE) -> CandidateAnalysis:
    return CandidateAnalysis(
        findings=(
            CandidateFinding(
                issue_type=IssueType.AMBIGUOUS_TERM,
                severity=Severity.LOW,
                requirement_ids=("FR-001",),
                explanation="The timing word has no measurable threshold.",
                citations=(
                    CandidateCitation(
                        source_id="ABS-FR-001",
                        exact_quote="The portal shall verify a new applicant quickly.",
                    ),
                ),
                origin=origin,
            ),
        )
    )


def test_fixture_adapter_accepts_only_the_bound_source_pack(repository: Path) -> None:
    pack = load_case_pack(repository)
    adapter = FixtureAnalysisAdapter(repository / "case" / "fixtures" / "candidate-analysis.json")

    result = adapter.analyze(documents=pack.documents, requirements=pack.requirements)

    assert result.findings
    assert result.findings[0].requirement_ids
    assert adapter.name == "digest-bound-fixture"
    assert adapter.model_id is None
    assert adapter.reasoning_effort is None
    assert len(adapter.prompt_sha256) == 64


def test_fixture_adapter_fails_for_an_unknown_source_pack(repository: Path) -> None:
    pack = load_case_pack(repository)
    adapter = FixtureAnalysisAdapter(repository / "case" / "fixtures" / "candidate-analysis.json")
    changed_documents = (
        pack.documents[0].model_copy(update={"sha256": "f" * 64}),
        *pack.documents[1:],
    )

    with pytest.raises(FixtureNotFound, match="no fixture for source pack"):
        adapter.analyze(documents=changed_documents, requirements=pack.requirements)


def test_openai_adapter_parses_structured_output_and_forces_openai_origin(
    repository: Path,
) -> None:
    pack = load_case_pack(repository)
    responses = Mock()
    responses.parse.return_value = SimpleNamespace(output_parsed=_single_candidate())
    client = SimpleNamespace(responses=responses)
    adapter = OpenAIResponsesAdapter(
        model="test-model",
        reasoning_effort="low",
        client=client,
    )

    result = adapter.analyze(documents=pack.documents, requirements=pack.requirements)

    assert result.findings[0].origin is AnalysisOrigin.OPENAI
    call = responses.parse.call_args
    assert call.kwargs["model"] == "test-model"
    assert call.kwargs["reasoning"] == {"effort": "low"}
    assert call.kwargs["text_format"] is CandidateAnalysis
    assert call.kwargs["store"] is False
    assert "tools" not in call.kwargs
    assert call.kwargs["input"][0] == {"role": "system", "content": SYSTEM_INSTRUCTIONS}
    assert "case/expected" not in call.kwargs["input"][1]["content"]
    assert adapter.name == "openai-responses"
    assert adapter.model_id == "test-model"
    assert adapter.reasoning_effort == "low"
    assert len(adapter.prompt_sha256) == 64


@pytest.mark.parametrize("parsed", [None, "not-structured", {"findings": []}])
def test_openai_adapter_refusal_or_unparsed_response_fails_closed(
    repository: Path,
    parsed: object,
) -> None:
    pack = load_case_pack(repository)
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **_: SimpleNamespace(output_parsed=parsed),
        )
    )
    adapter = OpenAIResponsesAdapter(
        model="test-model",
        reasoning_effort="low",
        client=client,
    )

    with pytest.raises(OpenAIAdapterError, match="no parsed candidate analysis"):
        adapter.analyze(documents=pack.documents, requirements=pack.requirements)


def test_openai_adapter_masks_provider_errors(repository: Path) -> None:
    pack = load_case_pack(repository)

    class FailingResponses:
        def parse(self, **_: object) -> object:
            raise RuntimeError("secret raw provider payload")

    adapter = OpenAIResponsesAdapter(
        model="test-model",
        reasoning_effort="low",
        client=SimpleNamespace(responses=FailingResponses()),
    )

    with pytest.raises(OpenAIAdapterError, match="live analysis failed closed") as captured:
        adapter.analyze(documents=pack.documents, requirements=pack.requirements)
    assert "secret raw provider payload" not in str(captured.value)


def test_openai_adapter_reports_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def without_openai(name: str, *args: object, **kwargs: object) -> object:
        if name == "openai":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_openai)
    with pytest.raises(OpenAIAdapterError, match="install the 'openai' project extra"):
        OpenAIResponsesAdapter(model="test-model", reasoning_effort="low")
