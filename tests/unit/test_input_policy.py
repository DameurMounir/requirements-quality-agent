import hashlib
from pathlib import Path

import pytest

import requirements_quality_agent.controls.input_policy as input_policy
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


def test_manifest_roots_are_fixed_application_boundaries(tmp_path: Path) -> None:
    _, digest = write_source(tmp_path)
    changed = manifest("case/evidence/source.md", digest).model_copy(
        update={"model_input_root": "other/evidence"}
    )
    with pytest.raises(SourcePackRejected, match="manifest roots"):
        load_model_documents(repository_root=tmp_path, manifest=changed)


def test_too_many_authorized_sources_are_rejected_before_file_access(tmp_path: Path) -> None:
    base = manifest("case/evidence/source.md", "0" * 64)
    entry = base.sources[0]
    sources = tuple(
        entry.model_copy(
            update={
                "source_id": f"SRC-{number:03d}",
                "path": f"case/evidence/source-{number:03d}.md",
            }
        )
        for number in range(21)
    )
    with pytest.raises(SourcePackRejected, match="too many"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=base.model_copy(update={"sources": sources}),
        )


def test_missing_evidence_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SourcePackRejected, match="missing or unreadable"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.md", "0" * 64),
        )


def test_evidence_root_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "case").mkdir()
    (tmp_path / "case" / "evidence").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SourcePackRejected, match="root may not be a symlink"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.md", "0" * 64),
        )


def test_absolute_source_path_is_rejected(tmp_path: Path) -> None:
    write_source(tmp_path)
    with pytest.raises(SourcePackRejected, match="unsafe source path"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest(str((tmp_path / "outside.md").resolve()), "0" * 64),
        )


def test_source_symlink_is_rejected(tmp_path: Path) -> None:
    evidence = tmp_path / "case" / "evidence"
    evidence.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    source = evidence / "source.md"
    source.symlink_to(outside)
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    with pytest.raises(SourcePackRejected, match="symlink source path"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.md", digest),
        )


def test_intermediate_source_symlink_is_rejected_even_within_evidence_root(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "case" / "evidence"
    target = evidence / "real-directory"
    target.mkdir(parents=True)
    source = target / "source.md"
    source.write_text("synthetic evidence", encoding="utf-8")
    (evidence / "linked-directory").symlink_to(target, target_is_directory=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(SourcePackRejected, match="symlink source path"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/linked-directory/source.md", digest),
        )


def test_unsupported_source_suffix_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "case" / "evidence" / "source.txt"
    path.parent.mkdir(parents=True)
    path.write_text("text")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(SourcePackRejected, match="unsupported source type"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.txt", digest),
        )


def test_per_source_size_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, digest = write_source(tmp_path, b"12345")
    monkeypatch.setattr(input_policy, "MAX_SOURCE_BYTES", 4)
    with pytest.raises(SourcePackRejected, match="source is too large"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.md", digest),
        )


def test_total_source_size_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "case" / "evidence" / "first.md"
    second = tmp_path / "case" / "evidence" / "second.md"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"12345")
    second.write_bytes(b"67890")
    base = manifest("case/evidence/first.md", hashlib.sha256(first.read_bytes()).hexdigest())
    second_entry = base.sources[0].model_copy(
        update={
            "source_id": "SRC-002",
            "path": "case/evidence/second.md",
            "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
        }
    )
    monkeypatch.setattr(input_policy, "MAX_TOTAL_SOURCE_BYTES", 9)
    with pytest.raises(SourcePackRejected, match="pack is too large"):
        load_model_documents(
            repository_root=tmp_path,
            manifest=base.model_copy(update={"sources": (*base.sources, second_entry)}),
        )


@pytest.mark.parametrize(
    ("content", "message"),
    [(b"contains\x00nul", "NUL byte"), (b"\xff", "valid UTF-8")],
)
def test_binary_or_invalid_utf8_sources_are_rejected(
    tmp_path: Path,
    content: bytes,
    message: str,
) -> None:
    _, digest = write_source(tmp_path, content)
    with pytest.raises(SourcePackRejected, match=message):
        load_model_documents(
            repository_root=tmp_path,
            manifest=manifest("case/evidence/source.md", digest),
        )
