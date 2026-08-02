# Transparent rule baseline evaluation

> **Scope:** This is a case-tuned deterministic rule baseline evaluated on one frozen
> synthetic case. It is **not AI/model accuracy** and makes no generalization claim. The
> digest-bound fixture is excluded from this evaluation.

## Exact finding results

| Metric | Value |
|---|---:|
| Expected normalized keys | 43 |
| Predicted normalized keys | 43 |
| True positives | 43 |
| False positives | 0 |
| False negatives | 0 |
| Precision | 1.000000 |
| Recall | 1.000000 |
| F1 | 1.000000 |

The answer key contains 48 row-level labels and 43 exact normalized keys. 5 mirrored pair labels were deduplicated before scoring.

## Per-category results

| Category | Expected | Predicted | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AMBIGUOUS_TERM | 10 | 10 | 10 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |
| CONTRADICTION | 3 | 3 | 3 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |
| DUPLICATE | 2 | 2 | 2 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |
| INCOMPLETE | 6 | 6 | 6 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |
| MISSING_ACCEPTANCE_CRITERIA | 7 | 7 | 7 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |
| NON_ATOMIC | 4 | 4 | 4 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |
| UNDEFINED_TERM | 3 | 3 | 3 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |
| UNTESTABLE | 8 | 8 | 8 | 0 | 0 | 1.000000 | 1.000000 | 1.000000 |

## Clean/flawed item classification

| Count | Value |
|---|---:|
| Total items | 50 |
| Gold flawed | 40 |
| Gold clean | 10 |
| Predicted flawed | 40 |
| Predicted clean | 10 |
| Flawed classified as flawed | 40 |
| Clean classified as flawed | 0 |
| Flawed classified as clean | 0 |
| Clean classified as clean | 10 |
| Accuracy | 1.000000 |

## Locked provenance

| Digest | SHA-256 |
|---|---|
| `source_pack_sha256` | `29bcdfed002dc505b519b2ab85f929e86db58fc053a444d9d0eaff565232c6dc` |
| `source_manifest_sha256` | `5cd6a5c34a0465668105c9c89d473dc0242e5d1fc7b4281a667071b0ce36d317` |
| `answer_key_sha256` | `6f82b13b77bb378f587d9fbfbf76ba9a984fc1d2a7832f129036f36bfddb97ec` |
| `evaluator_sha256` | `11ce2064cc51d7ad0e9e2bb9278c049f8e10cedf801a74e3fb3cfdac388c00d4` |
| `configuration_sha256` | `c773be60716c53d58085687101d540f89cedae84067a8b4e515bcc5ef980cc03` |
| `rule_source_sha256` | `2d630fda0e18d859372c70e0d4e1ef2918e93243e7c81bb62483ef66d3df1d3f` |
| `adapter_prompt_sha256` | `368f4bc0fb3a49afcd9197cfcff16b4d366d5b37d4b50dc32580ae8cc051954c` |

## Interpretation boundary

These rules were written for this published synthetic case. The scores show agreement with this answer key only. They do not measure an LLM, the offline fixture, unseen requirements, semantic generalization, or production fitness.
