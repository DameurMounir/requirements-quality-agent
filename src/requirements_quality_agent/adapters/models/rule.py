"""Transparent provider-free baseline tuned to the published synthetic case."""

from __future__ import annotations

import re
from dataclasses import dataclass

from requirements_quality_agent.controls.canonical import sha256_text
from requirements_quality_agent.domain.enums import AnalysisOrigin, IssueType, Severity
from requirements_quality_agent.domain.models import (
    CandidateAnalysis,
    CandidateCitation,
    CandidateFinding,
    EvidenceDocument,
    Requirement,
)


@dataclass(frozen=True, slots=True)
class PatternRule:
    issue_type: IssueType
    expression: re.Pattern[str]


PATTERN_RULES = (
    PatternRule(
        IssueType.AMBIGUOUS_TERM,
        re.compile(
            r"\b(quickly|easy|as necessary|enough|efficiently|fast|high availability|"
            r"suspicious|important|promptly|simple|without difficulty|soon)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        IssueType.UNTESTABLE,
        re.compile(
            r"\b(user-friendly|intuitive|useful results|secure|scalable|acceptable time|"
            r"appropriate checks|best notification experience)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        IssueType.INCOMPLETE,
        re.compile(
            r"^(Send a confirmation|The portal shall store onboarding data)|"
            r"\b(right people|support all browsers|fails validation, escalate|"
            r"want account details)\b",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        IssueType.NON_ATOMIC,
        re.compile(
            r"(validate identity, create|upload, crop, compress|available and responsive|"
            r"update my phone and email and delete)",
            re.IGNORECASE,
        ),
    ),
    PatternRule(
        IssueType.UNDEFINED_TERM,
        re.compile(r"\b(trusted source|enhanced diligence|control my profile)\b", re.IGNORECASE),
    ),
    PatternRule(
        IssueType.MISSING_ACCEPTANCE_CRITERIA,
        re.compile(r"Acceptance criteria: not supplied\.", re.IGNORECASE),
    ),
)

PAIR_RULES = (
    (IssueType.CONTRADICTION, "FR-008", "BR-001"),
    (IssueType.CONTRADICTION, "NFR-006", "BR-007"),
    (IssueType.CONTRADICTION, "US-003", "BR-008"),
    (IssueType.DUPLICATE, "FR-006", "FR-016"),
    (IssueType.DUPLICATE, "US-002", "US-008"),
)

SEVERITY = {
    IssueType.CONTRADICTION: Severity.CRITICAL,
    IssueType.DUPLICATE: Severity.MEDIUM,
    IssueType.NON_ATOMIC: Severity.MEDIUM,
    IssueType.AMBIGUOUS_TERM: Severity.HIGH,
    IssueType.UNTESTABLE: Severity.HIGH,
    IssueType.INCOMPLETE: Severity.HIGH,
    IssueType.MISSING_ACCEPTANCE_CRITERIA: Severity.HIGH,
    IssueType.UNDEFINED_TERM: Severity.HIGH,
}

PROPOSALS = {
    "FR-004": (
        "The portal shall accept PDF, JPEG, and PNG uploads up to 10 MiB and shall show "
        "the validation reason when an upload is rejected."
    ),
    "US-002": (
        "As an applicant, I want to save and resume my application so that I do not lose "
        "my work. Acceptance: saving a format-valid draft and reopening it within 30 calendar "
        "days restores the last saved values."
    ),
    "US-005": (
        "As a Sales Manager, I want an email within five minutes after account activation so "
        "that I know when a customer is ready. Acceptance: the registered Sales Manager "
        "receives one activation email within five minutes."
    ),
    "US-006": (
        "As a Support Analyst, I want to view non-sensitive application status information so "
        "that I can answer applicant questions without viewing internal review data."
    ),
}


def _citation(requirement: Requirement) -> CandidateCitation:
    return CandidateCitation(
        source_id=requirement.source_span.source_id,
        exact_quote=requirement.text,
    )


def _question(requirement: Requirement, issue_type: IssueType) -> str:
    return (
        f"What approved wording or decision resolves {issue_type.value} for "
        f"{requirement.requirement_id} without changing its intended outcome?"
    )


class RuleAnalysisAdapter:
    """A visible baseline; it is not presented as general AI understanding."""

    @property
    def name(self) -> str:
        return "transparent-rule-baseline"

    @property
    def model_id(self) -> None:
        return None

    @property
    def prompt_sha256(self) -> str:
        return sha256_text("transparent-rule-baseline/v1")

    @property
    def reasoning_effort(self) -> None:
        return None

    @property
    def configuration(self) -> dict[str, str | int | float | bool | None]:
        return {"ruleset": "transparent-rule-baseline/v1"}

    def analyze(
        self,
        *,
        documents: tuple[EvidenceDocument, ...],
        requirements: tuple[Requirement, ...],
    ) -> CandidateAnalysis:
        del documents
        by_id = {requirement.requirement_id: requirement for requirement in requirements}
        required_pair_ids = {item_id for _, left, right in PAIR_RULES for item_id in (left, right)}
        missing = required_pair_ids - set(by_id)
        if missing:
            raise ValueError(f"rule baseline requires IDs: {', '.join(sorted(missing))}")
        findings: list[CandidateFinding] = []
        for requirement in requirements:
            for rule in PATTERN_RULES:
                match = rule.expression.search(requirement.text)
                if match is None:
                    continue
                findings.append(
                    CandidateFinding(
                        issue_type=rule.issue_type,
                        severity=SEVERITY[rule.issue_type],
                        requirement_ids=(requirement.requirement_id,),
                        explanation=(
                            f"The wording matched the published {rule.issue_type.value} "
                            f"baseline rule at '{match.group(0)}'."
                        ),
                        citations=(_citation(requirement),),
                        proposed_revision=PROPOSALS.get(requirement.requirement_id),
                        clarification_question=_question(requirement, rule.issue_type),
                        origin=AnalysisOrigin.RULE,
                    )
                )

        for issue_type, left_id, right_id in PAIR_RULES:
            left = by_id[left_id]
            right = by_id[right_id]
            findings.append(
                CandidateFinding(
                    issue_type=issue_type,
                    severity=SEVERITY[issue_type],
                    requirement_ids=(left_id, right_id),
                    explanation=(
                        f"The published baseline relation identifies {left_id} and {right_id} "
                        f"as a candidate {issue_type.value.lower()}."
                    ),
                    citations=(_citation(left), _citation(right)),
                    clarification_question=(
                        f"Which evidence-backed statement should resolve the relationship between "
                        f"{left_id} and {right_id}?"
                    ),
                    origin=AnalysisOrigin.RULE,
                )
            )

        findings.sort(key=lambda item: (tuple(item.requirement_ids), item.issue_type.value))
        return CandidateAnalysis(findings=tuple(findings))
