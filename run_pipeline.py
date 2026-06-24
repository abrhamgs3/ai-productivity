from pathlib import Path

import numpy as np
import pandas as pd

from agents.data_agent import (
    load_panel,
    report_has_blockers,
    sample_selection_summary,
    save_validation_report,
    validate_data,
)
from agents.econometrics_agent import (
    run_falsification_suite,
    run_robustness_suite,
    run_sensitivity_suite,
)
from agents.visualization_agent import (
    ai_coefficient_comparison,
    ai_tfp_scatter,
    ai_tfp_trend,
    missingness_profile,
)
from agents.writing_agent import write_falsification_results, write_results


def save_model_summaries(results, out_dir="tables"):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    for name, res in results.items():
        with (out_path / f"{name}.txt").open("w", encoding="utf-8") as f:
            f.write(str(res.summary))


def _safe_stat(value):
    try:
        return float(value)
    except Exception:
        return float("nan")


def _fmt_cell(value, digits=4):
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    text = str(value)
    text = text.replace("\\", "\\textbackslash{}")
    text = text.replace("_", "\\_")
    text = text.replace("&", "\\&")
    text = text.replace("%", "\\%")
    return text


def _write_simple_latex_table(df, output_file):
    lines = []
    cols = list(df.columns)
    lines.append("\\begin{tabular}{lrrrrr}")
    lines.append("\\hline")
    lines.append("model & ai\\_coef & ai\\_se & ai\\_pvalue & n\\_obs & r2\\_within \\\\")
    lines.append("\\hline")

    for _, row in df.iterrows():
        cells = [_fmt_cell(row[c]) for c in cols]
        lines.append(" & ".join(cells) + " \\\\")

    lines.append("\\hline")
    lines.append("\\end{tabular}")

    with output_file.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def save_robustness_table(results, out_dir="tables"):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    rows = []
    for model_name, res in results.items():
        ai_name = "ln_ai_l1" if model_name == "lagged_ai_fe" else "ln_ai"
        rows.append(
            {
                "model": model_name,
                "ai_coef": _safe_stat(res.params.get(ai_name)),
                "ai_se": _safe_stat(res.std_errors.get(ai_name)),
                "ai_pvalue": _safe_stat(res.pvalues.get(ai_name)),
                "n_obs": int(getattr(res, "nobs", 0)),
                "r2_within": _safe_stat(getattr(res, "rsquared_within", float("nan"))),
            }
        )

    table_df = pd.DataFrame(rows)
    table_df = table_df.sort_values("model").reset_index(drop=True)
    table_df.to_csv(out_path / "robustness_summary.csv", index=False)
    _write_simple_latex_table(table_df, out_path / "robustness_summary.tex")


def save_sensitivity_table(results, out_dir="tables"):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    keys = ["lagged_ai_fe", "time_cluster_fe", "placebo_hc_fe", "driscoll_kraay_fe"]
    subset = {k: v for k, v in results.items() if k in keys}
    if not subset:
        return

    rows = []
    for model_name, res in subset.items():
        ai_name = "ln_ai_l1" if model_name == "lagged_ai_fe" else "ln_ai"
        rows.append(
            {
                "model": model_name,
                "ai_coef": _safe_stat(res.params.get(ai_name)),
                "ai_se": _safe_stat(res.std_errors.get(ai_name)),
                "ai_pvalue": _safe_stat(res.pvalues.get(ai_name)),
                "n_obs": int(getattr(res, "nobs", 0)),
                "r2_within": _safe_stat(getattr(res, "rsquared_within", float("nan"))),
            }
        )

    table_df = pd.DataFrame(rows).sort_values("model").reset_index(drop=True)
    table_df.to_csv(out_path / "sensitivity_summary.csv", index=False)
    _write_simple_latex_table(table_df, out_path / "sensitivity_summary.tex")


FALSIFICATION_PARAM_NAMES = {
    "digital_infra_fe": "digital_infra_index",
    "innovation_fe": "innovation_index",
    "reverse_causality_fe": "ln_tfp_l1",
    "coverage_restricted_fe": "ln_ai",
}


def save_falsification_table(results, out_dir="tables"):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    rows = []
    for model_name, res in results.items():
        param_name = FALSIFICATION_PARAM_NAMES.get(model_name, "ln_ai")
        rows.append(
            {
                "model": model_name,
                "ai_coef": _safe_stat(res.params.get(param_name)),
                "ai_se": _safe_stat(res.std_errors.get(param_name)),
                "ai_pvalue": _safe_stat(res.pvalues.get(param_name)),
                "n_obs": int(getattr(res, "nobs", 0)),
                "r2_within": _safe_stat(getattr(res, "rsquared_within", float("nan"))),
            }
        )

    table_df = pd.DataFrame(rows).sort_values("model").reset_index(drop=True)
    table_df.to_csv(out_path / "falsification_summary.csv", index=False)
    _write_simple_latex_table(table_df, out_path / "falsification_summary.tex")


def save_sample_selection_table(summary_df, out_dir="tables"):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(out_path / "sample_selection_comparison.csv", index=False)

    lines = []
    lines.append("\\begin{tabular}{lrrrr}")
    lines.append("\\hline")
    lines.append("variable & in-sample mean & out-of-sample mean & in-sample n & out-of-sample n \\\\")
    lines.append("\\hline")
    for _, row in summary_df.iterrows():
        lines.append(
            f"{_fmt_cell(row['variable'])} & {_fmt_cell(row['in_sample_mean'])} & "
            f"{_fmt_cell(row['out_of_sample_mean'])} & {_fmt_cell(row['in_sample_n'])} & "
            f"{_fmt_cell(row['out_of_sample_n'])} \\\\"
        )
    lines.append("\\hline")
    lines.append("\\end{tabular}")

    with (out_path / "sample_selection_comparison.tex").open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def save_results_text(text, output_path="paper/sections/results_auto.tex"):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(text)


def run_pipeline(data_path="data/processed/panel_clean.csv"):
    np.random.seed(42)

    validation_report = validate_data(data_path)
    save_validation_report(validation_report, "tables/data_validation_report.json")

    if report_has_blockers(validation_report):
        raise ValueError("Data validation failed. See tables/data_validation_report.json for details.")

    df = load_panel(data_path)

    results = run_robustness_suite(df)
    sensitivity_results = run_sensitivity_suite(df)
    falsification_results = run_falsification_suite(df)
    all_results = {**results, **sensitivity_results}

    save_model_summaries(all_results)
    save_model_summaries(falsification_results)
    save_robustness_table(all_results)
    save_sensitivity_table(all_results)
    save_falsification_table(falsification_results)

    selection_summary = sample_selection_summary(df)
    save_sample_selection_table(selection_summary, "tables")

    ai_tfp_scatter(df, "figures/ai_tfp_scatter.png")
    ai_tfp_trend(df, "figures/ai_tfp_trend.png")
    ai_coefficient_comparison(all_results, "figures/ai_coef_comparison.png")
    missingness_profile(validation_report, "figures/missingness_profile.png")

    narrative = write_results(all_results)
    save_results_text(narrative, "paper/sections/results_auto.tex")

    falsification_narrative = write_falsification_results(falsification_results, selection_summary)
    save_results_text(falsification_narrative, "paper/sections/falsification_auto.tex")


if __name__ == "__main__":
    run_pipeline()