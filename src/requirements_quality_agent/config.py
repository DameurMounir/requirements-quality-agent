"""Explicit environment and path configuration for local composition."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    repository_root: Path
    provider: str = "rule"
    reviewer_id: str = "demo-requirement-owner"
    model: str = "gpt-5.6-terra"
    reasoning_effort: str = "low"
    state_root: Path = Path("run-state")
    output_root: Path = Path("output")

    def __post_init__(self) -> None:
        if self.provider not in {"rule", "fixture", "openai"}:
            raise ValueError("provider is not in the explicit allowlist")
        if self.reasoning_effort not in {"none", "low", "medium", "high"}:
            raise ValueError("reasoning effort is not in the explicit allowlist")
        if not self.reviewer_id or len(self.reviewer_id) > 120:
            raise ValueError("reviewer ID is missing or too long")
        if not self.model or len(self.model) > 120:
            raise ValueError("model identifier is missing or too long")

    @classmethod
    def from_environment(cls, repository_root: Path | None = None) -> Settings:
        root = (repository_root or Path.cwd()).resolve()
        return cls(
            repository_root=root,
            provider=os.getenv("REQUIREMENTS_AGENT_PROVIDER", "rule"),
            reviewer_id=os.getenv("REQUIREMENTS_AGENT_REVIEWER_ID", "demo-requirement-owner"),
            model=os.getenv("REQUIREMENTS_AGENT_MODEL", "gpt-5.6-terra"),
            reasoning_effort=os.getenv("REQUIREMENTS_AGENT_REASONING_EFFORT", "low"),
            state_root=Path(os.getenv("REQUIREMENTS_AGENT_STATE_ROOT", "run-state")),
            output_root=Path(os.getenv("REQUIREMENTS_AGENT_OUTPUT_ROOT", "output")),
        )
