"""
Sample-selection and coverage diagnostics.

These functions answer the question: "Is the sub-sample of country-years with
AI data representative of the full panel?"  The answer goes into the paper's
sample-selection table.
"""

from __future__ import annotations

import pandas as pd

from ai_productivity.logging import get_logger

log = get_logger(__name__)


def sample_selection_summary(
    df: pd.DataFrame,
    indicator_col: str = "ln_ai",
    compare_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Compare country-years with vs. without AI data on key observables.

    Parameters
    ----------
    df:
        Panel DataFrame (country × year rows, not yet multi-indexed).
    indicator_col:
        The AI variable whose missingness defines in- vs. out-of-sample.
    compare_cols:
        Columns to compare across groups.  Defaults to governance and income
        indicators available in the panel.

    Returns
    -------
    pd.DataFrame
        One row per ``compare_col`` with columns:
        ``variable``, ``in_sample_mean``, ``out_of_sample_mean``,
        ``in_sample_n``, ``out_of_sample_n``.

        DataFrame-level ``.attrs`` carries aggregate counts:
        ``in_sample_rows``, ``out_of_sample_rows``,
        ``in_sample_countries``, ``out_of_sample_countries``.
    """
    compare_cols = compare_cols or ["ln_gdp", "ln_hc", "population", "rule_law", "gov_effect"]
    compare_cols = [c for c in compare_cols if c in df.columns]

    in_sample = df[df[indicator_col].notna()]
    out_sample = df[df[indicator_col].isna()]

    log.info(
        "Sample split on '%s': in=%d rows (%d countries), out=%d rows (%d countries)",
        indicator_col,
        len(in_sample),
        in_sample["country"].nunique() if "country" in in_sample.columns else 0,
        len(out_sample),
        out_sample["country"].nunique() if "country" in out_sample.columns else 0,
    )

    rows = []
    for col in compare_cols:
        in_col = pd.to_numeric(in_sample[col], errors="coerce")
        out_col = pd.to_numeric(out_sample[col], errors="coerce")
        rows.append(
            {
                "variable": col,
                "in_sample_mean": in_col.mean(),
                "out_of_sample_mean": out_col.mean(),
                "in_sample_n": int(in_col.notna().sum()),
                "out_of_sample_n": int(out_col.notna().sum()),
            }
        )

    summary = pd.DataFrame(rows)
    summary.attrs["in_sample_rows"] = int(len(in_sample))
    summary.attrs["out_of_sample_rows"] = int(len(out_sample))
    summary.attrs["in_sample_countries"] = (
        int(in_sample["country"].nunique()) if "country" in in_sample.columns else 0
    )
    summary.attrs["out_of_sample_countries"] = (
        int(out_sample["country"].nunique()) if "country" in out_sample.columns else 0
    )
    return summary
