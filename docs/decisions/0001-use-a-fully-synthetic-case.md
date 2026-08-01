# Decision 0001: use a fully synthetic case

- Status: Accepted
- Date: 2026-08-01
- Scope: Repository 1

## Context

The project needs realistic ambiguity, duplication, conflict, and missing
information while remaining safe to publish and independently reproducible.

## Decision

Use the fictional AtlasBridge Services onboarding case. Freeze 50 stable items,
including 40 flawed and 10 clean examples, before agent implementation begins.
Publish the answer key for reproducibility but enforce that it is not included
in model context.

## Alternatives considered

1. Use a private real-world document: rejected because it violates the public
   boundary and makes reproduction impossible.
2. Copy a tutorial dataset: rejected because originality and licence authority
   would be unclear and the case would not demonstrate the intended method.
3. Generate cases dynamically: rejected for the evaluation baseline because
   changing inputs would make public metrics incomparable.

## Consequences

- The benchmark is small and cannot establish production performance.
- Every planted issue can be traced and reviewed openly.
- Future dataset changes require a new version and recalculated metrics.

