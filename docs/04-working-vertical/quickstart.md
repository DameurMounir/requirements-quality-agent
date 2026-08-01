# Working vertical quick start

The default run is local, provider-free, and uses only the frozen synthetic
case. No API key or external service is required.

## Install and validate

```bash
uv sync --all-extras
uv run requirements-quality-agent --repo . validate
```

## Analyze and pause for review

```bash
uv run requirements-quality-agent --repo . analyze \
  --provider rule \
  --run-id RUN-DEMO-001

uv run requirements-quality-agent --repo . show --run-id RUN-DEMO-001
```

The run stops in `NEEDS_REVIEW`. The one-use nonce is stored in the ignored
local run ledger and is not printed for screenshots or copied into shell
history. The `review` command loads that binding locally.

## Record one review action

Approve the exact artifact and export it:

```bash
uv run requirements-quality-agent --repo . review \
  --run-id RUN-DEMO-001 \
  --action APPROVE \
  --comment "Approved for the synthetic demonstration."
```

Other supported actions:

```bash
uv run requirements-quality-agent --repo . review \
  --run-id RUN-DEMO-001 --action REJECT

uv run requirements-quality-agent --repo . review \
  --run-id RUN-DEMO-001 --action REQUEST_REVISION

uv run requirements-quality-agent --repo . resume \
  --provider rule --run-id RUN-DEMO-001
```

`EDIT` takes one or more `PROPOSAL-ID=REPLACEMENT` arguments. An edit produces
a content-derived proposal ID, a different artifact digest, a fresh nonce, and
the next review round before another approval is possible.

## Recover an approved export

An approval is committed before file export. If the filesystem write fails,
the run remains honestly `APPROVED` and can be retried:

```bash
uv run requirements-quality-agent --repo . export --run-id RUN-DEMO-001
```

Export is idempotent for an existing complete, digest-matched report and never
overwrites a different or incomplete run directory.

## Optional visual demo

```bash
uv run streamlit run \
  src/requirements_quality_agent/presentation/streamlit_app.py
```

The reviewer identity in this local demonstration is an integrity binding, not
authentication or an electronic signature.
