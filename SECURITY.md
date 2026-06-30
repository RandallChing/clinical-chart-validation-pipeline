# Security & Data Minimization Architecture

This document describes the data handling policies enforced by the chart
correction pipeline. It is intended for engineers maintaining or extending
this system, and for security reviewers evaluating the pipeline for clinical
deployment.

---

## Data Classification

The raw encounter export ingested by this pipeline contains student health
records that may constitute **Protected Health Information (PHI)** under
HIPAA and **student education records** under FERPA. Specifically:

| Field | Classification |
|---|---|
| State ID | Student identifier — PHI / FERPA |
| Visit Date, Start Time, End Time | Treatment timestamps — PHI |
| Complaint Type, Discharge | Clinical encounter data — PHI |
| Clinical Note | Narrative PHI — highest sensitivity |
| Staff Name, Email | Workforce data — internal only |

---

## Zero-Egress Text Processing

The `Clinical Note` column contains free-text narrative documentation
written by clinical staff. This field:

- **Is never read, parsed, or passed to any function** beyond a null/empty
  character-count check.
- **Is never transmitted** to Google Sheets, external APIs, or any
  third-party service.
- **Is stripped from all output files** before the master error file is
  written to disk or pushed to the cloud layer.

**Rationale:** Narrative text de-identification carries significant
compliance risk. The pipeline's validation objective — confirming that
documentation *exists* — does not require reading its contents. Evaluating
a null flag satisfies the requirement with zero PHI exposure.

---

## Local Processing Boundaries

All validation logic executes entirely within the local Python environment:

- Name integrity checks
- All 17 boolean compliance audits
- Duplicate detection
- Role-based permission evaluation
- Clinical note null check

No patient data leaves the local processing boundary during the audit phase.

---

## Stateless Cloud Handoff

The data pushed to Google Sheets is strictly minimized to the fields
required for staff notification and Infinite Campus record lookup:

```
Visit ID | Visit Date | Staff Name | Email | Role |
School Name | State ID | Start Time | End Time | Action Required
```

**Excluded from cloud push:**
- Clinical Note (narrative PHI)
- Referred By (routing context, not needed for correction)
- Complaint Type (not needed to locate record in Infinite Campus)
- All raw boolean flag columns (consolidated into Action Required)

---

## Service Account Credential Management

Google Sheets authentication uses a Google Cloud service account key
(`credentials.json`). This file:

- **Must never be committed to version control.** It is included in
  `.gitignore` by default. Verify this before pushing.
- Should be stored in the project root on the machine running `main.py`,
  accessible only to the service account that owns the pipeline.
- Should be rotated on a schedule consistent with your organization's
  credential lifecycle policy (recommend: every 90 days).
- The service account should be granted **Editor** access only to the
  specific target Google Sheet — not to the entire Google Drive.

---

## Minimum Necessary Access Principle

The Google Apps Script email sender reads only the `MasterErrorFile` sheet
tab. It does not have access to the raw encounter CSV, master roles file,
or any other organizational data source.

Staff notification emails contain only the minimum identifiers needed to
locate a record in Infinite Campus:
**School Name, State ID, Visit Date, Start Time, Action Required.**

---

## Incident Response

If `credentials.json` is accidentally committed:

1. Immediately revoke the key in Google Cloud Console →
   IAM & Admin → Service Accounts → Keys → Delete key.
2. Generate a new key and replace the local `credentials.json`.
3. Rotate the key in any other environments using the same credential.
4. Review Git history and force-push a cleaned history if the credential
   was pushed to a remote branch.
