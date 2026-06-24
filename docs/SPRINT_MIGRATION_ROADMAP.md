# Sprint Migration Roadmap: run_pipeline.py → src/ai_productivity/

**Status:** Active  
**Covers:** Sprints 2–8  
**Constraint:** Scientific results (coefficients, standard errors, p-values, figures) must be
exactly reproducible at every step. No original code is removed until an automated regression
test proves identical outputs.

---

## Orientation: What Has Already Moved

Before Sprint 2 begins, the following functions already live exclusively in
`src/ai_productivity/` and are reached by `run_pipeline.py` through transparent
re-export shims in `agents/`:

| Capability | src/ location | agents/ shim |
|---|---|---|
| Panel loading | `data/loaders.py` — `load_panel`, `drop_aggregate_entities` | `agents/data_agent.py` |
| Data validation | `data/validators.py` — `validate_data`, `report_has_blockers`, `save_validation_report` | `agents/data_agent.py` |
| Sample selection | `data/cleaning.py` — `sample_selection_summary` | `agents/data_agent.py` |
| All econometrics | `econometrics/panel.py` — all `run_*_suite` functions | `agents/econometrics_agent.py` |
| All figures | `visualization/figures.py` — all four figure functions | `agents/visualization_agent.py` |
| LaTeX narrative | `reporting/narrative.py` — `write_results`, `write_falsification_results` | `agents/writing_agent.py` |

`run_pipeline.py` therefore **already executes src/ code** for all scientific
computation. The shim layer makes this invisible. The remaining migration is
about output formatting, orchestration, and the elimination of redundant
structures — not about moving any econometric logic.

---

## Pre-Sprint Prerequisite: Resolve the Ground Truth Ambiguity

**This must happen before Sprint 2 work begins.**

`run_pipeline.py` calls three suites: `run_robustness_suite`,
`run_sensitivity_suite`, `run_falsification_suite`. It does **not** call
`run_heterogeneity_suite`. However, `tables/` currently contains:

- `heterogeneity_summary.csv` and `heterogeneity_summary.tex`
- Seven heterogeneity model `.txt` files: `ai_hc_interact_fe.txt`,
  `covid_interact_fe.txt`, `no_covid_fe.txt`, `post_2020_fe.txt`,
  `post_chatgpt_fe.txt`, `pre_2020_fe.txt`, `solow_excl_fe.txt`

These were produced by `src/ai_productivity/pipeline.py`'s `run()` function,
which does call `run_heterogeneity_suite`. Additionally, `tables/` contains
`tfp_regression.txt` and `summary_stats.tex`, which neither orchestrator
produces; they originate from the numbered `scripts/`.

**Required decision before Sprint 2:** Designate exactly one script as the
canonical producer of each published output. Until this decision is made, the
phrase "identical to ground truth" is undefined. Recommended resolution:

- `run_pipeline.py` is extended to call `run_heterogeneity_suite` before Sprint 2,
  making it the single canonical producer of all tables and figures.
- `tfp_regression.txt` and `summary_stats.tex` are documented as script outputs
  outside the pipeline scope, or the relevant script is wired into the pipeline.
- All tables and figures currently in the repository are committed as the frozen
  reference set.

---

## Sprint 2 — Establish the Regression Baseline

**Goal:** Make reproducibility verifiable before changing anything.

### 2.1 — Freeze reference outputs

**Functions involved:** None moved. This is infrastructure only.

**Action:** From a clean environment, run `run_pipeline.py` on the live data
and copy all outputs to `tests/fixtures/reference_outputs/`. This directory
becomes the regression reference set and is committed to version control.
Reference outputs include:
- All `.txt` model summary files from `tables/`
- `robustness_summary.csv`, `sensitivity_summary.csv`, `falsification_summary.csv`
- `robustness_summary.tex`, `sensitivity_summary.tex`, `falsification_summary.tex`
- `sample_selection_comparison.csv`, `sample_selection_comparison.tex`
- `data_validation_report.json`
- All `.png` figures from `figures/`
- `paper/sections/results_auto.tex`
- `paper/sections/falsification_auto.tex`

**Regression tests:** None yet. This sprint creates the test infrastructure.

