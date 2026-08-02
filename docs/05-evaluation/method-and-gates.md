# Evaluation method and gates

## What is measured

The transparent rule adapter is evaluated against the locked public answer key.
One finding key consists of its issue type and sorted target requirement IDs.
Pair findings such as contradictions and duplicates are therefore counted once,
even though the answer key records the relation on both source rows.

The evaluator reports exact true positives, false positives, false negatives,
precision, recall, and F1 overall and by issue type. It also reports whether
each source item was correctly classified as clean or flawed. All input and
configuration digests are stored beside the result.

This is a **case-tuned deterministic baseline**, not AI accuracy and not an
estimate of performance on unseen requirements. The digest-bound fixture is
excluded because it is generated from the same rule output. The optional live
OpenAI evaluation is explicitly `NOT_RUN`.

## Claim gate

A number may appear in the public README only when:

1. the evaluator and answer-key contracts are committed;
2. the generated JSON and Markdown are byte-reproducible;
3. CI regenerates them and rejects drift;
4. the result names the adapter and dataset limitation; and
5. an independent review confirms the wording does not generalize beyond the
   evidence.

## CI gate

Both supported Python lines run linting, formatting, strict typing, branch-aware
coverage, frozen-case validation, generated-artifact drift checks, public-boundary
checks for both the current tree and reachable history, static security analysis,
secret detection, a strict hash-pinned dependency audit, and lock freshness.
Python 3.12 additionally inspects the wheel/source distribution and installs the
wheel into a clean temporary environment for an import and CLI smoke test.

GitHub Actions are pinned to immutable commits. The workflow has read-only
repository permission, does not persist checkout credentials, has no deployment
job, and receives no model secret.
