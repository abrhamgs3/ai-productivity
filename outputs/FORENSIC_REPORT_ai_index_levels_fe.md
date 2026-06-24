# Forensic Report: `ai_index_levels_fe` Sample Change
## n = 1,144 → n = 2,053

**Date:** 2026-06-23  
**Investigator:** Independent forensic analysis  
**Input data SHA-256:** `9a65183a5406c76b...` (panel_clean.csv — identical in reference and working copy)  
**Conclusion:** The reference baseline and the current `panel_clean.csv` were produced by **different data-construction pipelines**. The reference model output was captured from an intermediate dataset that no longer exists in the repository. The `panel_clean.csv` stored in `tests/fixtures/reference_outputs/data/` cannot reproduce the reference model outputs.

---

## 1. The Core Paradox

The manifest and audit reports state that both the reference and current runs use input SHA-256 `9a65183a...`. Byte-for-byte, `tests/fixtures/reference_outputs/data/panel_clean.csv` and `data/processed/panel_clean.csv` are **identical files**. Yet applying the current model code to this identical file produces n=2,053, while the reference model output records n=1,144 with 12 time periods.

This is not a contradiction. It is evidence that the reference `ai_index_levels_fe.txt` was **not produced from the current `panel_clean.csv`**. The fixture's `panel_clean.csv` was captured at a later time than the model output files, and it replaced an intermediate version of the file without regenerating the models.

---

## 2. Data Lineage: Every Transformation of AI_index

### Stage 0 — `data/raw/merged_dataset.csv`

| Metric | Value |
|---|---|
| Total rows | 3,990 |
| Year range | 2010–2024 |
| Countries (incl. aggregates) | 266 |
| **AI_index NaN (all rows)** | **2,551** |
| AI_index NaN (sovereign rows only) | 1,611 |
| AI_index negative (sovereign) | 654 |
| AI_index positive (sovereign) | 630 |
| **Last year with any AI_index data** | **2021** (years 2022–2024 are 100% NaN) |
| **Last year with any tfp data** | **2019** (years 2020–2024 are 100% NaN) |

The raw merged dataset contains AI_index from an external z-score composite source that was only available through 2021 at the time of the original pipeline run. TFP from Penn World Tables was only available through 2019.

AI_index is a z-score composite. It takes negative values for low-AI countries. In the raw data, 654 sovereign country-year observations have negative AI_index values (e.g., Afghanistan 2010–2019 ≈ −1.2 to −0.8). Zero values: none. NaN represents countries with no AI readiness data at all.

### Stage 1 — `drop_aggregate_entities()`
**File:** `src/ai_productivity/data/loaders.py`, function `drop_aggregate_entities()`, line 135

```python
df = df[~df["country"].isin(_EXCLUDED)].reset_index(drop=True)
```

| Metric | Value |
|---|---|
| Rows before | 3,990 |
| Rows dropped (aggregates + non-sovereign territories) | 1,095 |
| **Rows after** | **2,895** |
| AI_index NaN after drop | 1,611 |
| Observations removed for AI_index | 0 (filtering is on country identity, not AI_index value) |

No AI_index values are imputed or modified. Negative values pass through unchanged.

### Stage 2 — Log transforms (`scripts/02_clean_data.py`)

#### Old code (commit `0c3b17e`):
```python
df['ln_ai'] = np.log(df['AI_index'])   # ← WRONG: AI_index is z-score, takes negatives
```
`numpy.log` of a negative number produces `NaN` with a `RuntimeWarning`. So the old `ln_ai` column was NaN for ALL of: (a) the 1,611 rows where AI_index itself was NaN, and (b) the 654 rows where AI_index was negative.

| Old ln_ai = log(AI_index) | Count |
|---|---|
| NaN from AI_index NaN | 1,611 |
| NaN from AI_index < 0 | 654 |
| **Total NaN in ln_ai** | **2,265** |
| Non-NaN (positive AI_index only) | 630 |

#### Current code (commit `e4668c3`, June 18 2026):
```python
df["ln_ai"] = np.log(df["ai_proxy_total"])   # ← correct: always positive
```
`ai_proxy_total` is an external AI-adoption proxy that is always strictly positive (range: 2.0 to 3,401,100). The switch from `log(AI_index)` to `log(ai_proxy_total)` was the stated fix in commit `e4668c3`.

