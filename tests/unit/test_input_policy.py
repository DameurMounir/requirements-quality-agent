import hashlib
from pathlib import Path

import pytest

from requirements_quality_agent.controls.input_policy import (
    SourcePackRejected,
    load_model_documents,
)
from requirements_quality_agent.domain.models import SourceManifest, SourceManifestEntry


def manifest(path: str, digest: str, *, allowed: bool = True) -> SourceManifest:
    return SourceManifest(
        case_id="CASE-001",
        version="1.0.0",
        created_on="2026-08-01",
        classification="SYNTHETIC-PUBLIC",
        licence="CC-BY-4.0",
        model_input_root="case/evidence",
        expected_root="case/expected",
        sources=(
            SourceManifestEntry(
                source_id="SRC-001",
                version="1.0",
                path=path,
                sha256=digest,
                allowed_for_model=allowed,
            ),
        ),
    )


def write_source(root: Path, content: bytes = b"synthetic evidence") -> tuple[Path, str]:
    path = root / "case" / "evidence" / "source.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def test_loads_only_authorized_digest_matched_markdown(tmp_path: Path) -> None:
    _, digest = write_source(tmp_path)
    documents = load_model_documents(
        repository_root=tmp_path,
        manifest=manifest("case/evidence/source.md", digest),
    )
    assert len(documents) == 1
    assert documents[0].text == "synthetic evidence"


def test_digest_change_is_rejected(tmp_path: Path) -> None:
    write_source(tmp_path)
    with pytest.raises(SourcePackRejected, match="digest changed"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.md", "0" * 64),
        )


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    write_source(tmp_path)
    with pytest.raises(SourcePackRejected, match="unsafe source path"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("../outside.md", "0" * 64),
        )


def test_answer_key_cannot_be_loaded_as_model_input(tmp_path: Path) -> None:
    (tmp_path / "case" / "evidence").mkdir(parents=True)
    expected = tmp_path / "case" / "expected" / "gold.md"
    expected.parent.mkdir(parents=True)
    expected.write_text("answer", encoding="utf-8")
    digest = hashlib.sha256(expected.read_bytes()).hexdigest()
    with pytest.raises(SourcePackRejected, match="outside model input root"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/expected/gold.md", digest),
        )


def test_manifest_with_no_model_documents_is_rejected(tmp_path: Path) -> None:
    _, digest = write_source(tmp_path)
    with pytest.raises(SourcePackRejected, match="authorizes no model input"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.md", digest, allowed=False),
        )
