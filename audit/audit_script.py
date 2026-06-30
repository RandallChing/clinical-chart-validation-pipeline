"""
audit_script.py
---------------
Core validation engine for the Hawaii DOE chart correction pipeline.

Runs 17 compliance checks against the raw encounter export using vectorized
pandas operations. Each check produces a boolean flag column. Any record
triggering at least one flag is written to the master error file and queued
for staff notification.

Role-Based Permission Model
---------------------------
Discharge types carry clinical authority constraints that mirror scope-of-
practice boundaries for each staff tier:

  APRN / RN only:
    - Transferred to Emergency Medical Services (EMS)
    - Referred to Primary Care Provider (PCP)
    - Referred to Mental Health Professional
    - Administered Prescribed Medication & Released

  Admin / APRN / RN only  (SHA and HT excluded):
    - Scheduled Follow-up Audit

All other discharge types (Return to Class, Released to Parent/Guardian)
are available to all roles.

PHI Handling
------------
The 'Clinical Note' column is evaluated exclusively for null / empty status.
Note text is never transmitted to any external service, API, or cloud layer.
The column is stripped from the master error output before Google Sheets push.
"""

import pandas as pd


# ---------------------------------------------------------------------------
# Role-permission constants
# ---------------------------------------------------------------------------

_APRN_RN_ONLY_DISCHARGE: frozenset[str] = frozenset(
    {
        "Transferred to Emergency Medical Services (EMS)",
        "Referred to Primary Care Provider (PCP)",
        "Referred to Mental Health Professional",
        "Administered Prescribed Medication & Released",
    }
)

_ADMIN_APRN_RN_ONLY_DISCHARGE: frozenset[str] = frozenset(
    {"Scheduled Follow-up Audit"}
)

# SHA and HT are restricted from all of the above
_SHA_HT_RESTRICTED_DISCHARGE: frozenset[str] = (
    _APRN_RN_ONLY_DISCHARGE | _ADMIN_APRN_RN_ONLY_DISCHARGE
)

# ---------------------------------------------------------------------------
# Human-readable action messages keyed by flag column name
# ---------------------------------------------------------------------------

FLAG_MESSAGES: dict[str, str] = {
    "flag_duplicate_visit_id":      "Duplicate Visit ID",
    "flag_data_entry_duplicate":    "Possible Duplicate Office Visit",
    "flag_chart_incomplete":        "Chart Marked Incomplete",
    "flag_discharge_missing":       "Discharge Type Missing",
    "flag_complaint_missing":       "Complaint Type Missing",
    "flag_weekend":                 "Visit Date is on a Weekend",
    "flag_holiday":                 "Visit Date is on a Holiday",
    "flag_end_time_missing":        "Discharge Time Missing",
    "flag_start_time_missing":      "Start Time Missing",
    "flag_start_after_end":         "Start Time After Discharge Time",
    "flag_zero_duration":           "Visit Duration is Zero Minutes",
    "flag_referral_missing":        "Referral Source Missing",
    "flag_duration_over_6h":        "Visit Duration Exceeds 6 Hours",
    "flag_start_before_630":        "Start Time Before 6:30 AM",
    "flag_end_after_1700":          "Discharge Time After 5:00 PM",
    "flag_unauthorized_discharge":  "Unauthorized Discharge Type for Role",
    "flag_clinical_note_missing":   "Clinical Note Missing",
}

