"""
05b_download_all_extended.py
-----------------------------
RUN THIS ON YOUR WINDOWS MACHINE (has full internet access).

Downloads all data needed to extend the panel to 2010–2024:

  1. WDI extended indicators (21 series via World Bank API)
  2. PWT 10.02 CSV (TFP/hc/capital_stock through 2022)
  3. WIPO patent data (2010–2023, more granular than WDI)
  4. WGI updated governance data (through 2023)

Usage:
  cd "C:\\Users\\Lenovo\\Desktop\\Courses\\EconWithAi\\AI and Productivity"
  pip install wbgapi --break-system-packages   (or: uv pip install wbgapi)
  python scripts/05b_download_all_extended.py

Outputs (all saved to data/raw/):
  wdi_extended.csv        — 21 WDI indicators, 193 countries, 2010–2024
  pwt102_harmonized.csv   — PWT 10.02 TFP/hc/capital_stock, 2010–2022
  wipo_patents.csv        — Patent applications by country, 2010–2023
"""

import io, os, json, time
import urllib.request
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

os.makedirs("data/raw", exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# 1. WDI EXTENDED  (via wbgapi)
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("1. WDI Extended Indicators")
print("=" * 60)

try:
    import wbgapi as wb

    INDICATORS = {
        # Core (extend to 2024)
        "NY.GDP.PCAP.KD":     "gdp_pc",
        "SP.POP.TOTL":        "population",
        "IT.NET.USER.ZS":     "internet_users",
        "IT.CEL.SETS.P2":     "mobile_subs",
        # NEW: R&D and Innovation
        "GB.XPD.RSDV.GD.ZS":  "rd_expenditure",
        "TX.VAL.TECH.MF.ZS":   "hitech_exports",
        "SP.POP.SCIE.RD.P6":   "researchers_pm",
        "IP.TMK.TOTL":          "trademark_apps",
        "IP.JRN.ARTC.SC":      "sci_articles",
        # NEW: Digital Infrastructure
        "IT.NET.BBND.P2":      "broadband_subs",
        "BX.GSR.CCIS.ZS":      "ict_service_exports",
        "EG.USE.ELEC.KH.PC":   "electricity_pc",
        # NEW: Macro Controls
        "NE.GDI.TOTL.ZS":      "gross_cap_formation",
        "SE.XPD.TOTL.GD.ZS":   "edu_expenditure",
        "FP.CPI.TOTL.ZG":      "inflation",
        "BN.CAB.XOKA.GD.ZS":   "current_account",
        "NE.TRD.GNFS.ZS":      "trade_openness",
        # NEW: Labour & Finance
        "SL.TLF.TOTL.IN":      "labor_force",
        "SL.UEM.TOTL.ZS":      "unemployment_rate",
        "FS.AST.PRVT.GD.ZS":   "private_credit_gdp",
        "CM.MKT.LCAP.GD.ZS":   "stock_market_cap_gdp",
    }

    records = []
    for wb_code, col_name in INDICATORS.items():
        try:
            data = wb.data.DataFrame(wb_code, time=range(2010, 2025), labels=True)
            data = data.reset_index()
            id_col = [c for c in ["economy", "Economy", "Country"] if c in data.columns][0]
            data = data.melt(id_vars=[id_col], var_name="year", value_name=col_name)
            data.rename(columns={id_col: "country"}, inplace=True)
            data["year"] = data["year"].astype(str).str.extract(r"(\d{4})")[0].astype(int)
            records.append(data[["country", "year", col_name]])
            n = data[col_name].notna().sum()
            print(f"  ✓ {col_name:25s}: {n:,} obs")
            time.sleep(0.3)
        except Exception as e:
            print(f"  ✗ {col_name}: {e}")

    if records:
        from functools import reduce
        wdi_ext = reduce(lambda a, b: pd.merge(a, b, on=["country","year"], how="outer"), records)
        wdi_ext.sort_values(["country","year"], inplace=True)
        wdi_ext.to_csv("data/raw/wdi_extended.csv", index=False)
        print(f"\n  Saved: data/raw/wdi_extended.csv  ({wdi_ext.shape})")
    else:
        print("  No WDI data downloaded.")

except ImportError:
    print("  wbgapi not installed. Run: pip install wbgapi")

# ═══════════════════════════════════════════════════════════════════════════
# 2. PWT 10.02
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("2. Penn World Tables 10.02")
print("=" * 60)

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
}

PWT_URLS = [
    "https://dataverse.nl/api/access/datafile/526474",
    "https://www.rug.nl/ggdc/docs/pwt1002.csv",
]

pwt = None
for url in PWT_URLS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
        if url.endswith(".xlsx"):
            pwt = pd.read_excel(io.BytesIO(content), sheet_name="Data")
        else:
            pwt = pd.read_csv(io.BytesIO(content))
        print(f"  Downloaded from {url[:55]}: {pwt.shape}")
        break
    except Exception as e:
        print(f"  Failed {url[:55]}: {e}")

if pwt is None:
    # Check for manually downloaded file
    for fname in ["data/raw/pwt1002.csv", "data/raw/pwt1002.xlsx"]:
        if os.path.exists(fname):
            pwt = pd.read_excel(fname, sheet_name="Data") if fname.endswith(".xlsx") else pd.read_csv(fname)
            print(f"  Loaded local file: {fname}")
            break

if pwt is not None:
    keep = [c for c in ["country","year","rtfpna","hc","rnna","pop","rgdpna"] if c in pwt.columns]
    pwt_sub = pwt[keep].copy()
    pwt_sub = pwt_sub[pwt_sub["year"].between(2010, 2024)]
    pwt_sub.rename(columns={"rtfpna":"tfp","rnna":"capital_stock","pop":"pwt_pop","rgdpna":"pwt_gdp"}, inplace=True)
    pwt_sub["country"] = pwt_sub["country"].replace(NAME_MAP)
    pwt_sub.to_csv("data/raw/pwt102_harmonized.csv", index=False)
    tfp_cov = pwt_sub.groupby("year")["tfp"].apply(lambda s: s.notna().sum())
    print(f"  TFP coverage 2019–2022: {dict(tfp_cov[tfp_cov.index >= 2019])}")
    print(f"  Saved: data/raw/pwt102_harmonized.csv")
else:
    print("\n  PWT 10.02 not downloaded. MANUAL STEP:")
    print("  1. Open: https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/penn-world-table-10-02")
    print("  2. Download pwt1002.csv")
    print("  3. Save to: data/raw/pwt1002.csv")
    print("  4. Re-run this script")

# ═══════════════════════════════════════════════════════════════════════════
# 3. WIPO Patent Statistics (via bulk download)
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("3. WIPO Patent Data (2010–2023)")
print("=" * 60)

WIPO_URL = "https://www.wipo.int/ipstats/en/statistics/patents/"
# WIPO provides bulk CSV downloads via their API
wipo_api = "https://www3.wipo.int/ipstats/api/5.0/countries/all/patents/total/applications?format=csv&from=2010&to=2023"

try:
    req = urllib.request.Request(wipo_api, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read()
    wipo = pd.read_csv(io.BytesIO(content))
    print(f"  Downloaded WIPO data: {wipo.shape}")
    wipo.to_csv("data/raw/wipo_patents.csv", index=False)
    print(f"  Saved: data/raw/wipo_patents.csv")
except Exception as e:
    print(f"  WIPO download failed: {e}")
    print("  Manual: https://www3.wipo.int/ipstats/ → Patent → Resident + Non-resident")

print("\n" + "=" * 60)
print("DONE. Check data/raw/ for downloaded files.")
print("=" * 60)
