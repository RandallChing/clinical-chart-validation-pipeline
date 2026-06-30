# csv-validation-pipeline

A weekly data integrity audit and staff notification system for a public school health network.

Ingests student health encounter records exported from a student information system, applies 17 compliance validation checks using vectorized pandas operations, and dispatches personalized correction notices to clinical staff via Google Apps Script.

Built to replace a manual audit process across 400+ clinical staff serving Hawaii's DOE public and charter school network.

---

## Background

School health rooms generate thousands of encounter records weekly. Incomplete or erroneous charts — missing discharge types, incorrectly timed visits, unauthorized clinical dispositions — create compliance gaps that affect grant reporting, psychiatric referral tracking, and care continuity.

This pipeline automates the detection of those gaps and routes correction notices directly to the staff member responsible, with enough context (School Name, State ID, Start Time) to locate the record in the source system and fix it before the next audit cycle.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  INPUT LAYER                                             │
│  ┌─────────────────────┐  ┌────────────────────────────┐ │
│  │  raw_data.csv        │  │  master_roles.csv          │ │
│  │  (IC export)         │  │  holiday_calendar.csv      │ │
│  └──────────┬──────────┘  └──────────────┬─────────────┘ │
└─────────────┼─────────────────────────────┼──────────────┘
              │                             │
┌─────────────▼─────────────────────────────▼──────────────┐
│  VALIDATION LAYER  (Python / pandas)                      │
│  ┌───────────────────────┐  ┌────────────────────────┐   │
│  │  name_integrity_check  │  │  audit_script          │   │
│  │  · Name coverage       │  │  · 17 boolean checks   │   │
│  │  · Count parity        │  │  · Role permissions    │   │
│  └───────────────────────┘  │  · Action Required msg  │   │
│                              └──────────────┬──────────┘  │
└─────────────────────────────────────────────┼─────────────┘
                                              │
┌─────────────────────────────────────────────▼─────────────┐
│  OUTPUT LAYER                                              │
│  ┌─────────────────────────┐  ┌─────────────────────────┐ │
│  │  master_error_file.csv   │  │  Google Sheets          │ │
│  │  (local, gitignored)     │  │  (via gspread API)      │ │
│  └─────────────────────────┘  └──────────────┬──────────┘ │
└──────────────────────────────────────────────┼────────────┘
                                               │
                              ┌────────────────▼────────────┐
                              │  Google Apps Script          │
                              │  (Tuesday 7:00 AM trigger)   │
                              │  Sends HTML email per staffer │
                              └─────────────────────────────┘
```

---

## Repository Structure

```
csv-validation-pipeline/
├── data/
│   ├── mock_raw_data.csv          # 33-row synthetic encounter log
│   ├── mock_master_roles.csv      # 5 fictional staff (all role tiers)
│   └── mock_holiday_calendar.csv  # Hawaii 2025–26 school year holidays
│
├── audit/
│   ├── name_integrity_check.py    # Name coverage + record count parity
│   └── audit_script.py            # All 17 compliance checks (vectorized)
│
├── apps_script/
│   └── Code.gs                    # Google Apps Script email sender
│
├── tests/
│   └── test_audit.py              # 20-case pytest harness
│
├── output/
│   └── .gitkeep                   # Runtime output directory (CSV gitignored)
│
├── main.py                        # Pipeline orchestrator
├── requirements.txt
├── .gitignore
├── RUNBOOK.md                     # Onboarding and operations guide
└── SECURITY.md                    # PHI handling and data minimization policy
```

---

## Validation Checks

The audit engine applies 17 compliance checks. Each produces a boolean flag column in the master error output.

| # | Flag | Description |
|---|---|---|
| 1 | `flag_duplicate_visit_id` | Two or more records share the same Visit ID |
| 2 | `flag_data_entry_duplicate` | Records share staff, date, start time, school, and state ID |
| 3 | `flag_chart_incomplete` | Completed field is 0 (chart marked in-progress) |
| 4 | `flag_discharge_missing` | Discharge type field is null or empty |
| 5 | `flag_complaint_missing` | Complaint type field is null or empty |
| 6 | `flag_weekend` | Visit date falls on Saturday or Sunday |
| 7 | `flag_holiday` | Visit date matches a school holiday |
| 8 | `flag_end_time_missing` | Discharge time field is null or empty |
| 9 | `flag_start_time_missing` | Start time field is null or empty |
| 10 | `flag_start_after_end` | Start time is chronologically after discharge time |
| 11 | `flag_zero_duration` | Start time equals discharge time (0-minute visit) |
| 12 | `flag_referral_missing` | Referred By field is null or empty |
| 13 | `flag_duration_over_6h` | Visit duration exceeds 6 hours |
| 14 | `flag_start_before_630` | Start time is before 6:30 AM |
| 15 | `flag_end_after_1700` | Discharge time is after 5:00 PM |
| 16 | `flag_unauthorized_discharge` | SHA or HT used a discharge type requiring APRN/RN authority |
| 17 | `flag_clinical_note_missing` | Clinical note field is null or empty |

### Role-Based Discharge Permissions

| Discharge Type | Authorized Roles |
|---|---|
| Return to Class | All |
| Released to Parent/Guardian | All |
| Transferred to Emergency Medical Services (EMS) | APRN, RN |
| Referred to Primary Care Provider (PCP) | APRN, RN |
| Referred to Mental Health Professional | APRN, RN |
| Administered Prescribed Medication & Released | APRN, RN |
| Scheduled Follow-up Audit | APRN, RN, Admin |

---

## Synthetic Test Environment

The `data/` directory contains fully synthetic data designed to stress-test the validation engine without exposing any real student or staff information.

**`mock_master_roles.csv`** — 5 fictional staff members covering all clinical role tiers (APRN, RN, HT, SHA, Admin). One staff name (`Joanna Reyes`) is intentionally absent to trip the name integrity check.

**`mock_raw_data.csv`** — 33 rows split 13 clean / 20 flagged. Each flagged row trips exactly one compliance rule, ensuring the test harness validates deterministic, isolated flag behavior.

**`mock_holiday_calendar.csv`** — Hawaii 2025–26 federal and state holidays in MM/DD/YYYY format.

---

## Quickstart

```bash
# Install dependencies
pip install -r requirements.txt

# Run the test harness (all 20 tests should pass)
pytest tests/test_audit.py -v

# Run the full pipeline against mock data
python main.py

# Run against a live Infinite Campus export
python main.py --raw-data path/to/your_export.csv
```

The pipeline prints a name integrity report and audit summary to the terminal,
writes `output/master_error_file.csv` locally, and pushes to Google Sheets
if `credentials.json` is present.

See [RUNBOOK.md](RUNBOOK.md) for full setup and operational instructions.

---

## Security Model

This pipeline processes records that may constitute PHI under HIPAA. Key design decisions:

- **Zero-egress text processing:** The `Clinical Note` column is evaluated only for null/empty status. Note text is never read, parsed, or transmitted.
- **Local processing boundary:** All 17 validation checks execute locally. No raw encounter data leaves the local environment during the audit phase.
- **Stateless cloud handoff:** Only the minimum identifiers required for staff notification (School Name, State ID, Visit Date, Start Time, Action Required) are pushed to Google Sheets.
- **Credential isolation:** Service account credentials are excluded from version control via `.gitignore`.

See [SECURITY.md](SECURITY.md) for the full data handling policy.

---

## License

MIT