**Success criteria:**
- `tests/fixtures/reference_outputs/` exists and is committed.
- A `tests/regression/` directory exists with a `conftest.py` that loads
  the reference set into pytest fixtures.
- A helper function `assert_csv_equal(actual_path, reference_path, rtol=1e-5)`
  is available in `tests/regression/helpers.py`. It uses pandas to compare
  numeric columns within floating-point tolerance and string columns exactly.
- A helper function `assert_tex_equal(actual, reference)` strips LaTeX
  whitespace and compares the substantive content.
- A helper function `assert_coefficient_equal(actual_result, reference_result,
  param_name, rtol=1e-6)` compares a single parameter estimate, standard error,
  and p-value from a linearmodels result object.

**Removal gate:** Nothing is removed this sprint.

---

### 2.2 — Document the dependency graph

**Action:** Write `docs/DEPENDENCY_GRAPH.md` mapping every import in
`run_pipeline.py` to its ultimate source file in `src/ai_productivity/`.
This makes every migration step traceable. The graph has two columns:
what `run_pipeline.py` imports, and what module in `src/` ultimately
provides it.

**Success criteria:** Graph is complete, reviewed, and committed.

---

## Sprint 3 — Migrate Output-Formatting Functions to `reporting/`

**Goal:** Move the only code in `run_pipeline.py` that does not yet have a
home in `src/` — the table-writing helpers — into `src/ai_productivity/reporting/`.

### What to move

`run_pipeline.py` contains these functions that have no equivalent in `src/`
as public, callable functions (though private versions exist inside
`src/ai_productivity/pipeline.py`):

| Function | Current location | Target location |
|---|---|---|
| `_safe_stat` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `_fmt_cell` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `_write_simple_latex_table` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `save_model_summaries` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `save_robustness_table` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `save_sensitivity_table` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `save_falsification_table` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `save_sample_selection_table` | `run_pipeline.py` | `src/ai_productivity/reporting/tables.py` |
| `save_results_text` | `run_pipeline.py` | Inline in orchestrator; no new module needed |

**Note on duplication:** `src/ai_productivity/pipeline.py` already contains
private implementations of these helpers (`_save_model_summaries`,
`_save_robustness_table`, etc.). The canonical implementations are the ones in
`run_pipeline.py` — they are the ground truth. The private functions in
`src/pipeline.py` should be replaced by calls to the new public functions in
`reporting/tables.py`, not the other way around.

### Dependencies

`save_model_summaries` depends on: a dict of linearmodels result objects, a
filesystem path, and `str(res.summary)`.

`save_robustness_table` depends on: `_safe_stat`, `_fmt_cell`,
`_write_simple_latex_table`, pandas, and a dict of linearmodels results.

`save_sensitivity_table` depends on: same as above, plus a hardcoded list of
model name keys.

`save_falsification_table` depends on: same as `save_robustness_table`, plus
`FALSIFICATION_PARAM_NAMES` — a dict that maps model names to their key
parameter.

`save_sample_selection_table` depends on: `_fmt_cell`, a pandas DataFrame,
a filesystem path.

None of these depend on any external API, network, or the live data file.

### Regression tests

For each table function, write a pytest parametrized test that:
1. Constructs a minimal synthetic `results` dict using the fixtures already
   in `tests/conftest.py` (the `sample_panel` fixture provides the panel;
   running `run_robustness_suite(sample_panel)` provides real result objects
   at low computational cost on 100 rows).
2. Calls the function under test (new location in `reporting/tables.py`).
3. Calls the original implementation in `run_pipeline.py` with identical inputs.
4. Asserts that the CSV output is identical (byte-for-byte for string columns,
   within `rtol=1e-10` for float columns).
5. Asserts that the `.tex` output is identical after normalizing whitespace.

This is the highest-value test in the migration: it proves the new code and the
old code produce identical files before any caller is switched.

### Success criteria

- `src/ai_productivity/reporting/tables.py` exists and exports all eight functions.
- `src/ai_productivity/reporting/__init__.py` exports the new functions alongside
  `write_results` and `write_falsification_results`.
- Regression tests for all eight functions pass.
- `run_pipeline.py` is updated to import the table functions from
  `src/ai_productivity/reporting/` rather than defining them locally.
- `src/ai_productivity/pipeline.py`'s private table helpers are replaced by
  calls to the new public functions.
