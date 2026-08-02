from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import requirements_quality_agent.presentation.factory as factory
from requirements_quality_agent.adapters.models.fixture import FixtureAnalysisAdapter
from requirements_quality_agent.adapters.models.rule import RuleAnalysisAdapter
from requirements_quality_agent.config import Settings
from requirements_quality_agent.presentation.factory import (
    UnknownProvider,
    build_model,
    build_service,
)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"provider": "unknown"}, "provider"),
        ({"reasoning_effort": "extreme"}, "reasoning effort"),
        ({"reviewer_id": ""}, "reviewer ID"),
        ({"reviewer_id": "x" * 121}, "reviewer ID"),
        ({"model": ""}, "model identifier"),
        ({"model": "x" * 121}, "model identifier"),
    ],
)
def test_settings_reject_invalid_allowlisted_values(
    repository: Path,
    changes: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings(repository_root=repository, **changes)


def test_settings_default_to_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_environment()
    assert settings.repository_root == tmp_path.resolve()


def test_factory_builds_rule_fixture_and_model_free_services(repository: Path) -> None:
    rule_settings = Settings(repository_root=repository, provider="rule")
    fixture_settings = Settings(repository_root=repository, provider="fixture")

    assert isinstance(build_model(rule_settings), RuleAnalysisAdapter)
    assert isinstance(build_model(fixture_settings), FixtureAnalysisAdapter)
    service = build_service(rule_settings, include_model=False)
    assert service.model is None


def test_factory_builds_openai_adapter_without_network(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()

    def constructor(**_: object) -> object:
        return sentinel

    monkeypatch.setattr(factory, "OpenAIResponsesAdapter", constructor)

    result = build_model(
        Settings(
            repository_root=repository,
            provider="openai",
            model="test-model",
            reasoning_effort="medium",
        )
    )

    assert result is sentinel


def test_factory_unknown_provider_guard_is_defensive() -> None:
    settings = SimpleNamespace(provider="not-allowlisted")
    with pytest.raises(UnknownProvider, match="unknown provider"):
        build_model(settings)  # type: ignore[arg-type]
