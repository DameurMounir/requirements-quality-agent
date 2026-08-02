# Verified local sample run

This branch was exercised with the transparent rule baseline against the
frozen 50-item synthetic pack.

| Observation | Measured result |
|---|---:|
| Source items extracted | 50 |
| Candidate findings | 43 |
| Exact-evidence findings | 43 |
| Blocked findings | 0 |
| Draft revision proposals | 4 |
| Initial status | `NEEDS_REVIEW` |

These numbers demonstrate workflow behavior only. The evaluation layer compares
the baseline findings with the public answer key and calculates precision,
recall, and category-level misses. No model-accuracy claim is made here.

## Exercised decision paths

| Action | Persisted effect | Export authority |
|---|---|---|
| `EDIT` | New proposal ID, artifact digest, nonce, and review round | None |
| `REQUEST_REVISION` | `REVISION_REQUESTED`; `resume` creates round `n+1` | None |
| `REJECT` | Terminal `REJECTED` ledger state | None |
| `APPROVE` | One atomic decision and used-nonce record | Exact bound artifact only |

The tested edit path changed round one to round two, then approved the round-two
digest. Re-running `export` returned the already-complete, digest-matched report
without overwriting it.

## Failure behavior

- Invalid source roots, paths, file types, encodings, or hashes fail before the
  analysis adapter runs.
- Provider or schema failures persist `ERROR` without an empty-success result.
- An unsupported contradiction is `BLOCKED` using application-owned severity;
  model-supplied severity cannot lower this gate.
- A decision from the wrong run, reviewer, digest, round, nonce, or current
  status is rejected.
- Absolute, traversing, or symlinked output paths are rejected before a
  directory is created.
- An approved-but-not-exported run remains recoverable through the explicit
  `export` command.

Runtime state and outputs are ignored local artifacts. Committed examples in a
later public-case branch are generated from the same schemas with fixed,
non-secret presentation values.