- All 25 existing unit tests continue to pass.
- The regression baseline (Sprint 2.1) is reproduced byte-for-byte by
  `run_pipeline.py` after the import change.

### Removal gate

The local function definitions in `run_pipeline.py` (`_safe_stat`, `_fmt_cell`,
`_write_simple_latex_table`, `save_*`) may be removed as soon as:
- All regression tests in Sprint 3 pass.
- `run_pipeline.py` has been updated to import from `src/`.
- A full end-to-end run of `run_pipeline.py` produces byte-identical output to
  the Sprint 2 reference set.

The private versions in `src/pipeline.py` may be removed when Sprint 4 is
complete.

---

## Sprint 4 — Align `src/ai_productivity/pipeline.py` with `run_pipeline()`

**Goal:** Make `src/ai_productivity/pipeline.py`'s `run()` function produce
exactly the same outputs as `run_pipeline()` on the same input data.

### Current divergences to resolve

**Divergence 1 — Heterogeneity suite.** `run_pipeline()` does not call
`run_heterogeneity_suite`. `src/pipeline.run()` does. Before aligning, the
ground truth decision from the pre-sprint prerequisite must be in place. If
the decision is that heterogeneity outputs are canonical (which the presence
of those files in `tables/` implies), then `run_pipeline()` must be updated
to call `run_heterogeneity_suite` as the first step, before any further
migration.

**Divergence 2 — Figure path convention.** `run_pipeline()` passes full `.png`
paths to figure functions (`"figures/ai_tfp_scatter.png"`). `src/pipeline.run()`
passes path stems (`figures_dir / "ai_tfp_scatter"`). Both produce identical
files because `visualization/figures.py`'s `_save()` uses `with_suffix()`.
This is not a functional divergence, but it should be documented explicitly
and standardized to the stem convention (no extension in the caller).

**Divergence 3 — Output directory defaults.** `run_pipeline()` defaults to
`"tables"`, `"figures"`, `"paper/sections"` as string literals.
`src/pipeline.run()` takes these as typed `Path` arguments with the same
defaults. No behavioral difference, but the types differ at the call site.

**Divergence 4 — Validation error handling.** `run_pipeline()` raises a bare
`ValueError` on validation failure. `src/pipeline.run()` raises `PipelineError`.
The raised type must match the CLI's `except AIProdError` clause. `ValueError`
is not caught by `except AIProdError`, so CLI error reporting would silently
differ. The canonical behavior is `PipelineError`.

### Functions involved

`run_pipeline()` in `run_pipeline.py` (the complete function, ~60 lines).
`run()` in `src/ai_productivity/pipeline.py` (the complete function, ~50 lines).

### Dependencies

`src/pipeline.run()` depends on:
- `src/ai_productivity/data/` — `load_panel`, `validate_data`,
  `report_has_blockers`, `save_validation_report`, `sample_selection_summary`
- `src/ai_productivity/econometrics/panel.py` — all four suite functions
- `src/ai_productivity/visualization/figures.py` — all four figure functions
- `src/ai_productivity/reporting/narrative.py` — `write_results`,
  `write_falsification_results`
- `src/ai_productivity/reporting/tables.py` — all table-writing functions
  (after Sprint 3)
- `src/ai_productivity/logging.py` — `configure_logging`, `get_logger`
- `src/ai_productivity/exceptions.py` — `PipelineError`
- `numpy` for `np.random.seed(42)`

### Regression tests

Write `tests/regression/test_pipeline_alignment.py`:

**Test A — Suite-level output agreement.** For each of the four suites
(`run_robustness_suite`, `run_sensitivity_suite`, `run_falsification_suite`,
`run_heterogeneity_suite`), call both the run_pipeline.py call sequence and
the src/ call sequence on the same `sample_panel` fixture, then assert:
- The result dict has the same keys.
- For each model name, the `params`, `std_errors`, and `pvalues` Series are
  equal within `rtol=1e-10`.
- `nobs` is identical (integer equality).

**Test B — Table file agreement.** Write a temp directory, run the table-saving
functions from both call sites on the same result dicts, then diff:
- All `.csv` files: column names identical, float values within `rtol=1e-10`.
- All `.tex` files: content identical after normalizing line endings and
  trailing whitespace.

