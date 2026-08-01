# Public answer key

`requirements-labels.jsonl` is the versioned gold label set for this small
synthetic benchmark. Each row identifies one source item, whether it is
intentionally clean, its expected issue labels, and any linked item needed to
evaluate a duplicate or contradiction.

The answer key is intentionally public for reproducibility. It is not secret
test data. The workflow's source loader is restricted to `case/evidence/`, and
an automated test confirms that `case/expected/` is never included in model
input.

Metrics operate on `(requirement_id, issue_type)` pairs. A finding is correct
only when its requirement ID and issue type match the answer key. Pair-based
issues additionally require the expected related item.

