#!/usr/bin/env python3
"""Build the deterministic NOT_RUN record for the optional live adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.adapters.models.openai_responses import OpenAIResponsesAdapter
from requirements_quality_agent.config import Settings
from requirements_quality_agent.controls.canonical import domain_digest
from requirements_quality_agent.domain.models import CandidateAnalysis

ROOT = Path(__file__).resolve().parents[1]
ANSWER_KEY = ROOT / "case" / "expected" / "requirements-labels.jsonl"
JSON_OUTPUT = ROOT / "evaluation" / "results" / "openai-adapter.json"
MARKDOWN_OUTPUT = ROOT / "evaluation" / "results" / "openai-adapter.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_record(repository_root: Path = ROOT) -> dict[str, Any]:
    root = repository_root.resolve(strict=True)
    settings = Settings(repository_root=root)
    adapter = OpenAIResponsesAdapter(
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
        client=object(),
    )
    pack = load_case_pack(root)
    configuration: dict[str, Any] = {
        "adapter": adapter.name,
        "model": adapter.model_id,
        "reasoning_effort": adapter.reasoning_effort,
        "adapter_configuration": adapter.configuration,
    }
    return {
        "schema_version": "1.0.0",
        "adapter": adapter.name,
        "status": "NOT_RUN",
        "reason_code": "NO_LIVE_EXECUTION_RECORDED",
        "metrics": None,
        "is_ai_accuracy": False,
        "measurement_scope": (
            "No live provider call was executed for this release; no model quality, latency, "
            "cost, or robustness metric is available."
        ),
        "configuration": configuration,
        "planned_evaluation_digests": {
            "source_pack_sha256": pack.source_pack_sha256,
            "source_manifest_sha256": pack.manifest_sha256,
            "answer_key_sha256": _sha256(root / "case" / "expected" / "requirements-labels.jsonl"),
            "prompt_sha256": adapter.prompt_sha256,
            "candidate_schema_sha256": domain_digest(
                "candidate-analysis-schema",
                CandidateAnalysis.model_json_schema(),
            ),
            "configuration_sha256": domain_digest(
                "openai-evaluation-config",
                configuration,
            ),
        },
    }


def render_markdown(record: dict[str, Any]) -> str:
    configuration = record["configuration"]
    digests = record["planned_evaluation_digests"]
    lines = [
        "# Optional OpenAI adapter evaluation",
        "",
        "**Status: `NOT_RUN`.**",
        "",
        str(record["measurement_scope"]),
        "",
        (
            f"Planned model: `{configuration['model']}`; reasoning effort: "
            f"`{configuration['reasoning_effort']}`. The adapter is implemented and tested "
            "with a fake typed Responses client, but these tests are not live-model "
            "measurements."
        ),
        "",
        "## Planned evaluation provenance",
        "",
        "| Digest | SHA-256 |",
        "|---|---|",
    ]
    lines.extend(f"| `{label}` | `{digest}` |" for label, digest in digests.items())
    lines.extend(
        [
            "",
            (
                "A future live result must replace this record and preserve the source-pack, "
                "answer-key, prompt, schema, model, reasoning, and adapter-configuration "
                "bindings before any precision, recall, latency, cost, or robustness claim "
                "can be published."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    record = build_record(ROOT)
    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    MARKDOWN_OUTPUT.write_text(render_markdown(record), encoding="utf-8", newline="\n")
    print("PASS: optional OpenAI adapter result is NOT_RUN; no live metrics claimed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
