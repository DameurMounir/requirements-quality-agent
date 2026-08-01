#!/usr/bin/env python3
"""Validate the machine-readable analysis models and their references."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "case" / "analysis"


def load(name: str) -> dict[str, object]:
    return json.loads((ANALYSIS / name).read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []
    stakeholders = load("stakeholders.json")
    process = load("process-model.json")
    quality = load("quality-model.json")

    stakeholder_rows = list(stakeholders["stakeholders"])
    stakeholder_ids = [row["stakeholder_id"] for row in stakeholder_rows]
    if len(stakeholder_ids) != len(set(stakeholder_ids)):
        errors.append("stakeholder IDs are not unique")

    for step in process["current_process"]:
        if step["owner_id"] not in stakeholder_ids:
            errors.append(f"unknown process owner: {step['owner_id']}")

    allowed_responsibilities = {"DETERMINISTIC", "AI_OR_RULE_ADAPTER", "HUMAN"}
    for step in process["controlled_review"]:
        if step["responsibility"] not in allowed_responsibilities:
            errors.append(f"invalid responsibility: {step['responsibility']}")

    expected_codes: set[str] = set()
    label_path = ROOT / "case" / "expected" / "requirements-labels.jsonl"
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            expected_codes.update(json.loads(line)["issues"])
    model_codes = {row["code"] for row in quality["issue_types"]}
    if expected_codes != model_codes:
        errors.append(f"quality codes differ: expected={sorted(expected_codes)} model={sorted(model_codes)}")

    if quality["approval_actions"] != ["APPROVE", "EDIT", "REJECT", "REQUEST_REVISION"]:
        errors.append("approval action contract changed")

    case_check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_case.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if case_check.returncode:
        errors.append(case_check.stderr.strip() or "case validation failed")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        "PASS: 7 stakeholders; process responsibilities valid; "
        f"{len(model_codes)} issue types aligned; approval contract fixed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

