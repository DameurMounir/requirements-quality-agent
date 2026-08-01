#!/usr/bin/env python3
"""Regenerate committed JSON Schemas from the authoritative Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

from requirements_quality_agent.domain.models import (
    ApprovalSubmission,
    CandidateAnalysis,
    ReviewArtifact,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas"
MODELS = {
    "approval-submission.schema.json": ApprovalSubmission,
    "candidate-analysis.schema.json": CandidateAnalysis,
    "review-artifact.schema.json": ReviewArtifact,
}


def main() -> int:
    SCHEMA_ROOT.mkdir(exist_ok=True)
    for filename, model in MODELS.items():
        content = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        (SCHEMA_ROOT / filename).write_text(content, encoding="utf-8")
    print(f"PASS: exported {len(MODELS)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
