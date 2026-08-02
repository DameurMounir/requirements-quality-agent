# Decision 0005: use an atomic application review ledger

## Status

Accepted for the local demonstration.

## Decision

Use LangGraph for the validation-to-review analysis graph. End that graph after
it creates a typed review request. Persist cross-process human decisions in one
run-scoped JSON ledger protected by a local file lock and atomically replaced
on each state change.

The ledger binds:

- all review-round artifacts and requests;
- decisions and consumed nonce hashes;
- current status and failure record; and
- the final export manifest.

Every load revalidates the complete history: schema version, sequential rounds,
each historical artifact digest, decision-to-request reviewer/round/nonce/action
binding, each later round's preceding-decision digest, the exact used-nonce
sequence, status/failure consistency, and final export digests.

Approval and export are separate recoverable operations. Output-path validation
occurs before approval is committed. If a later filesystem failure prevents
export, the persisted `APPROVED` state can be exported again without reusing
the approval nonce.

## Why

The command-line demonstration pauses in one process and resumes in another.
An in-memory LangGraph checkpointer cannot preserve that boundary. Claiming a
native LangGraph interrupt without a durable checkpointer would be misleading.

A single ledger prevents a partial individual commit in which a nonce is
consumed but its decision is missing, or an edited/reanalysed round is only
partly appended. A revision request and its later `resume` are separate atomic
commits by design; `REVISION_REQUESTED` is the valid recoverable state between
them.

## Consequences

- The pause/resume behavior is application-managed and labelled as such.
- Local `fcntl` locking targets the Linux environment used by this release and
  its CI. Cross-platform or multi-host deployment requires another store.
- The reviewer ID remains demonstrative, not authenticated.
- These checks establish internal consistency and catch the tested isolated
  mutations. The unsigned local JSON file is not adversarial tamper evidence:
  someone who can rewrite the complete ledger can construct another internally
  consistent history. A production audit record needs authenticated,
  append-only or externally anchored storage.
- Export is idempotent only when the existing report and manifest exactly match
  the approved digests.
