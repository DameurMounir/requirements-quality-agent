# Evidence and citation controls

## Input policy

1. Load the repository-owned source manifest.
2. Accept only relative paths explicitly marked `allowed_for_model`.
3. Resolve every path beneath `case/evidence/`.
4. Reject absolute paths, `..`, symlinks, unsupported suffixes, NUL bytes,
   invalid UTF-8, oversized files, and digest mismatches.
5. Never enumerate the evaluation answer-key directory for model input.

## Exact-quote resolution

The model returns a source ID and exact quote. It does not calculate offsets or
digests.

- No exact occurrence: `QUOTE_NOT_FOUND`.
- More than one occurrence and no occurrence number: `QUOTE_AMBIGUOUS`.
- Unknown source: `SOURCE_UNKNOWN`.
- One exact occurrence: application code records start/end offsets plus source
  and quote SHA-256 values.
- A duplicate or contradiction requires at least two resolved citations.

A valid quote proves that wording exists at a location. It does not prove that
the interpretation is correct; the finding still requires human review.

## Canonical artifact

Semantic objects are serialized as UTF-8 JSON with sorted keys, compact
separators, and non-finite numbers forbidden. The digest uses domain
separation:

```text
SHA256("requirements-quality-agent/review-artifact/v1\0" + canonical_json)
```

Changing a requirement, finding, proposal, scorecard, configuration, prompt,
adapter, or model changes the artifact digest and invalidates approval.