**Critical:** Neither the old nor the current committed cleaning script is what produced `data/processed/panel_clean.csv`. The current panel has 7 additional columns (`tfp_solow_flag`, `ai_proxy_reconstructed_flag`, `hc_extrapolated_flag`, `covid_dummy`, `post_chatgpt`, `post_2020`, `ai_reconstructed_flag`) that are absent from the output of `02_clean_data.py`. The current `panel_clean.csv` was produced by an **uncommitted data-preparation pipeline**.

### Stage 3 — Current `data/processed/panel_clean.csv` (SHA-256 `9a65183a...`)

This is the file stored in both `data/processed/` and `tests/fixtures/reference_outputs/data/`.

| Metric | Value |
|---|---|
| Total rows | 2,895 |
| Year range | **2010–2024** (15 years) |
| Countries | 193 |
| **AI_index NaN** | **0** (zero — all country-years have a value) |
| AI_index negative | 1,586 |
| AI_index zero | 0 |
| AI_index positive | 1,309 |
| AI_index min | −2.403327 |
| AI_index max | 10.050024 |
| ln_ai (from ai_proxy_total) NaN | 997 |
| ln_tfp NaN | 842 |
| ln_hc NaN | 825 |

**The AI_index column contains no NaN values.** All 1,586 negative values are legitimate negative z-scores for countries with below-average AI readiness. They are NOT missing data.

This is the critical difference from the old panel: the current panel's AI_index was imputed/extended to cover all 193 sovereign country-years across 2010–2024 using an expanded external dataset. The imputed values for previously-missing country-years are negative z-scores (these countries had no measured AI activity, so their z-scores fall well below zero). The flag column `ai_reconstructed_flag` tracks which values were reconstructed.

Similarly, `ln_tfp` was extended through 2024 using Solow residual computation (tracked by `tfp_solow_flag`).

### Stage 4 — `_to_panel()` (`src/ai_productivity/econometrics/panel.py`, lines 36–45)

```python
def _to_panel(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if list(work.index.names) == ["country", "year"]:
        return work.sort_index()
    return work.set_index(["country", "year"]).sort_index()
```

**No filtering. No dropna. No value modification.** This function only sets a MultiIndex. All 2,895 rows pass through unchanged.

### Stage 5 — `_fit_model()` dropna (`panel.py`, line 62) ← **THE RESPONSIBLE LINE**

```python
model_df = panel_df[needed].dropna()
```

Where `needed = ["ln_tfp", "AI_index", "ln_hc"]` for `ai_index_levels_fe`.

This is the sole data-filtering step between loading the panel and fitting the model. It drops every row where **any** of the three model variables is NaN. It does NOT drop negative values. It does NOT apply any substantive sample restriction.

| Scenario | AI_index NaN | ln_tfp NaN | ln_hc NaN | Rows dropped | **n** |
|---|---|---|---|---|---|
| Current panel (SHA-256 9a65183a) | 0 | 842 | 825 | 842 (dominated by ln_tfp) | **2,053** |
| Intermediate panel (reference) | ~1,286 est. | ~615 est. | ~635 est. | ~1,751 est. | **1,144** |
| Old panel (0c3b17e sim.) | 1,611 | 1,875 | 1,645 | 2,141 | **754** |

The intermediate panel that produced the reference n=1,144 had:
- 12 time periods (2010–2021) — AI_index and ln_tfp were NaN for 2022–2024
- 119 entities — fewer countries had both AI_index and ln_tfp available
- Average 9.61 observations per entity (unbalanced panel, some country-years missing)

---

## 3. Exact Root Cause

The sample change from n=1,144 to n=2,053 is caused by **three simultaneous data-construction changes** applied to `panel_clean.csv` between the reference capture and the current state:

### Cause 1: AI_index temporal extension (primary driver, +3 years)
In the intermediate panel (reference), AI_index was NaN for all observations in years 2022–2024. The raw `merged_dataset.csv` still reflects this: AI_index is 100% NaN for years 2022–2024 in sovereign rows. In the current `panel_clean.csv`, AI_index was **imputed forward to 2024** using the `ai_reconstructed_flag` methodology. Because the imputed 2022–2024 values are non-NaN, `dropna()` on line 62 no longer drops them.

**Effect:** Adds approximately 3 × 137 = 411 observations (3 years × 137 entities with ln_tfp).

