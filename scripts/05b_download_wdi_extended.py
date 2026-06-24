"""
05b_download_wdi_extended.py
-----------------------------
Downloads an enriched set of WDI indicators via the World Bank API (wbgapi).
Extends the original panel with:

NEW INDICATORS (for richer heterogeneity analysis):
  GB.XPD.RSDV.GD.ZS  — R&D expenditure (% of GDP)
  TX.VAL.TECH.MF.ZS   — High-technology exports (% of manufactured exports)
  IT.NET.BBND.P2       — Fixed broadband subscriptions (per 100 people)
  BX.GSR.CCIS.ZS      — ICT service exports (% of service exports)
  SP.POP.SCIE.RD.P6   — Researchers in R&D (per million people)
  IP.TMK.TOTL          — Trademark applications, total
  EG.USE.ELEC.KH.PC   — Electric power consumption (kWh per capita)  [AI infra proxy]
  NE.GDI.TOTL.ZS      — Gross capital formation (% of GDP)
  SE.XPD.TOTL.GD.ZS   — Government expenditure on education (% of GDP)
  FP.CPI.TOTL.ZG      — Inflation, consumer prices (annual %)
  BN.CAB.XOKA.GD.ZS   — Current account balance (% of GDP)

EXISTING INDICATORS (re-download to extend to 2024):
  NY.GDP.PCAP.KD      — GDP per capita (constant 2015 USD)
  SP.POP.TOTL         — Population, total
  IT.NET.USER.ZS      — Individuals using the Internet (% of population)
  IT.CEL.SETS.P2      — Mobile cellular subscriptions (per 100 people)
  IP.JRN.ARTC.SC      — Scientific and technical journal articles (proxy for R&D output)

Output: data/raw/wdi_extended.csv
"""

import wbgapi as wb
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── Indicator catalogue ────────────────────────────────────────────────────
INDICATORS = {
    # Core (re-fetch to 2024)
    "NY.GDP.PCAP.KD":    "gdp_pc",
    "SP.POP.TOTL":       "population",
    "IT.NET.USER.ZS":    "internet_users",
    "IT.CEL.SETS.P2":    "mobile_subs",

    # NEW: R&D and Innovation
    "GB.XPD.RSDV.GD.ZS": "rd_expenditure",
    "TX.VAL.TECH.MF.ZS":  "hitech_exports",
    "SP.POP.SCIE.RD.P6":  "researchers_pm",
    "IP.TMK.TOTL":         "trademark_apps",
    "IP.JRN.ARTC.SC":     "sci_articles",

    # NEW: Digital Infrastructure
    "IT.NET.BBND.P2":     "broadband_subs",
    "BX.GSR.CCIS.ZS":     "ict_service_exports",
    "EG.USE.ELEC.KH.PC":  "electricity_pc",

    # NEW: Macro controls
    "NE.GDI.TOTL.ZS":     "gross_cap_formation",
    "SE.XPD.TOTL.GD.ZS":  "edu_expenditure",
    "FP.CPI.TOTL.ZG":     "inflation",
    "BN.CAB.XOKA.GD.ZS":  "current_account",

    # NEW: Labour
    "SL.TLF.TOTL.IN":     "labor_force",
    "SL.UEM.TOTL.ZS":     "unemployment_rate",

    # NEW: Financial development
    "FS.AST.PRVT.GD.ZS":  "private_credit_gdp",
    "CM.MKT.LCAP.GD.ZS":  "stock_market_cap_gdp",

    # NEW: Trade openness
    "NE.TRD.GNFS.ZS":     "trade_openness",
}

YEARS = list(range(2010, 2025))

print(f"Downloading {len(INDICATORS)} WDI indicators, 2010–2024...")
print("This uses the World Bank API (wbgapi) — no API key required.\n")

# Fetch all indicators in one call
records = []
failed = []
for wb_code, col_name in INDICATORS.items():
    try:
        data = wb.data.DataFrame(
            wb_code,
            time=range(2010, 2025),
            labels=True,
        )
        # wbgapi returns DataFrame with economy as index, time as columns
        data = data.reset_index()
        # Melt to long format
        id_cols = [c for c in ["economy", "Economy"] if c in data.columns]
        if not id_cols:
            id_cols = [data.columns[0]]
        data = data.melt(id_vars=id_cols, var_name="year", value_name=col_name)
        data.rename(columns={id_cols[0]: "country"}, inplace=True)
        data["year"] = data["year"].astype(str).str.extract(r"(\d{4})").astype(int)
        data = data[data["year"].between(2010, 2024)]
        records.append(data[["country", "year", col_name]])
        n = data[col_name].notna().sum()
        countries = data[col_name].notna()["country"].nunique() if False else data.dropna(subset=[col_name])["country"].nunique()
        print(f"  ✓ {col_name:25s}: {n:5,} obs, {countries} countries")
    except Exception as e:
        failed.append((wb_code, col_name, str(e)))
        print(f"  ✗ {col_name:25s}: {e}")

if not records:
    print("\nNo data downloaded. API may be unavailable.")
    exit(1)

# Merge all into one wide DataFrame
from functools import reduce
wdi_ext = reduce(lambda l, r: pd.merge(l, r, on=["country","year"], how="outer"), records)
wdi_ext = wdi_ext.sort_values(["country","year"]).reset_index(drop=True)

print(f"\nMerged shape: {wdi_ext.shape}")
print(f"Countries: {wdi_ext['country'].nunique()}")
print(f"Years: {sorted(wdi_ext['year'].unique())}")
print(f"\nCoverage 2022–2024:")
for col in [c for c in wdi_ext.columns if c not in ["country","year"]]:
    recent = wdi_ext[wdi_ext["year"]>=2022][col].notna().sum()
    print(f"  {col:25s}: {recent}")

if failed:
    print(f"\nFailed indicators ({len(failed)}): {[f[1] for f in failed]}")

wdi_ext.to_csv("data/raw/wdi_extended.csv", index=False)
print(f"\nSaved: data/raw/wdi_extended.csv")
