# Runbook — Hawaii DOE Chart Correction Pipeline

**System:** Weekly data integrity audit and staff notification pipeline  
**Owner:** Clinical Systems team  
**Last Updated:** June 2026

This runbook is written for the engineer inheriting this system. It covers
setup, weekly operations, common failure modes, and how to extend the pipeline
when the organization changes.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Prerequisites](#2-prerequisites)
3. [Local Setup](#3-local-setup)
4. [Google Cloud Setup](#4-google-cloud-setup)
5. [Google Apps Script Setup](#5-google-apps-script-setup)
6. [Running the Pipeline](#6-running-the-pipeline)
7. [Weekly Operations Checklist](#7-weekly-operations-checklist)
8. [Understanding Error Flags](#8-understanding-error-flags)
9. [Maintaining Reference Data](#9-maintaining-reference-data)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. System Overview

The pipeline runs once per week and performs three jobs:

1. **Audit** — Ingests a raw encounter export from Infinite Campus,
   validates every record against 17 compliance rules, and produces a
   master error file listing every flagged chart.

2. **Distribute** — Pushes the master error file to a Google Sheet via
   the Sheets API.

3. **Notify** — A Google Apps Script triggers every Tuesday at 7:00 AM,
   reads the sheet, and sends each clinical staff member a personalized
   email listing only their flagged records.

**Data flow:**
```
Infinite Campus export (manual download)
        ↓
   main.py (Python)
        ├── name_integrity_check.py
        └── audit_script.py
              ↓
      output/master_error_file.csv  ←—— local copy
              ↓
       Google Sheets (via gspread)
              ↓
       Code.gs (Apps Script, Tuesday 7 AM)
              ↓
       Staff email inboxes
```

---

## 2. Prerequisites

- Python 3.10 or later
- A Google account with access to Google Cloud Console
- Editor access to the target Google Sheet
- The repository cloned locally

---

## 3. Local Setup

```bash
# Clone the repository
git clone https://github.com/RandallChing/csv-validation-pipeline.git
cd csv-validation-pipeline

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Verify the test harness runs cleanly against the mock data
pytest tests/test_audit.py -v
```

All 20 tests should pass before you run the pipeline against live data.

---

## 4. Google Cloud Setup

This pipeline authenticates to Google Sheets using a service account.
Follow these steps once per environment:

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or use an existing one).
3. Enable the **Google Sheets API** for the project.
4. Navigate to **IAM & Admin → Service Accounts → Create Service Account**.
5. Name it (e.g., `chart-correction-pipeline`) and click Create.
6. Click the service account → **Keys → Add Key → Create new key → JSON**.
7. Download the JSON key file and rename it `credentials.json`.
8. Place `credentials.json` in the project root directory.
   - **Confirm it is listed in `.gitignore` before committing anything.**
9. Open the target Google Sheet.
10. Click **Share** and add the service account email
    (visible in the JSON file as `"client_email"`) with **Editor** access.
11. Update `GOOGLE_SHEET_ID` in `main.py` with your sheet's ID.
    - The sheet ID is the long alphanumeric string in the sheet URL:
      `https://docs.google.com/spreadsheets/d/`**`SHEET_ID`**`/edit`

---

## 5. Google Apps Script Setup

1. Open the target Google Sheet.
2. Click **Extensions → Apps Script**.
3. Delete any placeholder code in `Code.gs`.
4. Copy the contents of `apps_script/Code.gs` from this repository
   and paste it into the Apps Script editor.
5. Update `SHEET_ID`, `TAB_NAME`, and `GUIDE_URL` in the configuration
   block at the top of the file.
6. Click **Save**.
7. Click **Triggers (clock icon) → Add Trigger**:
   - Function: `sendCorrectionEmails`
   - Deployment: Head
   - Event source: Time-driven
   - Type: Week timer
   - Day: Every Tuesday
   - Time: 7:00 AM – 8:00 AM
   - Failure notification: Immediately
8. Authorize the trigger when prompted.
   The script requires Gmail send permission and Sheets read permission.

---

## 6. Running the Pipeline

**Standard run (uses mock data):**
```bash
python main.py
```

**Live run (pass in the Infinite Campus export):**
```bash
python main.py --raw-data "path/to/infinite_campus_export.csv"
```

The pipeline will:
- Print a name integrity report to the terminal.
- Print a summary of flagged record counts.
- Write `output/master_error_file.csv`.
- Push to Google Sheets (if `credentials.json` is present).

The Apps Script then runs automatically the following Tuesday at 7:00 AM.

---

## 7. Weekly Operations Checklist

| Step | When | Action |
|---|---|---|
| Download IC export | Monday afternoon | Run the Infinite Campus SQL report. Save as CSV. |
| Run pipeline | Monday evening | `python main.py --raw-data <path>` |
| Verify sheet | Monday evening | Open Google Sheet. Confirm row count matches terminal output. |
| Confirm emails | Tuesday 7:00–8:00 AM | Check Apps Script execution log for send confirmations. |
| Handle bounces | Tuesday morning | Investigate any email delivery failures in Apps Script logs. |

---

## 8. Understanding Error Flags

| Flag | Meaning | How to Fix in Infinite Campus |
|---|---|---|
| Duplicate Visit ID | Two records share the same Visit ID | Investigate both records; delete the erroneous duplicate |
| Possible Duplicate Office Visit | Same staff, date, start time, school, student | Verify if it was a genuine second visit; delete if not |
| Chart Marked Incomplete | Completed = 0 | Open record and mark as complete |
| Discharge Type Missing | No discharge selected | Open record and select appropriate discharge |
| Complaint Type Missing | No complaint selected | Open record and select appropriate complaint |
| Visit Date is on a Weekend | Date falls Saturday or Sunday | Verify date entry; correct if typo |
| Visit Date is on a Holiday | Date matches school holiday calendar | Verify date entry; correct if typo |
| Discharge Time Missing | End Time field is blank | Enter the time the student was released |
| Start Time Missing | Start Time field is blank | Enter the time the student arrived |
| Start Time After Discharge Time | Start time is later than end time | Correct one or both time entries |
| Visit Duration is Zero Minutes | Start time equals end time | Correct end time; visits must be at least 1 minute |
| Referral Source Missing | Referred By field is blank | Enter how the student was routed to the health office |
| Visit Duration Exceeds 6 Hours | End time – Start time > 6 hours | Verify; correct if entry error |
| Start Time Before 6:30 AM | Start time before 06:30 | Verify; correct if entry error |
| Discharge Time After 5:00 PM | End time after 17:00 | Verify; correct if entry error |
| Unauthorized Discharge Type for Role | SHA/HT used APRN/RN-only discharge | Correct discharge to an authorized type, or escalate to RN |
| Clinical Note Missing | Clinical Note field is blank | Open record and add a documentation note |

---

## 9. Maintaining Reference Data

### Adding a new staff member
1. Open `data/mock_master_roles.csv` (or the live roles file).
2. Add a new row: `Last Name, First Name,email@hawaiidoe.edu,ROLE`
3. Valid roles: `APRN`, `RN`, `HT`, `SHA`, `Admin`
4. Ensure name formatting matches Infinite Campus exactly
   (Last Name, First Name — with comma and space).

### Updating the holiday calendar
1. Open `data/mock_holiday_calendar.csv` (or the live calendar file).
2. Add or remove rows. Date format must be `MM/DD/YYYY`.
3. Sources: [Hawaii DOE School Calendar](https://www.hawaiipublicschools.org),
   federal holiday schedule.

---

## 10. Troubleshooting

**`ModuleNotFoundError: No module named 'gspread'`**
→ Run `pip install -r requirements.txt` inside your virtual environment.

**`FileNotFoundError: credentials.json not found`**
→ Pipeline will still run locally. Sheets push is skipped. See § 4 for setup.

**`KeyError` on column name during audit**
→ The column names in your IC export differ from the expected schema.
  Compare your CSV headers to the field list in `audit/audit_script.py`
  and update the column references to match.

**Apps Script sends no emails**
→ Check the Apps Script execution log (View → Executions).
  Common causes: sheet is empty, `SHEET_ID` is wrong, trigger not authorized.

**Staff report receiving emails for records they already fixed**
→ The pipeline data window is set by when you download the IC export.
  If staff fixed records before the Monday evening pull, those records
  will not be in the report. If corrections happen after the pull,
  they will still appear this week and should resolve next cycle.
