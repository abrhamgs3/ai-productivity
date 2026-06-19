"""
Panel data loading utilities.

Responsibilities
----------------
- Read the processed panel CSV into a sorted DataFrame.
- Remove World Bank aggregate entities and non-sovereign territories so the
  panel contains actual countries only.

These functions are intentionally stateless and side-effect free: they receive
a path and return a DataFrame.  Downstream steps decide what to do with it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ai_productivity.exceptions import DataValidationError
from ai_productivity.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Exclusion lists
# ---------------------------------------------------------------------------

AGGREGATE_ENTITIES: list[str] = [
    "Africa Eastern and Southern", "Africa Western and Central", "Arab World",
    "Caribbean small states", "Central Europe and the Baltics",
    "Early-demographic dividend", "East Asia & Pacific",
    "East Asia & Pacific (IDA & IBRD countries)",
    "East Asia & Pacific (excluding high income)",
    "Euro area", "Europe & Central Asia",
    "Europe & Central Asia (IDA & IBRD countries)",
    "Europe & Central Asia (excluding high income)", "European Union",
    "Fragile and conflict affected situations",
    "Heavily indebted poor countries (HIPC)",
    "High income", "IBRD only", "IDA & IBRD total", "IDA blend", "IDA only",
    "IDA total", "Late-demographic dividend", "Latin America & Caribbean",
    "Latin America & Caribbean (excluding high income)",
    "Latin America & the Caribbean (IDA & IBRD countries)",
    "Least developed countries: UN classification",
    "Low & middle income", "Low income", "Lower middle income",
    "Middle East, North Africa, Afghanistan & Pakistan",
    "Middle East, North Africa, Afghanistan & Pakistan (IDA & IBRD)",
    "Middle East, North Africa, Afghanistan & Pakistan (excluding high income)",
    "Middle income", "North America", "Not classified", "OECD members",
    "Other small states", "Pacific island small states",
    "Post-demographic dividend", "Pre-demographic dividend",
    "Small states", "South Asia", "South Asia (IDA & IBRD)",
    "Sub-Saharan Africa", "Sub-Saharan Africa (IDA & IBRD countries)",
    "Sub-Saharan Africa (excluding high income)", "Upper middle income", "World",
]

NON_SOVEREIGN_ENTITIES: list[str] = [
    "American Samoa", "Aruba", "Bermuda", "British Virgin Islands",
    "Cayman Islands", "Channel Islands", "Curacao", "Faroe Islands",
    "French Polynesia", "Gibraltar", "Greenland", "Guam",
    "Hong Kong SAR, China", "Isle of Man", "Kosovo", "Macao SAR, China",
    "New Caledonia", "Northern Mariana Islands", "Puerto Rico (US)",
    "Sint Maarten (Dutch part)", "St. Martin (French part)",
    "Turks and Caicos Islands", "Virgin Islands (U.S.)", "West Bank and Gaza",
]

_EXCLUDED: frozenset[str] = frozenset(AGGREGATE_ENTITIES + NON_SOVEREIGN_ENTITIES)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_panel(path: str | Path) -> pd.DataFrame:
    """Load the processed panel CSV and return a sorted DataFrame.

    Parameters
    ----------
    path:
        Path to the panel CSV (typically ``data/processed/panel_clean.csv``).

    Returns
    -------
    pd.DataFrame
        Sorted by ``["country", "year"]`` with a clean integer index.

    Raises
    ------
    DataValidationError
        If the file does not exist or cannot be parsed.
    """
    path = Path(path)
    if not path.exists():
        raise DataValidationError(
            f"Panel file not found: {path}. "
            "Run scripts/02_clean_data.py to generate it."
        )

    log.info("Loading panel from %s", path)
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise DataValidationError(f"Cannot read {path}: {exc}") from exc

    if {"country", "year"}.issubset(df.columns):
        df = df.sort_values(["country", "year"]).reset_index(drop=True)

    log.info(
        "Panel loaded: %d rows, %d countries, %d years",
        len(df),
        df["country"].nunique() if "country" in df.columns else 0,
        df["year"].nunique() if "year" in df.columns else 0,
    )
    return df


def drop_aggregate_entities(df: pd.DataFrame) -> pd.DataFrame:
    """Remove World Bank aggregates and non-sovereign territories.

    Parameters
    ----------
    df:
        DataFrame with a ``country`` column.

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame with a clean integer index.
    """
    if "country" not in df.columns:
        log.warning("drop_aggregate_entities: no 'country' column found — returning unchanged")
        return df

    before = len(df)
    df = df[~df["country"].isin(_EXCLUDED)].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        log.debug("Dropped %d aggregate/non-sovereign rows", dropped)
    return df
