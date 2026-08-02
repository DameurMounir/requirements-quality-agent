"""Read only manifest-authorized, local synthetic Markdown evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

from requirements_quality_agent.controls.canonical import canonical_text
from requirements_quality_agent.domain.models import EvidenceDocument, SourceManifest

MAX_SOURCE_BYTES = 1_000_000
ALLOWED_SUFFIXES = {".md"}


class SourcePackRejected(ValueError):
    """Raised when the pack violates a deterministic input boundary."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def load_model_documents(
    *, repository_root: Path, manifest: SourceManifest
) -> tuple[EvidenceDocument, ...]:
    try:
        evidence_root = (repository_root / manifest.model_input_root).resolve(strict=True)
    except OSError as exc:
        raise SourcePackRejected("model input root is missing or unreadable") from exc
    if not _inside(evidence_root, repository_root.resolve(strict=True)):
        raise SourcePackRejected("model input root escapes the repository")

    documents: list[EvidenceDocument] = []
    for entry in manifest.sources:
        if not entry.allowed_for_model:
            continue
        relative = Path(entry.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise SourcePackRejected(f"unsafe source path: {entry.path}")
        path = repository_root / relative
        if path.is_symlink():
            raise SourcePackRejected(f"symlink source is forbidden: {entry.path}")
        resolved = path.resolve(strict=True)
        if not _inside(resolved, evidence_root):
            raise SourcePackRejected(f"source is outside model input root: {entry.path}")
        if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
            raise SourcePackRejected(f"unsupported source type: {entry.path}")
        raw = resolved.read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            raise SourcePackRejected(f"source is too large: {entry.path}")
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
