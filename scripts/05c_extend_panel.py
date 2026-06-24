"""
05c_extend_panel.py  — Extended panel 2010–2024
Extends TFP, hc, capital_stock to 2020-2024 via:
  - PWT 10.02 if available (data/raw/pwt102_harmonized.csv)
  - Perpetual inventory for K + linear extrapolation for hc + Solow residual for TFP
Reconstructs AI proxy for 2022-2024 from WDI components.
Adds covid_dummy, post_chatgpt, post_2020 columns.
Merges wdi_extended.csv if available.
"""

import os
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ALPHA = 0.33
DELTA = 0.06

# ── Load base panel ────────────────────────────────────────────────────────
panel = pd.read_csv("data/processed/panel_clean.csv")
merged = pd.read_csv("data/raw/merged_dataset.csv")

# Drop non-sovereign from merged
AGGREGATES = {
    "World","High income","Low income","Middle income","Low & middle income",
    "Upper middle income","Lower middle income","East Asia & Pacific",
    "Europe & Central Asia","Latin America & Caribbean","Middle East & North Africa",
    "North America","South Asia","Sub-Saharan Africa","Africa Eastern and Southern",
    "Africa Western and Central","Arab World","Central Europe and the Baltics",
    "Caribbean small states","Early-demographic dividend","Euro area",
    "Fragile and conflict affected situations","Heavily indebted poor countries (HIPC)",
    "IBRD only","IDA & IBRD total","IDA blend","IDA only","IDA total",
    "Late-demographic dividend","Least developed countries: UN classification",
    "OECD members","Other small states","Pacific island small states",
    "Post-demographic dividend","Pre-demographic dividend","Small states",
    "South Asia (IDA & IBRD)","East Asia & Pacific (excluding high income)",
    "Europe & Central Asia (excluding high income)","Kosovo","West Bank and Gaza",
    "Puerto Rico","Bermuda","Greenland","Hong Kong SAR, China","Macao SAR, China",
    "Taiwan, China","Channel Islands","Isle of Man","Faroe Islands",
    "Northern Mariana Islands","Virgin Islands (U.S.)","Guam","American Samoa",
    "Cayman Islands","Turks and Caicos Islands","British Virgin Islands",
    "Sint Maarten (Dutch part)","St. Martin (French part)","Curacao",
    "New Caledonia","French Polynesia","Gibraltar","Liechtenstein",
    "Not classified","Africa","Americas","Asia","Europe","Oceania",
}
merged = merged[~merged["country"].isin(AGGREGATES)].copy()

print(f"Base panel: {panel.shape}, years {int(panel['year'].min())}–{int(panel['year'].max())}")

p = panel.copy().sort_values(["country","year"]).reset_index(drop=True)

# ── Step 1: Fill WDI variables 2020-2024 from merged ──────────────────────
WDI_FILL_COLS = ["gdp_pc","population","internet_users","mobile_subs",
                 "secure_servers","electricity_access","rule_law","gov_effect",
                 "reg_quality","pat_res","pat_nres","ip_receipts","ai_proxy_total"]

m = merged[["country","year"] + WDI_FILL_COLS].set_index(["country","year"])
p = p.set_index(["country","year"])
for col in WDI_FILL_COLS:
    if col in m.columns:
        p[col] = p[col].fillna(m[col])
p = p.reset_index()

# ── Step 2: Reconstruct AI proxy 2022-2024 from components ────────────────
print("Reconstructing AI proxy 2022–2024 from WDI components...")
ai_comps = ["internet_users","mobile_subs","secure_servers"]
for col in ai_comps:
    mu = p[col].mean(); sd = p[col].std()
    p[f"_z_{col}"] = (p[col] - mu) / sd

reconstructed = p[[f"_z_{c}" for c in ai_comps]].mean(axis=1, skipna=True)
fill_ai = p["ai_proxy_total"].isna() & reconstructed.notna()
p.loc[fill_ai, "ai_proxy_total"] = reconstructed[fill_ai]
p["ai_reconstructed_flag"] = fill_ai.astype(int)
p.drop(columns=[f"_z_{c}" for c in ai_comps], inplace=True)
print(f"  Filled {fill_ai.sum()} rows for {p.loc[fill_ai,'country'].nunique()} countries")

