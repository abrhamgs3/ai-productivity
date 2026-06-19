"""
Panel data validation.

A validation report is a plain dict — no custom classes.  This makes it easy
to serialise to JSON, log, and pass across process boundaries.

Blockers vs. warnings
---------------------
``report_has_blockers`` distinguishes hard failures (missing required columns,
duplicate panel keys) from soft warnings (high missingness in optional columns).
The pipeline aborts on blockers; warnings are logged and continue.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ai_productivity.data.loaders import load_panel
from ai_productivity.logging import get_logger

log = get_logger(__name__)

REQUIRED_COLUMNS: list[str] = ["country", "year", "ln_ai", "ln_tfp", "ln_hc", "ln_gdp"]


def validate_data(
    path: str | Path,
    required_columns: list[str] | None = None,
) -> dict:
    """Run schema and quality checks on the panel CSV.

    Parameters
    ----------
    path:
        Path to the panel CSV.
    required_columns:
        Columns that must be present.  Defaults to ``REQUIRED_COLUMNS``.

    Returns
    -------
    dict
        Validation report with keys: ``path``, ``required_columns``,
        ``missing_columns``, ``duplicate_country_year``,
        ``missing_by_column``, ``log_vars_non_finite``, ``coverage``.
    """
    required_columns = required_columns or REQUIRED_COLUMNS
    log.info("Validating panel at %s", path)

    df = load_panel(path)

    missing_columns = [c for c in required_columns if c not in df.columns]
    if missing_columns:
        log.warning("Required columns missing: %s", missing_columns)

    duplicate_country_year = 0
    if {"country", "year"}.issubset(df.columns):
        duplicate_country_year = int(df.duplicated(["country", "year"]).sum())
        if duplicate_country_year:
            log.warning("Duplicate (country, year) rows: %d", duplicate_country_year)

    missing_by_column = {k: int(v) for k, v in df.isna().sum().to_dict().items()}

    coverage = {
        "countries": int(df["country"].nunique()) if "country" in df.columns else 0,
        "years": int(df["year"].nunique()) if "year" in df.columns else 0,
        "rows": int(len(df)),
    }
    log.info(
        "Coverage: %d countries, %d years, %d rows",
        coverage["countries"], coverage["years"], coverage["rows"],
    )

    log_vars_non_finite: dict[str, int] = {}
    for col in ["ln_ai", "ln_tfp", "ln_hc", "ln_gdp"]:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            non_finite = int((~series.replace([float("inf"), float("-inf")], pd.NA).notna()).sum())
            log_vars_non_finite[col] = non_finite
            if non_finite:
                log.warning("%s has %d non-finite values", col, non_finite)

    report = {
        "path": str(path),
        "required_columns": required_columns,
        "missing_columns": missing_columns,
        "duplicate_country_year": duplicate_country_year,
        "missing_by_column": missing_by_column,
        "log_vars_non_finite": log_vars_non_finite,
        "coverage": coverage,
    }
    log.info("Validation complete — blockers: %s", report_has_blockers(report))
    return report


def report_has_blockers(report: dict) -> bool:
    """Return ``True`` if the validation report contains pipeline-blocking issues."""
    if report.get("missing_columns"):
        return True
    if report.get("duplicate_country_year", 0) > 0:
        return True
    return False


def save_validation_report(report: dict, output_path: str | Path) -> None:
    """Write the validation report to a JSON file.

    Parameters
    ----------
    report:
        Dict returned by :func:`validate_data`.
    output_path:
        Destination path (parent directories are created if needed).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log.debug("Validation report saved to %s", output_path)
