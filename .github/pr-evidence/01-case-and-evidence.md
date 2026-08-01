# Freeze the fictional onboarding case and evaluation baseline

## Question answered

What problem are we solving, and which evidence is trusted?

## Scope

- Define the AtlasBridge Services fictional onboarding case.
- Freeze 50 source items: 40 flawed and 10 clean.
- Publish stable IDs, issue taxonomy, expected labels, and success gates.
- Add origin, licence, and private-boundary documentation.

## Evidence added

- Five versioned synthetic evidence documents.
- Public gold labels kept outside model input.
- Source manifest with SHA-256 digests.
- Deterministic case-integrity verifier.

## Decisions

- Use original synthetic material only.
- Publish the answer key for reproducibility.
- Prevent the model adapter from loading the answer-key directory.
- Treat public quality numbers as targets until branch 05 measures them.

## Validation

Run `python scripts/verify_case.py`.

## Known gaps

- Analysis models are introduced in branch 02.
- No agent implementation or model call exists in this branch.
- No accuracy claim is made.

## Boundary confirmation

No private code, data, schemas, architecture, URLs, or screenshots are used.
Repositories 2–5, deployment, and social publication remain out of scope.