# ── Step 3: Load PWT 10.02 if available ───────────────────────────────────
if os.path.exists("data/raw/pwt102_harmonized.csv"):
    print("Loading PWT 10.02...")
    pwt102 = pd.read_csv("data/raw/pwt102_harmonized.csv")
    for col in ["tfp","hc","capital_stock"]:
        if col in pwt102.columns:
            src = pwt102[["country","year",col]].set_index(["country","year"])[col]
            p = p.set_index(["country","year"])
            p[col] = p[col].fillna(src)
            p = p.reset_index()
    print(f"  TFP 2020 coverage after PWT 10.02: {p[p['year']==2020]['tfp'].notna().sum()}")
else:
    print("PWT 10.02 not found — computing TFP via Solow residual")

# ── Step 4: Perpetual inventory — forward-fill capital_stock ──────────────
print("Perpetual inventory: forward-filling capital_stock 2020–2024...")
p = p.sort_values(["country","year"]).reset_index(drop=True)

# Vectorised: for each year 2020-2024, K(t) = K(t-1)*(1-delta) + inv_rate*GDP(t)
INV_RATE = 0.22
for yr in range(2020, 2025):
    prev_yr = yr - 1
    prev_k = p.loc[p["year"]==prev_yr, ["country","capital_stock"]].set_index("country")["capital_stock"]
    curr = p[p["year"]==yr].copy()
    missing_k = curr["capital_stock"].isna()
    gdp_t = curr["gdp_pc"] * curr["population"] / 1e6
    k_prev_mapped = curr["country"].map(prev_k)
    k_new = k_prev_mapped * (1 - DELTA) + INV_RATE * gdp_t
    idx = curr[missing_k & k_prev_mapped.notna() & gdp_t.notna()].index
    p.loc[idx, "capital_stock"] = k_new.loc[idx]

print(f"  capital_stock 2022 coverage: {p[p['year']==2022]['capital_stock'].notna().sum()} countries")

# ── Step 5: Linear extrapolation of hc for 2020-2024 ─────────────────────
print("Extrapolating hc (human capital) via linear trend through 2019...")

# Fit per-country linear trend on 2015-2019 hc
known = p[p["year"].between(2015,2019) & p["hc"].notna()]
slopes = {}
intercepts = {}
for country, grp in known.groupby("country"):
    if len(grp) >= 2:
        c = np.polyfit(grp["year"], grp["hc"], 1)
        slopes[country] = c[0]
        intercepts[country] = c[1]

for yr in range(2020, 2025):
    mask = (p["year"] == yr) & p["hc"].isna() & p["country"].isin(slopes)
    if mask.sum() == 0:
        continue
    p.loc[mask, "hc"] = (
        p.loc[mask, "country"].map(slopes) * yr +
        p.loc[mask, "country"].map(intercepts)
    )
    # Cap hc between 1.0 and 5.0 (plausible PWT range)
    p.loc[mask, "hc"] = p.loc[mask, "hc"].clip(lower=1.0, upper=5.0)

p["hc_extrapolated_flag"] = ((p["year"] >= 2020) & p["hc"].notna()).astype(int)
print(f"  hc 2022 coverage: {p[p['year']==2022]['hc'].notna().sum()} countries")

# ── Step 6: Solow-residual TFP for 2020-2024 ─────────────────────────────
print("Computing Solow TFP for 2020–2024...")

# Only fill where tfp is still NaN
needs = p["tfp"].isna() & p["year"].between(2020,2024)
can   = p["gdp_pc"].notna() & p["population"].notna() & p["capital_stock"].notna() & p["hc"].notna()
mask  = needs & can

