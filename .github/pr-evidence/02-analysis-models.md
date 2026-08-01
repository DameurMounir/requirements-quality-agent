# Define the requirement, finding, evidence, and decision models

## Question answered

What do the people, process, rules, and evidence tell us before implementation?

## Scope

- Model stakeholder needs and decision authority.
- Compare the current review pattern with the controlled workflow.
- Define quality dimensions, issue types, severities, and finding states.
- Define source-to-requirement-to-decision traceability.
- Freeze assumptions, constraints, and analysis decisions.

## Evidence added

- Three machine-readable analysis models.
- Five explanatory analysis documents and two Mermaid views.
- Deterministic cross-model validation.
- Decision 0002 separating interpretation, control, and authority.

## Validation

Run:

```bash
python scripts/verify_case.py
python scripts/validate_analysis.py
```

## Known gaps

- Typed application contracts and the state graph are branch 03 scope.
- No candidate analysis is presented as a measured result.
- The demonstration reviewer is not enterprise authentication.

## Boundary confirmation

All models describe the synthetic case. No private material, external write,
deployment, or additional portfolio repository is included.

