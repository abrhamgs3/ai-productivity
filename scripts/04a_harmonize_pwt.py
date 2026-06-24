"""
04a_harmonize_pwt.py
--------------------
PWT uses different country names from the World Bank / WDI standard used
throughout this project. This script maps PWT names → WDI names and saves
a harmonized file so the merge in 04b works correctly.

16 countries are affected, including Korea, Czechia, Slovak Republic,
Turkiye, Egypt — all of which have AI proxy data and would expand the
estimation sample once TFP is correctly merged.

Input:  data/raw/pwt.csv              (PWT 10.x, 183 countries, 2010-2019)
Output: data/raw/pwt_harmonized.csv   (same data, WDI country names)
"""

import pandas as pd

# ------------------------------------------------------------------
# PWT name → WDI/World Bank name
# Source: cross-referencing both datasets manually
# ------------------------------------------------------------------
NAME_MAP = {
    "Bolivia (Plurinational State of)":  "Bolivia",
    "China, Hong Kong SAR":              "Hong Kong SAR, China",
    "China, Macao SAR":                  "Macao SAR, China",
    "Czech Republic":                    "Czechia",
    "Côte d'Ivoire":                     "Cote d'Ivoire",
    "Egypt":                             "Egypt, Arab Rep.",
    "Iran (Islamic Republic of)":        "Iran, Islamic Rep.",
    "Kyrgyzstan":                        "Kyrgyz Republic",
    "Lao People's DR":                   "Lao PDR",
    "Republic of Korea":                 "Korea, Rep.",
    "Republic of Moldova":               "Moldova",
    "Slovakia":                          "Slovak Republic",
    "Taiwan":                            "Taiwan, China",           # WDI label
    "Turkey":                            "Turkiye",
    "U.R. of Tanzania: Mainland":        "Tanzania",
    "Venezuela (Bolivarian Republic of)":"Venezuela, RB",
}

df = pd.read_csv("data/raw/pwt.csv")
before = df["country"].nunique()

df["country"] = df["country"].replace(NAME_MAP)
after = df["country"].nunique()

mapped = {k: v for k, v in NAME_MAP.items() if k in df["country"].values or v in df["country"].values}

df.to_csv("data/raw/pwt_harmonized.csv", index=False)

print(f"PWT harmonized: {before} → {after} unique country names (same, renamed)")
print(f"Mappings applied: {len(NAME_MAP)}")
print()
for old, new in NAME_MAP.items():
    in_df = old in pd.read_csv('data/raw/pwt.csv')['country'].values
    print(f"  {'✔' if in_df else '–'} '{old}' → '{new}'")

print()
print(f"Saved to data/raw/pwt_harmonized.csv")
