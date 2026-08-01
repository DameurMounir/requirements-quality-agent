# Decision 0002: separate interpretation, control, and authority

- Status: Accepted
- Date: 2026-08-01
- Scope: Repository 1

## Context

Language models can interpret wording and propose alternatives, but they are
not reliable sources of identity, evidence integrity, permission, or approval.

## Decision

Use three explicit responsibility lanes:

1. AI or a deterministic fixture interprets meaning and proposes candidates.
2. Deterministic code validates sources, schemas, citations, transitions,
   digests, and export rules.
3. A person approves, edits, rejects, or requests revision for the exact
   artifact under review.

## Consequences

- A plausible unsupported finding cannot become confirmed.
- The agent cannot approve its own proposal.
- The implementation contains more explicit contracts than a single prompt.
- Local approval demonstrates integrity binding, not enterprise authentication.

