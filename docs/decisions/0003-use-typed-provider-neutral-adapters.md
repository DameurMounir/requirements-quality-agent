# Decision 0003: use typed provider-neutral adapters

- Status: Accepted
- Date: 2026-08-01

## Decision

Define a small `AnalysisModel` protocol that accepts controlled documents and
requirements and returns a strict `CandidateAnalysis`. Keep fixture, rule, and
OpenAI implementations behind that port.

## Rationale

- Tests can run offline and reproducibly.
- The workflow does not depend on one vendor or model name.
- Model output cannot bypass domain schemas.
- Provider failures have one fail-closed application contract.

## Consequences

- Provider-specific features are intentionally not exposed in version 1.
- A fixture run proves workflow behavior, not model accuracy.
- Live-model provenance records the adapter, exact model identifier, reasoning
  effort, prompt digest, and configuration digest. That digest includes the
  timeout, retry count, output-token cap, response-storage flag, and tool flag;
  the human-readable constants remain explicit in adapter source.
