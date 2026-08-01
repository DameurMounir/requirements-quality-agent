# Decision 0004: bind approval to the artifact digest

- Status: Accepted
- Date: 2026-08-01

## Decision

An approval submission must exactly match the run ID, canonical artifact
SHA-256, reviewer ID, review round, and single-use nonce shown in the request.

## Rationale

A general “approved” flag can be reused after content changes or moved between
runs. Exact binding makes stale and replayed decisions detectable.

## Consequences

- Any semantic edit invalidates the previous approval.
- The exporter can prove which artifact was reviewed.
- The local reviewer ID is still demonstrative and does not replace real
  authentication in a production system.

