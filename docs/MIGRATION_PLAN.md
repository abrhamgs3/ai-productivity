# APRP Migration Plan

**Status:** In Progress — v0.1 scaffold exists; existing pipeline is ground truth.

---

## Guiding Principle

The existing pipeline (`run_pipeline.py` + `src/ai_productivity/`) is the
scientific ground truth.  Every migration step must produce identical results
before it replaces the existing code.  No step is taken until the previous
step is verified.  The pattern is a **strangler fig**: new code wraps old
code, intercepts one call at a time, and the old code is retired only after
the new code is confirmed correct.

---

## Current State

| Component | Location | Status |
|---|---|---|
| Active CLI | `src/ai_productivity/cli.py` | Working |
| Pipeline orchestration | `src/ai_productivity/pipeline.py` | Working |
| Data loading/validation | `src/ai_productivity/data/` | Working, tested |
| Econometrics suites | `src/ai_productivity/econometrics/panel.py` | Working |
| Feature engineering | `src/ai_productivity/features/engineering.py` | Working |
| Visualisation | `src/ai_productivity/visualization/` | Working |
| Narrative generation | `src/ai_productivity/reporting/narrative.py` | Working |
| Backward-compat shims | `agents/` | Re-export from `src/` |
| Scaffold (future arch.) | `ai_productivity/` (root) | All stubs |
| Project config | `projects/ai_productivity/*.yaml` | Validates against models |

---

## Migration Phases

### Phase 1 — Data Layer (next)

**Goal:** `ai_productivity.ingestion` connectors produce a DataFrame that is
byte-for-byte identical to what `scripts/01_download_data.py` currently
downloads.

**Steps:**
1. Implement `WorldBankConnector.fetch()` in `ai_productivity/ingestion/world_bank.py`.
   - Call the same World Bank API endpoint as `scripts/01_download_data.py`.
   - Return a tidy `["iso3", "year", "indicator", "value"]` DataFrame.
   - Acceptance criterion: `pd.testing.assert_frame_equal(old_df, new_df)`.
2. Implement `OECDConnector.fetch()` and `PWTConnector.fetch()` the same way.
3. Implement `DownloadCache.get/put` — filesystem key-value store.
4. Write unit tests for each connector using the `world_bank_raw` and
   `oecd_raw` fixtures already in `tests/conftest.py`.
5. Implement `ai_productivity.processing.harmonise.CountryHarmoniser`.
   - Acceptance criterion: same ISO-3 mapping as `src/ai_productivity/data/loaders.py`.

**Do NOT change `src/ai_productivity/data/` during Phase 1.**

---

### Phase 2 — Processing Layer

**Goal:** `ai_productivity.processing` produces the same `panel_clean.csv`
as `scripts/02_clean_data.py` + `src/ai_productivity/features/engineering.py`.

**Steps:**
1. Implement `TransformPipeline` wrapping `src/ai_productivity/features/engineering.py`.
2. Implement `AIProxyIndexBuilder` (PCA and equal-weight variants) using the
   same scikit-learn / numpy logic as the current index construction.
3. Implement `TFPProcessor` wrapping the PWT column extraction already in
   `src/ai_productivity/data/loaders.py`.
4. Implement `DatasetMerger` wrapping the merge logic in `src/`.
5. Implement `QualityReporter` wrapping `src/ai_productivity/data/validators.py`.
6. Acceptance criterion: `panel_clean.csv` is unchanged.

**Do NOT change `src/ai_productivity/data/` or `features/` during Phase 2.**

---

### Phase 3 — Estimation and Diagnostics

**Goal:** `ai_productivity.estimation` and `ai_productivity.diagnostics`
produce coefficient tables identical to those currently written by
`src/ai_productivity/econometrics/panel.py`.

**Steps:**
1. Implement each estimator (`PooledOLS`, `TwoWayFE`, `RandomEffectsGLS`,
   `IVEstimator`, `GMMEstimator`, `PanelQuantile`) as a thin wrapper around
   the existing `linearmodels` calls in `panel.py`.
2. Implement `SensitivityRunner.from_models_yaml()` so that loading
   `projects/ai_productivity/models.yaml` and calling `.run(panel)` produces
   the same dict of results as `run_robustness_suite(df)` + `run_sensitivity_suite(df)`.
3. Implement diagnostic tests (`hausman_test`, `sargan_hansen_test`,
   `arellano_bond_test`, `pesaran_cd_test`).
4. Acceptance criterion: all regression table `.txt` files in `tables/` are
   unchanged.

---

### Phase 4 — Outputs and CLI

**Goal:** `ai_productivity.outputs` and `ai_productivity.cli` replace
`src/ai_productivity/visualization/`, `reporting/`, and `cli.py`.

**Steps:**
1. Implement `TableRenderer.render()` wrapping the LaTeX/CSV table logic in
   `src/ai_productivity/pipeline.py`.
2. Implement `FigureRenderer.render()` wrapping `src/ai_productivity/visualization/figures.py`.
3. Implement `PDFReportCompiler.compile()`.
4. Implement `ai_productivity.core.provenance.record_run()`.
5. Wire the scaffold CLI (`ai_productivity/cli/main.py`) entry point in
   `pyproject.toml`.  At this point, `ai-productivity run <project_id>` must
   produce the same outputs as `ai-productivity run` (current command).
6. Acceptance criterion: full end-to-end run produces identical outputs.

**After Phase 4:** Remove `src/ai_productivity/cli.py` and the old `run`
command.  The scaffold CLI is now the only surface.

---

### Phase 5 — Retire the Old Package

**Goal:** `src/ai_productivity/` is removed; `ai_productivity/` (root) is
the only package.

**Steps:**
1. Update `pyproject.toml`: `packages = ["ai_productivity"]`.
2. Update `pyproject.toml` ruff `src = ["."]`.
3. Delete `src/ai_productivity/` and `agents/` shims.
4. Delete `run_pipeline.py`.
5. Run full test suite.  All 25 existing tests plus new scaffold tests pass.

---

## Non-Negotiable Rules

- **Never change econometric logic** while migrating plumbing.  If you need
  to fix a model, fix it in `src/ai_productivity/econometrics/panel.py` first,
  confirm the fix, then port it to the scaffold.
- **Tests before cutover.**  A Phase N stub has tests before Phase N+1 begins.
- **No big-bang.** Each phase is a separate PR.  A reviewer must confirm
  identical output before the PR merges.
- **`projects/ai_productivity/config.yaml` is the single configuration
  source of truth** throughout all phases.  Scripts should read from it;
  hardcoded paths in scripts should be eliminated progressively.

---

## Open Questions for Human Review

1. **Bartik instrument** — `config.yaml` lists `bartik_ai` as an instrument
   but no construction code exists yet.  Decide whether this is Phase 1 or
   Phase 3 work.
2. **`SL.TLF.TOTL.IN`** (labour force total) is in the World Bank indicator
   list in `config.yaml` but does not appear in any model specification in
   `models.yaml` or in any control variable.  Confirm whether it should be
   fetched, used as a scaling factor, or removed.
3. **`models.yaml` per-estimator options** (`absorb_entity`, `lag_dep`,
   `n_bootstrap`, etc.) are currently unvalidated `extra` dicts.  Phase 3
   should introduce per-estimator config models to catch typos before they
   produce silent wrong results.
