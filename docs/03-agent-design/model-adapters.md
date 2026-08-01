# Model adapters

## Fixture adapter

The fixture adapter loads a typed analysis only for a known source-pack digest.
Unknown input fails; there is no generic fallback. It demonstrates the complete
state, evidence, approval, and export workflow without network access or an API
key.

Fixture results are **not** model-accuracy evidence and may not satisfy a public
AI-quality claim.

## Rule adapter

The provider-free default is the local rule adapter. It detects transparent
patterns such as explicit missing
acceptance criteria, known vague terms, simple non-atomic lists, and the frozen
synthetic relationship patterns. Its measured results are reported as an
offline baseline, not as proof of general language understanding.

## Optional OpenAI adapter

The live adapter uses the Responses API with Pydantic Structured Outputs and no
tools. The official guide recommends native Pydantic support to keep program
types and JSON Schema aligned: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Configuration is explicit:

- `REQUIREMENTS_AGENT_PROVIDER=openai`
- `OPENAI_API_KEY` supplied by the operator and never logged
- `REQUIREMENTS_AGENT_MODEL` recorded in provenance
- `REQUIREMENTS_AGENT_REASONING_EFFORT` recorded in provenance
- timeout, retry count, output-token limit, response-storage flag, and tool flag
  included in the provenance configuration digest

Current model guidance identifies `gpt-5.6-terra` as the balance of capability
and cost, while the `gpt-5.6` alias routes to the flagship model. The model name
remains configurable so a future benchmark can compare versions:
[OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model).

Refusal, incomplete output, missing parsed data, timeout, authentication error,
or schema failure becomes `ERROR`; none is converted to an empty success. CI
never invokes the live adapter.
