"""Load and extract the manifest-authorized local synthetic case pack."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from requirements_quality_agent.controls.canonical import domain_digest, sha256_text
from requirements_quality_agent.controls.input_policy import load_model_documents
from requirements_quality_agent.domain.enums import RequirementKind
from requirements_quality_agent.domain.models import (
    EvidenceDocument,
    Requirement,
    SourceManifest,
    SourceSpan,
)

ITEM_PATTERN = re.compile(r"^\[(?P<id>(?:FR|NFR|BR|US)-\d{3})\] (?P<text>.+)$")
KIND_BY_PREFIX = {
    "FR": RequirementKind.FUNCTIONAL,
    "NFR": RequirementKind.NON_FUNCTIONAL,
    "BR": RequirementKind.BUSINESS_RULE,
    "US": RequirementKind.USER_STORY,
}
PREFIX_ORDER = {"FR": 0, "NFR": 1, "BR": 2, "US": 3}


class RequirementPackRejected(ValueError):
    """Raised when stable item extraction cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class LoadedPack:
    manifest: SourceManifest
    manifest_sha256: str
    source_pack_sha256: str
    documents: tuple[EvidenceDocument, ...]
    requirements: tuple[Requirement, ...]


def _item_order(requirement: Requirement) -> tuple[int, int]:
    prefix, number = requirement.requirement_id.rsplit("-", 1)
    return PREFIX_ORDER[prefix], int(number)


def extract_requirements(documents: tuple[EvidenceDocument, ...]) -> tuple[Requirement, ...]:
    extracted: dict[str, Requirement] = {}
    for document in documents:
        cursor = 0
        for line_number, line_with_end in enumerate(document.text.splitlines(keepends=True), 1):
            line = line_with_end.rstrip("\n")
            match = ITEM_PATTERN.fullmatch(line)
            if match:
                requirement_id = match.group("id")
                if requirement_id in extracted:
                    raise RequirementPackRejected(f"duplicate requirement ID: {requirement_id}")
                text = match.group("text")
                prefix = requirement_id.rsplit("-", 1)[0]
                text_start = cursor + line.index(text)
                extracted[requirement_id] = Requirement(
                    requirement_id=requirement_id,
                    kind=KIND_BY_PREFIX[prefix],
                    text=text,
                    source_span=SourceSpan(
                        source_id=document.source_id,
                        source_sha256=document.sha256,
                        line_start=line_number,
                        line_end=line_number,
                        char_start=text_start,
                        char_end=text_start + len(text),
                        exact_text=text,
                        exact_text_sha256=sha256_text(text),
                    ),
                )
            cursor += len(line_with_end)
    requirements = tuple(sorted(extracted.values(), key=_item_order))
    if len(requirements) != 50:
        raise RequirementPackRejected(f"expected 50 requirements, found {len(requirements)}")
    return requirements


def load_case_pack(repository_root: Path) -> LoadedPack:
    root = repository_root.resolve(strict=True)
    manifest_path = root / "case" / "source-manifest.json"
    if manifest_path.is_symlink():
        raise RequirementPackRejected("source manifest may not be a symlink")
    raw_manifest = manifest_path.read_bytes()
    manifest = SourceManifest.model_validate_json(raw_manifest)
    documents = load_model_documents(repository_root=root, manifest=manifest)
    requirements = extract_requirements(documents)
    source_identity = [
        {
            "source_id": document.source_id,
            "version": document.version,
            "relative_path": document.relative_path,
            "sha256": document.sha256,
        }
        for document in sorted(documents, key=lambda item: item.source_id)
    ]
    return LoadedPack(
        manifest=manifest,
        manifest_sha256=hashlib.sha256(raw_manifest).hexdigest(),
        source_pack_sha256=domain_digest("source-pack", source_identity),
        documents=documents,
        requirements=requirements,
    )
