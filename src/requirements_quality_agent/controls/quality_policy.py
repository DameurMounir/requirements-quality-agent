"""Deterministic severity and blocking policy independent of model output."""

from requirements_quality_agent.domain.enums import IssueType, Severity

SEVERITY_BY_ISSUE: dict[IssueType, Severity] = {
    IssueType.AMBIGUOUS_TERM: Severity.HIGH,
    IssueType.UNTESTABLE: Severity.HIGH,
    IssueType.INCOMPLETE: Severity.HIGH,
    IssueType.DUPLICATE: Severity.MEDIUM,
    IssueType.CONTRADICTION: Severity.CRITICAL,
    IssueType.NON_ATOMIC: Severity.MEDIUM,
    IssueType.MISSING_ACCEPTANCE_CRITERIA: Severity.HIGH,
    IssueType.UNDEFINED_TERM: Severity.HIGH,
}

BLOCKING_WITHOUT_EVIDENCE = frozenset({IssueType.CONTRADICTION})


def controlled_severity(issue_type: IssueType) -> Severity:
    """Return the application-owned severity for a closed issue type."""

    return SEVERITY_BY_ISSUE[issue_type]


def blocks_without_evidence(issue_type: IssueType) -> bool:
    """Return whether unsupported evidence blocks the complete review run."""

    return issue_type in BLOCKING_WITHOUT_EVIDENCE