**Test C — Narrative agreement.** Call `write_results(results)` and
`write_falsification_results(results, selection_summary)` from both call sites
on the same inputs. Assert string equality (these functions are deterministic
and produce no floating-point rounding variation beyond what is in the
formatted strings themselves).

**Test D — Figure file agreement** (advisory, not blocking). Render all four
figures to temp paths from both call sites using the `sample_panel` fixture.
Compare PNG checksums. If matplotlib rendering is not bit-reproducible across
machines (known issue with font rasterization), compare only figure dimensions
and a sample of pixel value statistics. This test is marked `@pytest.mark.slow`
and excluded from the default test run.

### Success criteria

- All regression tests in `test_pipeline_alignment.py` pass.
- `src/pipeline.run()` and `run_pipeline()` produce identical outputs on
  identical inputs (verified by Test A, B, C above).
- All four divergences documented above are resolved.
- All 25 existing unit tests continue to pass.

### Removal gate

The `run()` function in `src/pipeline.py` may replace `run_pipeline()` only
after all Sprint 4 regression tests pass and after Sprint 5 (the end-to-end
regression) is complete.

---

## Sprint 5 — End-to-End Regression Test on Live Data

**Goal:** Prove that `src/ai_productivity/pipeline.py`'s `run()` reproduces
the full published output set when run on the live panel data.

### Why this sprint is separate from Sprint 4

Sprint 4 regression tests use the synthetic `sample_panel` fixture (100 rows,
10 countries, 10 years). The live panel has approximately 2,895 rows, 193
countries, and 15 years. Floating-point accumulation in panel OLS across this
many observations can diverge from small-panel tests even when the code is
identical. The live-data test is the only test that proves the published tables
will be reproduced.

### Test design

Write `tests/regression/test_live_data_reproduction.py`:

**Prerequisites:** The test is skipped unless the environment variable
`APRP_RUN_LIVE_REGRESSION=1` is set and `data/processed/panel_clean.csv`
exists. This prevents the test from running in CI on every push.

**Procedure:**
1. Run `src/ai_productivity/pipeline.run()` into a fresh temp directory.
2. For each file in `tests/fixtures/reference_outputs/`:
   - CSV files: compare using `assert_csv_equal` with `rtol=1e-6`.
   - `.tex` files: compare with `assert_tex_equal`.
   - Model summary `.txt` files: compare line by line, skipping any lines
     that contain timestamps or session-specific strings (e.g.,
     "Estimation Date", "Time").
   - `.json` files: compare values, not whitespace.
3. Collect all failures and report them together (do not stop at first failure).

**Tolerance rationale:** `rtol=1e-6` for the live regression (looser than
`rtol=1e-10` for synthetic tests) accounts for possible differences in
linearmodels' internal convergence tolerance across platform variations.
If any coefficient differs by more than `1e-6` relatively, this is a signal
that the implementations diverge in a scientifically meaningful way and must
be investigated before proceeding.

### Success criteria

- `test_live_data_reproduction.py` passes with `APRP_RUN_LIVE_REGRESSION=1`.
- The maximum relative difference across all coefficient estimates is below
  `1e-6`.
- The narrative text files are identical.
- The test result is recorded in a CI artifact (or manually committed log)
  for audit purposes.

### Removal gate

Sprints 6 and 7 are gated on this sprint passing. Nothing in `run_pipeline.py`
or `agents/` is removed until this test passes on live data.

---

## Sprint 6 — Wire the CLI to `src/ai_productivity/pipeline.run()`

**Goal:** The `ai-productivity run` CLI command calls `src/pipeline.run()`
directly. Previously it already did so (via `from ai_productivity.pipeline
import run`), but this sprint verifies it after the Sprint 4 and 5 alignment
work.

### Functions involved

`run()` command in `src/ai_productivity/cli.py`. It already contains:

```
from ai_productivity.pipeline import run as _run
```

This import chain is already correct. What Sprint 6 verifies is that the
aligned `run()` function (post-Sprint 4) works correctly end-to-end through
the CLI.

### Additional work in this sprint

**Add `--project-dir` option to the CLI.** Currently, all path arguments
resolve relative to the working directory. A `--project-dir` option allows
the CLI to be run from any directory. Default: current working directory.
All relative `--data-path`, `--tables-dir`, `--figures-dir`, `--paper-dir`
arguments are resolved relative to `--project-dir`.

