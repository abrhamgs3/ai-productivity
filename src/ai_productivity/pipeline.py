"""
Main pipeline orchestrator.

Calling :func:`run` executes the full analysis in order:

    Validate → Load → Econometrics → Visualization → Reporting

One command generates every table, figure, and narrative section.

Usage
-----
    # From Python
    from ai_productivity.pipeline import run
    run()

    # From CLI (Sprint 3)
    ai-productivity run
"""

from __future__ import annotations

import numpy as np
from pathlib import Path

from ai_productivity.data import (
    load_panel,
    validate_data,
    report_has_blockers,
    save_validation_report,
    sample_selection_summary,
)
from ai_productivity.econometrics import (
    run_robustness_suite,
    run_sensitivity_suite,
    run_falsification_suite,
)
from ai_productivity.visualization import (
    ai_tfp_scatter,
    ai_tfp_trend,
    ai_coefficient_comparison,
    missingness_profile,
)
from ai_productivity.reporting import write_results, write_falsification_results
from ai_productivity.exceptions import PipelineError
from ai_productivity.logging import get_logger, configure_logging

import pandas as pd

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Table-writing helpers (kept here to avoid cluttering the modules above)
# ---------------------------------------------------------------------------

def _safe_stat(value) -> float:
    try:
        return float(value)
    except Exception:
        return float("nan")


def _fmt_cell(value, digits: int = 4) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    text = str(value)
    for old, new in [("\\", "\\textbackslash{}"), ("_", "\\_"), ("&", "\\&"), ("%", "\\%")]:
        text = text.replace(old, new)
    return text


def _write_latex_table(df: pd.DataFrame, output_file: Path) -> None:
    lines = [
        "\\begin{tabular}{lrrrrr}",
        "\\hline",
        "model & ai\\_coef & ai\\_se & ai\\_pvalue & n\\_obs & r2\\_within \\\\",
        "\\hline",
    ]
    for _, row in df.iterrows():
        lines.append(" & ".join(_fmt_cell(row[c]) for c in df.columns) + " \\\\")
    lines += ["\\hline", "\\end{tabular}"]
    output_file.write_text("\n".join(lines), encoding="utf-8")


def _model_row(model_name: str, res, ai_param: str) -> dict:
    return {
        "model":       model_name,
        "ai_coef":     _safe_stat(res.params.get(ai_param)),
        "ai_se":       _safe_stat(res.std_errors.get(ai_param)),
        "ai_pvalue":   _safe_stat(res.pvalues.get(ai_param)),
        "n_obs":       int(getattr(res, "nobs", 0)),
        "r2_within":   _safe_stat(getattr(res, "rsquared_within", float("nan"))),
    }


