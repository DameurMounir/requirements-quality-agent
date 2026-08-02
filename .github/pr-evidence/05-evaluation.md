# Branch 05 evidence: evaluation

## Purpose

Turn quality and security claims into reproducible evidence without presenting
the case-tuned rule baseline as general AI performance.

## Intended proof

- exact locked-answer-key metrics and configuration digests;
- explicit `NOT_RUN` status for the optional live adapter;
- adversarial and integrity scenario traceability;
- two-version CI with immutable action pins;
- secret, dependency, static-security, public-boundary, generated-drift, test,
  typing, coverage, and distribution gates;
- reachable-history redaction, binary-asset provenance, and a local confidential
  denylist that is never committed;
- a clean-environment wheel install/import/CLI smoke test.

## Merge gate

This branch is not ready until every local CI-equivalent command passes, the
evaluation results regenerate without drift, and an independent reviewer finds
no unsupported metric or security claim.