**Validate `doctor` command paths.** The `doctor` command hardcodes
`Path("data/processed/panel_clean.csv")`. After adding `--project-dir`, this
path must also resolve relative to it.

### Dependencies

Depends on Sprint 4 and Sprint 5 passing.

### Regression tests

Write `tests/regression/test_cli_integration.py`:

**Test A.** Run `ai-productivity doctor` via `typer.testing.CliRunner` in a
temp directory that contains the expected data files. Assert exit code 0.

**Test B.** Run `ai-productivity run` via `CliRunner` pointing at the test
fixture data. Assert exit code 0 and that output files were created in the
expected directories.

**Test C.** Run `ai-productivity run --data-path /nonexistent.csv` and assert
exit code 1 with a message containing the path.

### Success criteria

- All three CLI tests pass.
- `ai-productivity run` executed from any working directory with
  `--project-dir` pointing at the project root produces the same outputs as
  running from within the project root.
- `ai-productivity --help`, `doctor --help`, and `run --help` all exit 0 and
  display accurate option descriptions.

### Removal gate

Nothing is removed this sprint. The removal of `run_pipeline.py` and
`agents/` is Sprint 7.

---

## Sprint 7 — Retire `run_pipeline.py` and `agents/`

**Goal:** Remove the legacy orchestrator and the shim layer. All callers must
use `src/ai_productivity/` directly or the CLI.

### Gate conditions (all must be true before any deletion)

- Sprint 5 live-data regression test passes.
- Sprint 6 CLI integration tests pass.
- `git grep -r "from agents\." --include="*.py"` returns no results outside
  of `run_pipeline.py` itself.
- `git grep -r "import run_pipeline" --include="*.py"` returns no results.
- `git grep -r "from run_pipeline" --include="*.py"` returns no results.
- The numbered `scripts/` files that import from `agents/` have been updated
  to import from `src/ai_productivity/` directly (audit each script).
- `app/streamlit_app.py` has been audited and does not import from `agents/`
  or `run_pipeline`.

### Retirement order

Retire in this order to ensure each removal is independently verifiable:

1. Remove function bodies from `run_pipeline.py` one by one, replacing each
   with `from ai_productivity.reporting.tables import <function>` (the imports
   were already updated in Sprint 3). After each replacement, run the full
   regression suite and confirm it passes.

2. Once all function bodies in `run_pipeline.py` have been replaced by imports,
   `run_pipeline.py` is effectively a thin wrapper that calls
   `src/pipeline.run()`. At this point, delete `run_pipeline.py` in a single
   commit with the message: "Remove run_pipeline.py: replaced by
   ai-productivity run CLI (Sprint 7)".

3. Delete `agents/data_agent.py`, `agents/econometrics_agent.py`,
   `agents/visualization_agent.py`, `agents/writing_agent.py` in a single
   commit with the message: "Remove agents/ shims: all callers now import from
   src/ directly (Sprint 7)".

4. Delete the `agents/` directory.

### Regression tests after retirement

Re-run `tests/regression/test_live_data_reproduction.py` with
`APRP_RUN_LIVE_REGRESSION=1`. All outputs must match the Sprint 2 reference
set within `rtol=1e-6`. This is the formal proof that retirement was safe.

### Success criteria

- `agents/` directory does not exist.
- `run_pipeline.py` does not exist.
- The live-data regression test passes.
- The full unit test suite (25+ tests) passes.
- `git log --oneline -3` shows exactly two retirement commits (one for
  `run_pipeline.py`, one for `agents/`).

---

## Sprint 8 — Retire the Root Scaffold

**Goal:** Delete `ai_productivity/` from the repository root. This is the
dual-package problem identified in the architectural review.

### Gate conditions

- Sprint 7 is complete.
- The root scaffold has been confirmed unreachable: no test, no script, and
  no installed entry point resolves to `ai_productivity/` (root) rather than
  `src/ai_productivity/`.
