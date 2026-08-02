from requirements_quality_agent.controls.canonical import sha256_text
from requirements_quality_agent.controls.citations import resolve_citation
from requirements_quality_agent.domain.enums import EvidenceVerdict
from requirements_quality_agent.domain.models import CandidateCitation, EvidenceDocument


def document(text: str = "Alpha requirement. Beta requirement.") -> EvidenceDocument:
    return EvidenceDocument(
        source_id="SRC-001",
        version="1.0",
        relative_path="case/evidence/source.md",
        text=text,
        sha256=sha256_text(text),
    )


def test_resolves_one_exact_quote() -> None:
    result = resolve_citation(
        CandidateCitation(source_id="SRC-001", exact_quote="Beta requirement."),
        (document(),),
    )
    assert result.verdict is EvidenceVerdict.RESOLVED
    assert result.char_start == 19
    assert result.char_end == 36
    assert result.quote_sha256 == sha256_text("Beta requirement.")


def test_unknown_source_fails_closed() -> None:
    result = resolve_citation(
        CandidateCitation(source_id="SRC-999", exact_quote="Alpha"),
        (document(),),
    )
    assert result.verdict is EvidenceVerdict.SOURCE_UNKNOWN
    assert result.char_start is None


def test_missing_quote_fails_closed() -> None:
    result = resolve_citation(
        CandidateCitation(source_id="SRC-001", exact_quote="Invented"),
        (document(),),
    )
    assert result.verdict is EvidenceVerdict.QUOTE_NOT_FOUND


def test_repeated_quote_requires_occurrence() -> None:
    repeated = document("same then same")
    unresolved = resolve_citation(
        CandidateCitation(source_id="SRC-001", exact_quote="same"),
        (repeated,),
    )
    resolved = resolve_citation(
        CandidateCitation(source_id="SRC-001", exact_quote="same", occurrence=2),
        (repeated,),
    )
    assert unresolved.verdict is EvidenceVerdict.QUOTE_AMBIGUOUS
    assert resolved.verdict is EvidenceVerdict.RESOLVED
    assert resolved.char_start == 10


def test_out_of_range_occurrence_fails_closed() -> None:
    result = resolve_citation(
        CandidateCitation(source_id="SRC-001", exact_quote="same", occurrence=3),
        (document("same then same"),),
    )

    assert result.verdict is EvidenceVerdict.QUOTE_NOT_FOUND
    assert result.source_sha256 is None
    assert result.char_start is None
    assert result.char_end is None
    assert result.quote_sha256 is None
