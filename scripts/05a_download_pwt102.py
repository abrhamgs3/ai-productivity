"""
05a_download_pwt102.py
----------------------
Downloads Penn World Tables 10.02 (covers 1950–2022 for ~183 countries).
PWT 10.02 adds three years (2020, 2021, 2022) vs. PWT 10.01.

Key variables extracted:
  rtfpna   — TFP at national prices (index, 2017=1)
  hc       — Human capital index (Barro-Lee / PWT methodology)
  rnna     — Capital stock at national prices (mil. 2017 USD)
  pop      — Population (millions)
  rgdpna   — Real GDP at national prices (mil. 2017 USD)

Country names are harmonized to WDI standard using the same
mapping from 04a_harmonize_pwt.py.

Output: data/raw/pwt102.csv
        data/raw/pwt102_harmonized.csv
"""

import io
import urllib.request
import pandas as pd
import numpy as np

# ── PWT 10.02 download URLs (Groningen dataverse) ─────────────────────────
# Try multiple mirrors
URLS = [
    # Primary Groningen dataverse
    "https://dataverse.nl/api/access/datafile/526474",
    # Alternative: direct from GGDC website
    "https://www.rug.nl/ggdc/docs/pwt1002.xlsx",
    # Another mirror
    "https://data.worldbank.org/data-catalog/pdh?dataset=pwt",
]

NAME_MAP = {
    "Bolivia (Plurinational State of)":   "Bolivia",
    "China, Hong Kong SAR":               "Hong Kong SAR, China",
    "China, Macao SAR":                   "Macao SAR, China",
    "Czech Republic":                     "Czechia",
    "Côte d'Ivoire":                      "Cote d'Ivoire",
    "Egypt":                              "Egypt, Arab Rep.",
    "Iran (Islamic Republic of)":         "Iran, Islamic Rep.",
    "Kyrgyzstan":                         "Kyrgyz Republic",
    "Lao People's DR":                    "Lao PDR",
    "Republic of Korea":                  "Korea, Rep.",
    "Republic of Moldova":                "Moldova",
    "Slovakia":                           "Slovak Republic",
    "Taiwan":                             "Taiwan, China",
    "Turkey":                             "Turkiye",
    "U.R. of Tanzania: Mainland":         "Tanzania",
    "Venezuela (Bolivarian Republic of)": "Venezuela, RB",
    "Viet Nam":                           "Vietnam",
    "Congo, Democratic Republic of the":  "Congo, Dem. Rep.",
    "Congo, Republic of":                 "Congo, Rep.",
    "Korea, Republic of":                 "Korea, Rep.",
    "North Macedonia":                    "North Macedonia",
}

print("Attempting PWT 10.02 download...")

pwt = None
for url in URLS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
        print(f"  Downloaded {len(content):,} bytes from {url[:60]}")

        if url.endswith(".xlsx") or b"PK" in content[:4]:
            pwt = pd.read_excel(io.BytesIO(content), sheet_name="Data")
        else:
            pwt = pd.read_csv(io.BytesIO(content))
        print(f"  Shape: {pwt.shape}, columns: {list(pwt.columns[:8])}")
        break
    except Exception as e:
        print(f"  Failed {url[:50]}: {e}")

if pwt is None:
    print("\nAll direct downloads failed (likely network restriction).")
    print("Please download PWT 10.02 manually:")
    print("  1. Go to: https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/penn-world-table-10-02")
    print("  2. Download the CSV or Excel file")
    print("  3. Save as: data/raw/pwt1002.csv or data/raw/pwt1002.xlsx")
    print("  4. Re-run this script")

    # Check if already downloaded manually
    import os
    for fname in ["data/raw/pwt1002.csv", "data/raw/pwt1002.xlsx", "data/raw/pwt102.csv"]:
        if os.path.exists(fname):
            print(f"\nFound local file: {fname}")
            if fname.endswith(".xlsx"):
                pwt = pd.read_excel(fname, sheet_name="Data")
            else:
                pwt = pd.read_csv(fname)
            print(f"  Loaded: {pwt.shape}")
            break

if pwt is None:
    print("\nNo PWT 10.02 data available. Exiting.")
    exit(0)

# ── Extract key variables ─────────────────────────────────────────────────
KEEP_COLS = ["country", "year", "rtfpna", "hc", "rnna", "pop", "rgdpna"]
available = [c for c in KEEP_COLS if c in pwt.columns]
print(f"Available PWT columns: {available}")

pwt_sub = pwt[available].copy()
pwt_sub = pwt_sub[pwt_sub["year"].between(2010, 2024)]

# Rename to match panel conventions
rename = {
    "rtfpna": "tfp",
    "rnna":   "capital_stock",
    "pop":    "pwt_pop",
    "rgdpna": "pwt_gdp",
}
pwt_sub.rename(columns={k: v for k, v in rename.items() if k in pwt_sub.columns}, inplace=True)

# Apply name harmonization
pwt_sub["country"] = pwt_sub["country"].replace(NAME_MAP)

print(f"\nPWT 10.02 extracted: {pwt_sub.shape}")
print(f"Years: {sorted(pwt_sub['year'].unique())}")
print(f"Countries: {pwt_sub['country'].nunique()}")

# Check 2020-2022 TFP coverage
tfp_cov = pwt_sub.groupby("year")["tfp"].apply(lambda s: s.notna().sum())
print(f"\nTFP coverage by year:")
print(tfp_cov[tfp_cov.index >= 2018])

pwt_sub.to_csv("data/raw/pwt102_harmonized.csv", index=False)
print("\nSaved: data/raw/pwt102_harmonized.csv")