### Cause 2: TFP temporal extension (secondary driver, +years 2020–2024)
In the intermediate panel (reference), `ln_tfp` was NaN for years 2020–2024 in the raw PWT data (PWT only covered through 2019 in the original source). In the current panel, TFP was extended through 2024 using Solow residual computation for 137 countries (tracked by `tfp_solow_flag`). The raw `merged_dataset.csv` still shows `tfp = NaN` for 2020–2024.

**Effect:** Adds 5 × 137 = 685 observations from years 2020–2024 that previously had no ln_tfp.

### Cause 3: Entity expansion (+18 entities)
The combined availability of AI_index and ln_tfp for 2010–2021 in the intermediate panel gave 119 entities. With both variables extended to 2024 and additional data imputed, the current panel supports 137 entities.

**Effect:** +18 entities × avg 9.61 years = +173 additional observations.

*(Note: causes 1, 2, and 3 overlap — the total is 909 observations, not the sum of the three estimates.)*

---

## 4. The Responsible Function and Line

```
File:     src/ai_productivity/econometrics/panel.py
Function: _fit_model()
Line:     62
Code:     model_df = panel_df[needed].dropna()
```

This line is the **sole observation-selection gate** for the model. It is correct behavior — listwise deletion is standard for panel OLS. The line itself has not changed between versions. The sample change is entirely driven by what NaN values are present in the input data, not by any change to this line.

---

## 5. Internal Inconsistency of the Reference Baseline

The `tests/fixtures/reference_outputs/` directory contains artifacts from at least **three different versions of `panel_clean.csv`**:

| Artifact | Source panel | AI_index NaN | Years | Notes |
|---|---|---|---|---|
| `tables/ai_index_levels_fe.txt` | **Intermediate** panel | ~1,286 | 12 (2010–2021) | Captured before 2024 extension |
| `tables/data_validation_report.json` | **Old** panel (0c3b17e sim) | 1,611 | 10 (2010–2019) | Shows AI_index: 1611 |
| `data/panel_clean.csv` | **Current** panel | 0 | 15 (2010–2024) | SHA-256 9a65183a |

The current `data/panel_clean.csv` (SHA-256 `9a65183a...`) **cannot reproduce any of the model output files** in the reference fixtures. Running the full pipeline against this file produces n=2,053 for `ai_index_levels_fe`, not n=1,144.

The reference fixtures were assembled by capturing model outputs from one pipeline run and the data file from a later run. They do not represent a self-consistent snapshot of the scientific pipeline at any single point in time.

---

## 6. What n=1,144 Represents Scientifically

The reference model (n=1,144, 12 periods, 119 entities) used data from an intermediate dataset that covered 2010–2021 for a subset of countries. The coefficient in the reference (AI_index: +0.0132, p=0.0216) was estimated on this smaller, temporally constrained sample.

The current model (n=2,053, 15 periods, 137 entities) uses the same functional form but on an extended dataset that includes:
- 2022–2024 data (a period with elevated AI adoption globally)
- 18 additional countries
- TFP values computed via Solow residual for years when PWT data was unavailable

Whether the coefficient from the current dataset (+0.0132 in reference vs. current estimate TBD) reflects the same underlying relationship depends on whether the TFP and AI_index imputation/extension is scientifically valid. This is a research design question, not a software defect.

---

## 7. Implications

1. **The reference baseline for `ai_index_levels_fe` is not reproducible** from any files currently in the repository. A new reference must be established from a known, committed pipeline state.

2. **`02_clean_data.py` is not the script that produced `panel_clean.csv`.** Running it against `merged_dataset.csv` produces 754 observations for this model (not 1,144 or 2,053) and omits 7 flag columns. The actual data-construction pipeline is uncommitted.

3. **`data/raw/merged_dataset.csv` is outdated.** It does not contain the extended TFP, AI_index, or hc data that is present in `panel_clean.csv`. The source data used to construct the current panel no longer matches what the committed cleaning script would produce.

4. **The sample change is scientifically material.** Moving from n=1,144 (2010–2021, 119 countries) to n=2,053 (2010–2024, 137 countries) includes different entities, different time periods, and imputed values. The paper must explicitly specify which dataset version its results correspond to.

---

*Report produced 2026-06-23. No production code was modified during this investigation.*