- `git grep -r "from ai_productivity.core\." --include="*.py"` returns no
  results (the scaffold's `core/` subpackage is not src/).
- `git grep -r "from ai_productivity.ingestion\." --include="*.py"` returns
  no results.
- `git grep -r "from ai_productivity.estimation\." --include="*.py"` returns
  no results.
- `git grep -r "from ai_productivity.processing\." --include="*.py"` returns
  no results.
- `git grep -r "from ai_productivity.diagnostics\." --include="*.py"` returns
  no results.

### Why this is last

The root scaffold is unreachable at runtime due to the `packages =
["src/ai_productivity"]` pyproject.toml setting. It poses no risk to
scientific reproducibility. However, it creates confusion for anyone reading
the repository. It is deleted last because its deletion has zero scientific
risk and can be done cleanly in a single commit after all functional migration
is complete.

### Additional cleanup in this sprint

- Remove `--import-mode=importlib` from pytest `addopts` (it was added as a
  workaround for the dual-package problem; with the scaffold gone, default
  import mode is correct).
- Remove `pythonpath = ["src"]` from pytest ini only if the editable install
  `.pth` file already ensures `src/` is on `sys.path`. Verify before removing.
- Delete `docs/MIGRATION_PLAN.md` and replace it with a one-line note in
  `CHANGELOG.md` referencing the completed migration.
- Promote the richer exception hierarchy from the scaffold's
  `ai_productivity/core/exceptions.py` into `src/ai_productivity/exceptions.py`
  if the team decides to adopt `DownloadError`, `CacheError`,
  `HarmonisationError`, and `ConvergenceError` as canonical types. This is a
  new-feature decision, not a migration task, and belongs in a separate PR.

### Regression tests

Re-run the full test suite and the live-data regression. All tests pass.
The CI matrix (Python 3.11, 3.12) must pass on the clean repository state.

### Success criteria

- `ai_productivity/` directory does not exist in the repository.
- `src/ai_productivity/` is the only package directory.
- All tests pass.
- `pip install -e .` followed by `ai-productivity doctor` exits 0.
- `python -c "import ai_productivity; print(ai_productivity.__version__)"` prints
  `0.1.0` from any working directory.
- The CI pipeline passes on a fresh checkout.

---

## Sprint Dependency Summary

```
Sprint 2 (Baseline) ──► Sprint 3 (Tables) ──► Sprint 4 (Alignment)
                                                      │
                                                      ▼
                                             Sprint 5 (Live data)
                                                      │
                                                      ▼
                                             Sprint 6 (CLI verify)
                                                      │
                                                      ▼
                                             Sprint 7 (Retire pipeline)
                                                      │
                                                      ▼
                                             Sprint 8 (Retire scaffold)
```

No sprint may begin until its predecessor's success criteria are met.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Heterogeneity suite not in run_pipeline.py — published tables are incomplete relative to ground truth | High (known) | High | Resolve in pre-sprint prerequisite; extend run_pipeline.py before Sprint 2 |
| Floating-point divergence on live panel (linearmodels BLAS-dependent) | Medium | Medium | Use `rtol=1e-6` tolerance; document if any coefficient differs |
| `scripts/` import from `agents/` and break after Sprint 7 | Medium | Low | Audit all scripts in Sprint 7 gate conditions |
| `app/streamlit_app.py` imports from `agents/` | Unknown | Medium | Audit in Sprint 7 gate conditions |
| matplotlib figure hashes differ across OS (font rasterization) | High | Low | Advisory test only; compare summary statistics not checksums |
| `tfp_regression.txt` and `summary_stats.tex` not reproducible by any pipeline | High (known) | Medium | Document source script in Sprint 2; wire into pipeline or exclude from regression set |

---

## What This Roadmap Does Not Cover

- **Instrument construction** (`bartik_ai`): Listed in `config.yaml` but no
  construction code exists. Out of scope for this migration; tracked separately.
- **Data downloading and caching**: The `scripts/` download pipeline is not
  part of this migration. It is addressed in the scaffold's Phase 1
  (`docs/MIGRATION_PLAN.md`).
- **Config file integration**: `projects/ai_productivity/config.yaml` is not
  currently read by `src/pipeline.run()`. Wiring it in is a new feature, not
  a migration step.
- **New estimators** (quantile regression, system GMM, IV/2SLS): These exist
  as stubs in the scaffold's `estimation/`. Adding them to the real pipeline
  is new feature work, not migration.
