"""Composition root shared by local presentation adapters."""

from __future__ import annotations

from requirements_quality_agent.adapters.models.fixture import FixtureAnalysisAdapter
from requirements_quality_agent.adapters.models.openai_responses import OpenAIResponsesAdapter
from requirements_quality_agent.adapters.models.rule import RuleAnalysisAdapter
from requirements_quality_agent.adapters.output.local_files import LocalReportExporter
from requirements_quality_agent.adapters.storage.local_store import LocalRunStore
from requirements_quality_agent.application.ports import AnalysisModel
from requirements_quality_agent.application.services import ReviewService
from requirements_quality_agent.config import Settings


class UnknownProvider(ValueError):
    """Raised when a provider name is not in the explicit allowlist."""


def build_model(settings: Settings) -> AnalysisModel:
    if settings.provider == "rule":
        return RuleAnalysisAdapter()
    if settings.provider == "fixture":
        return FixtureAnalysisAdapter(
            settings.repository_root / "case" / "fixtures" / "candidate-analysis.json"
        )
    if settings.provider == "openai":
        return OpenAIResponsesAdapter(
            model=settings.model,
            reasoning_effort=settings.reasoning_effort,
        )
    raise UnknownProvider(f"unknown provider: {settings.provider}")


def build_service(settings: Settings, *, include_model: bool = True) -> ReviewService:
    return ReviewService(
        repository_root=str(settings.repository_root),
        model=build_model(settings) if include_model else None,
        store=LocalRunStore(
            repository_root=settings.repository_root,
            state_root=settings.state_root,
        ),
        exporter=LocalReportExporter(settings.repository_root),
        reviewer_id=settings.reviewer_id,
    )