FLAG_COLS: list[str] = list(FLAG_MESSAGES.keys())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_audit(
    raw_df: pd.DataFrame,
    master_df: pd.DataFrame,
    holiday_dates: set,
) -> pd.DataFrame:
    """
    Execute all 17 compliance checks and return the master error dataframe.

    Parameters
    ----------
    raw_df : pd.DataFrame
        Raw encounter export from Infinite Campus. All columns are read as
        strings; type coercion happens internally.
    master_df : pd.DataFrame
        Master roles file with columns: Staff Name, Email, Role.
    holiday_dates : set[pd.Timestamp]
        Set of holiday dates parsed from the holiday calendar CSV.

    Returns
    -------
    pd.DataFrame
        Subset of raw_df containing only flagged records, augmented with:
          - Email and Role columns (joined from master_df)
          - One boolean flag column per check
          - An 'Action Required' column with semicolon-delimited messages
        The 'Clinical Note' column is excluded from the output.
    """
    df = raw_df.copy()

    # ------------------------------------------------------------------
    # Pre-processing: join email + role from master roles
    # ------------------------------------------------------------------
    master_lookup: dict = (
        master_df.set_index("Staff Name")[["Email", "Role"]]
        .to_dict("index")
    )
    df["Email"] = df["Staff Name"].map(
        lambda x: master_lookup.get(x, {}).get("Email", "UNKNOWN")
    )
    df["Role"] = df["Staff Name"].map(
        lambda x: master_lookup.get(x, {}).get("Role", "UNKNOWN")
    )

    # ------------------------------------------------------------------
    # Parse dates and times
    # ------------------------------------------------------------------
    df["_visit_date"] = pd.to_datetime(
        df["Visit Date"], format="%m/%d/%Y", errors="coerce"
    )
    _base = "2000-01-01 "  # dummy date for time-only arithmetic
    df["_start_dt"] = pd.to_datetime(
        _base + df["Start Time"].where(df["Start Time"].str.strip() != "", other=pd.NA),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )
    df["_end_dt"] = pd.to_datetime(
        _base + df["End Time"].where(df["End Time"].str.strip() != "", other=pd.NA),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )

    # ------------------------------------------------------------------
    # FLAG 1: Duplicate Visit ID
    # ------------------------------------------------------------------
    df["flag_duplicate_visit_id"] = df.duplicated(subset=["Visit ID"], keep=False)

    # ------------------------------------------------------------------
    # FLAG 2: Data Entry Duplicate
    # Same staff name, visit date, start time, school, and state ID
    # is a strong signal of a double-charted visit.
    # ------------------------------------------------------------------
    _dup_cols = ["Staff Name", "Visit Date", "Start Time", "School Name", "State ID"]
    df["flag_data_entry_duplicate"] = df.duplicated(subset=_dup_cols, keep=False)

    # ------------------------------------------------------------------
    # FLAG 3: Chart Marked Incomplete (Completed == 0)
    # ------------------------------------------------------------------
    df["flag_chart_incomplete"] = df["Completed"].str.strip() == "0"

    # ------------------------------------------------------------------
    # FLAG 4: Discharge Type Missing
    # ------------------------------------------------------------------
    df["flag_discharge_missing"] = (
        df["Discharge"].isna() | (df["Discharge"].str.strip() == "")
    )

    # ------------------------------------------------------------------
    # FLAG 5: Complaint Type Missing
    # ------------------------------------------------------------------
    df["flag_complaint_missing"] = (
        df["Complaint Type"].isna() | (df["Complaint Type"].str.strip() == "")
    )

    # ------------------------------------------------------------------
    # FLAG 6: Visit on Weekend
    # ------------------------------------------------------------------
    df["flag_weekend"] = df["_visit_date"].dt.dayofweek >= 5  # 5=Sat, 6=Sun

    # ------------------------------------------------------------------
    # FLAG 7: Visit on Holiday
    # ------------------------------------------------------------------
    df["flag_holiday"] = df["_visit_date"].isin(holiday_dates)

    # ------------------------------------------------------------------
    # FLAG 8: Discharge Time (End Time) Missing
    # ------------------------------------------------------------------
    df["flag_end_time_missing"] = (
        df["End Time"].isna() | (df["End Time"].str.strip() == "")
    )

    # ------------------------------------------------------------------
    # FLAG 9: Start Time Missing
    # ------------------------------------------------------------------
    df["flag_start_time_missing"] = (
        df["Start Time"].isna() | (df["Start Time"].str.strip() == "")
    )

    # ------------------------------------------------------------------
    # FLAG 10: Start Time After Discharge Time
    # ------------------------------------------------------------------
    df["flag_start_after_end"] = (
        df["_start_dt"].notna()
        & df["_end_dt"].notna()
        & (df["_start_dt"] > df["_end_dt"])
    )

    # ------------------------------------------------------------------
    # FLAG 11: Zero Duration (Start Time == Discharge Time)
    # ------------------------------------------------------------------
    df["flag_zero_duration"] = (
        df["_start_dt"].notna()
        & df["_end_dt"].notna()
        & (df["_start_dt"] == df["_end_dt"])
    )

    # ------------------------------------------------------------------
    # FLAG 12: Referral Source Missing
    # ------------------------------------------------------------------
    df["flag_referral_missing"] = (
        df["Referred By"].isna() | (df["Referred By"].str.strip() == "")
    )

    # ------------------------------------------------------------------
    # FLAG 13: Visit Duration Exceeds 6 Hours
    # ------------------------------------------------------------------
    df["_duration_hrs"] = (
        (df["_end_dt"] - df["_start_dt"]).dt.total_seconds() / 3600
    )
    df["flag_duration_over_6h"] = df["_duration_hrs"] > 6

    # ------------------------------------------------------------------
    # FLAG 14: Start Time Before 6:30 AM
    # ------------------------------------------------------------------
    _cutoff_start = pd.Timestamp("2000-01-01 06:30")
    df["flag_start_before_630"] = df["_start_dt"].notna() & (
        df["_start_dt"] < _cutoff_start
    )

    # ------------------------------------------------------------------
    # FLAG 15: Discharge Time After 5:00 PM
    # ------------------------------------------------------------------
    _cutoff_end = pd.Timestamp("2000-01-01 17:00")
    df["flag_end_after_1700"] = df["_end_dt"].notna() & (
        df["_end_dt"] > _cutoff_end
    )

    # ------------------------------------------------------------------
    # FLAG 16: Unauthorized Discharge Type for Role
    # SHA and HT may not use APRN/RN-only or Admin/APRN/RN-only discharges.
    # ------------------------------------------------------------------
    def _is_unauthorized_discharge(row: pd.Series) -> bool:
        role = row["Role"]
        discharge = row["Discharge"] if pd.notna(row["Discharge"]) else ""
        return role in ("SHA", "HT") and discharge in _SHA_HT_RESTRICTED_DISCHARGE

    df["flag_unauthorized_discharge"] = df.apply(
        _is_unauthorized_discharge, axis=1
    )

    # ------------------------------------------------------------------
    # FLAG 17: Clinical Note Missing or Empty
    # Note: text content is never read, only null/length evaluated.
    # ------------------------------------------------------------------
    df["flag_clinical_note_missing"] = (
        df["Clinical Note"].isna() | (df["Clinical Note"].str.strip() == "")
    )

    # ------------------------------------------------------------------
    # Build Action Required column
    # ------------------------------------------------------------------
    def _build_action_required(row: pd.Series) -> str:
        messages = [
            msg for col, msg in FLAG_MESSAGES.items() if row[col]
        ]
        return "; ".join(messages) if messages else ""

    df["Action Required"] = df.apply(_build_action_required, axis=1)

    # ------------------------------------------------------------------
    # Filter to flagged rows only
    # ------------------------------------------------------------------
    any_flag = df[FLAG_COLS].any(axis=1)
    error_df = df[any_flag].copy()

    # ------------------------------------------------------------------
    # Build output: drop internal parse columns and clinical note text
    # ------------------------------------------------------------------
    output_cols = (
        [
            "Visit ID", "Visit Date", "Staff Name", "Email", "Role",
            "Referred By", "Completed", "Complaint Type", "Discharge",
            "Start Time", "End Time", "School Name", "State ID",
        ]
        + FLAG_COLS
        + ["Action Required"]
    )
    return error_df[output_cols].reset_index(drop=True)
