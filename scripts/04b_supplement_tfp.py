"""
04b_supplement_tfp.py
---------------------
Fills missing TFP (and hc, capital_stock) values in panel_clean.csv
using the harmonized PWT file produced by 04a_harmonize_pwt.py.

Priority: existing PWT values in the panel are kept as-is.
          Only NaN cells are filled from pwt_harmonized.csv.

This recovers countries previously lost to name mismatches:
Korea, Rep. | Czechia | Slovak Republic | Turkiye | Egypt, Arab Rep.
Moldova | Iran, Islamic Rep. | Kyrgyz Republic | Lao PDR |
Hong Kong SAR, China | Bolivia | Tanzania | Venezuela, RB | and more.

Input:  data/processed/panel_clean.csv
        data/raw/pwt_harmonized.csv
Output: data/processed/panel_clean.csv  (updated in-place)
        data/processed/tfp_supplement_report.txt
"""

import numpy as np
import pandas as pd

# ── Load ──────────────────────────────────────────────────────────────────
panel = pd.read_csv("data/processed/panel_clean.csv")
pwt   = pd.read_csv("data/raw/pwt_harmonized.csv")

# PWT cols we want to fill
PWT_COLS = ["tfp", "hc", "capital_stock"]

# Track before
before_tfp = panel["tfp"].notna().sum()
before_countries = panel.dropna(subset=["tfp"])["country"].nunique()

# ── Merge ─────────────────────────────────────────────────────────────────
pwt_sub = pwt[["country", "year"] + PWT_COLS].copy()
pwt_sub.columns = ["country", "year"] + [f"{c}_pwt" for c in PWT_COLS]

panel = panel.merge(pwt_sub, on=["country", "year"], how="left")

# Fill NaN cells only
for col in PWT_COLS:
    filled_mask = panel[col].isna() & panel[f"{col}_pwt"].notna()
    panel.loc[filled_mask, col] = panel.loc[filled_mask, f"{col}_pwt"]
    n = filled_mask.sum()
    if n:
        countries = panel.loc[filled_mask, "country"].unique()
        print(f"  {col}: filled {n} rows across {len(countries)} countries")
        print(f"    {sorted(countries)}")

panel.drop(columns=[f"{c}_pwt" for c in PWT_COLS], inplace=True)

# ── Recompute log transforms ───────────────────────────────────────────────
panel["ln_tfp"] = np.log(panel["tfp"])
panel["ln_hc"]  = np.log(panel["hc"])

# ── Report ────────────────────────────────────────────────────────────────
after_tfp       = panel["tfp"].notna().sum()
after_countries = panel.dropna(subset=["tfp"])["country"].nunique()

complete_before = panel.dropna(subset=["ln_ai","ln_tfp","ln_hc","ln_gdp"])
# we need the old complete count — approximate from earlier result
print()
print("=" * 60)
print("TFP supplement summary")
print("=" * 60)
print(f"TFP rows:      {before_tfp:,} → {after_tfp:,}  (+{after_tfp - before_tfp})")
print(f"TFP countries: {before_countries} → {after_countries}  (+{after_countries - before_countries})")
print()
complete = panel.dropna(subset=["ln_ai","ln_tfp","ln_hc","ln_gdp"])
print(f"Complete-case sample: {complete['country'].nunique()} countries, {len(complete)} obs")
print()

# Which countries newly have complete data?
old_complete_countries = {
    'Argentina','Armenia','Australia','Austria','Bahrain','Barbados','Belgium',
    'Brazil','Bulgaria','Canada','Chile','China','Costa Rica','Croatia','Cyprus',
    'Denmark','Dominican Republic','Estonia','Finland','France','Germany','Greece',
    'Hungary','Iceland','Ireland','Israel','Italy','Jamaica','Japan','Jordan',
    'Kazakhstan','Kuwait','Latvia','Lithuania','Luxembourg','Malaysia','Malta',
    'Mexico','Morocco','Netherlands','New Zealand','Norway','Paraguay','Poland',
    'Portugal','Qatar','Romania','Russian Federation','Saudi Arabia','Serbia',
    'Singapore','Slovenia','South Africa','Spain','Sweden','Switzerland',
    'Trinidad and Tobago','Ukraine','United Kingdom','United States','Uruguay',
    'Angola','Botswana','Burundi','Colombia','Ecuador','Guatemala','Honduras',
    'India','Indonesia','Iraq','Kenya','Mauritius','Mongolia','Mozambique',
    'Namibia','Nicaragua','Nigeria','Panama','Peru','Philippines','Rwanda',
    'Sri Lanka','Sudan','Tajikistan','Thailand','Tunisia','Zambia','Zimbabwe',
}
new_countries = set(complete["country"].unique()) - old_complete_countries
print(f"Newly recovered countries ({len(new_countries)}):")
for c in sorted(new_countries):
    n_obs = len(complete[complete["country"] == c])
    yrs   = complete[complete["country"] == c]["year"].agg(["min","max"])
    print(f"  {c}: {n_obs} obs ({yrs['min']:.0f}–{yrs['max']:.0f})")

# ── Save ──────────────────────────────────────────────────────────────────
panel.to_csv("data/processed/panel_clean.csv", index=False)
print()
print("Saved: data/processed/panel_clean.csv")
