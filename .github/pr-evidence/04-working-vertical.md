# Deliver the end-to-end requirements review vertical

## Question answered

Can the frozen synthetic pack travel from validation through evidence-linked
analysis, persisted human review, and an approved report without granting the
model authority?

## Scope

- Implement the LangGraph validation, analysis, verification, and failure flow.
- Add rule, digest-bound fixture, and optional no-tool OpenAI adapters.
- Add an atomic cross-process review ledger and four review actions.
- Add deterministic Markdown/JSON export and explicit export recovery.
- Add a CLI and small local Streamlit demonstration.

## Controls demonstrated

- Frozen input roots, file counts, byte limits, safe paths, and source digests.
- Exact quote resolution and application-owned severity policy.
- Run, artifact, reviewer, round, and one-use nonce approval binding.
- Atomic decision/edit/revision persistence under a local file lock.
- Repository-relative, non-symlink, idempotent approved export.
- Provider failure and unsupported critical evidence fail closed.

## Validation

Run the quick start and the complete offline quality gate. Branch 05 adds the
locked evaluation metrics, adversarial corpus, CI workflow, and published
coverage evidence.

## Known gaps

- The review boundary is application-managed, not a native LangGraph interrupt.
- Local reviewer identity is not authentication.
- The rule and fixture adapters are not evidence of general AI accuracy.
- The optional live adapter is not exercised in offline CI.

## Boundary confirmation

Only the original synthetic case is used. There are no external actions,
deployments, private materials, or additional portfolio repositories.
