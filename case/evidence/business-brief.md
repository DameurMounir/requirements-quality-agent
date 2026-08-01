# AtlasBridge Services — customer onboarding brief

Document ID: `ABS-BRIEF-001`  
Version: `1.0`  
Classification: `SYNTHETIC-PUBLIC`

## Context

AtlasBridge Services is a fictional business-services provider. New business
customers currently submit account details through email and spreadsheets.
Operations staff then re-enter the same data, request identity documents, and
coordinate risk review manually.

## Intended outcome

The proposed portal should let an applicant submit an onboarding application,
save progress, upload evidence, and track the decision. Standard-risk
applications should normally complete within four business hours after a
complete submission. Elevated-risk applications require a Risk Reviewer
decision before activation.

## Roles

- Applicant: submits and tracks an application.
- Onboarding Specialist: checks completeness and resolves routine exceptions.
- Risk Reviewer: decides elevated-risk applications.
- Sales Manager: receives notification when an account becomes active.
- Support Analyst: helps applicants and can view non-sensitive status data.

## Defined terms

- Business hours: Monday–Friday, 08:00–18:00 UTC, excluding fictional company
  holidays.
- Standard risk: no elevated-risk indicator is present after validation.
- Elevated risk: at least one configured risk indicator requires manual review.
- Complete submission: all mandatory fields and required documents pass format
  validation.

## Fixed demonstration constraints

- The portal is English-only in version 1.
- Email is the only outbound notification channel in version 1.
- Source documents are never modified by the review workflow.
- The case does not encode real legal or regulatory obligations.

