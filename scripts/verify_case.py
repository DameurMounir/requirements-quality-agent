#!/usr/bin/env python3
"""Verify the frozen synthetic case without third-party dependencies."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "case"
ITEM_PATTERN = re.compile(r"^\[(?P<id>(?:FR|NFR|BR|US)-\d{3})\] (?P<text>.+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_items() -> dict[str, tuple[Path, int, str]]:
    items: dict[str, tuple[Path, int, str]] = {}
    for path in sorted((CASE / "evidence").glob("*.md")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = ITEM_PATTERN.match(line)
            if not match:
                continue
            item_id = match.group("id")
            if item_id in items:
                raise ValueError(f"duplicate item ID: {item_id}")
            items[item_id] = (path, line_number, match.group("text"))
    return items


def load_labels() -> dict[str, dict[str, object]]:
    labels: dict[str, dict[str, object]] = {}
    path = CASE / "expected" / "requirements-labels.jsonl"
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        item_id = str(row["requirement_id"])
        if item_id in labels:
            raise ValueError(f"duplicate label ID at line {line_number}: {item_id}")
        labels[item_id] = row
    return labels


def main() -> int:
    items = load_items()
    labels = load_labels()
    errors: list[str] = []

    if len(items) != 50:
        errors.append(f"expected 50 source items, found {len(items)}")
    if set(items) != set(labels):
        errors.append("source IDs and label IDs differ")

    clean = sum(bool(row["clean"]) for row in labels.values())
    flawed = len(labels) - clean
    if (flawed, clean) != (40, 10):
        errors.append(f"expected 40 flawed and 10 clean, found {flawed} and {clean}")

    for item_id, row in labels.items():
        issues = list(row["issues"])
        related_ids = list(row["related_ids"])
        if bool(row["clean"]) == bool(issues):
            errors.append(f"clean/issue mismatch for {item_id}")
        for related_id in related_ids:
            if related_id not in items:
                errors.append(f"unknown related ID {related_id} for {item_id}")

    manifest_path = CASE / "source-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["sources"]:
            source_path = ROOT / entry["path"]
            if not source_path.is_file():
                errors.append(f"missing manifest source: {entry['path']}")
            elif sha256(source_path) != entry["sha256"]:
                errors.append(f"digest mismatch: {entry['path']}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(items)} items; {flawed} flawed; {clean} clean; IDs and digests valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
