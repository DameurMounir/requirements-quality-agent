# Data origin and public boundary

## Origin

The AtlasBridge Services case was written specifically for this public
portfolio project. The organization, roles, requirements, business rules,
metrics, and decisions are invented. No real customer or private company
document was transformed into this pack.

## Isolation rule

Only files under `case/evidence/` may be supplied to an analysis adapter. Files
under `case/expected/` are evaluation authority and are excluded from model
context. A source loader may not accept arbitrary paths, URLs, archives, pickle
files, databases, or executable documents.

## Publication stop conditions

Publication is blocked if any artifact contains:

- a private project name, domain, path, branch identifier, or screenshot;
- a personal email address, phone number, IP address, credential, or API key;
- content copied from a tutorial without compatible licence authority;
- an unexplained external image, font, template, or dataset;
- a metric that cannot be reproduced from committed evidence.

Forbidden private identifiers are not repeated in public artifacts. The final
boundary scan uses a locally supplied denylist so the denylist values
themselves never need to be committed.

Run the current-tree and reachable-history gates before publication:

```bash
uv run python scripts/scan_public_boundary.py \
  --denylist /absolute/path/to/untracked-denylist.txt
uv run python scripts/scan_public_boundary.py \
  --history --denylist /absolute/path/to/untracked-denylist.txt
```

The scanner reports only the file and finding category; it never prints a
matched denylist value, credential candidate, email, phone number, or public IP.
Tracked binary images must have an exact path/digest/origin/licence record in
`assets/provenance.json`. The first release uses no tracked binary asset.
