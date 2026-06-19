"""
Panel econometrics: fixed-effects models for the AI-TFP analysis.

All estimation functions follow the same contract:
- Accept a plain DataFrame (not yet multi-indexed).
- Return a ``linearmodels`` result object.
- Log what they're doing at INFO level.
- Raise ``ModelSpecificationError`` for recoverable spec problems.

Model inventory
---------------
run_tfp_model          Baseline FE: ln_tfp ~ ln_ai + ln_hc (entity effects)
run_growth_model       GDP growth: first-differenced ln_gdp (entity effects)
run_robustness_suite   Baseline + two-way FE + trimmed + growth
run_sensitivity_suite  Lagged AI + time cluster + placebo HC + Driscoll-Kraay
run_falsification_suite Digital infra + innovation + reverse causality + coverage-restricted
"""

from __future__ import annotations

import statsmodels.api as sm
from linearmodels.panel import PanelOLS

from ai_productivity.exceptions import ModelSpecificationError
from ai_productivity.logging import get_logger

import pandas as pd

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the DataFrame has a (country, year) MultiIndex."""
    work = df.copy()
    if list(work.index.names) == ["country", "year"]:
        return work.sort_index()
    if not {"country", "year"}.issubset(work.columns):
        raise ModelSpecificationError(
            "Data must include 'country' and 'year' columns or a (country, year) MultiIndex."
        )
    return work.set_index(["country", "year"]).sort_index()


def _fit_model(
    df: pd.DataFrame,
    dependent: str,
    regressors: list[str],
    *,
    entity_effects: bool = True,
    time_effects: bool = False,
    cluster_entity: bool = True,
    cluster_time: bool = False,
    label: str = "",
):
    """Fit a PanelOLS model and return the result.

    Parameters
    ----------
    df:
        Panel data (plain DataFrame or (country, year) MultiIndex).
    dependent:
        Name of the outcome column.
    regressors:
        List of regressor column names (constant is added automatically).
    entity_effects / time_effects:
        Whether to demean by entity and/or time.
    cluster_entity / cluster_time:
        Clustering dimensions for standard errors.
    label:
        Human-readable name for log messages.
    """
    panel_df = _to_panel(df)
    needed = [dependent] + list(regressors)
    model_df = panel_df[needed].dropna()

    n_obs = len(model_df)
    n_entities = model_df.index.get_level_values("country").nunique()
    log.info(
        "Fitting %s — %d obs, %d entities, regressors: %s",
        label or dependent,
        n_obs,
        n_entities,
        regressors,
    )

    if n_obs < len(regressors) + 2:
        raise ModelSpecificationError(
            f"Model '{label}' has only {n_obs} observations for {len(regressors)} regressors."
        )

    y = model_df[dependent]
    X = sm.add_constant(model_df[list(regressors)])

    try:
        model = PanelOLS(
            y, X,
            entity_effects=entity_effects,
            time_effects=time_effects,
            drop_absorbed=True,
        )
        result = model.fit(
            cov_type="clustered",
            cluster_entity=cluster_entity,
            cluster_time=cluster_time,
        )
    except Exception as exc:
        raise ModelSpecificationError(f"Estimation failed for '{label}': {exc}") from exc

    ai_param = "ln_ai_l1" if dependent == "ln_tfp" and "ln_ai_l1" in regressors else "ln_ai"
    coef = result.params.get(ai_param)
    pval = result.pvalues.get(ai_param)
    if coef is not None:
        log.info("  %s coef=%.4f  p=%.4f  nobs=%d", ai_param, float(coef), float(pval), n_obs)

    return result


def _fit_driscoll_kraay(
    df: pd.DataFrame,
    dependent: str,
    regressors: list[str],
    *,
    entity_effects: bool = True,
    time_effects: bool = True,
    label: str = "",
):
    """Driscoll-Kraay standard errors (robust to cross-sectional and temporal dependence)."""
    panel_df = _to_panel(df)
    needed = [dependent] + list(regressors)
    model_df = panel_df[needed].dropna()

    log.info("Fitting Driscoll-Kraay %s — %d obs", label or dependent, len(model_df))

    y = model_df[dependent]
    X = sm.add_constant(model_df[list(regressors)])

    try:
        model = PanelOLS(y, X, entity_effects=entity_effects, time_effects=time_effects, drop_absorbed=True)
        return model.fit(cov_type="kernel", kernel="bartlett", bandwidth=2)
    except Exception as exc:
        raise ModelSpecificationError(f"Driscoll-Kraay estimation failed for '{label}': {exc}") from exc


# ---------------------------------------------------------------------------
# Named specifications
# ---------------------------------------------------------------------------

def run_tfp_model(df: pd.DataFrame):
    """Baseline FE: ln_tfp ~ ln_ai + ln_hc with country fixed effects."""
    return _fit_model(df, "ln_tfp", ["ln_ai", "ln_hc"], entity_effects=True, time_effects=False, label="baseline_tfp_fe")


def run_growth_model(df: pd.DataFrame):
    """GDP growth model: first-differenced ln_gdp on ln_ai and ln_hc."""
    panel_df = _to_panel(df).copy()
    panel_df["gdp_growth"] = panel_df.groupby(level=0)["ln_gdp"].diff()
    log.info("Constructed gdp_growth (within-country first difference of ln_gdp)")
    return _fit_model(panel_df, "gdp_growth", ["ln_ai", "ln_hc"], entity_effects=True, time_effects=False, label="growth_fe")


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------

def run_robustness_suite(df: pd.DataFrame) -> dict:
    """Four robustness specifications: baseline, two-way FE, trimmed, growth."""
    log.info("Running robustness suite (4 models)")

    baseline = run_tfp_model(df)
    twoway = _fit_model(df, "ln_tfp", ["ln_ai", "ln_hc"], entity_effects=True, time_effects=True, label="two_way_fe")

    panel_df = _to_panel(df).reset_index()
    low = panel_df["ln_ai"].quantile(0.01)
    high = panel_df["ln_ai"].quantile(0.99)
    trimmed = panel_df[(panel_df["ln_ai"] >= low) & (panel_df["ln_ai"] <= high)]
    trimmed_res = _fit_model(trimmed, "ln_tfp", ["ln_ai", "ln_hc"], entity_effects=True, time_effects=False, label="trimmed_tfp_fe")

    growth = run_growth_model(df)

    return {
        "baseline_tfp_fe": baseline,
        "two_way_fe": twoway,
        "trimmed_tfp_fe": trimmed_res,
        "growth_fe": growth,
    }


def run_sensitivity_suite(df: pd.DataFrame) -> dict:
    """Four sensitivity checks: lagged AI, time cluster, placebo HC, Driscoll-Kraay."""
    log.info("Running sensitivity suite (4 models)")
    panel_df = _to_panel(df).copy()

    lagged = panel_df.reset_index().sort_values(["country", "year"]).reset_index(drop=True)
    lagged["ln_ai_l1"] = lagged.groupby("country")["ln_ai"].shift(1)
    lagged_ai = _fit_model(lagged, "ln_tfp", ["ln_ai_l1", "ln_hc"], entity_effects=True, time_effects=True, label="lagged_ai_fe")

    time_cluster = _fit_model(
        panel_df, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        cluster_entity=False, cluster_time=True,
        label="time_cluster_fe",
    )

    placebo_hc = _fit_model(panel_df, "ln_hc", ["ln_ai"], entity_effects=True, time_effects=True, label="placebo_hc_fe")
    driscoll_kraay = _fit_driscoll_kraay(panel_df, "ln_tfp", ["ln_ai", "ln_hc"], entity_effects=True, time_effects=True, label="driscoll_kraay_fe")

    return {
        "lagged_ai_fe": lagged_ai,
        "time_cluster_fe": time_cluster,
        "placebo_hc_fe": placebo_hc,
        "driscoll_kraay_fe": driscoll_kraay,
    }


def run_falsification_suite(df: pd.DataFrame) -> dict:
    """Four falsification checks: digital infra, innovation, reverse causality, coverage-restricted."""
    log.info("Running falsification suite (4 models)")
    panel_df = _to_panel(df).copy()

    digital_infra = _fit_model(panel_df, "ln_tfp", ["digital_infra_index", "ln_hc"], entity_effects=True, time_effects=False, label="digital_infra_fe")
    innovation = _fit_model(panel_df, "ln_tfp", ["innovation_index", "ln_hc"], entity_effects=True, time_effects=False, label="innovation_fe")

    reversed_df = panel_df.reset_index().sort_values(["country", "year"]).reset_index(drop=True)
    reversed_df["ln_tfp_l1"] = reversed_df.groupby("country")["ln_tfp"].shift(1)
    reverse_causality = _fit_model(reversed_df, "ln_ai", ["ln_tfp_l1", "ln_hc"], entity_effects=True, time_effects=True, label="reverse_causality_fe")

    panel_reset = panel_df.reset_index()
    coverage = panel_reset.groupby("country")["ln_ai"].apply(lambda s: s.notna().sum())
    covered = coverage[coverage >= 8].index
    log.info("Coverage-restricted sample: %d countries with ≥8 years of AI data", len(covered))
    coverage_restricted = _fit_model(
        panel_reset[panel_reset["country"].isin(covered)],
        "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=False,
        label="coverage_restricted_fe",
    )

    return {
        "digital_infra_fe": digital_infra,
        "innovation_fe": innovation,
        "reverse_causality_fe": reverse_causality,
        "coverage_restricted_fe": coverage_restricted,
    }
