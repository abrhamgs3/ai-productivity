"""
Feature engineering for the AI & Productivity panel.

This module transforms raw merged data into model-ready variables:
- Log transformations (ln_gdp, ln_ai, ln_tfp, ln_hc)
- Sub-indices for falsification tests (digital_infra_index, innovation_index)

Why a dedicated module?
-----------------------
Keeping transformations here — rather than scattered across notebooks and
scripts — means every pipeline run applies identical feature definitions.
If you change a transform, you change it in one place.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_productivity.exceptions import DataValidationError
from ai_productivity.logging import get_logger

log = get_logger(__name__)

# Columns that form the digital-infrastructure sub-index
_DIGITAL_COLS = ["internet_users", "mobile_subs", "secure_servers"]

# Columns that form the innovation sub-index
_INNOVATION_COLS = ["pat_res", "pat_nres", "ip_receipts"]


def add_log_transforms(df: pd.DataFrame) -> pd.DataFrame:
    """Add log-transformed versions of the four main economic variables.

    Parameters
    ----------
    df:
        Raw/merged panel DataFrame.  Must contain ``gdp_pc``, ``AI_index``,
        ``tfp``, ``hc``.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with four new columns:
        ``ln_gdp``, ``ln_ai``, ``ln_tfp``, ``ln_hc``.
    """
    df = df.copy()
    mapping = {
        "ln_gdp": "gdp_pc",
        "ln_ai":  "AI_index",
        "ln_tfp": "tfp",
        "ln_hc":  "hc",
    }
    for log_col, raw_col in mapping.items():
        if raw_col not in df.columns:
            log.warning("Column '%s' not found — '%s' will be all NaN", raw_col, log_col)
            df[log_col] = np.nan
        else:
            df[log_col] = np.log(df[raw_col])
            n_nan = df[log_col].isna().sum()
            log.debug("  %s: %d non-null values, %d NaN", log_col, len(df) - n_nan, n_nan)

    log.info("Log transforms added: ln_gdp, ln_ai, ln_tfp, ln_hc")
    return df


def add_sub_indices(df: pd.DataFrame) -> pd.DataFrame:
    """Add digital-infrastructure and innovation sub-indices.

    Each sub-index is the row-wise mean of z-scored input columns.  Missing
    inputs are skipped (``skipna=True``), so a country with partial data still
    gets a partial sub-index score.

    These sub-indices are used in the falsification suite to test whether the
    headline AI-TFP association is driven by general digital diffusion or by
    innovation activity specifically.

    Parameters
    ----------
    df:
        Panel DataFrame.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with ``digital_infra_index`` and ``innovation_index``
        columns added (NaN where all inputs are missing).
    """
    df = df.copy()

    def _sub_index(cols: list[str], name: str) -> pd.Series:
        available = [c for c in cols if c in df.columns]
        if not available:
            log.warning("%s: none of %s found — index will be all NaN", name, cols)
            return pd.Series(np.nan, index=df.index)
        z_scored = df[available].apply(lambda s: (s - s.mean()) / s.std())
        idx = z_scored.mean(axis=1, skipna=True)
        log.debug("%s built from %s (%d non-null)", name, available, idx.notna().sum())
        return idx

    df["digital_infra_index"] = _sub_index(_DIGITAL_COLS, "digital_infra_index")
    df["innovation_index"]    = _sub_index(_INNOVATION_COLS, "innovation_index")

    log.info("Sub-indices added: digital_infra_index, innovation_index")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all feature engineering steps in the correct order.

    This is the main entry point called by the pipeline.

    Parameters
    ----------
    df:
        Raw/merged panel DataFrame (output of data merge step).

    Returns
    -------
    pd.DataFrame
        Feature-engineered DataFrame ready for econometric analysis.
    """
    log.info("Starting feature engineering — input shape: %s", df.shape)
    df = add_log_transforms(df)
    df = add_sub_indices(df)
    log.info("Feature engineering complete — output shape: %s", df.shape)
    return df
