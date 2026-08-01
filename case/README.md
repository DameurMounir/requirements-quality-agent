# AtlasBridge Services case pack

This directory contains the frozen synthetic input and answer key for the
Requirements Quality Agent demonstration.

## Case question

Is the draft onboarding information clear, consistent, and testable enough to
build from?

## Contents

- `evidence/`: material supplied to the workflow.
- `expected/`: public gold labels used only by evaluation code.
- `source-manifest.json`: immutable source identity, version, and digest data.

The workflow must never send `expected/` content to a model. Tests enforce
that separation.

## Dataset contract

- 50 draft items: 20 functional requirements, 10 non-functional requirements,
  10 business rules, and 10 user stories.
- 40 items contain at least one planted quality issue.
- 10 items are intentionally clean.
- Cross-item conflicts and duplicates name both participants in the answer key.
- Every item has a stable identifier and a one-line source span.

All names and facts are fictional. See `DATA_LICENSE.md`.

