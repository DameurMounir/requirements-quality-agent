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
- `EDIT`: applies typed proposal edits, invalidates the digest and nonce, runs
  verification again, and requests a new decision.
- `REQUEST_REVISION`: returns to analysis under a bounded review-round limit.
- `REJECT`: closes the run without an approved export.

## Demonstration limitation

The local reviewer ID proves integrity binding only. It is not authentication,
an electronic signature, or multi-user authorization. A production design
would require an authenticated principal, durable transaction store, access
policy, concurrency control, and audit-retention policy.

