# Design the evidence-linked review and approval workflow

## Question answered

Where may a model interpret, and where must deterministic controls or human
decisions apply?

## Scope

- Add strict domain schemas and provider-neutral ports.
- Freeze canonical digest, citation, input, approval, and transition controls.
- Document workflow states, model adapters, capabilities, and threats.
- Lock runtime and development dependencies.

## Key decisions

- One controlled graph instead of unnecessary multi-agent orchestration.
- No tools or external action capability for the model.
- Pydantic structured outputs at the provider boundary.
- Exact quote resolution rather than fuzzy citation matching.
- Approval bound to run, artifact digest, reviewer, round, and nonce.

## Validation

Branch 03 must pass schema import, case and analysis validation, static checks,
and deterministic unit tests for controls. Full workflow tests are branch 04.

## Known gaps

- Model adapters, graph nodes, local store, exporter, CLI, and UI arrive in
  branch 04.
- The live adapter cannot be benchmarked without a separately configured key.
- Local reviewer identity is not enterprise authentication.

## Boundary confirmation

No external write surface, deployment, private material, or additional
portfolio repository is introduced.

