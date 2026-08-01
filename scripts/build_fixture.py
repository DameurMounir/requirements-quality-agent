#!/usr/bin/env python3
"""Regenerate the digest-bound offline candidate-analysis fixture."""

from __future__ import annotations

import json
from pathlib import Path

from requirements_quality_agent.adapters.input.local_pack import load_case_pack
from requirements_quality_agent.adapters.models.rule import RuleAnalysisAdapter

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "case" / "fixtures" / "candidate-analysis.json"


def main() -> int:
    pack = load_case_pack(ROOT)
    analysis = RuleAnalysisAdapter().analyze(
        documents=pack.documents,
        requirements=pack.requirements,
    )
    payload = {
        "fixture_version": "1.0.0",
        "purpose": "workflow reproduction only; not model-accuracy evidence",
        "source_pack_sha256": pack.source_pack_sha256,
        "candidate_analysis": analysis.model_dump(mode="json"),
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"PASS: wrote {len(analysis.findings)} fixture findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
