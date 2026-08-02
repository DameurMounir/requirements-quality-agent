# Assumptions, constraints, and decisions

## Assumptions

| ID | Assumption | Validation or treatment |
|---|---|---|
| `ASM-001` | Each scored item occupies one physical Markdown line. | Loader validates the syntax and records the line. |
| `ASM-002` | English wording is sufficient for dataset version 1. | Limitation is visible; multilingual evaluation is deferred. |
| `ASM-003` | The public labels are correct for the bounded taxonomy. | They are evaluation authority, not universal truth. |
| `ASM-004` | The Requirement Owner can resolve meaning in the local demo. | The reviewer identity is demonstrative, not authenticated. |
| `ASM-005` | Source documents remain unchanged during a run. | A digest change blocks continuation. |

## Constraints

| ID | Constraint |
|---|---|
| `CON-001` | Only manifest-listed UTF-8 Markdown evidence is accepted. |
| `CON-002` | The answer key is never included in analysis input. |
| `CON-003` | No tool can browse the web or modify an external system. |
| `CON-004` | A proposed revision never overwrites the source. |
| `CON-005` | An approval is valid only for one run, reviewer, artifact digest, round, and nonce. |
| `CON-006` | A public accuracy claim requires a committed evaluation result. |

## Decisions

| ID | Decision | Rationale |
|---|---|---|
| `DEC-001` | Keep model judgment, deterministic controls, and human authority separate. | A prompt is not an enforcement boundary. |
| `DEC-002` | Use exact quote resolution, not fuzzy citation matching. | A near match can attach a claim to the wrong evidence. |
| `DEC-003` | Publish transparent counts instead of one opaque quality score. | Visitors can reproduce and challenge each measure. |
| `DEC-004` | Preserve clean examples in the benchmark. | Precision cannot be measured using only flawed requirements. |
| `DEC-005` | Treat fake-model output as workflow evidence, not AI accuracy evidence. | Deterministic fixtures cannot prove model quality. |

