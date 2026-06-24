# Architecture Overview

**AI & Productivity Research Platform** — Sprint 2

This document describes the current architecture of the `ai_productivity`
package located at `src/ai_productivity/`.  It is kept in sync with the
code; do not edit it to describe future intentions.

---

## Design Goals

The platform is built around three principles: **reproducibility** (every result
traces to a specific data file, code commit, and pipeline run),
**modularity** (each subsystem can be tested independently), and
**simplicity** (one command re-runs the entire analysis from cleaned data
to publication artefacts).

---

## Package Layout

```
src/ai_productivity/
├── __init__.py          version string, top-level re-exports
├── cli.py               Typer CLI — doctor and run commands
├── pipeline.py          Sequential pipeline orchestrator
├── provenance.py        ProvenanceRecorder — run metadata to JSON
├── exceptions.py        Domain exception hierarchy (AIProdError)
├── logging.py           Structured logging configuration
├── config/              Configuration loading (stub, v0.2)
├── data/
│   ├── loaders.py       load_panel(), drop_aggregate_entities()
│   ├── validators.py    validate_data(), report_has_blockers()
│   └── cleaning.py      sample_selection_summary()
├── econometrics/
│   └── panel.py         PanelOLS wrappers: robustness, sensitivity,
│                        falsification, heterogeneity suites
├── features/
│   └── engineering.py   Log transforms, sub-index construction (dead code)
├── reporting/
│   └── narrative.py     Auto-generated LaTeX narrative sections
├── visualization/
│   ├── figures.py       Publication figures (scatter, trend, coefficient)
│   └── style.py         Matplotlib style configuration
├── ml/                  Reserved — not yet populated
└── utils/               Reserved — not yet populated

tests/
├── conftest.py          Shared pytest fixtures (panel, validation report)
├── test_data.py         Data layer unit tests
├── test_exceptions.py   Exception hierarchy tests
├── test_provenance.py   ProvenanceRecorder unit tests (35 tests)
├── regression/
│   ├── helpers.py       Six comparison utilities (assert_csv_equal, etc.)
│   ├── conftest.py      Fixtures for regression test helpers
│   └── test_helpers.py  Unit tests for all six helpers (49 tests)
├── fixtures/
│   └── reference_outputs/  Sprint 2 baseline (45 artifacts, manifest.yaml)
├── unit/                Reserved — empty stubs
└── integration/         Reserved — empty stubs

outputs/
├── provenance/
│   ├── run_metadata.json    Last pipeline run metadata
│   ├── schema.json          JSON Schema for run_metadata.json
│   └── REPRODUCIBILITY_REPORT.md  Sprint 2 reproducibility audit
└── FORENSIC_REPORT_ai_index_levels_fe.md  ai_index sample-change investigation
```

---

## Subsystems

**1. Data (`ai_productivity.data`)**

Reads and validates the processed panel CSV.  `load_panel()` reads the file,
sorts by `(country, year)`, and drops aggregate/non-sovereign entities.
`validate_data()` checks required columns, duplicate panel keys, and
missingness, returning a plain dict report.  `report_has_blockers()` decides
whether the pipeline should abort.  All functions are stateless — they accept
paths or DataFrames and return values; no global state is modified.

**2. Econometrics (`ai_productivity.econometrics.panel`)**

Fixed-effects panel models implemented with `linearmodels.PanelOLS`.  Four
model suites cover the paper's analysis:

- `run_robustness_suite` — baseline FE, two-way FE, trimmed sample, GDP growth
- `run_sensitivity_suite` — lagged AI, time clustering, placebo HC, Driscoll-Kraay SE, AI index levels, PWT-only TFP
- `run_falsification_suite` — digital infrastructure, innovation index, reverse causality, coverage-restricted
- `run_heterogeneity_suite` — pre/post 2020, COVID interaction, post-ChatGPT, no-COVID, Solow exclusion, AI×HC interaction

All functions accept a plain `pd.DataFrame` and return a dict of
`linearmodels` result objects.  Standard errors are clustered by entity
unless the specification overrides this.

**3. Features (`ai_productivity.features.engineering`)**

Variable transformations applied after loading: log GDP, log AI proxy, log
TFP, log human capital.  Also builds the `digital_infra_index` and
`innovation_index` sub-indices used in the falsification suite.

**4. Visualization (`ai_productivity.visualization`)**

Four publication figures rendered as both PDF (for LaTeX) and PNG (300 dpi
preview): AI-TFP scatter, AI-TFP trend over time, coefficient comparison
across specifications, and a data missingness profile heatmap.

**5. Reporting (`ai_productivity.reporting.narrative`)**

Generates LaTeX narrative text (`results_auto.tex`,
`falsification_auto.tex`) by inspecting fitted model result objects.
These files are `\input`-ed directly into the paper; re-running the
pipeline regenerates them without manual editing.

---

## Pipeline

`ai_productivity.pipeline.run()` executes the five subsystems in order:

```
validate_data → load_panel → econometrics suites → figures → narratives
```

Each step is a plain function call; there is no DAG, no topological sort,
and no parallelism.  If any step raises an `AIProdError`, the pipeline
aborts and the CLI exits with code 1.

---

## Exception Hierarchy

```
AIProdError
├── DataValidationError   missing columns, duplicate keys, non-finite values
├── MergeError            ISO3 lookup failur