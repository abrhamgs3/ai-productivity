"""
04d_merge_all_tfp.py
---------------------
Final TFP integration:
  1. PWT harmonized (already merged in 04b)
  2. Solow-residual TFP (computed from WDI in 04c) for remaining 22 countries
  
The Solow TFP uses: TFP = GDP / (K^0.33 * (L*H)^0.67)
Normalized to 2010=1.0 within each country.

NOTE: Solow-residual TFP is tagged with source='solow' for robustness checks.
      A dummy variable `tfp_solow_flag` is added for sensitivity testing.

Input:  data/processed/panel_clean.csv
        data/raw/tfp_solow_computed.csv
Output: data/processed/panel_clean.csv  (final)
        data/processed/tfp_sources.csv  (country-level TFP source registry)
"""

import numpy as np
import pandas as pd

# ── Load ──────────────────────────────────────────────────────────────────
panel = pd.read_csv("data/processed/panel_clean.csv")
solow = pd.read_csv("data/raw/tfp_solow_computed.csv")

print("Before merge:")
complete_before = panel.dropna(subset=["ln_ai","ln_tfp","ln_hc","ln_gdp"])
print(f"  Complete-case: {complete_before['country'].nunique()} countries, {len(complete_before)} obs")

# Rename so we can track source
solow = solow.rename(columns={"tfp_solow": "tfp_new"})

# Add tfp_solow_flag column if not present
if "tfp_solow_flag" not in panel.columns:
    panel["tfp_solow_flag"] = 0

# Left-join Solow into panel
panel = panel.merge(solow, on=["country","year"], how="left")

# Fill only where tfp is still NaN
solow_filled_mask = panel["tfp"].isna() & panel["tfp_new"].notna()
panel.loc[solow_filled_mask, "tfp"] = panel.loc[solow_filled_mask, "tfp_new"]
panel.loc[solow_filled_mask, "tfp_solow_flag"] = 1  # flag for sensitivity check

solow_countries_filled = panel.loc[solow_filled_mask, "country"].unique()
n_filled = solow_filled_mask.sum()
print(f"\nSolow-residual fill:")
print(f"  Filled {n_filled} rows across {len(solow_countries_filled)} countries:")
for c in sorted(solow_countries_filled):
    n = solow_filled_mask[panel["country"] == c].sum()
    print(f"    {c}: {n} obs")

panel.drop(columns=["tfp_new"], inplace=True)

# Recompute ln_tfp
panel["ln_tfp"] = np.log(panel["tfp"])

# ── Final sample report ───────────────────────────────────────────────────
print("\n" + "="*60)
print("FINAL SAMPLE REPORT")
print("="*60)

complete = panel.dropna(subset=["ln_ai","ln_tfp","ln_hc","ln_gdp"])
print(f"Complete-case (ln_ai + ln_tfp + ln_hc + ln_gdp):")
print(f"  Countries: {complete['country'].nunique()}")
print(f"  Obs:       {len(complete)}")
print(f"  Years:     {complete['year'].min():.0f}–{complete['year'].max():.0f}")

# Breakdown by TFP source
from_pwt   = complete[complete["tfp_solow_flag"] == 0]["country"].nunique()
from_solow = complete[complete["tfp_solow_flag"] == 1]["country"].nunique()
print(f"\n  TFP from PWT (standard):         {from_pwt} countries")
print(f"  TFP from Solow residual (WDI):   {from_solow} countries")

# By income group (approximate)
print(f"\n  Top-10 countries by obs count:")
top = complete.groupby("country").size().sort_values(ascending=False).head(10)
for c, n in top.items():
    print(f"    {c}: {n}")

# ── TFP sources registry ──────────────────────────────────────────────────
sources = []
for country in panel["country"].unique():
    cdf = panel[panel["country"] == country]
    tfp_rows = cdf["tfp"].notna().sum()
    solow_rows = cdf["tfp_solow_flag"].sum()
    if tfp_rows == 0:
        source = "none"
    elif solow_rows > 0 and solow_rows == tfp_rows:
        source = "solow"
    elif solow_rows > 0:
        source = "pwt+solow"
    else:
        source = "pwt"
    sources.append({"country": country, "tfp_source": source, "tfp_obs": int(tfp_rows)})

sources_df = pd.DataFrame(sources).sort_values(["tfp_source","country"])
sources_df.to_csv("data/processed/tfp_sources.csv", index=False)
print(f"\nTFP source breakdown:")
print(sources_df["tfp_source"].value_counts().to_string())

# ── Save ──────────────────────────────────────────────────────────────────
panel.to_csv("data/processed/panel_clean.csv", index=False)
print(f"\nSaved: data/processed/panel_clean.csv")
print(f"Saved: data/processed/tfp_sources.csv")
