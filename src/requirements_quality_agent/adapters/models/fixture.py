"""Digest-bound fixture adapter for network-free workflow tests and demos."""

from __future__ import annotations

import json
from pathlib import Path

from requirements_quality_agent.controls.canonical import domain_digest, sha256_text
from requirements_quality_agent.domain.models import (
    CandidateAnalysis,
    EvidenceDocument,
    Requirement,
)


class FixtureNotFound(LookupError):
    """Raised instead of inventing output for an unknown source pack."""


def _source_pack_digest(documents: tuple[EvidenceDocument, ...]) -> str:
    identity = [
        {
            "source_id": document.source_id,
            "version": document.version,
            "relative_path": document.relative_path,
            "sha256": document.sha256,
        }
        for document in sorted(documents, key=lambda item: item.source_id)
    ]
    return domain_digest("source-pack", identity)


class FixtureAnalysisAdapter:
    def __init__(self, fixture_path: Path) -> None:
        self._fixture_path = fixture_path

    @property
    def name(self) -> str:
        return "digest-bound-fixture"

    @property
    def model_id(self) -> None:
        return None

    @property
    def prompt_sha256(self) -> str:
        return sha256_text("digest-bound-fixture/v1")

    @property
    def reasoning_effort(self) -> None:
        return None

    @property
    def configuration(self) -> dict[str, str | int | float | bool | None]:
        return {"fixture_contract": "digest-bound-fixture/v1"}

    def analyze(
        self,
        *,
        documents: tuple[EvidenceDocument, ...],
        requirements: tuple[Requirement, ...],
    ) -> CandidateAnalysis:
        del requirements
        fixture = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        actual = _source_pack_digest(documents)
        if fixture["source_pack_sha256"] != actual:
            raise FixtureNotFound(f"no fixture for source pack {actual}")
        return CandidateAnalysis.model_validate(fixture["candidate_analysis"])
