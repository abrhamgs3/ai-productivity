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
run_sensitivity_suite  Lagged AI + time cluster + placebo HC + Driscoll-Kraay + AI_index levels + PWT-only TFP
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
    label: str | None = None,
) -> object:
    """Fit a PanelOLS model and return the result."""
    panel_df = _to_panel(df)
    needed = [dependent] + list(regressors)
    model_df = panel_df[needed].dropna()

    n_entities = model_df.index.get_level_values(0).nunique()
    log.info(
        "Fitting %s — %d obs, %d entities, regressors: %s",
        label or dependent, len(model_df), n_entities, regressors,
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
        cov_type = "clustered"
        cov_kwargs: dict = {}
        if cluster_entity and cluster_time:
            cov_kwargs = {"cluster_entity": True, "cluster_time": True}
        elif cluster_entity:
            cov_kwargs = {"cluster_entity": True}
        elif cluster_time:
            cov_kwargs = {"cluster_time": True}
        else:
            cov_type = "robust"

        result = model.fit(cov_type=cov_type, **cov_kwargs)

        # Log the first regressor's coefficient for a quick sanity check
        first = regressors[0]
        if first in result.params:
            log.info(
                "  %s coef=%.4f  p=%.4f  nobs=%d",
                first, result.params[first], result.pvalues[first], result.nobs,
            )
        return result

    except Exception as exc:
        raise ModelSpecificationError(
            f"Model estimation failed for '{label or dependent}': {exc}"
        ) from exc


def _fit_driscoll_kraay(
    df: pd.DataFrame,
    dependent: str,
    regressors: list[str],
    *,
    entity_effects: bool = True,
    time_effects: bool = False,
    label: str | None = None,
) -> object:
    """Fit with Driscoll-Kraay (kernel) standard errors."""
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
        raise ModelSpecificationError(
            f"Driscoll-Kraay estimation failed for '{label}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Named specifications
# ---------------------------------------------------------------------------

def run_tfp_model(df: pd.DataFrame):
    """Baseline FE: ln_tfp ~ ln_ai + ln_hc with country fixed effects."""
    return _fit_model(
        df, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=False,
        label="baseline_tfp_fe",
    )


def run_growth_model(df: pd.DataFrame):
    """GDP growth model: first-differenced ln_gdp on ln_ai and ln_hc."""
    panel_df = _to_panel(df).copy()
    panel_df["gdp_growth"] = panel_df.groupby(level=0)["ln_gdp"].diff()
    log.info("Constructed gdp_growth (within-country first difference of ln_gdp)")
    return _fit_model(
        panel_df, "gdp_growth", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=False,
        label="growth_fe",
    )


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------

def run_robustness_suite(df: pd.DataFrame) -> dict:
    """Four robustness specifications: baseline, two-way FE, trimmed, growth."""
    log.info("Running robustness suite (4 models)")

    baseline = run_tfp_model(df)
    twoway = _fit_model(
        df, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="two_way_fe",
    )

    panel_df = _to_panel(df).reset_index()
    low = panel_df["ln_ai"].quantile(0.01)
    high = panel_df["ln_ai"].quantile(0.99)
    trimmed = panel_df[(panel_df["ln_ai"] >= low) & (panel_df["ln_ai"] <= high)]
    trimmed_res = _fit_model(
        trimmed, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=False,
        label="trimmed_tfp_fe",
    )

    growth = run_growth_model(df)

    return {
        "baseline_tfp_fe": baseline,
        "two_way_fe": twoway,
        "trimmed_tfp_fe": trimmed_res,
        "growth_fe": growth,
    }


def run_sensitivity_suite(df: pd.DataFrame) -> dict:
    """Six sensitivity checks: lagged AI, time cluster, placebo HC, Driscoll-Kraay, AI_index levels, PWT-only TFP.

    The ai_index_levels_fe spec uses AI_index in levels (not log-transformed).
    AI_index is a z-score composite, so its coefficient reads: a 1-SD increase in
    AI readiness is associated with beta x 100% change in TFP. This spec uses the
    broadest available sample since AI_index avoids the negative-value dropout that
    log(ai_proxy_total) introduces for low-AI countries.

    The pwt_only_fe spec drops the 17 countries with Solow-residual TFP (tfp_solow_flag==1)
    to confirm results hold on the PWT-sourced TFP sample only.
    """
    log.info("Running sensitivity suite (6 models)")
    panel_df = _to_panel(df).copy()

    # Lagged AI (t-1)
    lagged = panel_df.reset_index().sort_values(["country", "year"]).reset_index(drop=True)
    lagged["ln_ai_l1"] = lagged.groupby("country")["ln_ai"].shift(1)
    lagged_ai = _fit_model(
        lagged, "ln_tfp", ["ln_ai_l1", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="lagged_ai_fe",
    )

    # Time-clustered SE
    time_cluster = _fit_model(
        panel_df, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        cluster_entity=False, cluster_time=True,
        label="time_cluster_fe",
    )

    # Placebo: ln_hc as dependent (should not respond to ln_ai)
    placebo_hc = _fit_model(
        panel_df, "ln_hc", ["ln_ai"],
        entity_effects=True, time_effects=True,
        label="placebo_hc_fe",
    )

    # Driscoll-Kraay (cross-sectional dependence robust)
    driscoll_kraay = _fit_driscoll_kraay(
        panel_df, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="driscoll_kraay_fe",
    )

    # AI_index in levels — avoids log-of-z-score issue, broader sample
    ai_index_levels = _fit_model(
        panel_df, "ln_tfp", ["AI_index", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="ai_index_levels_fe",
    )

    # PWT-only TFP: drop Solow-residual countries (tfp_solow_flag==1)
    # Confirms results are not driven by the 17 countries with computed TFP
    panel_reset = panel_df.reset_index()
    if "tfp_solow_flag" in panel_reset.columns:
        pwt_only_df = panel_reset[panel_reset["tfp_solow_flag"] == 0]
    else:
        pwt_only_df = panel_reset
    pwt_only_fe = _fit_model(
        pwt_only_df, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="pwt_only_fe",
    )

    return {
        "lagged_ai_fe": lagged_ai,
        "time_cluster_fe": time_cluster,
        "placebo_hc_fe": placebo_hc,
        "driscoll_kraay_fe": driscoll_kraay,
        "ai_index_levels_fe": ai_index_levels,
        "pwt_only_fe": pwt_only_fe,
    }


def run_falsification_suite(df: pd.DataFrame) -> dict:
    """Four falsification checks: digital infra, innovation, reverse causality, coverage-restricted."""
    log.info("Running falsification suite (4 models)")
    panel_df = _to_panel(df).copy()

    digital_infra = _fit_model(
        panel_df, "ln_tfp", ["digital_infra_index", "ln_hc"],
        entity_effects=True, time_effects=False,
        label="digital_infra_fe",
    )
    innovation = _fit_model(
        panel_df, "ln_tfp", ["innovation_index", "ln_hc"],
        entity_effects=True, time_effects=False,
        label="innovation_fe",
    )

    reversed_df = panel_df.reset_index().sort_values(["country", "year"]).reset_index(drop=True)
    reversed_df["ln_tfp_l1"] = reversed_df.groupby("country")["ln_tfp"].shift(1)
    reverse_causality = _fit_model(
        reversed_df, "ln_ai", ["ln_tfp_l1", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="reverse_causality_fe",
    )

    panel_reset = panel_df.reset_index()
    coverage = panel_reset.groupby("country")["ln_ai"].apply(lambda s: s.notna().sum())
    covered = coverage[coverage >= 8].index
    log.info("Coverage-restricted sample: %d countries with >=8 years of AI data", len(covered))
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


def run_heterogeneity_suite(df: pd.DataFrame) -> dict:
    """Seven heterogeneity checks exploiting the 2010-2024 extended panel.

    Specs
    -----
    pre_2020_fe         Baseline on 2010-2019 only (pre-COVID, pre-GenAI)
    post_2020_fe        Baseline on 2020-2024 only (COVID + generative-AI era)
    covid_interact_fe   Two-way FE with ln_ai * covid_dummy interaction term
    post_chatgpt_fe     Post-2022 subsample (pure generative-AI period)
    no_covid_fe         Drop 2020-2021 entirely (cleaner pre/post comparison)
    solow_excl_fe       Exclude Solow-computed TFP countries (purest PWT sample)
    ai_hc_interact_fe   ln_ai * ln_hc interaction (AI-complementarity hypothesis:
                        returns to AI larger in high-human-capital countries)
    """
    log.info("Running heterogeneity suite (7 models)")
    panel_df = _to_panel(df).copy()
    panel_reset = panel_df.reset_index()

    # 1. Pre-2020 (2010-2019 only) — isolates pre-COVID, pre-GenAI baseline
    pre2020 = panel_reset[panel_reset["year"] < 2020]
    pre_2020_fe = _fit_model(
        pre2020, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="pre_2020_fe",
    )

    # 2. Post-2020 (2020-2024) — COVID + generative-AI era
    post2020 = panel_reset[panel_reset["year"] >= 2020]
    post_2020_fe = _fit_model(
        post2020, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="post_2020_fe",
    )

    # 3. COVID interaction: ln_ai * covid_dummy in two-way FE
    interact_df = panel_reset.copy()
    if "covid_dummy" not in interact_df.columns:
        interact_df["covid_dummy"] = interact_df["year"].isin([2020, 2021]).astype(float)
    interact_df["ln_ai_x_covid"] = interact_df["ln_ai"] * interact_df["covid_dummy"]
    covid_interact_fe = _fit_model(
        interact_df, "ln_tfp", ["ln_ai", "ln_ai_x_covid", "ln_hc", "covid_dummy"],
        entity_effects=True, time_effects=True,
        label="covid_interact_fe",
    )

    # 4. Post-ChatGPT (2023-2024): pure generative-AI period
    post_gpt = panel_reset[panel_reset["year"] >= 2023]
    try:
        post_chatgpt_fe = _fit_model(
            post_gpt, "ln_tfp", ["ln_ai", "ln_hc"],
            entity_effects=True, time_effects=False,
            label="post_chatgpt_fe",
        )
    except Exception:
        post_chatgpt_fe = None
        log.warning("post_chatgpt_fe skipped (insufficient data for 2023-2024 only)")

    # 5. No-COVID: drop 2020-2021 to remove pandemic distortion
    no_covid = panel_reset[~panel_reset["year"].isin([2020, 2021])]
    no_covid_fe = _fit_model(
        no_covid, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="no_covid_fe",
    )

    # 6. Solow-excluded: drop all Solow-computed TFP observations
    if "tfp_solow_flag" in panel_reset.columns:
        solow_excl_df = panel_reset[panel_reset["tfp_solow_flag"] == 0]
    else:
        solow_excl_df = panel_reset
    solow_excl_fe = _fit_model(
        solow_excl_df, "ln_tfp", ["ln_ai", "ln_hc"],
        entity_effects=True, time_effects=True,
        label="solow_excl_fe",
    )

    # 7. AI × Human Capital interaction: tests complementarity hypothesis
    interact2 = panel_reset.copy()
    interact2["ln_ai_x_hc"] = interact2["ln_ai"] * interact2["ln_hc"]
    ai_hc_interact_fe = _fit_model(
        interact2, "ln_tfp", ["ln_ai", "ln_hc", "ln_ai_x_hc"],
        entity_effects=True, time_effects=True,
        label="ai_hc_interact_fe",
    )

    results = {
        "pre_2020_fe":       pre_2020_fe,
        "post_2020_fe":      post_2020_fe,
        "covid_interact_fe": covid_interact_fe,
        "no_covid_fe":       no_covid_fe,
        "solow_excl_fe":     solow_excl_fe,
        "ai_hc_interact_fe": ai_hc_interact_fe,
    }
    if post_chatgpt_fe is not None:
        results["post_chatgpt_fe"] = post_chatgpt_fe
    return results