def _save_model_summaries(results: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, res in results.items():
        (out_dir / f"{name}.txt").write_text(str(res.summary), encoding="utf-8")
    log.info("Saved %d model summaries to %s/", len(results), out_dir)


def _save_robustness_table(results: dict, out_dir: Path) -> None:
    rows = [
        _model_row(name, res, "ln_ai_l1" if name == "lagged_ai_fe" else "ln_ai")
        for name, res in results.items()
    ]
    df = pd.DataFrame(rows).sort_values("model").reset_index(drop=True)
    df.to_csv(out_dir / "robustness_summary.csv", index=False)
    _write_latex_table(df, out_dir / "robustness_summary.tex")
    log.info("Robustness table written")


def _save_sensitivity_table(results: dict, out_dir: Path) -> None:
    keys = {"lagged_ai_fe", "time_cluster_fe", "placebo_hc_fe", "driscoll_kraay_fe"}
    subset = {k: v for k, v in results.items() if k in keys}
    if not subset:
        return
    rows = [
        _model_row(name, res, "ln_ai_l1" if name == "lagged_ai_fe" else "ln_ai")
        for name, res in subset.items()
    ]
    df = pd.DataFrame(rows).sort_values("model").reset_index(drop=True)
    df.to_csv(out_dir / "sensitivity_summary.csv", index=False)
    _write_latex_table(df, out_dir / "sensitivity_summary.tex")
    log.info("Sensitivity table written")


_FALSIFICATION_PARAMS = {
    "digital_infra_fe":    "digital_infra_index",
    "innovation_fe":       "innovation_index",
    "reverse_causality_fe": "ln_tfp_l1",
    "coverage_restricted_fe": "ln_ai",
}


def _save_falsification_table(results: dict, out_dir: Path) -> None:
    rows = [
        _model_row(name, res, _FALSIFICATION_PARAMS.get(name, "ln_ai"))
        for name, res in results.items()
    ]
    df = pd.DataFrame(rows).sort_values("model").reset_index(drop=True)
    df.to_csv(out_dir / "falsification_summary.csv", index=False)
    _write_latex_table(df, out_dir / "falsification_summary.tex")
    log.info("Falsification table written")


def _save_sample_selection_table(summary_df: pd.DataFrame, out_dir: Path) -> None:
    summary_df.to_csv(out_dir / "sample_selection_comparison.csv", index=False)
    lines = [
        "\\begin{tabular}{lrrrr}",
        "\\hline",
        "variable & in-sample mean & out-of-sample mean & in-sample n & out-of-sample n \\\\",
        "\\hline",
    ]
    for _, row in summary_df.iterrows():
        lines.append(
            f"{_fmt_cell(row['variable'])} & {_fmt_cell(row['in_sample_mean'])} & "
            f"{_fmt_cell(row['out_of_sample_mean'])} & {_fmt_cell(row['in_sample_n'])} & "
            f"{_fmt_cell(row['out_of_sample_n'])} \\\\"
        )
    lines += ["\\hline", "\\end{tabular}"]
    (out_dir / "sample_selection_comparison.tex").write_text("\n".join(lines), encoding="utf-8")
    log.info("Sample selection table written")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    data_path: str | Path = "data/processed/panel_clean.csv",
    tables_dir: str | Path = "tables",
    figures_dir: str | Path = "figures",
    paper_dir: str | Path = "paper/sections",
    *,
    verbose: bool = False,
) -> None:
    """Execute the full analysis pipeline.

    Parameters
    ----------
    data_path:
        Path to the processed panel CSV.
    tables_dir / figures_dir / paper_dir:
        Output directories.
    verbose:
        If ``True``, set logging to DEBUG.
    """
    configure_logging(verbose=verbose)
    np.random.seed(42)

    tables_dir  = Path(tables_dir)
    figures_dir = Path(figures_dir)
    paper_dir   = Path(paper_dir)

    log.info("=" * 60)
    log.info("AI and Productivity pipeline starting")
    log.info("=" * 60)

    # 1. Validate
    report = validate_data(data_path)
    save_validation_report(report, tables_dir / "data_validation_report.json")
    if report_has_blockers(report):
        raise PipelineError(
            f"Data validation failed. See {tables_dir}/data_validation_report.json"
        )

    # 2. Load
    df = load_panel(data_path)

    # 3. Econometrics
    robustness     = run_robustness_suite(df)
    sensitivity    = run_sensitivity_suite(df)
    falsification  = run_falsification_suite(df)
    all_results    = {**robustness, **sensitivity}

    # 4. Tables
    _save_model_summaries(all_results, tables_dir)
    _save_model_summaries(falsification, tables_dir)
    _save_robustness_table(all_results, tables_dir)
    _save_sensitivity_table(all_results, tables_dir)
    _save_falsification_table(falsification, tables_dir)

    selection_summary = sample_selection_summary(df)
    _save_sample_selection_table(selection_summary, tables_dir)

    # 5. Figures
    ai_tfp_scatter(df,           figures_dir / "ai_tfp_scatter")
    ai_tfp_trend(df,             figures_dir / "ai_tfp_trend")
    ai_coefficient_comparison(all_results, figures_dir / "ai_coef_comparison")
    missingness_profile(report,  figures_dir / "missingness_profile")

    # 6. Narratives
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "results_auto.tex").write_text(write_results(all_results), encoding="utf-8")
    (paper_dir / "falsification_auto.tex").write_text(
        write_falsification_results(falsification, selection_summary), encoding="utf-8"
    )

    log.info("=" * 60)
    log.info("Pipeline complete")
    log.info("=" * 60)
