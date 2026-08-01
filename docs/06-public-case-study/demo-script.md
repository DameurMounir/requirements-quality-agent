# Five-minute demonstration script

## 0:00–0:35 — Open with the decision

“This project asks one question: is a requirements pack clear, consistent, and
testable enough to build from? It does not let a model make that decision.”

Show the README hero, decision question, and interface image.

## 0:35–1:15 — Show the fictional evidence

Open `case/evidence/functional-requirements.md` and
`case/evidence/business-rules.md`. Point to `FR-008`, which allows automatic
activation, and `BR-001`, which requires manual approval. Explain that each
document can look locally reasonable while the pair conflicts.

Open `case/source-manifest.json` briefly to show stable source IDs, versions,
paths, and digests.

## 1:15–2:15 — Run the review

Start the interface:

```bash
uv run streamlit run src/requirements_quality_agent/presentation/streamlit_app.py
```

Click **Run the evidence-linked review**. Show the measured packet: 50 source
items, 43 verified findings, zero blocked findings, and four draft proposals.
Filter or scroll to the `FR-008` / `BR-001` contradiction and point to both
source references.

## 2:15–3:10 — Explain the authority boundary

Show the three-lane table in the README:

- an adapter suggests candidate meaning;
- deterministic controls verify paths, schemas, citations, digests, and state;
- a person approves, edits, rejects, or requests revision.

Explain that an approval is bound to the artifact digest and cannot be replayed
after proposal wording changes.

## 3:10–3:55 — Exercise a human action

Edit one proposed revision and submit it. Show that the application creates a
new digest and review round instead of treating the old approval as valid.

Alternatively, request revision and then resume the analysis. Emphasize that
no approved export exists during revision or rejection.

## 3:55–4:30 — Show evidence, not inflated metrics

Open `evaluation/results/rule-baseline.md`. State clearly:

“The perfect score belongs to a deterministic rule set tuned to one frozen
synthetic case. It is not AI accuracy. The live OpenAI evaluation is marked
`NOT_RUN`.”

Open `evaluation/adversarial-scenarios.md` and show one replay, tamper, path, or
concurrency failure case.

## 4:30–5:00 — Close with what the repository proves

Show the six branch names and summarize the progression: evidence, analysis
models, controlled design, working vertical, evaluation, and public case study.

Close with:

“The value is not the number of agents. It is the visible path from messy
information to an evidence-backed human decision.”
