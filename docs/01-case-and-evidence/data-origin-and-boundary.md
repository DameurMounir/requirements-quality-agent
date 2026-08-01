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
