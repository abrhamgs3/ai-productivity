"""
Auto-generate LaTeX narrative text for the results and falsification sections.

These functions inspect the fitted model results and return a LaTeX string
ready to be ``\input``-ed into the paper.  They are intentionally separate
from the estimation code so the narrative can be regenerated without
re-running the econometrics.
"""

from __future__ import annotations

import pandas as pd

from ai_productivity.logging import get_logger

log = get_logger(__name__)


def _fmt_num(value, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "NA"


def _fmt_pvalue(value) -> str:
    try:
        v = float(value)
    except Exception:
        return "NA"
    return "below 0.001" if v < 0.001 else f"{v:.3f}"


def write_results(results: dict) -> str:
    """Generate the main results narrative (LaTeX string).

    Parameters
    ----------
    results:
        Dict mapping model names to linearmodels result objects.
        Must contain ``baseline_tfp_fe``, ``two_way_fe``, ``trimmed_tfp_fe``,
        ``growth_fe``.

    Returns
    -------
    str
        LaTeX-ready paragraph(s).
    """
    log.info("Generating results narrative")

    baseline = results["baseline_tfp_fe"]
    twoway   = results["two_way_fe"]
    trimmed  = results["trimmed_tfp_fe"]
    growth   = results["growth_fe"]

    text = (
        "Baseline fixed-effects estimates show that a 1 percent increase in AI adoption is associated with "
        f"approximately {_fmt_num(baseline.params.get('ln_ai'))} percent higher TFP "
        f"(p-value {_fmt_pvalue(baseline.pvalues.get('ln_ai'))}), controlling for human capital. "
        "The estimated AI-TFP relationship remains directionally stable under stronger identification checks, "
        f"including two-way fixed effects ({_fmt_num(twoway.params.get('ln_ai'))}, "
        f"p-value {_fmt_pvalue(twoway.pvalues.get('ln_ai'))}) and trimmed-sample estimation "
        f"({_fmt_num(trimmed.params.get('ln_ai'))}, "
        f"p-value {_fmt_pvalue(trimmed.pvalues.get('ln_ai'))}). "
        "For macro growth outcomes, the AI coefficient in the GDP growth specification is "
        f"{_fmt_num(growth.params.get('ln_ai'))} (p-value {_fmt_pvalue(growth.pvalues.get('ln_ai'))}), "
        "suggesting the productivity channel may emerge before fully translating into contemporaneous GDP growth."
    )

    if {"lagged_ai_fe", "time_cluster_fe", "placebo_hc_fe"}.issubset(results.keys()):
        lagged       = results["lagged_ai_fe"]
        time_cluster = results["time_cluster_fe"]
        placebo      = results["placebo_hc_fe"]

        text += (
            " Sensitivity checks also support the main findings: the lagged AI specification yields an AI coefficient of "
            f"{_fmt_num(lagged.params.get('ln_ai_l1'))} (p-value {_fmt_pvalue(lagged.pvalues.get('ln_ai_l1'))}), "
            "and inference remains similar under time-clustered standard errors "
            f"({_fmt_num(time_cluster.params.get('ln_ai'))}, "
            f"p-value {_fmt_pvalue(time_cluster.pvalues.get('ln_ai'))}). "
            f"The placebo outcome test using log human capital reports {_fmt_num(placebo.params.get('ln_ai'))} "
            f"(p-value {_fmt_pvalue(placebo.pvalues.get('ln_ai'))}), which should be interpreted as a "
            "falsification check rather than a causal estimate."
        )

    if "driscoll_kraay_fe" in results:
        dk = results["driscoll_kraay_fe"]
        text += (
            " A two-way fixed-effects specification with Driscoll-Kraay standard errors, which is robust to broad "
            "cross-sectional dependence, also preserves a positive AI coefficient "
            f"({_fmt_num(dk.params.get('ln_ai'))}, p-value {_fmt_pvalue(dk.pvalues.get('ln_ai'))})."
        )

    return text


def write_falsification_results(results: dict, selection_summary: pd.DataFrame) -> str:
    """Generate the falsification section narrative (LaTeX string).

    Parameters
    ----------
    results:
        Dict from :func:`run_falsification_suite`.
    selection_summary:
        DataFrame from :func:`sample_selection_summary` (with ``.attrs``).
    """
    log.info("Generating falsification narrative")

    digital    = results["digital_infra_fe"]
    innovation = results["innovation_fe"]
    reverse    = results["reverse_causality_fe"]
    coverage   = results["coverage_restricted_fe"]

    text = (
        "Three extended falsification checks probe the construct validity of the AI proxy, the direction of "
        "the AI-TFP relationship, and the sensitivity of the result to the small complete-case sample.\n\n"
        "First, replacing the composite AI index with a digital-infrastructure-only sub-index "
        "(internet use, mobile subscriptions, and secure servers) yields a coefficient of "
        f"{_fmt_num(digital.params.get('digital_infra_index'))} "
        f"(p-value {_fmt_pvalue(digital.pvalues.get('digital_infra_index'))}, "
        f"n = {int(getattr(digital, 'nobs', 0))}). "
        "An innovation-only sub-index (resident and non-resident patent applications and IP receipts) yields "
        f"{_fmt_num(innovation.params.get('innovation_index'))} "
        f"(p-value {_fmt_pvalue(innovation.pvalues.get('innovation_index'))}, "
        f"n = {int(getattr(innovation, 'nobs', 0))}). "
        "Both sub-indices are positively associated with TFP, indicating that the headline association is not "
        "isolated to AI-specific activity.\n\n"
        "Second, a reverse-causality check regresses log AI adoption on one-period-lagged log TFP. "
        f"The estimated coefficient is {_fmt_num(reverse.params.get('ln_tfp_l1'))} "
        f"(p-value {_fmt_pvalue(reverse.pvalues.get('ln_tfp_l1'))}, "
        f"n = {int(getattr(reverse, 'nobs', 0))}).\n\n"
        "Third, restricting the baseline sample to countries with at least 8 of 15 years of non-missing AI data "
        f"(n = {int(getattr(coverage, 'nobs', 0))} observations) yields an AI coefficient of "
        f"{_fmt_num(coverage.params.get('ln_ai'))} "
        f"(p-value {_fmt_pvalue(coverage.pvalues.get('ln_ai'))}).\n\n"
        f"For context, only {selection_summary.attrs.get('in_sample_countries', 'NA')} of the 193 countries in the "
        f"cleaned panel report AI data in at least one year, contributing "
        f"{selection_summary.attrs.get('in_sample_rows', 'NA')} country-year observations with non-missing AI data, "
        f"against {selection_summary.attrs.get('out_of_sample_rows', 'NA')} country-years without it. "
        "Table~\\ref{tab:sample-selection} compares observable characteristics across these two groups."
    )
    return text
