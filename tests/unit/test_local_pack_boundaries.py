from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from requirements_quality_agent.adapters.input.local_pack import (
    RequirementPackRejected,
    extract_requirements,
    load_case_pack,
)
from requirements_quality_agent.domain.models import EvidenceDocument


def _document(source_id: str, text: str) -> EvidenceDocument:
    raw = text.encode()
    return EvidenceDocument(
        source_id=source_id,
        version="1.0",
        relative_path=f"case/evidence/{source_id}.md",
        text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def test_duplicate_requirement_ids_are_rejected() -> None:
    documents = (
        _document("SRC-001", "[FR-001] First wording\n"),
        _document("SRC-002", "[FR-001] Different wording\n"),
    )
    with pytest.raises(RequirementPackRejected, match="duplicate requirement ID"):
        extract_requirements(documents)


def test_incomplete_extracted_pack_is_rejected() -> None:
    with pytest.raises(RequirementPackRejected, match="expected 50 requirements"):
        extract_requirements((_document("SRC-001", "[FR-001] Only one item\n"),))


def test_source_manifest_symlink_is_rejected(repository: Path, tmp_path: Path) -> None:
    manifest = repository / "case" / "source-manifest.json"
    outside = tmp_path / "outside-manifest.json"
    outside.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(outside)

    with pytest.raises(RequirementPackRejected, match="manifest may not be a symlink"):
        load_case_pack(repository)
