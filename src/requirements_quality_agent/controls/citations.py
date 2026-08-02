"""Resolve model-suggested exact quotes against controlled source text."""

from __future__ import annotations

from requirements_quality_agent.controls.canonical import canonical_text, sha256_text
from requirements_quality_agent.domain.enums import EvidenceVerdict
from requirements_quality_agent.domain.models import (
    CandidateCitation,
    EvidenceDocument,
    ResolvedCitation,
)


def resolve_citation(
    candidate: CandidateCitation,
    documents: tuple[EvidenceDocument, ...],
) -> ResolvedCitation:
    by_id = {document.source_id: document for document in documents}
    document = by_id.get(candidate.source_id)
    if document is None:
        return ResolvedCitation(
            verdict=EvidenceVerdict.SOURCE_UNKNOWN,
            source_id=candidate.source_id,
            exact_quote=candidate.exact_quote,
        )

    text = canonical_text(document.text)
    quote = canonical_text(candidate.exact_quote)
    starts: list[int] = []
    cursor = 0
    while True:
        position = text.find(quote, cursor)
        if position < 0:
            break
        starts.append(position)
        cursor = position + max(len(quote), 1)

    if not starts:
        verdict = EvidenceVerdict.QUOTE_NOT_FOUND
        return ResolvedCitation(
            verdict=verdict,
            source_id=document.source_id,
            exact_quote=quote,
        )

    if candidate.occurrence is None and len(starts) > 1:
        return ResolvedCitation(
            verdict=EvidenceVerdict.QUOTE_AMBIGUOUS,
            source_id=document.source_id,
            exact_quote=quote,
        )

    selected_index = (candidate.occurrence or 1) - 1
    if selected_index >= len(starts):
        return ResolvedCitation(
            verdict=EvidenceVerdict.QUOTE_NOT_FOUND,
            source_id=document.source_id,
            exact_quote=quote,
        )

    start = starts[selected_index]
    return ResolvedCitation(
        verdict=EvidenceVerdict.RESOLVED,
        source_id=document.source_id,
        source_sha256=document.sha256,
        char_start=start,
        char_end=start + len(quote),
        exact_quote=quote,
        quote_sha256=sha256_text(quote),
    )
