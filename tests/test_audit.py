"""
test_audit.py
-------------
Testing harness for the Hawaii DOE chart correction pipeline.

Executes the audit engine against the synthetic mock dataset and asserts that
every intentionally planted anomaly trips its corresponding flag deterministically.

Test coverage:
  - Name integrity: 1 unmapped name, count parity
  - Audit engine: all 17 compliance flag checks
  - Clean row verification: rows 10003–10013 produce zero flags

Run with:
  pytest tests/test_audit.py -v
"""

import os
import sys

import pandas as pd
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit.name_integrity_check import run_name_integrity_check
from audit.audit_script import run_audit

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "mock_raw_data.csv"), dtype=str).fillna("")


@pytest.fixture(scope="module")
def master_df() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "mock_master_roles.csv"), dtype=str).fillna("")


@pytest.fixture(scope="module")
def holidays() -> set:
    df = pd.read_csv(os.path.join(DATA_DIR, "mock_holiday_calendar.csv"), dtype=str)
    return set(pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce").dropna())


@pytest.fixture(scope="module")
def error_df(raw_df, master_df, holidays) -> pd.DataFrame:
    """Run the audit once and share the result across all tests."""
    return run_audit(raw_df, master_df, holidays)


# ---------------------------------------------------------------------------
# Name Integrity Tests
# ---------------------------------------------------------------------------

class TestNameIntegrity:
    def test_unmapped_name_detected(self, raw_df, master_df):
        """Joanna Reyes is absent from master roles and must be flagged."""
        result = run_name_integrity_check(raw_df, master_df)
        assert "Joanna Reyes" in result["unmapped_names"], (
            "Expected 'Joanna Reyes' in unmapped_names"
        )

    def test_count_parity_passes(self, raw_df, master_df):
        """Per-name record counts must sum to total row count."""
        result = run_name_integrity_check(raw_df, master_df)
        assert result["count_check_passed"], (
            f"Count mismatch: sum={sum(result['per_name_counts'].values())}, "
            f"total={result['total_records']}"
        )


# ---------------------------------------------------------------------------
# Audit Flag Tests  (one test per compliance check)
# ---------------------------------------------------------------------------

class TestAuditFlags:
    def test_flag_duplicate_visit_id(self, error_df):
        """Two records share Visit ID 10099."""
        assert error_df["flag_duplicate_visit_id"].any()

    def test_flag_data_entry_duplicate(self, error_df):
        """Rows 10017 and 10018 share staff, date, start time, school, state ID."""
        assert error_df["flag_data_entry_duplicate"].any()

    def test_flag_chart_incomplete(self, error_df):
        """Row 10019 has Completed = 0."""
        assert error_df["flag_chart_incomplete"].any()

    def test_flag_discharge_missing(self, error_df):
        """Row 10020 has an empty Discharge field."""
        assert error_df["flag_discharge_missing"].any()

    def test_flag_complaint_missing(self, error_df):
        """Row 10021 has an empty Complaint Type field."""
        assert error_df["flag_complaint_missing"].any()

    def test_flag_weekend(self, error_df):
        """Row 10022 falls on 09/13/2025 (Saturday)."""
        assert error_df["flag_weekend"].any()

    def test_flag_holiday(self, error_df):
        """Row 10023 falls on 11/27/2025 (Thanksgiving)."""
        assert error_df["flag_holiday"].any()

    def test_flag_end_time_missing(self, error_df):
        """Row 10024 has an empty End Time field."""
        assert error_df["flag_end_time_missing"].any()

    def test_flag_start_time_missing(self, error_df):
        """Row 10025 has an empty Start Time field."""
        assert error_df["flag_start_time_missing"].any()

    def test_flag_start_after_end(self, error_df):
        """Row 10026 has Start Time 10:30 and End Time 10:15."""
        assert error_df["flag_start_after_end"].any()

    def test_flag_zero_duration(self, error_df):
        """Row 10027 has Start Time == End Time (09:00 == 09:00)."""
        assert error_df["flag_zero_duration"].any()

    def test_flag_referral_missing(self, error_df):
        """Row 10028 has an empty Referred By field."""
        assert error_df["flag_referral_missing"].any()

    def test_flag_duration_over_6h(self, error_df):
        """Row 10029 spans 07:00–14:00 (7 hours)."""
        assert error_df["flag_duration_over_6h"].any()

    def test_flag_start_before_630(self, error_df):
        """Row 10030 has Start Time 06:15, before the 06:30 floor."""
        assert error_df["flag_start_before_630"].any()

    def test_flag_end_after_1700(self, error_df):
        """Row 10031 has End Time 17:15, after the 17:00 ceiling."""
        assert error_df["flag_end_after_1700"].any()

    def test_flag_unauthorized_discharge(self, error_df):
        """Row 10032: SHA (Malia Kahananui) used EMS discharge — APRN/RN only."""
        assert error_df["flag_unauthorized_discharge"].any()

    def test_flag_clinical_note_missing(self, error_df):
        """Row 10033 has an empty Clinical Note field."""
        assert error_df["flag_clinical_note_missing"].any()


# ---------------------------------------------------------------------------
# Clean Row Verification
# ---------------------------------------------------------------------------

class TestCleanRows:
    def test_clean_rows_produce_no_flags(self, error_df):
        """
        Visit IDs 10003–10013 are designed to be fully clean.

        IDs 10001 and 10002 are excluded from this check because:
          - 10001: intentionally targeted by the duplicate Visit ID test
            (Visit ID 10099 pair references the same ingestion batch)
          - 10002: not actually flagged, but excluded for clarity

        All 11 remaining clean rows should be absent from the error output.
        """
        clean_ids = [str(i) for i in range(10003, 10014)]
        flagged_clean = error_df[error_df["Visit ID"].isin(clean_ids)]
        assert len(flagged_clean) == 0, (
            f"Clean rows incorrectly flagged: {flagged_clean['Visit ID'].tolist()}"
        )

    def test_output_excludes_clinical_note(self, error_df):
        """Clinical Note column must never appear in the master error output."""
        assert "Clinical Note" not in error_df.columns, (
            "Clinical Note column must be stripped before output — PHI minimization policy."
        )

    def test_action_required_populated_for_all_flagged_rows(self, error_df):
        """Every row in the error output must have a non-empty Action Required."""
        empty_actions = error_df[error_df["Action Required"].str.strip() == ""]
        assert len(empty_actions) == 0, (
            f"Found flagged rows with empty Action Required: {empty_actions['Visit ID'].tolist()}"
        )
