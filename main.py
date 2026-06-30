"""
main.py
-------
Pipeline orchestrator for the Hawaii DOE chart correction system.

Execution sequence:
  1. Load raw encounter export CSV, master roles CSV, and holiday calendar.
  2. Run name integrity check — report unmapped staff names.
  3. Run audit script — apply all 17 compliance checks.
  4. Write master error file to output/ directory.
  5. Push master error file to Google Sheets (if credentials.json is present).

Usage
-----
  python main.py --raw-data data/mock_raw_data.csv

The --raw-data argument allows you to swap in the live Infinite Campus export
without modifying any source files. All other paths (master roles, holiday
calendar, credentials) are resolved relative to the project root.

Google Sheets Integration
--------------------------
Authentication uses a Google Cloud service account. Place credentials.json
in the project root (it is excluded from version control via .gitignore).
See RUNBOOK.md § "Google Cloud Setup" for step-by-step credential generation.

If credentials.json is not present, the pipeline still runs locally and
writes the master error file to output/master_error_file.csv.
"""

import argparse
import os
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# Optional Google Sheets dependencies — gracefully degrade if not installed
# ---------------------------------------------------------------------------
try:
    import gspread
    from google.oauth2.service_account import Credentials as GCredentials
    GSHEETS_AVAILABLE = True
except ImportError:
    GSHEETS_AVAILABLE = False

from audit.name_integrity_check import run_name_integrity_check
from audit.audit_script import run_audit

# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
CREDENTIALS_FILE = os.path.join(ROOT_DIR, "credentials.json")

MASTER_ROLES_PATH = os.path.join(DATA_DIR, "mock_master_roles.csv")
HOLIDAY_CALENDAR_PATH = os.path.join(DATA_DIR, "mock_holiday_calendar.csv")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "master_error_file.csv")

# ---------------------------------------------------------------------------
# Google Sheets configuration — replace before live deployment
# ---------------------------------------------------------------------------
GOOGLE_SHEET_ID = "YOUR_GOOGLE_SHEET_ID_HERE"
GOOGLE_SHEET_TAB = "MasterErrorFile"
GSHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_holidays(path: str) -> set:
    """Parse MM/DD/YYYY holiday dates into a set of pd.Timestamps."""
    df = pd.read_csv(path, dtype=str)
    return set(pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce").dropna())


def push_to_google_sheets(df: pd.DataFrame) -> None:
    """Overwrite the target Google Sheet tab with the master error dataframe."""
    if not GSHEETS_AVAILABLE:
        print(
            "[WARNING] gspread / google-auth not installed. "
            "Run `pip install -r requirements.txt` to enable Sheets push."
        )
        return

    creds = GCredentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=GSHEETS_SCOPES
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_SHEET_TAB)
    sheet.clear()

    # Convert to list-of-lists for gspread bulk update
    rows = [df.columns.tolist()] + df.astype(str).values.tolist()
    sheet.update(rows)
    print(f"[INFO] Pushed {len(df)} flagged records to Google Sheets tab '{GOOGLE_SHEET_TAB}'.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(raw_data_path: str) -> None:
    # --- Load ---
    print(f"[INFO] Loading raw data from: {raw_data_path}")
    raw_df = pd.read_csv(raw_data_path, dtype=str).fillna("")

    print(f"[INFO] Loading master roles from: {MASTER_ROLES_PATH}")
    master_df = pd.read_csv(MASTER_ROLES_PATH, dtype=str).fillna("")

    print(f"[INFO] Loading holiday calendar from: {HOLIDAY_CALENDAR_PATH}")
    holidays = load_holidays(HOLIDAY_CALENDAR_PATH)

    # --- Name Integrity Check ---
    print("\n[STEP 1] Running name integrity check...")
    integrity = run_name_integrity_check(raw_df, master_df)

    if integrity["unmapped_names"]:
        print(
            f"  [WARNING] {len(integrity['unmapped_names'])} unmapped staff name(s) found:\n"
            + "\n".join(f"    - {n}" for n in integrity["unmapped_names"])
        )
        print("  Action: Add missing entries to mock_master_roles.csv before re-running.")
    else:
        print("  [PASS] All staff names matched to master roles.")

    if integrity["count_check_passed"]:
        print(f"  [PASS] Record count verified: {integrity['total_records']} rows.")
    else:
        print(
            f"  [ERROR] Record count mismatch. "
            f"Expected {integrity['total_records']}, "
            f"got {sum(integrity['per_name_counts'].values())}."
        )

    # --- Audit ---
    print("\n[STEP 2] Running compliance audit...")
    error_df = run_audit(raw_df, master_df, holidays)
    print(f"  [INFO] Audit complete: {len(error_df)} record(s) flagged out of {len(raw_df)} total.")

    # --- Write master error file ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    error_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n[STEP 3] Master error file written to: {OUTPUT_PATH}")

    # --- Push to Google Sheets ---
    if os.path.exists(CREDENTIALS_FILE):
        print("\n[STEP 4] Pushing to Google Sheets...")
        push_to_google_sheets(error_df)
    else:
        print(
            "\n[STEP 4] credentials.json not found — skipping Google Sheets push.\n"
            "         See RUNBOOK.md § 'Google Cloud Setup' for credential instructions."
        )

    print("\n[DONE] Pipeline complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hawaii DOE Chart Correction Pipeline"
    )
    parser.add_argument(
        "--raw-data",
        default=os.path.join(DATA_DIR, "mock_raw_data.csv"),
        help="Path to the raw encounter export CSV (default: data/mock_raw_data.csv)",
    )
    args = parser.parse_args()
    main(args.raw_data)
