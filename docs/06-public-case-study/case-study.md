# Public case study

## The problem

Delivery teams often receive requirements spread across briefs, rules,
functional statements, non-functional statements, and user stories. A local
review may make each document look reasonable while contradictions,
duplicates, undefined terms, and missing acceptance criteria survive across
the complete pack.

The practical question is not whether a model can summarize those files. It is
whether a reviewer can trace every important finding back to exact evidence,
understand what remains uncertain, and make a decision without giving the model
approval authority.

## The fictional case

`AtlasBridge Services` wants to modernize customer onboarding. The frozen pack
contains 50 synthetic requirements across five documents. Forty items are
deliberately flawed and ten are deliberately clean. The public answer key
records the intended labels but is rejected from runtime model input.

The case includes:

- ambiguous words such as “quickly,” “easy,” and “appropriate”;
- incomplete actions with no actor, trigger, or expected outcome;
- user stories without testable acceptance criteria;
- multi-action requirements that should be separated;
- duplicate statements expressed in different wording; and
- cross-document contradictions about automatic and manual approval.

## The controlled solution

The application validates the pack manifest and source digests, extracts
stable requirement IDs, obtains candidate findings from one explicit adapter,
and then resolves exact quotes against the frozen documents. Findings that
cannot satisfy required evidence rules are blocked.

The result is a digest-bound review artifact containing:

- evidence-linked findings;
- severity owned by application policy;
- clarification questions;
- draft revision proposals;
- source and artifact digests; and
- a human review request.

The workflow pauses. A person may approve the exact artifact, edit proposal
wording, reject it, or request another analysis. Edits create a new digest and
review round. Approval permits a new JSON and Markdown export; it never edits
the original evidence.

## Measured result

The transparent rule adapter produces 43 normalized findings against the
locked case. After pair-label normalization, it matches all 43 expected keys.
This is a case-tuned deterministic result, not model accuracy and not evidence
of performance on unseen requirements.

The optional OpenAI Responses API adapter is implemented behind the same typed
port and exercised with a fake client. No live provider evaluation was run for
this release, so no live quality, latency, cost, or robustness claim is made.

The final local gate includes 179 passing tests and 93.06% branch-aware
coverage, plus linting, formatting, strict typing, case and generated-artifact
verification, public-boundary scanning, static security analysis, secret
detection, dependency audit, and distribution inspection.

## Why this project matters

The project demonstrates a complete reasoning path rather than a prompt demo:

1. define a real decision and its success measures;
2. preserve source identity and traceability;
3. distinguish interpretation from verification and authority;
4. design explicit failure and revision paths;
5. measure only what the evidence supports; and
6. communicate the result through a working interface, diagrams, tests, and
   an honest limitations section.

## Boundary

Everything is original and fictional. The repository contains no production
data, private company material, customer information, deployment, or external
write integration. The reviewer ID is a local integrity binding, not
enterprise authentication or an electronic signature.
