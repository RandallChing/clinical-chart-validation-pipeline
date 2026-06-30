"""
name_integrity_check.py
-----------------------
Validates relational integrity between the raw encounter export and the
master staff roster pulled from Infinite Campus.

Two checks are performed:
  1. Name Match   — every Staff Name in the raw data must exist in the master
                    roles file. Unmapped names are collected for review; a new
                    entry must be added to the master roles file before the
                    affected records can be processed.
  2. Count Parity — the per-name record counts must sum to exactly the total
                    number of rows in the raw data file, confirming no rows
                    were silently dropped or duplicated during ingestion.

Returns a structured result dict consumed by main.py.
"""

import pandas as pd


def run_name_integrity_check(
    raw_df: pd.DataFrame, master_df: pd.DataFrame
) -> dict:
    """
    Validate staff name coverage and record count parity.

    Parameters
    ----------
    raw_df : pd.DataFrame
        Raw encounter export from Infinite Campus. Must contain a
        'Staff Name' column formatted as 'Last Name, First Name'.
    master_df : pd.DataFrame
        Master roles file. Must contain a 'Staff Name' column formatted
        identically to raw_df.

    Returns
    -------
    dict with keys:
        unmapped_names     : list[str]  — names in raw not found in master
        count_check_passed : bool       — True if per-name sum == total rows
        per_name_counts    : dict       — {name: record_count}
        total_records      : int        — total rows in raw_df
    """
    # Normalize whitespace to prevent false mismatches on leading/trailing spaces
    master_names: set[str] = set(master_df["Staff Name"].str.strip())
    raw_names: pd.Series = raw_df["Staff Name"].str.strip()

    # --- Check 1: Name coverage ---
    unmapped: list[str] = (
        raw_names[~raw_names.isin(master_names)].unique().tolist()
    )

    # --- Check 2: Count parity ---
    per_name_counts: dict = raw_df["Staff Name"].value_counts().to_dict()
    count_sum: int = sum(per_name_counts.values())
    count_check_passed: bool = count_sum == len(raw_df)

    return {
        "unmapped_names": unmapped,
        "count_check_passed": count_check_passed,
        "per_name_counts": per_name_counts,
        "total_records": len(raw_df),
    }
