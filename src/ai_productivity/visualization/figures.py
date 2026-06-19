"""
Publication-quality figures for the AI & Productivity paper.

All functions follow the same contract:
- Accept a DataFrame (or dict) and a stem path (without extension).
- Write both a PDF (for LaTeX \includegraphics) and a PNG (for preview).
- Return nothing — side-effect functions kept intentionally simple.
- No figure titles: titles belong in the LaTeX \caption{}, not the image.

Figure inventory
----------------
ai_tfp_scatter         Scatter: log AI vs log TFP with OLS fit + 95% band
ai_tfp_trend           Time series: cross-country mean log AI and log TFP
ai_coefficient_comparison  Forest plot: AI coefficients ± 95% CI across specs
missingness_profile    Bar chart: top-N variables by missing observation count
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats

from ai_productivity.logging import get_logger
from ai_productivity.visualization.style import COLORS, WIDTH_FULL, apply_style

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _save(fig: plt.Figure, stem: Path) -> None:
    """Save figure as both PDF and PNG."""
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".pdf"))
    fig.savefig(stem.with_suffix(".png"))
    plt.close(fig)
    log.debug("Saved %s (.pdf + .png)", stem)


def _ols_band(x: np.ndarray, y: np.ndarray, alpha: float = 0.05):
    """Return (x_grid, y_hat, y_lower, y_upper) for an OLS fit with CI band."""
    from numpy.polynomial import polynomial as P

    # Fit via lstsq for numerical stability
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    x_grid = np.linspace(x.min(), x.max(), 300)
    X_grid = np.column_stack([np.ones_like(x_grid), x_grid])
    y_hat = X_grid @ coef

    # Prediction interval (pointwise)
    n = len(x)
    residuals = y - X @ coef
    s2 = residuals @ residuals / (n - 2)
    x_bar = x.mean()
    se = np.sqrt(s2 * (1 / n + (x_grid - x_bar) ** 2 / ((x - x_bar) @ (x - x_bar))))
    t_crit = stats.t.ppf(1 - alpha / 2, df=n - 2)
    return x_grid, y_hat, y_hat - t_crit * se, y_hat + t_crit * se


# ---------------------------------------------------------------------------
# Figure 1: AI adoption vs TFP scatter
# ---------------------------------------------------------------------------

def ai_tfp_scatter(
    df: pd.DataFrame,
    output_path: str | Path = "figures/ai_tfp_scatter",
) -> None:
    """Scatter plot of log AI adoption vs log TFP.

    Includes an OLS trend line with a 95% confidence band so the reader
    can assess the sign and magnitude of the raw correlation before
    looking at the regression tables.

    Parameters
    ----------
    df:
        Panel DataFrame with ``ln_ai`` and ``ln_tfp`` columns.
    output_path:
        File stem (no extension).  Both .pdf and .png are written.
    """
    apply_style()
    plot_df = df[["ln_ai", "ln_tfp"]].dropna()
    log.info("ai_tfp_scatter: %d observations → %s", len(plot_df), output_path)

    fig, ax = plt.subplots(figsize=(WIDTH_FULL, WIDTH_FULL * 0.55))

    # Scatter — semi-transparent to show density
    ax.scatter(
        plot_df["ln_ai"], plot_df["ln_tfp"],
        color=COLORS["blue"], alpha=0.35, s=12, linewidths=0, rasterized=True,
    )

    # OLS fit + confidence band
    if len(plot_df) > 4:
        x = plot_df["ln_ai"].values
        y = plot_df["ln_tfp"].values
        x_grid, y_hat, y_lo, y_hi = _ols_band(x, y)
        ax.plot(x_grid, y_hat, color=COLORS["blue"], linewidth=1.5, label="OLS fit")
        ax.fill_between(x_grid, y_lo, y_hi, color=COLORS["light_blue"], alpha=0.4, label="95% CI")
        ax.legend(loc="upper left")

    ax.set_xlabel("Log AI Adoption Index")
    ax.set_ylabel("Log Total Factor Productivity")

    fig.tight_layout()
    _save(fig, output_path)


# ---------------------------------------------------------------------------
# Figure 2: Average AI and TFP over time
# ---------------------------------------------------------------------------

def ai_tfp_trend(
    df: pd.DataFrame,
    output_path: str | Path = "figures/ai_tfp_trend",
) -> None:
    """Dual-line chart of cross-country mean log AI and log TFP over time.

    Uses a secondary y-axis so both series are visible despite different
    scales, with matching axis-label colors to avoid ambiguity.

    Parameters
    ----------
    df:
        Panel DataFrame with ``year``, ``ln_ai``, and ``ln_tfp`` columns.
    output_path:
        File stem (no extension).
    """
    apply_style()

    if {"year", "ln_ai", "ln_tfp"}.issubset(df.columns):
        avg = df.groupby("year")[["ln_ai", "ln_tfp"]].mean().reset_index()
    else:
        avg = df.reset_index().groupby("year")[["ln_ai", "ln_tfp"]].mean().reset_index()

    log.info("ai_tfp_trend: %d years → %s", len(avg), output_path)

    fig, ax1 = plt.subplots(figsize=(WIDTH_FULL, WIDTH_FULL * 0.50))
    ax2 = ax1.twinx()

    # AI on left axis
    l1, = ax1.plot(avg["year"], avg["ln_ai"], color=COLORS["blue"], linewidth=1.8,
                   marker="o", markersize=3.5, label="Log AI Index (left)")
    ax1.set_ylabel("Log AI Adoption Index (cross-country mean)", color=COLORS["blue"])
    ax1.tick_params(axis="y", labelcolor=COLORS["blue"])
    ax1.spines["left"].set_color(COLORS["blue"])

    # TFP on right axis
    l2, = ax2.plot(avg["year"], avg["ln_tfp"], color=COLORS["red"], linewidth=1.8,
                   linestyle="--", marker="s", markersize=3.5, label="Log TFP (right)")
    ax2.set_ylabel("Log TFP (cross-country mean)", color=COLORS["red"])
    ax2.tick_params(axis="y", labelcolor=COLORS["red"])
    ax2.spines["right"].set_color(COLORS["red"])
    ax2.spines["right"].set_visible(True)
    ax2.grid(False)

    ax1.set_xlabel("Year")

    # Single legend for both lines
    ax1.legend(handles=[l1, l2], loc="upper left", frameon=False)

    fig.tight_layout()
    _save(fig, output_path)


# ---------------------------------------------------------------------------
# Figure 3: AI coefficient comparison (forest plot)
# ---------------------------------------------------------------------------

_MODEL_LABELS: dict[str, str] = {
    "baseline_tfp_fe":      "Baseline FE",
    "two_way_fe":           "Two-Way FE",
    "trimmed_tfp_fe":       "Trimmed FE (p1–p99)",
    "growth_fe":            "GDP Growth FE",
    "lagged_ai_fe":         "Lagged AI (t-1)",
    "time_cluster_fe":      "Time-Clustered SE",
    "placebo_hc_fe":        "Placebo: Log HC",
    "driscoll_kraay_fe":    "Driscoll-Kraay SE",
}

_SECTION_COLORS: dict[str, str] = {
    "baseline_tfp_fe":   COLORS["blue"],
    "two_way_fe":        COLORS["blue"],
    "trimmed_tfp_fe":    COLORS["blue"],
    "growth_fe":         COLORS["blue"],
    "lagged_ai_fe":      COLORS["red"],
    "time_cluster_fe":   COLORS["red"],
    "placebo_hc_fe":     COLORS["grey"],
    "driscoll_kraay_fe": COLORS["red"],
}


def ai_coefficient_comparison(
    results: dict,
    output_path: str | Path = "figures/ai_coef_comparison",
) -> None:
    """Forest plot of AI coefficients (±95% CI) across all specifications.

    Models are grouped visually: robustness (blue), sensitivity (red),
    placebo (grey).  A vertical dashed line at zero helps the reader
    assess significance at a glance.

    Parameters
    ----------
    results:
        Dict mapping model names to linearmodels result objects.
    output_path:
        File stem (no extension).
    """
    apply_style()

    # Build ordered list following the preferred display order
    order = list(_MODEL_LABELS.keys())
    rows = []
    for name in order:
        if name not in results:
            continue
        res = results[name]
        param = "ln_ai_l1" if name == "lagged_ai_fe" else "ln_ai"
        coef = res.params.get(param)
        se   = res.std_errors.get(param)
        pval = res.pvalues.get(param)
        if coef is None or se is None:
            continue
        rows.append({
            "name":  name,
            "label": _MODEL_LABELS.get(name, name),
            "coef":  float(coef),
            "lo":    float(coef - 1.96 * se),
            "hi":    float(coef + 1.96 * se),
            "pval":  float(pval) if pval is not None else None,
            "color": _SECTION_COLORS.get(name, COLORS["grey"]),
        })

    if not rows:
        log.warning("ai_coefficient_comparison: no valid estimates to plot")
        return

    log.info("ai_coefficient_comparison: %d models → %s", len(rows), output_path)

    n = len(rows)
    height = max(2.5, n * 0.45)
    fig, ax = plt.subplots(figsize=(WIDTH_FULL * 0.75, height))

    y_pos = np.arange(n)

    for i, row in enumerate(rows):
        color = row["color"]
        # CI line
        ax.plot([row["lo"], row["hi"]], [i, i], color=color, linewidth=1.6, zorder=2)
        # Point estimate
        marker = "D" if row.get("pval") is not None and row["pval"] < 0.05 else "o"
        ax.scatter(row["coef"], i, color=color, s=40, zorder=3, marker=marker)

    # Zero line
    ax.axvline(0, color=COLORS["grey"], linewidth=0.8, linestyle="--", zorder=1)

    ax.set_yticks(y_pos)
    ax.set_yticklabels([r["label"] for r in rows])
    ax.set_xlabel("Estimated AI Coefficient (95% CI)")
    ax.invert_yaxis()
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")

    # Legend for significance
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="D", color=COLORS["grey"], label="p < 0.05",
               markersize=5, linestyle="None"),
        Line2D([0], [0], marker="o", color=COLORS["grey"], label="p ≥ 0.05",
               markersize=5, linestyle="None"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", frameon=False)

    fig.tight_layout()
    _save(fig, output_path)


# ---------------------------------------------------------------------------
# Figure 4: Missingness profile
# ---------------------------------------------------------------------------

def missingness_profile(
    validation_report: dict,
    output_path: str | Path = "figures/missingness_profile",
    top_n: int = 12,
) -> None:
    """Horizontal bar chart of the top-N variables by missing observation count.

    Horizontal bars are easier to read when variable names are long.
    Bars are sorted so the most-missing variable is at the top.

    Parameters
    ----------
    validation_report:
        Dict returned by :func:`validate_data`.
    output_path:
        File stem (no extension).
    top_n:
        Number of variables to show.
    """
    apply_style()

    missing_dict = validation_report.get("missing_by_column", {})
    if not missing_dict:
        log.warning("missingness_profile: no missing_by_column data in validation report")
        return

    ordered = sorted(missing_dict.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    # Filter out zero-missing variables
    ordered = [(k, v) for k, v in ordered if v > 0]
    if not ordered:
        log.info("missingness_profile: all variables complete — skipping figure")
        return

    labels = [k.replace("_", " ") for k, _ in ordered]
    values = [v for _, v in ordered]

    # Prettify common column names
    _pretty = {
        "ln ai": "log AI Index", "ln tfp": "log TFP", "ln hc": "log Human Capital",
        "ln gdp": "log GDP p.c.", "tfp": "TFP", "hc": "Human Capital",
        "capital stock": "Capital Stock", "pat res": "Patents (resident)",
        "pat nres": "Patents (non-res.)", "ip receipts": "IP Receipts",
        "internet users": "Internet Users", "mobile subs": "Mobile Subscriptions",
        "secure servers": "Secure Servers", "ai proxy total": "AI Proxy (total)",
        "AI index": "AI Index",
    }
    labels = [_pretty.get(l, l) for l in labels]

    log.info("missingness_profile: %d variables → %s", len(labels), output_path)

    height = max(2.8, len(labels) * 0.36)
    fig, ax = plt.subplots(figsize=(WIDTH_FULL * 0.72, height))

    colors = [COLORS["blue"] if v > 1000 else COLORS["light_blue"] for v in values]
    y_pos = np.arange(len(labels))

    ax.barh(y_pos, values, color=colors, edgecolor="none", height=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Missing Observations")
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")

    # Annotate bars with counts
    for i, v in enumerate(values):
        ax.text(v + max(values) * 0.01, i, f"{v:,}", va="center", fontsize=8,
                color=COLORS["black"])

    fig.tight_layout()
    _save(fig, output_path)
