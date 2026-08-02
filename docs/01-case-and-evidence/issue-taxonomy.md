# Requirement quality issue taxonomy

| Code | Meaning | Minimum evidence |
|---|---|---|
| `AMBIGUOUS_TERM` | Wording permits materially different interpretations. | Exact term and source span. |
| `UNTESTABLE` | No observable or measurable result establishes success. | Source span and missing measure or outcome. |
| `INCOMPLETE` | A necessary actor, trigger, condition, object, or result is absent. | Source span and the missing element. |
| `DUPLICATE` | Two items express materially the same obligation. | Both source spans and related IDs. |
| `CONTRADICTION` | Two items cannot both be satisfied under the same condition. | Both source spans and related IDs. |
| `NON_ATOMIC` | One item combines independently decidable obligations. | Source span and separable actions. |
| `MISSING_ACCEPTANCE_CRITERIA` | A user story has no observable acceptance check. | Story span and explicit absence. |
| `UNDEFINED_TERM` | A decision-relevant term lacks a definition in the pack. | Term, source span, and definition search result. |

## Severity

- `CRITICAL`: can authorize incompatible behavior or a materially unsafe scope.
- `HIGH`: likely to produce divergent implementation or test results.
- `MEDIUM`: creates avoidable clarification or maintainability work.
- `LOW`: editorial improvement with limited decision impact.

Severity is not inferred from wording alone. In the first release, the
application fixes severity by issue type so a model cannot lower a mandatory
gate. A reviewer may reject the artifact or explain a disagreement, but there
is no severity-override interface.
