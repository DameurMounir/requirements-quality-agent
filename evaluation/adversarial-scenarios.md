# Adversarial and integrity scenarios

The table states what the automated suite proves. It does not claim that every
possible attack is prevented or that a local demonstration equals a production
authorization system.

| Scenario | Expected result | Automated evidence |
|---|---|---|
| Instruction embedded in evidence | Remains user-supplied JSON data; no tools are available | `tests/security/test_evaluation_adversarial.py` |
| Answer-key or fixture leakage | Neither path enters model documents | `tests/security/test_storage_and_export.py` |
| Invented or mismatched exact quote | Citation is rejected or finding is blocked | `tests/unit/test_citations.py`, `tests/integration/test_failure_controls.py` |
| Provider refusal, malformed output, or exception | Run fails closed as `ERROR`; raw provider detail is masked | `tests/unit/test_branch04_adapters.py`, `tests/integration/test_failure_controls.py` |
| Absolute, traversing, or symlinked output path | Rejected before external mutation or approval commit | `tests/security/test_storage_and_export.py`, `tests/security/test_export_recovery.py` |
| Replayed or stale approval | Rejected by run, digest, reviewer, round, nonce, and status binding | `tests/unit/test_approval.py`, `tests/integration/test_review_vertical.py` |
| Isolated historical digest, status, nonce, order, action, or export-link mutation | Complete ledger load fails its internal-consistency checks | `tests/security/test_historical_ledger_regressions.py` |
| Markdown control characters or HTML | Escaped in the human-readable report | `tests/security/test_storage_and_export.py` |
| Export failure after approval | Approval remains recoverable; idempotent export validates exact digests | `tests/security/test_export_recovery.py` |
| Secret, PII, private denylist value, runtime artifact, or answer-key reference | Current-tree or reachable-history gate fails without echoing the value | `scripts/scan_public_boundary.py`, `.secrets.baseline` |

## Explicit limits

- Prompt isolation is structural: the adapter uses a system instruction, puts
  the evidence in a JSON user payload, and exposes no tools. It is not a claim
  that a model can never follow an injected instruction.
- The local reviewer identifier is not authentication.
- The unsigned local ledger is not adversarial tamper evidence. A writer who
  can replace the complete file can construct another internally consistent
  history; production requires authenticated append-only or externally anchored
  storage.
- The local lock and atomic replacement design is Linux and single-host only.
- The frozen synthetic pack is intentionally small and case-specific.
