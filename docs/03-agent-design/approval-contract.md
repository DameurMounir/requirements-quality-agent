# Human approval contract

## Binding

Every review request binds five values:

| Field | Purpose |
|---|---|
| `run_id` | Prevents a decision from moving between runs |
| `artifact_sha256` | Binds the decision to exact semantic content |
| `reviewer_id` | Names the demonstration reviewer; never model-generated |
| `review_round` | Prevents an old decision from approving a later revision |
| `nonce` | Makes one decision request single-use |

The submission must match all values using constant-time comparison for string
bindings. A mismatch, replay, stale round, or action outside the allowed set is
rejected.

## Actions

- `APPROVE`: creates a record for the exact digest and permits export.
- `EDIT`: applies typed proposal-text edits, revalidates schemas and ledger
  bindings, invalidates the digest and nonce, and requests a new decision. It
  does not rerun source analysis or citation resolution because the evidence
  findings are unchanged; use `REQUEST_REVISION` plus `resume` for reanalysis.
- `REQUEST_REVISION`: closes the current decision request. The explicit
  `resume` command reruns analysis for the same source-pack digest and creates
  the next review round, up to round ten.
- `REJECT`: closes the run without an approved export.

## Demonstration limitation

The local reviewer ID proves integrity binding only. It is not authentication,
an electronic signature, or multi-user authorization. A production design
would require an authenticated principal, enterprise transaction store, access
policy, and audit-retention policy. The demonstration ledger does provide a
local file lock and atomic replace for each persisted state change. An `EDIT`
commits its decision, used nonce, status, and edited next round together.
`REQUEST_REVISION` is intentionally two recoverable transactions: the decision
first commits `REVISION_REQUESTED`; a later explicit `resume` appends the next
analysis round. The intermediate state is valid and does not imply that both
operations are one atomic transaction.
