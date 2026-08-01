# People, needs, and decision authority

The review workflow assists with interpretation. It does not decide what people
need or who has authority. Those responsibilities remain explicit.

| Person or group | Primary need | Contribution | Decision boundary |
|---|---|---|---|
| Applicant | Clear steps and actionable errors | Confirms applicant-facing meaning | Does not define internal risk rules |
| Onboarding Specialist | Complete cases and bounded exceptions | Validates operational clarity | Does not approve elevated-risk accounts |
| Risk Reviewer | Clear triggers and auditable decisions | Clarifies manual-review rules | Owns elevated-risk decision wording |
| Sales Manager | Timely activation notice | Clarifies notification need | Does not receive restricted review data |
| Support Analyst | Safe status visibility | Validates support use cases | Cannot approve applications |
| Requirement Owner | Traceable, controlled baseline | Resolves scope and meaning | Approves the final requirement revision |
| Delivery and Test Team | Atomic, testable inputs | Challenges ambiguity and testability | Cannot silently choose business meaning |

## Human review in this demonstration

The local application uses an explicit demonstration reviewer ID. That proves
digest-bound review behavior; it does not claim enterprise identity or access
control. A final revision is accepted only when the Requirement Owner reviews
the exact artifact digest and chooses one of four actions:

- `APPROVE`
- `EDIT`
- `REJECT`
- `REQUEST_REVISION`

No model output can create or impersonate this decision.

