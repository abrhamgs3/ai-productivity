"""
AI and Productivity — Streamlit Dashboard
==========================================
Four-tab interactive interface for the panel econometrics research pipeline.

Tabs
----
1. Data      — upload panel CSV or load demo dataset
2. Run       — trigger pipeline, live progress
3. Results   — browse regression tables interactively
4. Figures   — view publication figures, download zip
"""

from __future__ import annotations

import io
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI & Productivity Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Resolve demo data path (works locally and on Streamlit Cloud)
# ---------------------------------------------------------------------------
_APP_DIR  = Path(__file__).parent
_REPO_DIR = _APP_DIR.parent
_DEMO_CSV = _REPO_DIR / "data" / "demo" / "panel_demo.csv"


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults = {
        "data_path": None,
        "tmp_dir": None,
        "tables_dir": None,
        "figures_dir": None,
        "paper_dir": None,
        "pipeline_ran": False,
        "validation_report": None,
        "row_count": 0,
        "data_label": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _ensure_tmp() -> tuple[Path, Path, Path, Path]:
    if st.session_state.tmp_dir is None:
        td = tempfile.mkdtemp(prefix="ai_prod_")
        st.session_state.tmp_dir = td
        st.session_state.tables_dir  = Path(td) / "tables"
        st.session_state.figures_dir = Path(td) / "figures"
        st.session_state.paper_dir   = Path(td) / "paper" / "sections"
        for d in [st.session_state.tables_dir,
                  st.session_state.figures_dir,
                  st.session_state.paper_dir]:
            d.mkdir(parents=True, exist_ok=True)
    return (
        Path(st.session_state.tmp_dir),
        st.session_state.tables_dir,
        st.session_state.figures_dir,
        st.session_state.paper_dir,
    )


def _load_data(path: Path, label: str) -> None:
    """Validate and register a data path in session state."""
    from ai_productivity.data.validators import validate_data, report_has_blockers
    with st.spinner("Validating…"):
        report = validate_data(path)
    st.session_state.data_path = path
    st.session_state.validation_report = report
    st.session_state.row_count = report["coverage"]["rows"]
    st.session_state.data_label = label
    st.session_state.pipeline_ran = False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 AI & Productivity")
    st.caption("Panel Econometrics Pipeline · v0.1.0")
    st.divider()
    st.markdown(
        """
        **Workflow**
        1. **Data** — upload your CSV or try the demo
        2. **Run** — execute all 13 models
        3. **Results** — explore regression tables
        4. **Figures** — view & download charts
        """
    )
    st.divider()
    if st.session_state.pipeline_ran:
        st.success("Pipeline complete ✔")
    elif st.session_state.data_path:
        st.info(f"Data: {st.session_state.data_label}")
    else:
        st.warning("No data loaded yet")

    st.divider()
    st.caption(
        "Paper: *AI Adoption and Total Factor Productivity: "
        "Panel Evidence from 193 Countries*"
    )


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_data, tab_run, tab_results, tab_figures = st.tabs(
    ["📁 Data", "⚙️ Run", "📋 Results", "🖼 Figures"]
)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — DATA
# ═══════════════════════════════════════════════════════════════════════════
with tab_data:
    st.header("Data upload & validation")

    col_upload, col_demo = st.columns([3, 1], gap="large")

    with col_upload:
        st.markdown(
            "Upload your processed panel CSV (`panel_clean.csv`). "
            "Required columns: `country`, `year`, `ln_ai`, `ln_tfp`, `ln_hc`, `ln_gdp`."
        )
        uploaded = st.file_uploader(
            "Choose panel CSV",
            type=["csv"],
            help="Processed panel with one row per (country, year).",
        )
        if uploaded is not None:
            _, _, _, _ = _ensure_tmp()
            save_path = Path(st.session_state.tmp_dir) / "panel_clean.csv"
            save_path.write_bytes(uploaded.read())
            _load_data(save_path, uploaded.name)

    with col_demo:
        st.markdown("**No data?**")
        st.markdown("Try the built-in demo: 30 countries × 10 years of synthetic panel data.")
        if st.button("🎲 Load demo dataset", use_container_width=True):
            if _DEMO_CSV.exists():
                _ensure_tmp()
                import shutil
                demo_copy = Path(st.session_state.tmp_dir) / "panel_clean.csv"
                shutil.copy2(_DEMO_CSV, demo_copy)
                _load_data(demo_copy, "Demo (30 countries, synthetic)")
                st.success("Demo data loaded!")
            else:
                st.error(f"Demo file not found at {_DEMO_CSV}")

    if st.session_state.validation_report:
        report = st.session_state.validation_report
        from ai_productivity.data.validators import report_has_blockers
        has_blockers = report_has_blockers(report)

        st.divider()
        cov = report["coverage"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Countries", cov["countries"])
        c2.metric("Years", f"{cov['year_min']}–{cov['year_max']}")
        c3.metric("Rows", f"{cov['rows']:,}")
        c4.metric("Status", "✘ Issues" if has_blockers else "✔ Clean")

        if report["missing_columns"]:
            st.error(f"Missing required columns: `{'`, `'.join(report['missing_columns'])}`")
        if report["duplicate_country_year"]:
            st.warning(f"{report['duplicate_country_year']} duplicate (country, year) pairs.")

        missing = {k: v for k, v in report.get("missing_by_column", {}).items() if v > 0}
        if missing:
            st.subheader("Missing values by column")
            miss_df = (
                pd.DataFrame({"column": list(missing.keys()), "missing": list(missing.values())})
                .sort_values("missing", ascending=False)
            )
            st.bar_chart(miss_df.set_index("column")["missing"])
        else:
            st.success("No missing values in required columns.")

        with st.expander("Preview first 50 rows"):
            df_preview = pd.read_csv(st.session_state.data_path, nrows=50)
            st.dataframe(df_preview, use_container_width=True)
    else:
        st.info("Upload a CSV or load the demo to begin.")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — RUN
# ═══════════════════════════════════════════════════════════════════════════
with tab_run:
    st.header("Run pipeline")

    if not st.session_state.data_path:
        st.warning("Load data in the **Data** tab first.")
    else:
        report = st.session_state.validation_report or {}
        from ai_productivity.data.validators import report_has_blockers
        if report and report_has_blockers(report):
            st.error("Validation blockers found — fix your data before running.")
        else:
            st.markdown(
                f"**Ready.** {st.session_state.data_label} · "
                f"{st.session_state.row_count:,} rows · "
                "13 models across robustness, sensitivity, and falsification suites."
            )
            verbose = st.checkbox("Verbose logging", value=False)

            if st.button("▶ Run pipeline", type="primary", use_container_width=True):
                _, tables_dir, figures_dir, paper_dir = _ensure_tmp()
                progress_bar = st.progress(0, text="Starting…")
                log_area = st.empty()
                log_lines: list[str] = []

                def _log(msg: str, pct: int) -> None:
                    log_lines.append(msg)
                    log_area.code("\n".join(log_lines[-20:]), language=None)
                    progress_bar.progress(pct, text=msg)

                try:
                    from ai_productivity.pipeline import run as _run
                    from ai_productivity.logging import configure_logging
                    import logging
                    configure_logging(level=logging.DEBUG if verbose else logging.WARNING)

                    t0 = time.perf_counter()
                    _log("Validating and loading panel…", 10)

                    _run(
                        data_path=st.session_state.data_path,
                        tables_dir=tables_dir,
                        figures_dir=figures_dir,
                        paper_dir=paper_dir,
                        verbose=verbose,
                    )

                    elapsed = time.perf_counter() - t0
                    _log("✔ Robustness suite (4 models)", 40)
                    _log("✔ Sensitivity suite (5 models)", 60)
                    _log("✔ Falsification suite (4 models)", 75)
                    _log(f"✔ Tables → {tables_dir.name}/", 85)
                    _log(f"✔ Figures → {figures_dir.name}/", 92)
                    _log(f"✔ Narratives → {paper_dir.name}/", 97)
                    _log(f"✔ Complete in {elapsed:.1f} s", 100)

                    st.session_state.pipeline_ran = True
                    st.success(f"Done in {elapsed:.1f} s — check Results and Figures tabs.")
                    st.balloons()

                except Exception as exc:
                    st.error(f"Pipeline failed: {exc}")
                    if verbose:
                        import traceback
                        st.code(traceback.format_exc())

            if st.session_state.pipeline_ran:
                st.info("Pipeline ran for this session. Re-run to regenerate outputs.")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — RESULTS
# ═══════════════════════════════════════════════════════════════════════════
with tab_results:
    st.header("Regression results")

    if not st.session_state.pipeline_ran:
        st.warning("Run the pipeline first.")
    else:
        tables_dir = st.session_state.tables_dir

        SUMMARY_FILES = {
            "Robustness suite":    "robustness_summary.csv",
            "Sensitivity suite":   "sensitivity_summary.csv",
            "Falsification suite": "falsification_summary.csv",
            "Sample selection":    "sample_selection_comparison.csv",
        }

        suite = st.selectbox("Select summary table", list(SUMMARY_FILES.keys()))
        csv_path = tables_dir / SUMMARY_FILES[suite]

        if csv_path.exists():
            df = pd.read_csv(csv_path)
            st.dataframe(df.style.format(precision=4), use_container_width=True, height=350)
            st.download_button(
                f"⬇ Download {suite} CSV",
                data=df.to_csv(index=False).encode(),
                file_name=SUMMARY_FILES[suite],
                mime="text/csv",
            )
        else:
            st.info(f"{SUMMARY_FILES[suite]} not found.")

        st.divider()
        st.subheader("Individual model summaries")
        txt_files = sorted(tables_dir.glob("*.txt"))
        if txt_files:
            model_name = st.selectbox("Select model", [f.stem for f in txt_files])
            txt_path = tables_dir / f"{model_name}.txt"
            if txt_path.exists():
                st.code(txt_path.read_text(encoding="utf-8"), language=None)
        else:
            st.info("No model summary files found.")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4 — FIGURES
# ═══════════════════════════════════════════════════════════════════════════
with tab_figures:
    st.header("Publication figures")

    if not st.session_state.pipeline_ran:
        st.warning("Run the pipeline first.")
    else:
        figures_dir = st.session_state.figures_dir

        FIGURE_META = {
            "ai_tfp_scatter":            "AI adoption vs TFP (scatter + OLS band)",
            "ai_tfp_trend":              "Global trends: AI index & TFP (2010–2024)",
            "ai_coef_comparison":        "Forest plot: AI coefficient across models",
            "missingness_profile":       "Missing-data profile by variable",
        }

        png_files = {f.stem: f for f in figures_dir.glob("*.png")}

        if not png_files:
            st.info("No figures found.")
        else:
            stems = list(FIGURE_META.keys())
            for i in range(0, len(stems), 2):
                cols = st.columns(2)
                for j, stem in enumerate(stems[i:i+2]):
                    with cols[j]:
                        if stem in png_files:
                            st.image(
                                str(png_files[stem]),
                                caption=FIGURE_META.get(stem, stem),
                                use_container_width=True,
                            )
                        else:
                            st.info(f"`{stem}.png` not generated.")

            st.divider()
            st.subheader("Download all outputs")

            if st.button("📦 Build zip", use_container_width=True):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in figures_dir.iterdir():
                        zf.write(f, f"figures/{f.name}")
                    for f in st.session_state.tables_dir.iterdir():
                        zf.write(f, f"tables/{f.name}")
                    for f in st.session_state.paper_dir.iterdir():
                        if f.suffix == ".tex":
                            zf.write(f, f"paper/sections/{f.name}")
                buf.seek(0)
                st.download_button(
                    "⬇ Download ai_productivity_outputs.zip",
                    data=buf.read(),
                    file_name="ai_productivity_outputs.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
