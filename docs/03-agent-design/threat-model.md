# Threat model

| Threat | Preventive control | Verification | Failure state |
|---|---|---|---|
| Instruction embedded in a source | Source text is data; model has no tools or policy authority | Adversarial evidence fixture | Unsupported output blocked |
| Invented citation | Exact quote must resolve in a manifest source | Missing-quote test | `BLOCKED` or finding rejected |
| Correct quote attached to wrong source | Source ID and source digest are both checked | Cross-source citation test | `SOURCE_UNKNOWN` or not found |
| Answer-key leakage | Loader independently freezes the evidence root | Model-input spy test | Initial pack `REJECTED` |
| Path traversal or symlink | Relative path and resolved-root enforcement | Traversal/symlink tests | `REJECTED` |
| Unsafe file format or deserialization | UTF-8 Markdown only; no pickle, archive, database, or arbitrary YAML | Suffix and magic-content tests | `REJECTED` |
| Malformed or extra model field | Pydantic `extra=forbid` contracts | Schema mutation tests | `ERROR` |
| Model creates approval-looking output | Candidate schema contains no approval field | Extra-field test | `ERROR` |
| Approval replay or stale decision | Run, digest, reviewer, round, and nonce binding | Mismatch and replay tests | Decision rejected |
| Edit bypasses reapproval | Typed proposal edits create a new digest, nonce, and review round | Approval-after-edit test | New `NEEDS_REVIEW` round |
| Unapproved export | Exporter requires an approval record for current digest | Topology and integration tests | Export rejected |
| Secret committed or logged | `.env` ignored; placeholder example; scanning and safe errors | Secret scan and log tests | Release blocked |
| Malicious Markdown/HTML | Deterministic renderer escapes untrusted text | Injection-render test | Safe escaped output |
| Unbounded cost or input | File size, output token, retry, and review-round limits | Limit tests | `REJECTED`, `ERROR`, or `BLOCKED` |

OWASP describes both direct and indirect prompt injection and notes that impact
depends on the agency available to the model. The no-tool design materially
limits that impact: [OWASP LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).
OWASP also recommends reducing functionality, permissions, and autonomy; this
workflow has no external action surface and requires manual approval:
[OWASP LLM06 Excessive Agency](https://genai.owasp.org/llmrisk/llm06-sensitive-information-disclosure/).
