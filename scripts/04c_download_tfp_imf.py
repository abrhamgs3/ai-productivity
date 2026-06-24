"""
04c_download_tfp_imf.py
-----------------------
Downloads TFP-related data from IMF and Conference Board via accessible APIs.

Strategy:
  1. IMF WEO: NGDP_R (real GDP), Employment, Capital → compute Solow residual TFP
     OR: use WEO's pre-computed TFP growth where available
  2. Feenstra-Inklaar-Timmer via direct CSV download (PWT 10.01 full dataset)

The IMF SDMX API is publicly accessible without a key.

Output: data/raw/imf_tfp.csv
"""

import json
import urllib.request
import urllib.error
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

panel = pd.read_csv("data/processed/panel_clean.csv")

# Count truly missing countries (all years missing TFP)
tfp_by_country = panel.groupby("country")["tfp"].apply(lambda s: s.notna().sum())
fully_missing = tfp_by_country[tfp_by_country == 0].index.tolist()
partial_missing = tfp_by_country[(tfp_by_country > 0) & (tfp_by_country < 10)].index.tolist()
print(f"Countries with NO TFP data at all: {len(fully_missing)}")
print(f"Countries with PARTIAL TFP data:   {len(partial_missing)}")
print()

# ── Approach 1: Try downloading PWT 10.01 directly ─────────────────────────
# PWT 10.01 is hosted at Groningen Growth and Development Centre
# Direct CSV download
PWT_URL = "https://dataverse.nl/api/access/datafile/354098"  # PWT 10.01 CSV

print("Attempting PWT 10.01 direct download from Groningen dataverse...")
try:
    req = urllib.request.Request(
        PWT_URL,
        headers={"User-Agent": "Mozilla/5.0 (research download)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read()
    print(f"  Downloaded {len(content):,} bytes")
    
    import io
    pwt_full = pd.read_csv(io.BytesIO(content))
    print(f"  PWT 10.01: {pwt_full.shape}, columns: {list(pwt_full.columns[:10])}")
    pwt_full.to_csv("data/raw/pwt1001_full.csv", index=False)
    print("  Saved: data/raw/pwt1001_full.csv")
except Exception as e:
    print(f"  Failed: {e}")

# ── Approach 2: IMF WEO via SDMX ───────────────────────────────────────────
print("\nAttempting IMF WEO API...")

# IMF DataMapper API (simpler, no auth)
# TFP proxy: use NGDP_R (real GDP) + employment + capital from WEO
# Or use existing WEO TFP indicator if available

# Try IMF DataMapper for a single indicator first
imf_url = "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH"
try:
    req = urllib.request.Request(imf_url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        imf_data = json.loads(resp.read())
    
    # Parse IMF DataMapper format
    # structure: {"values": {"NGDP_RPCH": {"AFG": {"2010": val, ...}, ...}}}
    gdp_growth = imf_data.get("values", {}).get("NGDP_RPCH", {})
    print(f"  IMF NGDP_RPCH: {len(gdp_growth)} countries")
    
    records = []
    for iso3, yr_dict in gdp_growth.items():
        for yr_str, val in yr_dict.items():
            yr = int(yr_str)
            if 2010 <= yr <= 2024 and val is not None:
                records.append({"iso3": iso3, "year": yr, "gdp_growth_imf": float(val)})
    
    imf_gdp = pd.DataFrame(records)
    print(f"  Parsed {len(imf_gdp)} observations, {imf_gdp['iso3'].nunique()} countries")
    imf_gdp.to_csv("data/raw/imf_gdpgrowth.csv", index=False)
    print("  Saved: data/raw/imf_gdpgrowth.csv (GDP growth — TFP proxy via Solow)")
    
except Exception as e:
    print(f"  IMF API failed: {e}")

# ── Approach 3: World Bank TFP via MRW Solow residual approach ─────────────
print("\nComputing TFP via Solow residual from already-downloaded WDI data...")
# We have: GDP per capita (gdp_pc), population, human capital (hc), capital_stock
# TFP = Y / (K^alpha * L^(1-alpha) * H)
# alpha = 0.33 (capital share, standard)
# We already have: gdp_pc, population, hc, capital_stock

# Reconstruct for countries with gdp_pc, capital_stock, hc but missing tfp
has_needed = panel[["country","year","gdp_pc","population","hc","capital_stock","tfp"]].copy()
can_compute = has_needed.dropna(subset=["gdp_pc","population","capital_stock","hc"])
still_missing_tfp = can_compute[can_compute["tfp"].isna()]

print(f"  Rows that have GDP, K, H, L but missing TFP: {len(still_missing_tfp)}")
print(f"  Countries: {still_missing_tfp['country'].nunique()}")

if len(still_missing_tfp) > 0:
    ALPHA = 0.33
    # GDP total = gdp_pc * population (thousands → actual)
    still_missing_tfp = still_missing_tfp.copy()
    still_missing_tfp["gdp_total"] = still_missing_tfp["gdp_pc"] * still_missing_tfp["population"]
    # Solow: TFP = GDP / (K^alpha * (L*H)^(1-alpha))
    # Normalize to avoid scale issues: compute index
    still_missing_tfp["tfp_solow"] = (
        still_missing_tfp["gdp_total"] /
        (still_missing_tfp["capital_stock"] ** ALPHA *
         (still_missing_tfp["population"] * still_missing_tfp["hc"]) ** (1 - ALPHA))
    )
    
    print(f"  Computed Solow TFP for {still_missing_tfp['tfp_solow'].notna().sum()} rows")
    
    # Normalize within country to 2010=1 (same as PWT convention)
    def normalize_to_2010(grp):
        base = grp.loc[grp["year"]==2010, "tfp_solow"]
        if len(base) == 0 or base.isna().all():
            base2 = grp["tfp_solow"].dropna()
            if len(base2) == 0:
                return grp
            base_val = base2.iloc[0]
        else:
            base_val = base.iloc[0]
        if base_val != 0 and not np.isnan(base_val):
            grp = grp.copy()
            grp["tfp_solow"] = grp["tfp_solow"] / base_val
        return grp
    
    still_missing_tfp = still_missing_tfp.groupby("country", group_keys=False).apply(normalize_to_2010)
    solow_out = still_missing_tfp[["country","year","tfp_solow"]].dropna()
    solow_out.to_csv("data/raw/tfp_solow_computed.csv", index=False)
    print(f"  Saved: data/raw/tfp_solow_computed.csv ({solow_out['country'].nunique()} countries, {len(solow_out)} obs)")
    print(f"  Countries: {sorted(solow_out['country'].unique())}")

print("\nDone.")