if mask.sum() > 0:
    gdp_t = p.loc[mask, "gdp_pc"] * p.loc[mask, "population"] / 1e6
    K     = p.loc[mask, "capital_stock"]
    L     = p.loc[mask, "population"] / 1e6
    H     = p.loc[mask, "hc"]
    solow_raw = gdp_t / (K**ALPHA * (L*H)**(1-ALPHA))

    # Scale each country's Solow TFP to match its 2019 PWT value
    scale_map = {}
    for country in p.loc[mask, "country"].unique():
        row_2019 = p[(p["country"]==country) & (p["year"]==2019)]
        if len(row_2019)==0: continue
        tfp_2019 = row_2019["tfp"].values[0]
        if pd.isna(tfp_2019): continue
        # Solow raw for 2019
        r2019 = row_2019
        if r2019["gdp_pc"].isna().all() or r2019["capital_stock"].isna().all(): continue
        g = r2019["gdp_pc"].values[0] * r2019["population"].values[0] / 1e6
        k = r2019["capital_stock"].values[0]
        l = r2019["population"].values[0] / 1e6
        h = r2019["hc"].values[0]
        if pd.isna(h) or k==0 or l==0: continue
        s_2019 = g / (k**ALPHA * (l*h)**(1-ALPHA))
        if s_2019 > 0:
            scale_map[country] = tfp_2019 / s_2019

    country_scale = p.loc[mask, "country"].map(scale_map)
    valid = country_scale.notna()
    fill_idx = mask[mask].index[valid.values]
    p.loc[fill_idx, "tfp"] = solow_raw[valid].values * country_scale[valid].values
    p.loc[fill_idx, "tfp_solow_flag"] = 1
    print(f"  Solow TFP filled: {valid.sum()} rows, {p.loc[fill_idx,'country'].nunique()} countries")

p["tfp_solow_flag"] = p["tfp_solow_flag"].fillna(0)

# ── Step 7: Merge WDI extended if available ───────────────────────────────
if os.path.exists("data/raw/wdi_extended.csv"):
    print("Merging extended WDI indicators...")
    wdi_ext = pd.read_csv("data/raw/wdi_extended.csv")
    new_cols = [c for c in wdi_ext.columns if c not in p.columns]
    if new_cols:
        p = p.merge(wdi_ext[["country","year"]+new_cols], on=["country","year"], how="left")
        print(f"  Added {len(new_cols)} new columns: {new_cols}")

# ── Step 8: Structural dummies and log transforms ─────────────────────────
p["covid_dummy"]  = p["year"].isin([2020,2021]).astype(int)
p["post_chatgpt"] = (p["year"] >= 2023).astype(int)
p["post_2020"]    = (p["year"] >= 2020).astype(int)

p["ln_gdp"] = np.log(p["gdp_pc"].clip(lower=1e-6))
p["ln_ai"]  = np.where(p["ai_proxy_total"] > 0, np.log(p["ai_proxy_total"]), np.nan)
p["ln_tfp"] = np.where(p["tfp"] > 0, np.log(p["tfp"]), np.nan)
p["ln_hc"]  = np.where(p["hc"] > 0, np.log(p["hc"]), np.nan)

# Sub-indices
for cols, name in [
    (["internet_users","mobile_subs","secure_servers"], "digital_infra_index"),
    (["pat_res","pat_nres","ip_receipts"], "innovation_index"),
]:
    avail = [c for c in cols if c in p.columns]
    p[name] = p[avail].apply(lambda s: (s-s.mean())/s.std()).mean(axis=1, skipna=True)

# ── Step 9: Report ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("EXTENDED PANEL REPORT")
print("="*60)
complete = p.dropna(subset=["ln_ai","ln_tfp","ln_hc","ln_gdp"])
print(f"Shape: {p.shape}")
print(f"Countries: {p['country'].nunique()}")
print(f"Complete-case: {complete['country'].nunique()} countries, {len(complete)} obs")
print(f"\nObs by year (complete-case):")
print(complete.groupby("year").size().to_string())
print(f"\nTFP coverage by year (all countries):")
print(p.groupby("year")["tfp"].apply(lambda s: s.notna().sum()).to_string())

p.to_csv("data/processed/panel_clean.csv", index=False)
print(f"\nSaved: data/processed/panel_clean.csv")
