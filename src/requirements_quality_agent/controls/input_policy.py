"""Read only manifest-authorized, local synthetic Markdown evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

from requirements_quality_agent.controls.canonical import canonical_text
from requirements_quality_agent.domain.models import EvidenceDocument, SourceManifest

MAX_SOURCE_BYTES = 1_000_000
MAX_SOURCE_FILES = 20
MAX_TOTAL_SOURCE_BYTES = 5_000_000
ALLOWED_SUFFIXES = {".md"}
MODEL_INPUT_ROOT = "case/evidence"
EXPECTED_ROOT = "case/expected"


class SourcePackRejected(ValueError):
    """Raised when the pack violates a deterministic input boundary."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _has_symlink_component(path: Path, root: Path) -> bool:
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def load_model_documents(
    *, repository_root: Path, manifest: SourceManifest
) -> tuple[EvidenceDocument, ...]:
    repository_root = repository_root.resolve(strict=True)
    if manifest.model_input_root != MODEL_INPUT_ROOT or manifest.expected_root != EXPECTED_ROOT:
        raise SourcePackRejected("manifest roots do not match the application boundary")
    allowed_sources = [entry for entry in manifest.sources if entry.allowed_for_model]
    if len(allowed_sources) > MAX_SOURCE_FILES:
        raise SourcePackRejected("manifest authorizes too many model input files")
    model_input_root = repository_root / manifest.model_input_root
    if model_input_root.is_symlink():
        raise SourcePackRejected("model input root may not be a symlink")
    try:
        evidence_root = model_input_root.resolve(strict=True)
    except OSError as exc:
        raise SourcePackRejected("model input root is missing or unreadable") from exc
    if not _inside(evidence_root, repository_root):
        raise SourcePackRejected("model input root escapes the repository")

    documents: list[EvidenceDocument] = []
    total_bytes = 0
    for entry in manifest.sources:
        if not entry.allowed_for_model:
            continue
        relative = Path(entry.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise SourcePackRejected(f"unsafe source path: {entry.path}")
        path = repository_root / relative
        if _has_symlink_component(path, repository_root):
            raise SourcePackRejected(f"symlink source path is forbidden: {entry.path}")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise SourcePackRejected(f"source is missing or unreadable: {entry.path}") from exc
        if not _inside(resolved, evidence_root):
            raise SourcePackRejected(f"source is outside model input root: {entry.path}")
        if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
            raise SourcePackRejected(f"unsupported source type: {entry.path}")
        raw = resolved.read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            raise SourcePackRejected(f"source is too large: {entry.path}")
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_SOURCE_BYTES:
            raise SourcePackRejected("model input pack is too large")
        if b"\x00" in raw:
            raise SourcePackRejected(f"NUL byte is forbidden: {entry.path}")
        actual_digest = hashlib.sha256(raw).hexdigest()
        if actual_digest != entry.sha256:
            raise SourcePackRejected(f"source digest changed: {entry.path}")
        try:
            text = canonical_text(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SourcePackRejected(f"source is not valid UTF-8: {entry.path}") from exc
        documents.append(
            EvidenceDocument(
                source_id=entry.source_id,
                version=entry.version,
                relative_path=entry.path,
                text=text,
                sha256=entry.sha256,
            )
        )
    if not documents:
        raise SourcePackRejected("manifest authorizes no model input documents")
    return tuple(documents)
